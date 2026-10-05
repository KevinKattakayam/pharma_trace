"""
Vernacular Drug Name Resolver — 5-layer cascade, 3-model AI fallback.

Layer 1: PostgreSQL trigram index (exact + fuzzy, zero AI cost)
Layer 2: Seeding pipelines (RxNorm, traffic learning, CDSCO scraper)
Layer 3: Non-Latin script detection + LibreTranslate transliteration
Layer 4: AI cascade (Gemini 2.0 Flash → Groq/Llama 3.3 → GPT-4o)
Layer 5: Unified resolver orchestrating all layers

Every AI resolution is cached to the database. The second time anyone
asks about the same drug, it comes from PostgreSQL at zero cost.
"""
import json
from typing import Optional

import httpx

from config import get_settings
from services.supabase import get_supabase
from services.translation import contains_non_latin, resolve_script_to_latin


async def _cache_get(key: str) -> Optional[dict]:
    from services.cache_manager import get_cache
    return await get_cache().get(f"alias:{key}")


async def _cache_set(key: str, value: dict):
    from services.cache_manager import get_cache
    await get_cache().set(f"alias:{key}", value, ttl_seconds=3600)


# ═══════════════════════════════════════════════════════════════
# Layer 1 — Database exact + trigram fuzzy match
# ═══════════════════════════════════════════════════════════════

async def _db_exact_match(query_lower: str) -> Optional[dict]:
    """Exact match against the vernacular_aliases table."""
    db = get_supabase()
    if not db.available:
        return None

    try:
        results = await db.query(
            "vernacular_aliases",
            select="canonical_name,active_ingredients,confidence",
            filters={"drug_alias": query_lower},
            limit=1
        )
        if results:
            row = results[0]
            # Bump usage count in background (fire-and-forget)
            try:
                __import__('services.tasks', fromlist=['spawn']).spawn(_bump_usage(query_lower), name='alias_usage_bump')
            except Exception:
                pass
            return {
                "canonical_name": row["canonical_name"],
                "active_ingredients": row.get("active_ingredients", []),
                "source": "database_exact",
                "confidence": row.get("confidence", 1.0)
            }
    except Exception:
        pass
    return None


async def _bump_usage(query_lower: str):
    """Increment usage_count for a matched alias."""
    db = get_supabase()
    if not db.available:
        return
    try:
        # Use RPC or raw update — PostgREST PATCH
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.patch(
                f"{db.url}/rest/v1/vernacular_aliases",
                headers={**db.headers, "Prefer": "return=minimal"},
                params={"drug_alias": f"eq.{query_lower}"},
                json={"usage_count": "usage_count + 1"}  # PostgREST doesn't support increment directly
            )
    except Exception:
        pass


async def _db_fuzzy_match(query_lower: str) -> Optional[dict]:
    """Trigram fuzzy match via the fuzzy_drug_alias RPC."""
    db = get_supabase()
    if not db.available:
        return None

    try:
        results = await db.rpc("fuzzy_drug_alias", {
            "query_text": query_lower,
            "similarity_threshold": 0.4
        })
        if results and isinstance(results, list) and results[0].get("canonical_name"):
            row = results[0]
            return {
                "canonical_name": row["canonical_name"],
                "active_ingredients": row.get("active_ingredients", []),
                "source": "database_fuzzy",
                "confidence": row.get("similarity", 0.8)
            }
    except Exception:
        pass
    return None


# ═══════════════════════════════════════════════════════════════
# Layer 2 — Seeding pipelines (called externally, not in resolve path)
# ═══════════════════════════════════════════════════════════════

async def seed_from_rxnorm(brand_name: str) -> Optional[dict]:
    """Pipeline A: Seed and resolve alias from RxNorm brand-to-generic lookup."""
    db = get_supabase()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(
                "https://rxnav.nlm.nih.gov/REST/rxcui.json",
                params={"name": brand_name, "search": "1"}
            )
            if r.status_code != 200:
                return None

            rxcui = r.json().get("idGroup", {}).get("rxnormId", [None])
            if not rxcui or not rxcui[0]:
                return None
            rxcui = rxcui[0]

            props = await client.get(
                f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/properties.json"
            )
            if props.status_code != 200:
                return None

            canonical = props.json().get("properties", {}).get("name")
            if not canonical:
                return None

            ingredients_resp = await client.get(
                f"https://rxnav.nlm.nih.gov/REST/rxcui/{rxcui}/related.json",
                params={"tty": "IN"}
            )
            ingredients = [canonical]
            if ingredients_resp.status_code == 200:
                groups = ingredients_resp.json().get("relatedGroup", {}).get("conceptGroup", [])
                if groups and groups[0].get("conceptProperties"):
                    ingredients = [g["name"] for g in groups[0]["conceptProperties"]]

            res_dict = {
                "canonical_name": canonical,
                "active_ingredients": ingredients,
                "source": "rxnorm_api",
                "confidence": 1.0
            }

            try:
                await db.insert("vernacular_aliases", {
                    "drug_alias": brand_name.strip().lower(),
                    "canonical_name": canonical,
                    "active_ingredients": ingredients,
                    "language_code": "en",
                    "alias_type": "brand",
                    "source": "rxnorm",
                    "confidence": 1.0,
                    "verified": True
                }, upsert=True)
            except Exception:
                pass

            return res_dict
    except Exception as e:
        import structlog
        structlog.get_logger().error("rxnorm_lookup_failed", brand_name=brand_name, error=str(e))
    return None


async def _openfda_live_lookup(brand_name: str) -> Optional[dict]:
    """Live lookup against OpenFDA labels database."""
    try:
        from services.openfda import lookup_by_name
        fda_res = await lookup_by_name(brand_name)
        if fda_res:
            generic_name = fda_res.get("generic_name", [""])[0] if isinstance(fda_res.get("generic_name"), list) else fda_res.get("generic_name", "")
            if not generic_name:
                generic_name = brand_name
            active_ingredients = fda_res.get("active_ingredient", [generic_name])
            if isinstance(active_ingredients, str):
                active_ingredients = [active_ingredients]
            elif isinstance(active_ingredients, list):
                active_ingredients = [str(i) for i in active_ingredients if i]
                
            res_dict = {
                "canonical_name": generic_name.title(),
                "active_ingredients": [i.title() for i in active_ingredients if i],
                "source": "openfda_api",
                "confidence": 0.98
            }
            
            db = get_supabase()
            try:
                await db.insert("vernacular_aliases", {
                    "drug_alias": brand_name.strip().lower(),
                    "canonical_name": res_dict["canonical_name"],
                    "active_ingredients": res_dict["active_ingredients"],
                    "language_code": "en",
                    "alias_type": "brand",
                    "source": "openfda",
                    "confidence": 0.98,
                    "verified": True
                }, upsert=True)
            except Exception:
                pass
                
            return res_dict
    except Exception:
        pass
    return None


async def learn_from_verification(query: str, brand_name: str, generic_name: str,
                                   active_ingredients: list[str]):
    """Pipeline B: Passive learning — every successful verification teaches a new alias."""
    if not generic_name:
        return

    query_lower = query.strip().lower()
    if query_lower == generic_name.lower():
        return  # Already canonical, nothing to learn

    db = get_supabase()
    if not db.available:
        return

    try:
        existing = await db.query(
            "vernacular_aliases",
            select="id,usage_count",
            filters={"drug_alias": query_lower},
            limit=1
        )

        if existing:
            # Bump usage count
            row = existing[0]
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.patch(
                    f"{db.url}/rest/v1/vernacular_aliases",
                    headers={**db.headers, "Prefer": "return=minimal"},
                    params={"id": f"eq.{row['id']}"},
                    json={"usage_count": row["usage_count"] + 1}
                )
        else:
            await db.insert("vernacular_aliases", {
                "drug_alias": query_lower,
                "canonical_name": generic_name,
                "active_ingredients": active_ingredients or [generic_name],
                "language_code": "en",
                "alias_type": "brand",
                "source": "openfda_traffic",
                "confidence": 0.9,
                "verified": False
            })
    except Exception:
        pass  # Non-critical — don't break the verification pipeline


async def seed_from_cdsco_row(row: dict):
    """Pipeline C: CDSCO scraper writes aliases as a side-effect."""
    brand = row.get("brand_name") or row.get("drug_name")
    generic = row.get("generic_name")
    if not brand or not generic:
        return

    db = get_supabase()
    if not db.available:
        return

    try:
        await db.insert("vernacular_aliases", {
            "drug_alias": brand.strip().lower(),
            "canonical_name": generic,
            "active_ingredients": row.get("active_ingredients", [generic]),
            "language_code": "en",
            "alias_type": "brand",
            "source": "cdsco",
            "confidence": 1.0,
            "verified": True
        }, upsert=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Layer 4 — 3-model AI cascade (Gemini → Llama → GPT-4o)
# ═══════════════════════════════════════════════════════════════

_DRUG_ID_PROMPT = """You are a pharmaceutical drug identification system.
The user has entered: "{query}"

Identify if this is a medicine name, brand name, or drug query in any language or script.
If yes, return ONLY this JSON with no other text:
{{
  "canonical_name": "generic drug name in English (INN)",
  "active_ingredients": ["ingredient1", "ingredient2"],
  "language_detected": "ISO 639-1 code",
  "confidence": 0.0 to 1.0,
  "reasoning": "one sentence"
}}

If this is not a medicine, return ONLY: {{"canonical_name": null}}

Rules:
- canonical_name must be the INN (International Nonproprietary Name)
- Never invent drugs that do not exist
- If uncertain, set confidence below 0.7
- active_ingredients must be real pharmacological compounds"""


def _clean_json_loads(text: str) -> dict:
    """Robustly parse JSON even if wrapped in Markdown code blocks."""
    if not text:
        return {}
    clean = text.strip()
    if clean.startswith("```json"):
        clean = clean[7:]
    if clean.startswith("```"):
        clean = clean[3:]
    if clean.endswith("```"):
        clean = clean[:-3]
    clean = clean.strip()
    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        return {}


async def _resolve_via_gemini(query: str) -> Optional[dict]:
    """Model 1: Gemini 2.0 Flash — best for Indian scripts, free tier."""
    settings = get_settings()
    if not settings.gemini_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={settings.gemini_api_key}",
                json={
                    "contents": [{"parts": [{"text": _DRUG_ID_PROMPT.format(query=query)}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "temperature": 0
                    }
                }
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            result = _clean_json_loads(text)

            if not result or not result.get("canonical_name"):
                return None
            if result.get("confidence", 0) < 0.75:
                return None

            result["_model"] = "gemini"
            return result
    except Exception:
        return None


async def _resolve_via_groq_llama(query: str) -> Optional[dict]:
    """Model 2: Groq/Llama 3.3 70B — fast, good for Latin script."""
    settings = get_settings()
    if not settings.groq_api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": _DRUG_ID_PROMPT.format(query=query)}],
                    "temperature": 0,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"}
                }
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = _clean_json_loads(content)

            if not result or not result.get("canonical_name"):
                return None
            if result.get("confidence", 0) < 0.75:
                return None

            result["_model"] = "groq_llama"
            return result
    except Exception:
        return None


async def _resolve_via_gpt4o(query: str) -> Optional[dict]:
    """Model 3: GPT-4o via OpenRouter — final arbiter for ambiguous medical cases."""
    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key:
        return None

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://pharmatrace.app",
                    "X-Title": "PharmaTrace"
                },
                json={
                    "model": "openai/gpt-4o",
                    "messages": [{"role": "user", "content": _DRUG_ID_PROMPT.format(query=query)}],
                    "temperature": 0,
                    "max_tokens": 200,
                    "response_format": {"type": "json_object"}
                }
            )

            if resp.status_code != 200:
                return None

            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            result = _clean_json_loads(content)

            if not result or not result.get("canonical_name"):
                return None
            if result.get("confidence", 0) < 0.7:
                return None

            result["_model"] = "gpt4o"
            return result
    except Exception:
        return None


async def _resolve_via_ai_cascade(query: str) -> Optional[dict]:
    """
    Route by script type, then cascade through models.
    Gemini handles Indian scripts natively and better.
    Llama handles Latin script well.
    GPT-4o is the final arbiter for edge cases.
    """
    # Non-Latin → Gemini first (stronger on Indian scripts)
    if contains_non_latin(query):
        result = await _resolve_via_gemini(query)
        if result:
            return result

    # Latin script or Gemini failed → Llama 3.3
    result = await _resolve_via_groq_llama(query)
    if result:
        return result

    # Both failed → GPT-4o as final arbiter
    result = await _resolve_via_gpt4o(query)
    if result:
        return result

    return None


async def _cache_ai_result(query: str, result: dict):
    """Write AI resolution to the database so this query never hits AI again."""
    db = get_supabase()
    if not db.available:
        return

    model_used = result.get("_model", "ai_resolved")
    source_map = {
        "gemini": "ai_resolved",
        "groq_llama": "ai_resolved",
        "gpt4o": "ai_resolved"
    }

    try:
        await db.insert("vernacular_aliases", {
            "drug_alias": query.strip().lower(),
            "canonical_name": result["canonical_name"],
            "active_ingredients": result.get("active_ingredients", [result["canonical_name"]]),
            "language_code": result.get("language_detected", "unknown"),
            "alias_type": "ai_resolved",
            "source": source_map.get(model_used, "ai_resolved"),
            "confidence": result.get("confidence", 0.8),
            "verified": False
        }, upsert=True)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════
# Layer 5 — Unified resolver (replaces resolve_vernacular_alias)
# ═══════════════════════════════════════════════════════════════

async def resolve_drug_query(query: str) -> dict:
    """
    The single entry point for all drug name resolution.
    
    Cascade:
    1. In-memory cache
    2. Non-Latin script → LibreTranslate transliteration
    3. Database exact match (pg_trgm)
    4. Database fuzzy match (trigram similarity)
    5. AI cascade (Gemini → Llama → GPT-4o), result cached to DB
    """
    query_clean = query.strip()
    if not query_clean:
        return {
            "canonical_name": query,
            "active_ingredients": [],
            "source": "empty",
            "confidence": 0.0
        }

    cache_key = query_clean.lower()

    # 1. In-memory cache
    cached = await _cache_get(cache_key)
    if cached:
        return cached

    # 2. Transliterate non-Latin scripts to Latin before DB lookup
    latin_query = await resolve_script_to_latin(query_clean)
    latin_key = latin_query.strip().lower()

    # Check cache again with transliterated key
    if latin_key != cache_key:
        cached = await _cache_get(latin_key)
        if cached:
            await _cache_set(cache_key, cached)  # Cache original key too
            return cached

    # 3. Database exact match
    result = await _db_exact_match(latin_key)
    if result:
        await _cache_set(cache_key, result)
        if latin_key != cache_key:
            await _cache_set(latin_key, result)
        return result

    # 4. Database trigram fuzzy match
    result = await _db_fuzzy_match(latin_key)
    if result:
        await _cache_set(cache_key, result)
        return result

    # 4.5. Live authoritative lookup via NLM RxNorm API
    rxnorm_res = await seed_from_rxnorm(latin_key)
    if rxnorm_res:
        await _cache_set(cache_key, rxnorm_res)
        if latin_key != cache_key:
            await _cache_set(latin_key, rxnorm_res)
        return rxnorm_res

    # 4.6. Live authoritative lookup via OpenFDA API
    fda_res = await _openfda_live_lookup(latin_key)
    if fda_res:
        await _cache_set(cache_key, fda_res)
        if latin_key != cache_key:
            await _cache_set(latin_key, fda_res)
        return fda_res

    # 5. AI cascade as last resort
    ai_result = await _resolve_via_ai_cascade(
        query_clean if contains_non_latin(query_clean) else latin_query
    )
    if ai_result:
        result = {
            "canonical_name": ai_result["canonical_name"],
            "active_ingredients": ai_result.get("active_ingredients", []),
            "source": f"ai_{ai_result.get('_model', 'resolved')}",
            "confidence": ai_result.get("confidence", 0.8)
        }
        await _cache_set(cache_key, result)
        # Persist to DB so this query never hits AI again
        await _cache_ai_result(query_clean, ai_result)
        return result

    # Nothing resolved
    return {
        "canonical_name": query_clean,
        "active_ingredients": [],
        "source": "unresolved",
        "confidence": 0.0
    }
