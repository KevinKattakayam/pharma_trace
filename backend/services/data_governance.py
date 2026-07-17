"""Small, failure-tolerant provenance ledger for regulatory-data ingestion."""
from datetime import datetime, timezone
from typing import Optional


async def start_source_run(source_name: str, source_url: str, source_version: Optional[str] = None) -> Optional[str]:
    """Record an ingestion attempt. Returns None when the ledger is unavailable."""
    try:
        from services.supabase import get_supabase
        row = await get_supabase().insert("data_source_runs", {
            "source_name": source_name,
            "source_url": source_url,
            "source_version": source_version,
            "status": "running",
        })
        return row.get("id")
    except Exception:
        return None


async def finish_source_run(
    run_id: Optional[str], *, status: str, records_seen: int = 0,
    records_upserted: int = 0, error_summary: Optional[str] = None,
) -> None:
    if not run_id:
        return
    try:
        from services.supabase import get_supabase
        await get_supabase().update("data_source_runs", {
            "status": status,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "records_seen": records_seen,
            "records_upserted": records_upserted,
            "error_summary": error_summary,
        }, filters={"id": run_id})
    except Exception:
        # Ingestion must still report its own primary failure if the observability
        # store is unavailable.
        return
