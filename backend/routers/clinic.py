"""
Clinic Admin Router — Multi-tenant B2B dashboard for health organizations.
Provides aggregate stats, health worker activity, and clinic management endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone, timedelta
from dependencies import get_current_user

router = APIRouter(prefix="/clinic", tags=["clinic"])


class ClinicCreateRequest(BaseModel):
    name: str
    address: Optional[str] = None
    contact_email: Optional[str] = None


class ClinicStatsResponse(BaseModel):
    clinic_id: str
    clinic_name: str
    total_scans_this_month: int
    total_scans_all_time: int
    recall_encounters: int
    counterfeit_flags: int
    pass_rate: float
    top_drugs: list[dict]
    daily_activity: list[dict]

class ClinicLoginRequest(BaseModel):
    email: str
    password: str

@router.post("/login")
async def clinic_login(req: ClinicLoginRequest):
    """
    Authenticate a clinic administrator via email and password.
    Issues a JWT containing the clinic_id on success.
    """
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        # Fetch clinic by email
        results = await db.query(
            "clinics",
            select="id,password_hash",
            filters={"contact_email": req.email.lower().strip()},
            limit=1
        )
        if not results:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        clinic = results[0]
        stored_hash = clinic.get("password_hash")

        if not stored_hash:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Verify password using passlib
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            if not pwd_context.verify(req.password, stored_hash):
                raise HTTPException(status_code=401, detail="Invalid credentials")
        except ImportError:
            # Fallback if passlib isn't installed in this env yet (prevent total lockout in dev)
            if req.password != stored_hash:
                raise HTTPException(status_code=401, detail="Invalid credentials")

        import jwt
        from config import get_settings
        settings = get_settings()
        secret = getattr(settings, 'jwt_secret', 'mock_secret_key_for_development')
        
        # Issue token with 24h expiration
        from datetime import datetime, timedelta, timezone
        exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours)
        token = jwt.encode({"clinic_id": clinic["id"], "exp": exp}, secret, algorithm=settings.jwt_algorithm)
        
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Authentication failed")
@router.post("/create")
async def create_clinic(req: ClinicCreateRequest):
    """Register a new clinic in the system."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="Database not configured")

    import uuid
    clinic_id = str(uuid.uuid4())
    try:
        await db.insert("clinics", {
            "id": clinic_id,
            "name": req.name,
            "address": req.address,
            "contact_email": req.contact_email,
        })
        return {"clinic_id": clinic_id, "name": req.name, "status": "created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{clinic_id}/dashboard")
async def clinic_dashboard(clinic_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, user: dict = Depends(get_current_user)):
    """
    Aggregate stats for a clinic administrator.
    Returns: total scans this month, recall encounters, most verified drugs,
    counterfeit flag rate, and daily activity breakdown.
    Defaults to a 30-day window if dates are not provided.
    """
    if user.get("clinic_id") != clinic_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this clinic dashboard")
        
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="Database not configured")

    if not from_date:
        from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not to_date:
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        # Fetch verifications for this clinic within date range
        all_verifs = await db.query(
            "verifications", 
            filters={"clinic_id": clinic_id},
            custom_params={"created_at": [f"gte.{from_date}", f"lte.{to_date}"]},
            limit=50000
        )
        clinic_verifs = all_verifs or []

        if not clinic_verifs:
            # Try to get clinic name anyway
            clinics = await db.query("clinics", limit=100)
            clinic_obj = next((c for c in (clinics or []) if c.get("id") == clinic_id), None)
            clinic_name = clinic_obj["name"] if clinic_obj else "Unknown Clinic"
            return ClinicStatsResponse(
                clinic_id=clinic_id,
                clinic_name=clinic_name,
                total_scans_this_month=0,
                total_scans_all_time=0,
                recall_encounters=0,
                counterfeit_flags=0,
                pass_rate=0.0,
                top_drugs=[],
                daily_activity=[]
            )

        # Get clinic name
        clinics = await db.query("clinics", limit=100)
        clinic_obj = next((c for c in (clinics or []) if c.get("id") == clinic_id), None)
        clinic_name = clinic_obj["name"] if clinic_obj else "Unknown Clinic"

        # Calculate month boundary
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        this_month = []
        for v in clinic_verifs:
            try:
                created = datetime.fromisoformat(v.get("created_at", "").replace("Z", "+00:00"))
                if created >= month_start:
                    this_month.append(v)
            except (ValueError, TypeError):
                pass

        # Recall encounters
        recall_count = sum(1 for v in clinic_verifs if v.get("has_recall"))

        # Counterfeit flags
        counterfeit_count = sum(
            1 for v in clinic_verifs
            if v.get("verdict") in ("counterfeit", "suspicious")
        )

        # Pass rate
        authentic_count = sum(1 for v in clinic_verifs if v.get("verdict") == "authentic")
        pass_rate = round((authentic_count / len(clinic_verifs)) * 100, 1) if clinic_verifs else 0.0

        # Top drugs by frequency
        drug_freq = {}
        for v in clinic_verifs:
            name = v.get("brand_name") or v.get("generic_name") or v.get("ndc")
            if name:
                drug_freq[name] = drug_freq.get(name, 0) + 1
        top_drugs = sorted(
            [{"name": k, "count": v} for k, v in drug_freq.items()],
            key=lambda x: x["count"],
            reverse=True
        )[:10]

        # Daily activity for last 30 days
        daily = {}
        for v in clinic_verifs:
            try:
                created = datetime.fromisoformat(v.get("created_at", "").replace("Z", "+00:00"))
                day_key = created.strftime("%Y-%m-%d")
                daily[day_key] = daily.get(day_key, 0) + 1
            except (ValueError, TypeError):
                pass

        daily_activity = sorted(
            [{"date": k, "scans": v} for k, v in daily.items()],
            key=lambda x: x["date"]
        )[-30:]

        return ClinicStatsResponse(
            clinic_id=clinic_id,
            clinic_name=clinic_name,
            total_scans_this_month=len(this_month),
            total_scans_all_time=len(clinic_verifs),
            recall_encounters=recall_count,
            counterfeit_flags=counterfeit_count,
            pass_rate=pass_rate,
            top_drugs=top_drugs,
            daily_activity=daily_activity
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{clinic_id}/workers")
async def clinic_workers(clinic_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, user: dict = Depends(get_current_user)):
    """
    List health worker activity for a clinic.
    Groups verifications by user_id to show per-worker scan counts.
    Defaults to 30 days.
    """
    if user.get("clinic_id") != clinic_id:
        raise HTTPException(status_code=403, detail="Not authorized to view this clinic data")
        
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="Database not configured")

    if not from_date:
        from_date = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if not to_date:
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    try:
        all_verifs = await db.query(
            "verifications",
            filters={"clinic_id": clinic_id},
            custom_params={"created_at": [f"gte.{from_date}", f"lte.{to_date}"]},
            limit=50000
        )
        clinic_verifs = all_verifs or []

        # Group by source user (using method as proxy since we don't have per-user auth yet)
        worker_stats = {}
        for v in clinic_verifs:
            worker = v.get("method", "unknown")
            if worker not in worker_stats:
                worker_stats[worker] = {"method": worker, "scans": 0, "recalls": 0, "flags": 0}
            worker_stats[worker]["scans"] += 1
            if v.get("has_recall"):
                worker_stats[worker]["recalls"] += 1
            if v.get("verdict") in ("counterfeit", "suspicious"):
                worker_stats[worker]["flags"] += 1

        return {"clinic_id": clinic_id, "workers": list(worker_stats.values())}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
