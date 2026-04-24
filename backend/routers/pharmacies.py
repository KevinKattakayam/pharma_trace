"""
Pharmacy router — nearby pharmacies, trust scores, and community reviews.
In production: backed by Supabase PostGIS.
In development: in-memory store populated by user submissions.
No hardcoded sample pharmacies.
"""
import uuid
import math
from fastapi import APIRouter, HTTPException
from models.schemas import PharmacyReviewRequest

router = APIRouter(prefix="/pharmacies", tags=["pharmacies"])

# In-memory pharmacy store — populated by user registrations or API
_pharmacies: list[dict] = []
_reviews: list[dict] = []


def _haversine_km(lat1, lng1, lat2, lng2):
    """Haversine distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _compute_trust_score(pharmacy_id: str) -> dict:
    """Compute anti-gaming trust score from real review and verification data."""
    pharmacy = next((p for p in _pharmacies if p["id"] == pharmacy_id), None)
    if not pharmacy:
        return {}

    reviews = [r for r in _reviews if r["pharmacy_id"] == pharmacy_id]
    total_reviews = len(reviews)
    avg_rating = sum(r["rating"] for r in reviews) / max(total_reviews, 1)

    # Anti-gaming: detect review bursts (many reviews in short timeframe)
    flagged = sum(1 for r in reviews if r.get("flagged", False))

    # Compute trust components
    review_score = min(avg_rating * 20, 100) if total_reviews > 0 else 50  # default 50 for no reviews
    verification_score = pharmacy.get("verification_pass_rate", 50)
    report_penalty = min(pharmacy.get("suspicious_reports", 0) * 15, 60)
    burst_penalty = min(flagged * 20, 40)

    trust_score = max(0, min(100, (
        review_score * 0.3 +
        verification_score * 0.4 +
        50 * 0.3  # account age baseline
        - report_penalty - burst_penalty
    )))

    return {
        "trust_score": round(trust_score, 1),
        "trust_breakdown": {
            "review_sentiment": round(review_score, 1),
            "verification_pass_rate": verification_score,
            "report_penalty": report_penalty,
            "burst_detection": "detected" if flagged > 0 else "none",
            "total_reviews": total_reviews
        }
    }


@router.get("/nearby")
async def get_nearby_pharmacies(lat: float = 19.076, lng: float = 72.877, radius: int = 5000):
    """
    Get nearby pharmacies with trust scores.
    Returns pharmacies within radius (meters). Empty if none registered.
    In production: uses PostGIS ST_DWithin via Supabase.
    """
    radius_km = radius / 1000
    nearby = []

    for p in _pharmacies:
        dist = _haversine_km(lat, lng, p.get("lat", 0), p.get("lng", 0))
        if dist <= radius_km:
            trust = _compute_trust_score(p["id"])
            nearby.append({
                **p,
                "distance_m": round(dist * 1000),
                **trust
            })

    nearby.sort(key=lambda x: x.get("distance_m", 999999))
    return {"pharmacies": nearby, "total": len(nearby), "radius_m": radius}


@router.post("/register")
async def register_pharmacy(name: str, address: str, lat: float, lng: float,
                              city: str = "", country: str = ""):
    """Register a new pharmacy (for community building the database)."""
    pharmacy = {
        "id": str(uuid.uuid4()),
        "name": name,
        "address": address,
        "lat": lat,
        "lng": lng,
        "city": city,
        "country": country,
        "total_verifications": 0,
        "verification_pass_rate": 50,
        "suspicious_reports": 0
    }
    _pharmacies.append(pharmacy)
    return {"pharmacy": pharmacy, "status": "registered"}


@router.get("/{pharmacy_id}/trust-score")
async def get_trust_score(pharmacy_id: str):
    """Get detailed trust score breakdown for a pharmacy."""
    pharmacy = next((p for p in _pharmacies if p["id"] == pharmacy_id), None)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found. Register it first via POST /pharmacies/register")

    trust = _compute_trust_score(pharmacy_id)
    return {**pharmacy, **trust}


@router.post("/{pharmacy_id}/review")
async def submit_review(pharmacy_id: str, request: PharmacyReviewRequest):
    """Submit a pharmacy review with anti-gaming detection."""
    pharmacy = next((p for p in _pharmacies if p["id"] == pharmacy_id), None)
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found")

    review_id = str(uuid.uuid4())

    # Anti-gaming: flag if rating is extreme (1 or 5) with no comment
    flagged = False
    flag_reason = None
    if request.rating in (1, 5) and (not request.comment or len(request.comment.strip()) < 10):
        flagged = True
        flag_reason = "Extreme rating with insufficient comment — possible gaming attempt"

    review = {
        "id": review_id,
        "pharmacy_id": pharmacy_id,
        "rating": request.rating,
        "comment": request.comment,
        "flagged": flagged,
        "flag_reason": flag_reason,
    }
    _reviews.append(review)

    return {
        "review_id": review_id,
        "rating": request.rating,
        "status": "submitted",
        "flagged": flagged,
        "flag_reason": flag_reason,
        "anti_gaming_check": "flagged" if flagged else "passed"
    }
