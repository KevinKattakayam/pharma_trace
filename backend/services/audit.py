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
GENESIS_HASH = "0" * 64  # Genesis block hash


def compute_hash(previous_hash: str, record_data: dict) -> str:
    """Compute SHA-256 hash of previous hash + record data."""
    payload = previous_hash + json.dumps(record_data, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def add_audit_record(verification_id: str, record_data: dict) -> dict:
    """Add a new record to the hash chain."""
    previous_hash = _audit_chain[-1]["record_hash"] if _audit_chain else GENESIS_HASH

    record_hash = compute_hash(previous_hash, record_data)

    record = {
        "id": len(_audit_chain) + 1,
        "verification_id": verification_id,
        "record_hash": record_hash,
        "previous_hash": previous_hash,
        "record_data": record_data,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    _audit_chain.append(record)
    return record


def verify_chain() -> dict:
    """Verify the integrity of the entire audit chain."""
    if not _audit_chain:
        return {
            "chain_valid": True,
            "total_records": 0,
            "last_hash": None,
            "checked_at": datetime.now(timezone.utc).isoformat()
        }

    valid = True
    for i, record in enumerate(_audit_chain):
        expected_prev = _audit_chain[i - 1]["record_hash"] if i > 0 else GENESIS_HASH
        if record["previous_hash"] != expected_prev:
            valid = False
            break

        expected_hash = compute_hash(record["previous_hash"], record["record_data"])
        if record["record_hash"] != expected_hash:
            valid = False
            break

    return {
        "chain_valid": valid,
        "total_records": len(_audit_chain),
        "last_hash": _audit_chain[-1]["record_hash"] if _audit_chain else None,
        "checked_at": datetime.now(timezone.utc).isoformat()
    }


def get_chain_length() -> int:
    return len(_audit_chain)
