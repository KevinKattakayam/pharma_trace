import asyncio
import logging

logger = logging.getLogger(__name__)

async def fetch_with_timeout(coro, seconds: float, name: str) -> dict:
    try:
        # asyncio.wait_for is available in older Pythons, asyncio.timeout in 3.11+
        result = await asyncio.wait_for(coro, timeout=seconds)
        if isinstance(result, dict) and result.get("error"):
            return {"source": name, "error": result.get("error"), "data": None}
        if isinstance(result, list) and any(isinstance(r, dict) and r.get("error") for r in result):
            return {"source": name, "error": "SERVICE_UNAVAILABLE", "data": None}
        return {"source": name, "error": None, "data": result}
    except asyncio.TimeoutError:
        return {"source": name, "error": "timeout", "data": None}
    except Exception as e:
        logger.error(f"Error in {name} lookup: {str(e)}")
        return {"source": name, "error": str(e), "data": None}

async def parallel_lookup(ndc: str, location: dict = None) -> dict:
    """
    Tier 2 — Parallel L1 lookups with circuit breakers.
    Calls OpenFDA, RxNav, CDSCO, DrugBank CE, and Weather API concurrently.
    """
    from config import get_settings
    from services.cdsco import lookup_indian_drug
    from services.cold_chain import check_cold_chain
    from services.openfda import check_recalls, lookup_by_ndc
    
    settings = get_settings()
    
    # DrugBank CE lookup via Local SQLite
    def _sync_drugbank_ce_lookup(identifier: str):
        import sqlite3
        from pathlib import Path
        db_path = Path(__file__).parent.parent / "data" / "drugbank_ce.db"
        if not db_path.exists() or db_path.stat().st_size == 0:
            return None
            
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM drugs WHERE LOWER(name) = ? OR drugbank_id = ? LIMIT 1', (identifier.lower(), identifier))
            row = cursor.fetchone()
            
            if not row and len(identifier) >= 6:
                query_prefix = identifier.lower() + "%"
                cursor.execute('SELECT * FROM drugs WHERE LOWER(name) LIKE ? LIMIT 1', (query_prefix,))
                row = cursor.fetchone()
            
            if row:
                drugbank_id = row["drugbank_id"]
                cursor.execute('SELECT drug_b_name, description FROM interactions WHERE drug_a_id = ? LIMIT 5', (drugbank_id,))
                interactions = [{"drug": r["drug_b_name"], "description": r["description"]} for r in cursor.fetchall()]
                conn.close()
                return {
                    "brand_name": row["name"],
                    "generic_name": row["name"],
                    "description": row["description"],
                    "interactions_sample": interactions,
                    "source": "DrugBank Local CE"
                }
            conn.close()
        except Exception as e:
            logger.error(f"DrugBank Local DB Error: {e}")
        return None
        
    async def drugbank_ce_lookup(identifier: str):
        import asyncio
        return await asyncio.to_thread(_sync_drugbank_ce_lookup, identifier)
        
    tasks = [
        fetch_with_timeout(lookup_by_ndc(ndc, api_key=settings.openfda_api_key), 3.0, "openfda"),
        fetch_with_timeout(check_recalls(ndc=ndc, api_key=settings.openfda_api_key), 2.0, "recalls"),
        # fetch_with_timeout(check_interactions([ndc]), 2.0, "rxnav"), # simplified for single NDC
        fetch_with_timeout(lookup_indian_drug(ndc), 2.0, "cdsco"),
        fetch_with_timeout(drugbank_ce_lookup(ndc), 2.0, "drugbank"),
    ]
    
    if location and location.get("lat"):
        tasks.append(fetch_with_timeout(check_cold_chain(location["lat"], location["lng"]), 1.5, "weather"))
        
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return merge_results(results)

def merge_results(results: list) -> dict:
    merged = {}
    for res in results:
        if isinstance(res, dict):
            merged[res["source"]] = res
    return merged
