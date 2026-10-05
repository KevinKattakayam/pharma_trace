"""
OpenFDA API client for drug lookup, recall checking, and adverse event queries.
Free API: https://api.fda.gov
Rate limits: 240 req/min with API key, 1000/day without.
"""
from typing import Optional

import httpx

OPENFDA_BASE = "https://api.fda.gov"

from services.ttl_cache import TTLCache

# Bounded caches (audit R10). Registry records change rarely; shortages more often.
_ndc_cache: TTLCache[dict] = TTLCache(maxsize=2048, ttl_seconds=12 * 3600)
_label_cache: TTLCache[dict] = TTLCache(maxsize=2048, ttl_seconds=12 * 3600)
_shortage_cache: TTLCache[dict] = TTLCache(maxsize=1024, ttl_seconds=6 * 3600)

_MAX_TERM_LEN = 200


def _esc(value: object) -> str:
    """Escape a value for use inside a double-quoted openFDA (Elasticsearch) phrase.

    Prevents callers from closing the phrase and injecting extra query clauses (audit S12).
    """
    text = "".join(ch for ch in str(value) if ch.isprintable())[:_MAX_TERM_LEN]
    return text.replace("\\", "\\\\").replace('"', '\\"')
from services.canonicalize import normalize_ndc
from services.circuit_breaker import circuit_breaker


@circuit_breaker(name="openfda", failure_threshold=3, recovery_timeout=30.0)
async def lookup_by_ndc(ndc: str, api_key: str = "") -> Optional[dict]:
    """Look up a drug by NDC code via OpenFDA NDC endpoint."""
    ndc_canonical = normalize_ndc(ndc)
    ndc_clean = ndc.strip().replace("-", "")

    # Check cache with canonical form first
    for key in (ndc_canonical, ndc_clean):
        cached = _ndc_cache.get(key)
        if cached is not None:
            return cached

    # Try multiple NDC formats, starting with canonical
    search_terms = [ndc_canonical, ndc, ndc_clean]
    if len(ndc_clean) == 10:
        # Try 4-4-2, 5-3-2, 5-4-1 formats
        search_terms.extend([
            f"{ndc_clean[:4]}-{ndc_clean[4:8]}-{ndc_clean[8:]}",
            f"{ndc_clean[:5]}-{ndc_clean[5:8]}-{ndc_clean[8:]}",
            f"{ndc_clean[:5]}-{ndc_clean[5:9]}-{ndc_clean[9:]}"
        ])

    # Also handle UPC barcodes (12 digits — strip check digit and leading zero)
    if len(ndc_clean) >= 11:
        inner = ndc_clean[1:11] if len(ndc_clean) == 12 else ndc_clean[:10]
        search_terms.append(inner)
        search_terms.append(f"{inner[:5]}-{inner[5:8]}-{inner[8:]}")
        search_terms.append(f"{inner[:5]}-{inner[5:9]}-{inner[9:]}")

    async with httpx.AsyncClient(timeout=15.0) as client:
        for term in search_terms:
            try:
                params = {"search": f'product_ndc:"{_esc(term)}" OR packaging.package_ndc:"{_esc(term)}"', "limit": 1}
                if api_key:
                    params["api_key"] = api_key

                resp = await client.get(f"{OPENFDA_BASE}/drug/ndc.json", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("results"):
                        result = data["results"][0]
                        _ndc_cache[ndc_clean] = result
                        return result
            except Exception:
                continue

    # Fallback: If not found by NDC number, try searching FDA drug labels by name
    return await lookup_by_name(ndc, api_key=api_key)


@circuit_breaker(name="openfda", failure_threshold=3, recovery_timeout=30.0)
async def lookup_by_name(drug_name: str, api_key: str = "") -> Optional[dict]:
    """Look up a drug by brand or generic name via OpenFDA labels."""
    cache_key = drug_name.lower().strip()
    cached = _label_cache.get(cache_key)
    if cached is not None:
        return cached

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            search = f'openfda.brand_name:"{_esc(drug_name)}" OR openfda.generic_name:"{_esc(drug_name)}"'
            params = {"search": search, "limit": 1}
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/label.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    result = data["results"][0]
                    _label_cache[cache_key] = result
                    return result
        except Exception:
            pass

    return None


async def get_drug_label(ndc: str = None, drug_name: str = None, api_key: str = "") -> Optional[dict]:
    """Get full drug label with warnings, side effects, dosage info."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            if ndc:
                search = f'openfda.product_ndc:"{_esc(ndc)}"'
            elif drug_name:
                search = f'openfda.brand_name:"{_esc(drug_name)}" OR openfda.generic_name:"{_esc(drug_name)}"'
            else:
                return None

            params = {"search": search, "limit": 1}
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/label.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("results"):
                    return data["results"][0]
        except Exception:
            pass
    return None


async def check_recalls(ndc: str = None, drug_name: str = None, api_key: str = "") -> list[dict]:
    """Check OpenFDA enforcement endpoint for active recalls."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            if ndc and any(c.isalpha() for c in ndc):
                search = f'product_description:"{_esc(ndc)}" OR openfda.brand_name:"{_esc(ndc)}" OR openfda.generic_name:"{_esc(ndc)}"'
            elif ndc:
                search = f'openfda.product_ndc:"{_esc(ndc)}"'
            elif drug_name:
                search = f'product_description:"{_esc(drug_name)}" OR openfda.brand_name:"{_esc(drug_name)}" OR openfda.generic_name:"{_esc(drug_name)}"'
            else:
                return []

            params = {"search": search + ' AND status:"Ongoing"', "limit": 5}
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/enforcement.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
            else:
                return [{"error": "SERVICE_UNAVAILABLE", "status": resp.status_code}]
        except Exception as e:
            return [{"error": "SERVICE_UNAVAILABLE", "detail": str(e)}]
    return [{"error": "SERVICE_UNAVAILABLE"}]


async def get_adverse_events(drug_name: str, limit: int = 10, api_key: str = "") -> list[dict]:
    """Get adverse event reports for a drug from OpenFDA FAERS."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            params = {
                "search": f'patient.drug.openfda.generic_name:"{_esc(drug_name.upper())}"',
                "limit": limit
            }
            if api_key:
                params["api_key"] = api_key

            resp = await client.get(f"{OPENFDA_BASE}/drug/event.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("results", [])
        except Exception:
            pass
    return []


async def find_generics(substance_name: str, api_key: str = "") -> list[dict]:
    """Find all drugs with matching active ingredient (generic alternatives)."""
    results = []

    # Try multiple search strategies
    searches = [
        f'openfda.substance_name:"{_esc(substance_name.upper())}"',
        f'openfda.generic_name:"{_esc(substance_name.upper())}"',
        f'active_ingredients.name:"{_esc(substance_name.upper())}"',
    ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        seen = set()
        for search_query in searches:
            if len(results) >= 10:
                break
            try:
                params = {"search": search_query, "limit": 20}
                if api_key:
                    params["api_key"] = api_key

                resp = await client.get(f"{OPENFDA_BASE}/drug/ndc.json", params=params)
                if resp.status_code == 200:
                    data = resp.json()
                    for item in data.get("results", []):
                        openfda = item.get("openfda", {})
                        brand = (openfda.get("brand_name") or [""])[0] if isinstance(openfda.get("brand_name"), list) else openfda.get("brand_name", "")
                        generic = (openfda.get("generic_name") or [""])[0] if isinstance(openfda.get("generic_name"), list) else openfda.get("generic_name", "")
                        mfr = (openfda.get("manufacturer_name") or [""])[0] if isinstance(openfda.get("manufacturer_name"), list) else openfda.get("manufacturer_name", "")
                        ndc = item.get("product_ndc", "")

                        key = f"{generic}:{mfr}"
                        if key not in seen and ndc:
                            seen.add(key)
                            results.append({
                                "brand_name": brand,
                                "generic_name": generic,
                                "manufacturer": mfr,
                                "ndc": ndc,
                                "strength": item.get("active_ingredients", [{}])[0].get("strength", "") if item.get("active_ingredients") else "",
                                "route": (item.get("route") or [""])[0] if isinstance(item.get("route"), list) else item.get("route", ""),
                                "dosage_form": item.get("dosage_form", "")
                            })
            except Exception:
                continue
    return results[:10]


def extract_openfda_info(ndc_result: dict) -> dict:
    """Extract standardized drug info from an NDC lookup result."""
    openfda = ndc_result.get("openfda", {})

    def first(field):
        val = openfda.get(field, [])
        if isinstance(val, list) and val:
            return val[0]
        return val or ""

    ingredients = ndc_result.get("active_ingredients", [])
    ingredient_str = ", ".join(
        f"{i.get('name', '')} {i.get('strength', '')}".strip()
        for i in ingredients
    ) if ingredients else ""

    return {
        "brand_name": first("brand_name") or ndc_result.get("brand_name", ""),
        "generic_name": first("generic_name") or ndc_result.get("generic_name", ""),
        "manufacturer": first("manufacturer_name") or ndc_result.get("labeler_name", ""),
        "ndc": ndc_result.get("product_ndc", ""),
        "product_type": (ndc_result.get("product_type") or first("product_type") or ""),
        "route": (ndc_result.get("route", [""])[0] if isinstance(ndc_result.get("route"), list) else ndc_result.get("route", "")),
        "active_ingredients": ingredient_str,
        "substance_name": first("substance_name"),
        "pharm_class": first("pharm_class_epc"),
        "rxcui": first("rxcui"),
        "upc": first("upc")
    }


async def check_drug_shortage(active_ingredient: str, api_key: str = "") -> dict:
    """Check FDA Drug Shortages endpoint for supply issues."""
    cache_key = active_ingredient.strip().lower()
    
    cached = _shortage_cache.get(cache_key)
    if cached is not None:
        return cached
    
    result = {"in_shortage": False, "reason": None, "status": None}
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            params = {
                "search": f'generic_name:"{_esc(active_ingredient)}"',
                "limit": 5
            }
            if api_key:
                params["api_key"] = api_key
            
            resp = await client.get(f"{OPENFDA_BASE}/drug/shortages.json", params=params)
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    latest = results[0]
                    result = {
                        "in_shortage": True,
                        "reason": latest.get("shortage_reason", "Unknown"),
                        "status": latest.get("status", "Active"),
                        "generic_name": latest.get("generic_name", active_ingredient),
                    }
        except Exception:
            pass
    
    _shortage_cache[cache_key] = result
    return result

