"""
CDSCO (Central Drugs Standard Control Organisation - India) integration.
Primary: Live Supabase Postgres `indian_drug_registry` table (nightly-synced).
Fallback: Local SQLite `cdsco_registry.db` (offline/cold-start only).
https://cdsco.gov.in
"""
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "data" / "cdsco_registry.db"


async def lookup_indian_drug(identifier: str) -> Optional[dict]:
    """
    Look up an Indian drug — tries live Supabase Postgres first,
    falls back to bundled SQLite only when the database is unreachable.
    """
    # Primary: Live distributed Postgres table (kept fresh by nightly sync)
    result = await _lookup_from_postgres(identifier)
    if result:
        return result

    # Fallback: Bundled SQLite (stale but available offline)
    import asyncio
    result = await asyncio.to_thread(_lookup_from_sqlite, identifier)
    if result:
        result["source"] = "cdsco_sqlite_fallback"
        result["_stale_warning"] = True
        logger.warning(
            f"cdsco_sqlite_fallback_used for {identifier}: Live Postgres unavailable — serving from bundled SQLite. Data may be stale."
        )
    return result


async def _lookup_from_postgres(identifier: str) -> Optional[dict]:
    """Query the live Supabase `indian_drug_registry` table."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return None

    try:
        # Exact match on CDSCO code or generic name
        rows = await db.query(
            "indian_drug_registry",
            filters={"cdsco_code": identifier},
            limit=1
        )
        if not rows:
            # Try case-insensitive generic or brand name match via PostgREST ilike
            rows = await db.query(
                "indian_drug_registry",
                custom_params={"or": f"(generic_name.ilike.{identifier},brand_name.ilike.{identifier})"},
                limit=1
            )
        if not rows and len(identifier) >= 4:
            # Prefix match via PostgREST ilike
            rows = await db.query(
                "indian_drug_registry",
                custom_params={"or": f"(generic_name.ilike.{identifier}%,brand_name.ilike.{identifier}%)"},
                limit=1
            )

        if rows:
            row = rows[0]
            return {
                "brand_name": row.get("brand_name") or row.get("generic_name"),
                "generic_name": row.get("generic_name"),
                "manufacturer": row.get("manufacturer"),
                "ndc": row.get("cdsco_code"),
                "product_type": "HUMAN DRUG",
                "route": row.get("route", "ORAL"),
                "indication": row.get("indication"),
                "approval_date": row.get("approval_date"),
                "source": "cdsco_live_postgres",
                "coverage": "full_registry",
                "last_synced": row.get("last_synced_at")
            }
    except Exception as e:
        logger.error(f"CDSCO Postgres lookup error: {e}")

    return None


def _lookup_from_sqlite(identifier: str) -> Optional[dict]:
    """Offline fallback: query the bundled SQLite CDSCO registry."""
    if not DB_PATH.exists():
        return None

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Exact or partial match on CDSCO code or generic name
        cursor.execute('''
            SELECT * FROM indian_drugs 
            WHERE cdsco_code = ? OR LOWER(generic_name) = ? OR LOWER(generic_name) LIKE ?
            LIMIT 1
        ''', (identifier, identifier.lower(), f"%{identifier.lower()}%"))

        row = cursor.fetchone()
        conn.close()

        if row:
            b_name = row["generic_name"].split("+")[0].strip() if row["generic_name"] else identifier
            return {
                "brand_name": b_name,
                "generic_name": row["generic_name"],
                "manufacturer": row["manufacturer"],
                "ndc": row["cdsco_code"],
                "product_type": "HUMAN DRUG",
                "route": "ORAL",
                "indication": row["indication"],
                "approval_date": row["approval_date"],
                "source": "cdsco_new_approvals",
                "coverage": "new_drugs_only"
            }
    except Exception as e:
        logger.error(f"CDSCO Local DB Error: {e}")

    return None


async def sync_cdsco_registry():
    """
    Nightly sync task: migrates all SQLite CDSCO records into the live
    Supabase `indian_drug_registry` table. Designed to be called from
    a Supabase Edge Function cron, a FastAPI background task, or manually.
    """
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        logger.error("cdsco_sync_failed: Supabase not available")
        return {"synced": 0, "error": "Supabase unavailable"}

    if not DB_PATH.exists():
        logger.warning("cdsco_sync_skipped: SQLite DB not found")
        return {"synced": 0, "error": "SQLite DB not found"}

    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM indian_drugs")
        rows = cursor.fetchall()
        conn.close()

        now = datetime.now(timezone.utc).isoformat()
        batch = []
        for row in rows:
            r_dict = dict(row)
            batch.append({
                "cdsco_code": r_dict["cdsco_code"],
                "generic_name": r_dict["generic_name"],
                "brand_name": r_dict.get("brand_name") or r_dict["generic_name"],
                "manufacturer": r_dict["manufacturer"],
                "indication": r_dict.get("indication"),
                "approval_date": r_dict.get("approval_date"),
                "route": "ORAL",
                "last_synced_at": now,
                "sync_source": "sqlite_seed"
            })

        # Upsert in batches of 100
        synced = 0
        for i in range(0, len(batch), 100):
            chunk = batch[i:i+100]
            for record in chunk:
                try:
                    await db.insert("indian_drug_registry", record, upsert=True)
                    synced += 1
                except Exception as e:
                    logger.warning(f"cdsco_sync_upsert_skip: {record.get('cdsco_code')}: {e}")

        logger.info(f"cdsco_sync_complete: {synced}/{len(batch)} records upserted")
        return {"synced": synced, "total": len(batch)}

    except Exception as e:
        logger.error(f"cdsco_sync_error: {e}")
        return {"synced": 0, "error": str(e)}


async def check_cdsco_recall(drug_name: str, batch_no: str = None) -> dict:
    """Check Supabase cdsco_recalls table for active Indian drug recalls."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return {"has_cdsco_recall": False, "available": False, "reason": "CDSCO recall store unavailable"}

    try:
        recalls = await db.query("cdsco_recalls", limit=1000)

        d_name_clean = drug_name.lower().strip()
        matches = []

        for r in recalls:
            r_name = r.get("drug_name", "").lower()
            if d_name_clean in r_name or r_name in d_name_clean:
                if batch_no:
                    r_batch = r.get("batch_no", "")
                    if r_batch and batch_no.lower().strip() == r_batch.lower().strip():
                        matches.append(r)
                else:
                    matches.append(r)

        if matches:
            latest = sorted(matches, key=lambda x: x.get("created_at", ""), reverse=True)[0]
            return {
                "has_cdsco_recall": True,
                "available": True,
                "recall_reason": latest.get("reason", "Sub-standard quality"),
                "recall_date": latest.get("date_issued"),
                "source": "CDSCO"
            }
    except Exception as e:
        logger.error(f"CDSCO Recall Check Error: {e}")
        return {"has_cdsco_recall": False, "available": False, "reason": "CDSCO recall lookup failed"}

    return {"has_cdsco_recall": False, "available": True}
