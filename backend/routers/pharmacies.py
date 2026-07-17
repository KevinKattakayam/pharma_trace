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
from services.supabase import get_supabase

router = APIRouter(prefix="/pharmacies", tags=["pharmacies"])


def _haversine_km(lat1, lng1, lat2, lng2):
    """Haversine distance in km between two coordinates."""
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


async def _compute_trust_score(pharmacy_id: str) -> dict:
    """Compute anti-gaming trust score from real review and verification data in Supabase with TTL caching and parallel batching."""
    from services.supabase import get_supabase
    from services.cache_manager import get_cache
    import math
    from datetime import datetime, timezone, timedelta
    import asyncio
    
    cache = get_cache()
    cache_key = f"trust_score:{pharmacy_id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    db = get_supabase()
    reviews = await db.query("pharmacy_reviews", filters={"pharmacy_id": pharmacy_id}, limit=500)
    if not reviews:
        reviews = []
        
    # Sort reviews by created_at ascending for burst detection
    reviews = sorted(reviews, key=lambda x: x.get("created_at", ""))
        
    now = datetime.now(timezone.utc)
    valid_reviews = []
    flagged_reviews_to_insert = []
    
    # Parallel batch fetch user account history to eliminate N+1 sequential loop queries
    unique_users = {r.get("user_id") for r in reviews if r.get("user_id")}
    user_history_map = {}
    if unique_users:
        user_list = list(unique_users)
        verif_results = await asyncio.gather(*[
            db.query("safety_check_log", filters={"user_id": uid}, limit=3) for uid in user_list
        ], return_exceptions=True)
        for uid, res in zip(user_list, verif_results):
            user_history_map[uid] = len(res) if isinstance(res, list) else 3
    
    for r in reviews:
        suspicious = False
        reason = ""
        
        user_id = r.get("user_id")
        if user_id:
            verif_count = user_history_map.get(user_id, 3)
            if verif_count < 3:
                suspicious = True
                reason = "Low account history (<3 verifications)"
                
        r_time_str = r.get("created_at")
        if r_time_str and not suspicious:
            try:
                r_dt = datetime.fromisoformat(r_time_str.replace("Z", "+00:00"))
                window_start = r_dt - timedelta(hours=1)
                burst_count = 0
                for prev in valid_reviews[-10:]:
                    if prev.get("created_at"):
                        p_dt = datetime.fromisoformat(prev["created_at"].replace("Z", "+00:00"))
                        if p_dt > window_start:
                            burst_count += 1
                if burst_count >= 5:
                    suspicious = True
                    reason = "Review burst (>5 in 1 hour)"
            except ValueError:
                pass
                
        if suspicious:
            if not r.get("flagged"):
                flagged_reviews_to_insert.append({
                    "review_id": r.get("id"),
                    "pharmacy_id": pharmacy_id,
                    "reason": reason,
                    "flagged_at": now.isoformat()
                })
        else:
            valid_reviews.append(r)
            
    if flagged_reviews_to_insert:
        try:
            asyncio.create_task(db.insert_many("flagged_reviews", flagged_reviews_to_insert))
        except Exception: pass
        
    local_verifications = await db.query("safety_check_log", filters={"pharmacy_id": pharmacy_id}, limit=100)
    pass_rate_score = 0
    if local_verifications:
        passed = sum(1 for v in local_verifications if v.get("verdict") == "authentic")
        pass_rate_score = (passed / len(local_verifications)) * 50
        
    review_score = min(math.log10(max(len(valid_reviews), 1)) * 15, 30)
    
    recency_boost = 0
    last_activity = None
    if valid_reviews:
        r_str = valid_reviews[-1].get("created_at")
        if r_str: last_activity = datetime.fromisoformat(r_str.replace("Z", "+00:00"))
    if local_verifications:
        v_str = local_verifications[0].get("created_at")
        if v_str:
            v_dt = datetime.fromisoformat(v_str.replace("Z", "+00:00"))
            if not last_activity or v_dt > last_activity:
                last_activity = v_dt
                
    if last_activity:
        days_since = (now - last_activity).days
        if days_since <= 14:
            recency_boost = 20 * (1 - (days_since / 14))
            
    trust_score = pass_rate_score + review_score + recency_boost
    
    res = {
        "trust_score": round(trust_score, 1),
        "trust_breakdown": {
            "pass_rate_score": round(pass_rate_score, 1),
            "review_volume_score": round(review_score, 1),
            "recency_boost": round(recency_boost, 1),
            "valid_reviews": len(valid_reviews),
            "flagged_reviews": len(reviews) - len(valid_reviews)
        }
    }
    await cache.set(cache_key, res, ttl_seconds=900)
    return res


@router.get("/nearby")
async def get_nearby_pharmacies(lat: float = 19.076, lng: float = 72.877, radius: int = 5000):
    """
    Get nearby pharmacies with trust scores.
    Returns pharmacies within radius (meters). Empty if none registered.
    In production: uses PostGIS ST_DWithin via Supabase.
    """
    import asyncio
    db = get_supabase()
    radius_km = radius / 1000
    
    # Use the geo_query wrapper
    nearby_raw = await db.geo_query("pharmacies", lat, lng, radius)
    nearby = []

    # Compute all trust scores concurrently using asyncio.gather
    trust_scores = await asyncio.gather(*[_compute_trust_score(p["id"]) for p in nearby_raw], return_exceptions=True)

    for p, trust in zip(nearby_raw, trust_scores):
        dist = p.get("distance_m")
        if dist is None:
            dist_km = _haversine_km(lat, lng, p.get("lat", 0), p.get("lng", 0))
            dist = round(dist_km * 1000)
            
        t_data = trust if isinstance(trust, dict) else {"trust_score": 100.0, "trust_breakdown": None}
        nearby.append({
            **p,
            "distance_m": dist,
            **t_data
        })

    nearby.sort(key=lambda x: x.get("distance_m", 999999))
    return {"pharmacies": nearby, "total": len(nearby), "radius_m": radius}


@router.post("/register")
async def register_pharmacy(name: str, address: str, lat: float, lng: float,
                              city: str = "", country: str = ""):
    """Register a new pharmacy (for community building the database)."""
    db = get_supabase()
    pharmacy = {
        "id": str(uuid.uuid4()),
        "name": name,
        "address": address,
        "lat": lat,
        "lng": lng,
        "location": f"POINT({lng} {lat})",
        "city": city,
        "country": country,
        "total_verifications": 0,
        "verification_pass_rate": 50,
        "suspicious_reports": 0,
        "is_claimed": False,
        "verified_inventory": [],
        "contact_number": None
    }
    
    await db.insert("pharmacies", pharmacy)
    return {"pharmacy": pharmacy, "status": "registered"}


@router.get("/{pharmacy_id}/trust-score")
async def get_trust_score(pharmacy_id: str):
    """Get detailed trust score breakdown for a pharmacy."""
    db = get_supabase()
    pharmacy_res = await db.query("pharmacies", filters={"id": pharmacy_id}, limit=1)
    
    if not pharmacy_res:
        raise HTTPException(status_code=404, detail="Pharmacy not found. Register it first via POST /pharmacies/register")

    pharmacy = pharmacy_res[0]
    trust = await _compute_trust_score(pharmacy_id)
    return {**pharmacy, **trust}

@router.post("/{pharmacy_id}/claim")
async def claim_pharmacy(pharmacy_id: str, contact_number: str, license_number: str = ""):
    """
    Request to claim a pharmacy listing.
    Creates a pending claim that must be verified by a clinic admin before going live.
    """
    db = get_supabase()
    pharmacy_res = await db.query("pharmacies", filters={"id": pharmacy_id}, limit=1)
    
    if not pharmacy_res:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
        
    pharmacy = pharmacy_res[0]
    claim_status = pharmacy.get("claim_status")
    if claim_status == "verified":
        raise HTTPException(status_code=400, detail="Pharmacy is already claimed and verified")
    if claim_status == "pending":
        raise HTTPException(status_code=400, detail="A claim is already pending review for this pharmacy")

    updates = {
        "claim_status": "pending",
        "contact_number": contact_number,
        "license_number": license_number,
        "is_claimed": False
    }

    await db.update("pharmacies", updates, filters={"id": pharmacy_id})

    return {
        "status": "pending",
        "message": "Claim submitted for verification. A clinic administrator will review your license and contact details before the listing goes live.",
        "pharmacy_id": pharmacy_id
    }


@router.post("/{pharmacy_id}/verify-claim")
async def verify_claim(pharmacy_id: str):
    """
    Admin-only: Approve a pending pharmacy claim.
    In production this must be gated behind Depends(get_current_user) with admin role check.
    """
    db = get_supabase()
    pharmacy_res = await db.query("pharmacies", filters={"id": pharmacy_id}, limit=1)
    
    if not pharmacy_res:
        raise HTTPException(status_code=404, detail="Pharmacy not found")

    pharmacy = pharmacy_res[0]
    if pharmacy.get("claim_status") != "pending":
        raise HTTPException(status_code=400, detail="No pending claim to verify")

    updates = {
        "claim_status": "verified",
        "is_claimed": True
    }
    
    await db.update("pharmacies", updates, filters={"id": pharmacy_id})
    pharmacy.update(updates)
    
    return {"status": "verified", "pharmacy": pharmacy}


@router.put("/{pharmacy_id}/inventory")
async def update_inventory(pharmacy_id: str, inventory: list[dict]):
    """Publish verified medicine inventory to the directory."""
    db = get_supabase()
    pharmacy_res = await db.query("pharmacies", filters={"id": pharmacy_id}, limit=1)
    
    if not pharmacy_res:
        raise HTTPException(status_code=404, detail="Pharmacy not found")
        
    pharmacy = pharmacy_res[0]
    if pharmacy.get("claim_status") != "verified":
        raise HTTPException(status_code=403, detail="Pharmacy must be claimed and verified before updating inventory")
        
    await db.update("pharmacies", {"verified_inventory": inventory}, filters={"id": pharmacy_id})
    
    return {"status": "inventory_updated", "inventory_count": len(inventory)}


@router.post("/{pharmacy_id}/review")
async def submit_review(pharmacy_id: str, request: PharmacyReviewRequest):
    """Submit a pharmacy review with anti-gaming detection."""
    db = get_supabase()
    pharmacy_res = await db.query("pharmacies", filters={"id": pharmacy_id}, limit=1)
    
    if not pharmacy_res:
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
    
    await db.insert("pharmacy_reviews", review)

    return {
        "review_id": review_id,
        "rating": request.rating,
        "status": "submitted",
        "flagged": flagged,
        "flag_reason": flag_reason,
        "anti_gaming_check": "flagged" if flagged else "passed"
    }
