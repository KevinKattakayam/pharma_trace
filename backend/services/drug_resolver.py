"""
Enterprise Multi-Tier Drug Resolver.
Resolves raw, misspelled, or brand drug names to their exact canonical generic equivalents using a cascade of exact and fuzzy matchers.
"""
import asyncio
from typing import Optional

import httpx
import structlog
from rapidfuzz import fuzz
from rapidfuzz import process as rfuzz_process

from services.cache_manager import get_cache
from services.circuit_breaker import circuit_breaker

logger = structlog.get_logger()

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"


async def resolve_drug_name(raw_name: str) -> dict:
    """
    Tier 0: Vernacular resolver (DB trigram + AI cascade)
    Tier 1: Exact RxNorm API lookup (CUI)
    Tier 2: Approximate RxNorm spelling suggestions
    Tier 3: Local CDSCO SQLite fuzzy match
    Tier 4: DrugBank CE fuzzy match
    Returns: { brand_name, generic_name, rxcui, source, confidence, resolution_source }
    """
    if not raw_name or not raw_name.strip():
        return {"raw_name": raw_name, "source": "unresolved", "confidence": 0.0}

    cache = get_cache()
    cache_key = f"drug_resolve:{raw_name.lower().strip()}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    res = await _resolve_drug_name_uncached(raw_name)
    await cache.set(cache_key, res, ttl_seconds=86400)  # 24-hour TTL
    return res


async def _resolve_drug_name_uncached(raw_name: str) -> dict:
    from services.vernacular_resolver import resolve_drug_query

    # Tier 0: Resolve vernacular/phonetic/non-Latin aliases via 5-layer cascade
    resolved = await resolve_drug_query(raw_name)
    name_clean = resolved["canonical_name"].strip().title()
    vernacular_meta = {
        "resolution_source": resolved["source"],
        "resolution_confidence": resolved["confidence"]
    }

    # Tier 1 — RxNorm exact
    result = await _rxnorm_exact(name_clean)
    if result:
        return {**result, **vernacular_meta, "source": "rxnorm_exact", "confidence": 0.98}

    # Tier 2 — RxNorm spelling suggest
    result = await _rxnorm_suggest(name_clean)
    if result:
        return {**result, **vernacular_meta, "source": "rxnorm_suggest", "confidence": 0.85}

    # Tier 3 — CDSCO SQLite fuzzy
    result = await _cdsco_fuzzy(name_clean)
    if result:
        res = {**result, **vernacular_meta, "source": "cdsco_fuzzy", "confidence": result["score"] / 100}
        return await _enrich_with_rxcui(res)

    # Tier 4 — DrugBank CE
    result = await _drugbank_fuzzy(name_clean)
    if result:
        res = {**result, **vernacular_meta, "source": "drugbank_fuzzy", "confidence": result["score"] / 100}
        return await _enrich_with_rxcui(res)

    # If the vernacular resolver itself resolved with high confidence, use that
    if resolved["confidence"] >= 0.75 and resolved["source"] != "unresolved":
        res = {
            "brand_name": raw_name,
            "generic_name": resolved["canonical_name"],
            "active_ingredients": resolved.get("active_ingredients", []),
            **vernacular_meta,
            "source": resolved["source"],
            "confidence": resolved["confidence"]
        }
        return await _enrich_with_rxcui(res)

    return {"raw_name": raw_name, **vernacular_meta, "source": "unresolved", "confidence": 0.0}


async def _enrich_with_rxcui(res: dict) -> dict:
    """If a resolved drug doesn't have an rxcui, look it up by its generic name or active ingredients in RxNorm."""
    if res.get("rxcui"):
        return res
    
    target_name = res.get("generic_name") or res.get("brand_name")
    if not target_name:
        return res
        
    # Check exact match on generic name
    cui_res = await _rxnorm_exact(target_name) or await _rxnorm_suggest(target_name)
    if cui_res and cui_res.get("rxcui"):
        res["rxcui"] = cui_res["rxcui"]
        return res
        
    # If combination drug (e.g. "Amoxicillin + Clavulanic Acid"), try first ingredient
    if "+" in target_name:
        first_ing = target_name.split("+")[0].strip()
        cui_res = await _rxnorm_exact(first_ing) or await _rxnorm_suggest(first_ing)
        if cui_res and cui_res.get("rxcui"):
            res["rxcui"] = cui_res["rxcui"]
            
    return res


@circuit_breaker(name="rxnorm", failure_threshold=3, recovery_timeout=30.0)
async def _rxnorm_exact(name: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(
                f"{RXNAV_BASE}/drugs.json",
                params={"name": name}
            )
            if r.status_code != 200:
                return None
            data = r.json()
            groups = data.get("drugGroup", {}).get("conceptGroup", [])
            for group in groups:
                concepts = group.get("conceptProperties", [])
                if concepts:
                    c = concepts[0]
                    return {
                        "rxcui": c["rxcui"],
                        "brand_name": name,
                        "generic_name": c["name"],
                        "tty": c["tty"]
                    }
        except Exception as e:
            logger.debug("rxnorm_exact_lookup_failed", name=name, error=str(e))
    return None


@circuit_breaker(name="rxnorm", failure_threshold=3, recovery_timeout=30.0)
async def _rxnorm_suggest(name: str) -> Optional[dict]:
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(
                f"{RXNAV_BASE}/spellingsuggestions.json",
                params={"name": name}
            )
            if r.status_code != 200:
                return None
            suggestions = r.json().get("suggestionGroup", {}).get("suggestionList", {}).get("suggestion", [])
            if suggestions:
                # Recurse with top suggestion
                return await _rxnorm_exact(suggestions[0])
        except Exception as e:
            logger.debug("rxnorm_suggest_lookup_failed", name=name, error=str(e))
    return None


def _sync_cdsco_fuzzy(name: str) -> Optional[dict]:
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "cdsco_registry.db"
    if not db_path.exists():
        return None
        
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT generic_name, generic_name FROM indian_drugs")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        brand_names = [r[0] for r in rows if r[0]]
        if not brand_names:
            return None
            
        match_tuple = rfuzz_process.extractOne(
            name, brand_names, scorer=fuzz.token_sort_ratio
        )
        if match_tuple:
            match, score, idx = match_tuple
            if score >= 80:
                return {
                    "brand_name": name.title(),
                    "generic_name": rows[idx][1],
                    "score": score
                }
    except Exception as e:
        logger.warning("cdsco_fuzzy_sqlite_error", name=name, error=str(e))
    return None


async def _cdsco_fuzzy(name: str) -> Optional[dict]:
    """Offload synchronous SQLite file read and fuzzy matching to background thread."""
    return await asyncio.to_thread(_sync_cdsco_fuzzy, name)


def _sync_drugbank_fuzzy(name: str) -> Optional[dict]:
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "drugbank_ce.db"
    if not db_path.exists() or db_path.stat().st_size == 0:
        return None
        
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM drugs")
        rows = cur.fetchall()
        conn.close()

        if not rows:
            return None

        drug_names = [r[0] for r in rows if r[0]]
        if not drug_names:
            return None
            
        match_tuple = rfuzz_process.extractOne(
            name, drug_names, scorer=fuzz.token_sort_ratio
        )
        if match_tuple:
            match, score, idx = match_tuple
            if score >= 80:
                return {
                    "brand_name": name.title(),
                    "generic_name": rows[idx][0],
                    "score": score
                }
    except Exception as e:
        logger.warning("drugbank_fuzzy_sqlite_error", name=name, error=str(e))
    return None


async def _drugbank_fuzzy(name: str) -> Optional[dict]:
    """Offload synchronous SQLite file read and fuzzy matching to background thread."""
    return await asyncio.to_thread(_sync_drugbank_fuzzy, name)


async def resolve_all_drugs(drug_names: list[str]) -> list[dict]:
    """Resolve multiple drugs in parallel."""
    return await asyncio.gather(*[resolve_drug_name(n) for n in drug_names])
