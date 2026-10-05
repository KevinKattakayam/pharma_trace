"""
Doctor Directory router — find nearby verified medical professionals.
In production: backed by Supabase PostGIS `nearby_doctors` function.
In development: in-memory store populated by user submissions.
"""
import math
import uuid

from fastapi import APIRouter, HTTPException

from services.supabase import get_supabase

router = APIRouter(prefix="/doctors", tags=["doctors"])


def _haversine_km(lat1, lng1, lat2, lng2):
    """Haversine distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


@router.get("/nearby")
async def get_nearby_doctors(lat: float = 19.076, lng: float = 72.877, radius: int = 10000):
    """
    Get nearby verified doctors.
    Returns doctors within radius (meters). Empty if none registered.
    In production: uses PostGIS ST_DWithin via Supabase.
    """
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        raise HTTPException(status_code=400, detail="Invalid coordinates: latitude must be between -90 and 90, longitude between -180 and 180.")

    db = get_supabase()
    
    # Use the geo_query wrapper (handles PostGIS RPC or local Haversine fallback)
    nearby = await db.geo_query("doctors", lat, lng, radius)
    
    # If the fallback returned raw rows without distance_m (which it might if we improve the fallback)
    for d in nearby:
        if "distance_m" not in d:
            dist = _haversine_km(lat, lng, d.get("lat", 0), d.get("lng", 0))
            d["distance_m"] = round(dist * 1000)

    # Sort if not already sorted
    nearby.sort(key=lambda x: x.get("distance_m", 999999))
    return {"doctors": nearby, "total": len(nearby), "radius_m": radius}


@router.post("/register")
async def register_doctor(name: str, specialty: str, address: str, lat: float, lng: float,
                          city: str = "", country: str = "", contact_number: str = "",
                          registration_number: str = "", accepts_digital: bool = True):
    """Register a new doctor to the directory with strict geospatial and E.164 contact validation."""
    import re
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        raise HTTPException(status_code=400, detail="Invalid coordinates: latitude must be between -90 and 90, longitude between -180 and 180.")

    if contact_number:
        clean_phone = contact_number.strip()
        if re.match(r'^[6-9]\d{9}$', clean_phone):
            clean_phone = f"+91{clean_phone}"
        elif not re.match(r'^\+[1-9]\d{6,14}$', clean_phone):
            raise HTTPException(status_code=400, detail="Invalid contact number format. Use E.164 international format (e.g., +919876543210).")
        contact_number = clean_phone

    if registration_number and len(registration_number.strip()) < 4:
        raise HTTPException(status_code=400, detail="Invalid medical registration number: must be at least 4 alphanumeric characters.")

    db = get_supabase()
    doctor = {
        "id": str(uuid.uuid4()),
        "name": name.strip(),
        "specialty": specialty.strip(),
        "address": address.strip(),
        "lat": lat,
        "lng": lng,
        "location": f"POINT({lng} {lat})",
        "city": city.strip(),
        "country": country.strip() or "India",
        "contact_number": contact_number,
        "registration_number": registration_number.strip(),
        "accepts_digital_prescriptions": accepts_digital,
        "trust_score": 100.0
    }
    
    await db.insert("doctors", doctor)
    return {"doctor": doctor, "status": "registered"}
