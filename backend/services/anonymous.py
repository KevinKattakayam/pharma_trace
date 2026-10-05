"""
Anonymous zero-knowledge reporting pipeline via ReportRepository.
"""
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from repositories.entities import ReportRepository

repo = ReportRepository()


def generate_anonymous_id(ip_address: Optional[str] = None) -> str:
    """Random, unlinkable report token (audit S3).

    The previous HMAC(IP) design used a public default key, letting anyone recover reporters'
    IPs by enumerating the IPv4 space. The token is returned to the reporter so they can check
    status; it is not derived from anything about them. ``ip_address`` is accepted and ignored
    for backward compatibility.
    """

    return secrets.token_hex(8)


import secrets as _secrets

_rng = _secrets.SystemRandom()  # unpredictable jitter (audit: S311)


def anonymize_location(lat: Optional[float], lng: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
    """Round to 1 decimal place (~11km) with random jitter to prevent deterministic recovery."""
    import random
    if lat is None or lng is None:
        return None, None
    
    j_lat = float(lat) + _rng.uniform(-0.05, 0.05)
    j_lng = float(lng) + _rng.uniform(-0.05, 0.05)
    
    return round(j_lat, 1), round(j_lng, 1)


async def create_report(
    drug_name: str,
    description: str,
    city: Optional[str] = None,
    country: Optional[str] = None,
    barcode: Optional[str] = None,
    anonymous: bool = False,
    user_id: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    photo_urls: Optional[List[str]] = None,
    client_ip: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new suspicious drug report via ReportRepository."""
    report_id = str(uuid.uuid4())
    anonymous_id = generate_anonymous_id(client_ip) if anonymous else None

    if anonymous:
        lat, lng = anonymize_location(lat, lng)
        user_id = None

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

    try:
        created = await repo.create(report)
        return created
    except Exception:
        return report


async def get_all_reports() -> List[Dict[str, Any]]:
    """Get all reports for heatmap display via ReportRepository."""
    try:
        return await repo.list_all(limit=1000)
    except Exception:
        return []


async def get_report_by_anonymous_id(anon_id: str) -> Optional[Dict[str, Any]]:
    """Allow anonymous reporter to check their report status."""
    try:
        records = await repo.list_all(filters={"anonymous_id": anon_id}, limit=1)
        if records:
            r = records[0]
            return {
                "report_id": r.get("id"),
                "anonymous_id": r.get("anonymous_id"),
                "drug_name": r.get("drug_name"),
                "status": r.get("status"),
                "created_at": r.get("created_at")
            }
    except Exception:
        pass
    return None
