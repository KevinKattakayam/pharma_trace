"""
Doctor Directory router — find nearby verified medical professionals.
In production: backed by Supabase PostGIS `nearby_doctors` function.
In development: in-memory store populated by user submissions.
"""
import uuid
import math
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/doctors", tags=["doctors"])

# In-memory doctors store
_doctors: list[dict] = []


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
    radius_km = radius / 1000
    nearby = []

    for d in _doctors:
        dist = _haversine_km(lat, lng, d.get("lat", 0), d.get("lng", 0))
        if dist <= radius_km:
            nearby.append({
                **d,
                "distance_m": round(dist * 1000)
            })

    nearby.sort(key=lambda x: x.get("distance_m", 999999))
    return {"doctors": nearby, "total": len(nearby), "radius_m": radius}


@router.post("/register")
async def register_doctor(name: str, specialty: str, address: str, lat: float, lng: float,
                          city: str = "", country: str = "", contact_number: str = "",
                          registration_number: str = "", accepts_digital: bool = True):
    """Register a new doctor to the directory."""
    doctor = {
        "id": str(uuid.uuid4()),
        "name": name,
        "specialty": specialty,
        "address": address,
        "lat": lat,
        "lng": lng,
        "city": city,
        "country": country,
        "contact_number": contact_number,
        "registration_number": registration_number,
        "accepts_digital_prescriptions": accepts_digital,
        "trust_score": 100.0
    }
    _doctors.append(doctor)
    return {"doctor": doctor, "status": "registered"}
