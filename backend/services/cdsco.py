"""
CDSCO (Central Drugs Standard Control Organisation - India) integration.
Provides a fallback lookup for Indian medicines when OpenFDA fails.
https://cdsco.gov.in
"""
import sqlite3
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "data" / "cdsco_registry.db"

async def lookup_indian_drug(identifier: str) -> Optional[dict]:
    """
    Attempt to look up a drug using the local CDSCO SQLite registry.
    """
    if not DB_PATH.exists():
        return None
        
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Exact match on CDSCO code or generic name first
        cursor.execute('''
            SELECT * FROM indian_drugs 
            WHERE cdsco_code = ? OR LOWER(generic_name) = ?
            LIMIT 1
        ''', (identifier, identifier.lower()))
        
        row = cursor.fetchone()
        
        # Fallback to strict prefix match if no exact match and input is long enough
        if not row and len(identifier) >= 6:
            query_prefix = identifier.lower() + "%"
            cursor.execute('''
                SELECT * FROM indian_drugs 
                WHERE LOWER(generic_name) LIKE ?
                LIMIT 1
            ''', (query_prefix,))
            row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                "brand_name": row["generic_name"],
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
        import logging
        logging.getLogger(__name__).error(f"CDSCO Local DB Error: {e}")

    return None

async def check_cdsco_recall(drug_name: str, batch_no: str = None) -> dict:
    """Check Supabase cdsco_recalls table for active Indian drug recalls."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return {"has_cdsco_recall": False}

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
                "recall_reason": latest.get("reason", "Sub-standard quality"),
                "recall_date": latest.get("date_issued"),
                "source": "CDSCO"
            }
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"CDSCO Recall Check Error: {e}")
        
    return {"has_cdsco_recall": False}
