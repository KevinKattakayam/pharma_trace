"""
Hash-chained audit log — immutable verification records.
Each record contains SHA-256(previous_hash + record_data).
If any record is deleted or modified, the chain breaks.
"""
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

# In-memory audit chain (replace with Supabase in production)
_audit_chain: list[dict] = []
GENESIS_HASH = hashlib.sha256(b"PHARMATRACE_GENESIS").hexdigest()

def compute_hash(previous_hash: str, record_data: dict) -> str:
    """Compute SHA-256 hash of previous hash + record data."""
    payload = previous_hash + json.dumps(record_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()

def add_audit_record(verification_id: str, record_data: dict) -> dict:
    """Add a new record to the hash chain."""
    previous_hash = _audit_chain[-1]["record_hash"] if _audit_chain else GENESIS_HASH
    
    if "verified_at" not in record_data:
        record_data["verified_at"] = datetime.now(timezone.utc).isoformat()
        
    if "source" not in record_data:
        record_data["source"] = "live"
        
    record_hash = compute_hash(previous_hash, record_data)

    record = {
        "id": len(_audit_chain) + 1,
        "verification_id": verification_id,
        "record_hash": record_hash,
        "previous_hash": previous_hash,
        "record_data": record_data,
        "verified_at": record_data["verified_at"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    _audit_chain.append(record)
    
    # Fire-and-forget sync to Supabase if available
    try:
        from services.supabase import get_supabase
        import asyncio
        db = get_supabase()
        if db.available:
            asyncio.create_task(db.insert("safety_check_log", {
                "verification_id": verification_id,
                "medicine_name_raw": record_data.get("barcode", "unknown"),
                "medicine_name_resolved": record_data.get("drug", "unknown"),
                "verdict": record_data.get("verdict", "unknown"),
                "confidence": record_data.get("confidence", 0),
                "source": record_data.get("source", "live"),
                "verified_at": record_data["verified_at"],
                "created_at": record["created_at"],
                "audit_hash": record_hash
            }))
    except Exception:
        pass
        
    return record

def verify_chain() -> dict:
    """Verify the integrity of the entire audit chain. Recomputes all hashes."""
    if not _audit_chain:
        return {
            "chain_valid": True,
            "total_records": 0,
            "last_hash": None,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    broken_at_row = None
    
    for i, record in enumerate(_audit_chain):
        expected_prev = _audit_chain[i - 1]["record_hash"] if i > 0 else GENESIS_HASH
        
        if record["previous_hash"] != expected_prev:
            broken_at_row = record["id"]
            break

        expected_hash = compute_hash(record["previous_hash"], record["record_data"])
        if record["record_hash"] != expected_hash:
            broken_at_row = record["id"]
            break

    return {
        "chain_valid": broken_at_row is None,
        "broken_at_row": broken_at_row,
        "total_records": len(_audit_chain),
        "last_hash": _audit_chain[-1]["record_hash"] if _audit_chain else None,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }


def get_chain_length() -> int:
    return len(_audit_chain)
