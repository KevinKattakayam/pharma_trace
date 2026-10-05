"""
Clinic Admin Router — Multi-tenant B2B dashboard for health organizations.
Provides aggregate stats, health worker activity, and clinic management endpoints.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from starlette.requests import Request

from dependencies import ensure_clinic_access, require_current_user, require_role
from models.schemas import CurrentUser
from services.limiter import limiter

router = APIRouter(prefix="/clinic", tags=["clinic"])


class ClinicCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    address: Optional[str] = Field(default=None, max_length=300)
    contact_email: str = Field(..., min_length=5, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    admin_password: str = Field(..., min_length=12, max_length=128)


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

# Precomputed hash so unknown e-mails cost the same bcrypt time as known ones (no user enumeration).
from functools import lru_cache


@lru_cache(maxsize=1)
def _dummy_hash() -> bytes:
    import bcrypt
    return bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt(rounds=12))


@router.post("/login")
@limiter.limit("5/minute")
async def clinic_login(request: Request, req: ClinicLoginRequest):
    """Authenticate a clinic administrator; issues a short-lived JWT scoped to the clinic."""
    import bcrypt
    import jwt

    from config import get_settings
    from services.supabase import get_supabase

    rows = await get_supabase().query("clinics", select="id,password_hash", filters={"contact_email": req.email.lower().strip()}, limit=1)
    stored = (rows[0].get("password_hash") if rows else None) or ""
    candidate = stored.encode() if stored.startswith("$2") else _dummy_hash()
    try:
        ok = bcrypt.checkpw(req.password.encode()[:72], candidate)
    except ValueError:
        ok = False
    if not (rows and stored.startswith("$2") and ok):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    settings = get_settings()
    now = datetime.now(timezone.utc)
    clinic_id = rows[0]["id"]
    token = jwt.encode(
        {"sub": f"clinic-admin:{clinic_id}", "role": "clinic_admin", "clinic_id": clinic_id,
         "iss": settings.jwt_issuer, "iat": now, "exp": now + timedelta(hours=settings.jwt_expiration_hours)},
        settings.jwt_secret, algorithm=settings.jwt_algorithm,
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": settings.jwt_expiration_hours * 3600, "clinic_id": clinic_id}


@router.post("/create")
async def create_clinic(req: ClinicCreateRequest, _admin: CurrentUser = Depends(require_role("admin"))):
    """Register a clinic tenant (platform admins only). Stores a bcrypt hash, never the password."""
    import uuid

    import bcrypt

    from services.supabase import get_supabase

    db = get_supabase()
    email = req.contact_email.lower().strip()
    if await db.query("clinics", select="id", filters={"contact_email": email}, limit=1):
        raise HTTPException(status_code=409, detail="A clinic with this e-mail already exists")
    clinic_id = str(uuid.uuid4())
    await db.insert("clinics", {
        "id": clinic_id, "name": req.name, "address": req.address, "contact_email": email,
        "password_hash": bcrypt.hashpw(req.admin_password.encode()[:72], bcrypt.gensalt(rounds=12)).decode(),
    })
    return {"clinic_id": clinic_id, "name": req.name, "status": "created"}


@router.get("/{clinic_id}/dashboard")
async def clinic_dashboard(clinic_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, user: CurrentUser = Depends(require_current_user)):
    """
    Aggregate stats for a clinic administrator.
    Returns: total scans this month, recall encounters, most verified drugs,
    counterfeit flag rate, and daily activity breakdown.
    Defaults to a 30-day window if dates are not provided.
    """
    ensure_clinic_access(user, clinic_id)
        
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
async def clinic_workers(clinic_id: str, from_date: Optional[str] = None, to_date: Optional[str] = None, user: CurrentUser = Depends(require_current_user)):
    """
    List health worker activity for a clinic.
    Groups verifications by user_id to show per-worker scan counts.
    Defaults to 30 days.
    """
    ensure_clinic_access(user, clinic_id)
    if False:
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
