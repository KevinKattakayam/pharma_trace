"""Tamper-evident, append-only audit chain.

Design (ADR-0003):

* Each record stores ``canonical``: a deterministic JSON string of the bound fields.
  ``record_hash = sha256(previous_hash + canonical)``. Verification recomputes from the
  stored string, so what was hashed is exactly what is checked (audit R6).
* Large/variable detail (evidence lists, batch items) is bound through ``payload_digest``
  inside the canonical string, so it cannot be altered without breaking the chain.
* ``recorded_at`` is server time. A client-claimed time (offline sync) is kept as
  ``client_reported_at`` and never replaces it (audit S14).
* Appends are serialised: an ``asyncio.Lock`` locally; in Postgres the
  ``append_audit_record`` function takes an advisory lock and a UNIQUE(previous_hash)
  constraint makes forks impossible even across processes.
* Persistence failures raise :class:`AuditWriteError`. A hash is never returned for a
  record that was not stored (audit headline 1).

This is *tamper-evidence*, not immutability: someone with database superuser access can
rewrite the whole chain. Anchor ``last_hash`` externally (e.g. daily signed export) for
stronger guarantees.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from models.exceptions import DatabaseWriteError, PharmaTraceDataError
from services.supabase import get_supabase

logger = structlog.get_logger()

TABLE = "audit_chain"
GENESIS_HASH = hashlib.sha256(b"PHARMATRACE_GENESIS").hexdigest()
CANONICAL_VERSION = 2
# Fields copied verbatim into the canonical record when present.
BOUND_FIELDS = (
    "event_type", "method", "verdict", "confidence", "drug", "barcode", "batch_number",
    "source", "actor", "actor_role", "clinic_id", "client_reported_at", "verification_scope",
)
_lock = asyncio.Lock()


class AuditWriteError(PharmaTraceDataError):
    """The audit record could not be durably stored."""


def _digest(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def compute_hash(previous_hash: str, canonical: str) -> str:
    return hashlib.sha256((previous_hash + canonical).encode()).hexdigest()


def build_canonical(verification_id: str, record_data: dict[str, Any], recorded_at: str) -> str:
    bound = {k: record_data[k] for k in BOUND_FIELDS if record_data.get(k) is not None}
    details = {k: v for k, v in record_data.items() if k not in BOUND_FIELDS}
    canonical = {
        "v": CANONICAL_VERSION,
        "verification_id": verification_id,
        "recorded_at": recorded_at,
        **bound,
        "payload_digest": _digest(details) if details else None,
    }
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)


async def add_audit_record(verification_id: str, record_data: dict[str, Any]) -> dict[str, Any]:
    """Append a record and return the stored row (including ``audit_hash``).

    Raises :class:`AuditWriteError` if the record could not be persisted.
    """
    record_data = dict(record_data)
    if "verified_at" in record_data:  # legacy key: client-supplied, never authoritative
        record_data.setdefault("client_reported_at", record_data.pop("verified_at"))
    record_data.setdefault("event_type", "verification")
    recorded_at = datetime.now(timezone.utc).isoformat()
    canonical = build_canonical(verification_id, record_data, recorded_at)
    db = get_supabase()

    try:
        if db.cloud_available:
            row = await db.rpc(
                "append_audit_record",
                {"p_verification_id": verification_id, "p_event_type": record_data["event_type"], "p_canonical": canonical},
            )
            row = row[0] if isinstance(row, list) and row else row
            if not row or not row.get("record_hash"):
                raise AuditWriteError("append_audit_record returned no row")
        else:
            async with _lock:
                last = await db.query(TABLE, limit=1, order_desc=True)
                previous_hash = last[0]["record_hash"] if last else GENESIS_HASH
                row = await db.insert(
                    TABLE,
                    {
                        "verification_id": verification_id,
                        "event_type": record_data["event_type"],
                        "previous_hash": previous_hash,
                        "record_hash": compute_hash(previous_hash, canonical),
                        "canonical": canonical,
                        "created_at": recorded_at,
                    },
                )
    except AuditWriteError:
        raise
    except (PharmaTraceDataError, DatabaseWriteError) as exc:
        logger.error("audit_write_failed", verification_id=verification_id, error=str(exc))
        raise AuditWriteError(str(exc)) from exc

    return {**row, "audit_hash": row["record_hash"], "recorded_at": recorded_at}


async def try_add_audit_record(verification_id: str, record_data: dict[str, Any]) -> dict[str, Any] | None:
    """Like :func:`add_audit_record` but returns ``None`` on failure (caller must surface it)."""
    try:
        return await add_audit_record(verification_id, record_data)
    except AuditWriteError:
        return None


async def _ordered_records(limit: int) -> list[dict[str, Any]]:
    db = get_supabase()
    if db.cloud_available:
        return await db.query(TABLE, limit=limit, order_by="id", order_desc=False)
    return await db.query(TABLE, limit=limit)  # local store returns insertion order


async def verify_chain(limit: int = 100_000) -> dict[str, Any]:
    """Recompute every link. Reports the first broken record, if any."""
    records = await _ordered_records(limit)
    broken_at: Any = None
    reason = None
    prev = GENESIS_HASH
    for rec in records:
        if rec.get("previous_hash") != prev:
            broken_at, reason = rec.get("id"), "previous_hash does not match preceding record"
            break
        canonical = rec.get("canonical")
        if not canonical:
            broken_at, reason = rec.get("id"), "record has no canonical payload (legacy/unverifiable)"
            break
        if compute_hash(prev, canonical) != rec.get("record_hash"):
            broken_at, reason = rec.get("id"), "record_hash does not match canonical payload"
            break
        prev = rec["record_hash"]
    return {
        "chain_valid": broken_at is None,
        "broken_at_row": broken_at,
        "reason": reason,
        "total_records": len(records),
        "last_hash": records[-1].get("record_hash") if records else None,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "truncated": len(records) >= limit,
    }


async def list_records(limit: int = 50) -> list[dict[str, Any]]:
    rows = await _ordered_records(100_000)
    out = []
    for r in rows[-limit:]:
        try:
            body = json.loads(r.get("canonical") or "{}")
        except json.JSONDecodeError:
            body = {}
        out.append({"id": r.get("id"), "record_hash": r.get("record_hash"), "previous_hash": r.get("previous_hash"),
                    "_canonical": r.get("canonical"), **body})
    return out


async def get_chain_length() -> int:
    return len(await _ordered_records(100_000))
