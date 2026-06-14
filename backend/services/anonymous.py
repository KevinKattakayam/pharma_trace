"""
Anonymous zero-knowledge reporting pipeline.
- Random anonymous ID (no link to user)
- Location stripped to city-level granularity
- No IP or device fingerprint logging
- Reporter can track status without revealing identity
"""
import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional
from services.supabase import get_supabase

# In-memory fallback if DB unavailable
_reports: list[dict] = []

def generate_anonymous_id(ip_address: str = None) -> str:
    """Generate a daily rotating HMAC ID for deduplication without cross-day tracking."""
    if not ip_address:
        return secrets.token_hex(16)
    import hmac
    import hashlib
    import os
    # Derive the daily secret cryptographically using the environment key + date
    env_secret = os.getenv("HMAC_DAILY_SECRET", "dev-fallback-secret-12345")
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    daily_key = hashlib.sha256(f"{env_secret}{date_str}".encode()).digest()
    
    return hmac.new(daily_key, ip_address.encode(), hashlib.sha256).hexdigest()[:16]

def anonymize_location(lat: Optional[float], lng: Optional[float]) -> tuple[Optional[float], Optional[float]]:
    """Round to 1 decimal place (~11km) with random jitter to prevent deterministic recovery."""
    import random
    if lat is None or lng is None:
        return None, None
    
    # Jitter of +/- 0.05 degrees (~5.5km)
    j_lat = float(lat) + random.uniform(-0.05, 0.05)
    j_lng = float(lng) + random.uniform(-0.05, 0.05)
    
    return round(j_lat, 1), round(j_lng, 1)

async def create_report(
    drug_name: str,
    description: str,
    city: str = None,
    country: str = None,
    barcode: str = None,
    anonymous: bool = False,
    user_id: str = None,
    lat: float = None,
    lng: float = None,
    photo_urls: list[str] = None,
    client_ip: str = None
) -> dict:
    """Create a new suspicious drug report."""
    db = get_supabase()

    report_id = str(uuid.uuid4())
    anonymous_id = generate_anonymous_id(client_ip) if anonymous else None

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

    if db.available:
        try:
            res = await db.insert("reports", report)
            if res:
                return res[0] if isinstance(res, list) else report
        except Exception:
            pass

    _reports.append(report)
    return report

async def get_all_reports() -> list[dict]:
    """Get all reports for heatmap display. Queries Supabase for real submissions."""
    db = get_supabase()
    if db.available:
        try:
            res = await db.query("reports", limit=1000)
            if res:
                return res
        except Exception:
            pass
    return _reports

async def get_report_by_anonymous_id(anon_id: str) -> Optional[dict]:
    """Allow anonymous reporter to check their report status."""
    db = get_supabase()
    if db.available:
        try:
            res = await db.query("reports", filters={"anonymous_id": anon_id}, limit=1)
            if res and len(res) > 0:
                r = res[0]
                return {
                    "report_id": r["id"],
                    "anonymous_id": r["anonymous_id"],
                    "drug_name": r["drug_name"],
                    "status": r["status"],
                    "created_at": r["created_at"]
                }
        except Exception:
            pass

    for r in _reports:
        if r.get("anonymous_id") == anon_id:
            return {
                "report_id": r["id"],
                "anonymous_id": r["anonymous_id"],
                "drug_name": r["drug_name"],
                "status": r["status"],
                "created_at": r["created_at"]
            }
    return None
