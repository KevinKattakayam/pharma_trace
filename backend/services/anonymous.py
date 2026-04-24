"""
Anonymous zero-knowledge reporting pipeline.
- Random anonymous ID (no link to user)
- Location stripped to city-level granularity
- No IP or device fingerprint logging
- Reporter can track status without revealing identity
"""
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Optional

# In-memory report storage (replace with Supabase in production)
_reports: list[dict] = []


def generate_anonymous_id() -> str:
    """Generate a random anonymous ID with no link to the reporter."""
    return "rpt-" + uuid.uuid4().hex[:12]


def anonymize_location(lat: Optional[float], lng: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Round coordinates to ~1km granularity (city level)."""
    if lat is None or lng is None:
        return None, None
    # 0.01 degrees ≈ 1.1km at the equator
    return round(lat, 2), round(lng, 2)


def create_report(
    drug_name: str,
    description: str,
    city: str = None,
    country: str = None,
    barcode: str = None,
    anonymous: bool = False,
    user_id: str = None,
    lat: float = None,
    lng: float = None,
    photo_urls: list[str] = None
) -> dict:
    """Create a new suspicious drug report."""

    report_id = str(uuid.uuid4())
    anonymous_id = generate_anonymous_id() if anonymous else None

    # Anonymize location if requested
    if anonymous:
        lat, lng = anonymize_location(lat, lng)
        user_id = None  # Never store user ID for anonymous reports

    report = {
        "id": report_id,
        "anonymous_id": anonymous_id,
        "drug_name": drug_name,
        "barcode": barcode,
        "description": description,
        "city": city,
        "country": country,
        "lat": lat,
        "lng": lng,
        "photo_urls": photo_urls or [],
        "status": "pending",
        "user_id": user_id if not anonymous else None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    _reports.append(report)
    return report


def get_all_reports() -> list[dict]:
    """Get all reports for heatmap display."""
    return _reports


def get_report_by_anonymous_id(anon_id: str) -> Optional[dict]:
    """Allow anonymous reporter to check their report status."""
    for r in _reports:
        if r.get("anonymous_id") == anon_id:
            # Return only non-identifying fields
            return {
                "report_id": r["id"],
                "anonymous_id": r["anonymous_id"],
                "drug_name": r["drug_name"],
                "status": r["status"],
                "created_at": r["created_at"]
            }
    return None
