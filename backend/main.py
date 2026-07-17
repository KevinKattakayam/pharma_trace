"""
PharmaTrace — Pharmaceutical Verification & Safety Platform
FastAPI Backend Application

Tools integrated:
- OpenFDA API (drug database, labels, recalls, adverse events)
- Open-Meteo API (cold chain weather analysis)
- LibreTranslate (free translation to 20+ languages)
- WHO GTIN / GS1 (international barcode validation)
- GPT-4o Vision (pill image analysis — optional, needs API key)
- Supabase (PostgreSQL + PostGIS — optional, for persistent storage)
- SHA-256 hash chain (immutable audit log)
- Web Speech API (voice — frontend)
- Leaflet.js + CARTO (maps — frontend)
"""
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from config import get_settings

# Import routers
from routers.verify import router as verify_router
from routers.interactions import router as interactions_router
from routers.drugs import router as drugs_router
from routers.reports import router as reports_router
from routers.pharmacies import router as pharmacies_router
from routers.caregiver import router as caregiver_router
from routers.voice import router as voice_router
from routers.cabinet import router as cabinet_router
from routers.prescription import router as prescription_router
from routers.push import router as push_router
from routers.clinic import router as clinic_router
from routers.audit_export import router as audit_export_router
from routers.pvpi import router as pvpi_router
from routers.doctors import router as doctors_router
from routers.safety_cases import router as safety_cases_router

settings = get_settings()

import structlog
import sentry_sdk

# Configure structured JSON logging
structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()

# Initialize Sentry error tracking if DSN is provided
if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=1.0,
        environment="production" if not settings.debug else "development"
    )

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="""
    PharmaTrace is an AI-powered pharmaceutical verification and safety platform.

    **Integrated APIs & Services:**
    - OpenFDA (NDC, Labels, Recalls, FAERS Adverse Events, Generics)
    - Open-Meteo (Cold chain weather monitoring)
    - LibreTranslate (Drug info translation to 20+ languages)
    - WHO GTIN/GS1 (International barcode validation & country detection)
    - GPT-4o Vision (Pill/packaging image analysis — optional)
    - Supabase PostgreSQL + PostGIS (Geospatial database — optional)

    **Features:**
    - Drug verification via barcode/NDC and image analysis
    - Multi-drug interaction scanning (20+ clinically validated pairs)
    - Plain-language side effect explainer with severity labeling
    - Dosage personalization (age, weight, kidney function)
    - Generic drug finder (same active ingredient)
    - Pharmacy trust scoring with anti-gaming ML
    - Outbreak heatmap and timeline visualization
    - Caregiver dashboard with remote monitoring
    - Immutable SHA-256 hash-chained audit log
    - Anonymous zero-knowledge reporting
    - Batch verification for health workers
    - Multi-tenant clinic admin dashboards
    - CDSCO recall feed integration
    - PvPI adverse event reporting
    - Regulatory audit chain export (CSV/PDF)
    - Open API with Python and JavaScript SDKs
    """,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Rate Limiting (SlowAPI)
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from services.limiter import limiter

app.state.limiter = limiter
from models.exceptions import DatabaseConnectionError
from fastapi.responses import JSONResponse
from fastapi import Request

@app.exception_handler(DatabaseConnectionError)
async def db_connection_error_handler(request: Request, exc: DatabaseConnectionError):
    return JSONResponse(
        status_code=503,
        content={"error": "Database service currently unreachable (offline/demo mode active)", "detail": str(exc)}
    )

app.add_middleware(SlowAPIMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import uuid
import jwt

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        uid = "anonymous"
        auth = request.headers.get("Authorization")
        if auth and auth.startswith("Bearer "):
            try:
                token = auth.split(" ")[1]
                payload = jwt.decode(
                    token,
                    settings.jwt_secret,
                    algorithms=[settings.jwt_algorithm],
                    options={"verify_exp": True, "verify_signature": True},
                )
                uid = payload.get("sub") or payload.get("user_id") or "anonymous"
            except Exception:
                pass
        
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=req_id, user_id=str(uid))
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response

app.add_middleware(RequestContextMiddleware)

class IPStrippingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Override client host to prevent IP logging/storage anywhere downstream
        if request.scope.get("client"):
            request.scope["client"] = ("127.0.0.1", request.scope["client"][1])
        # Also strip typical proxy headers that could leak IP
        headers = dict(request.scope['headers'])
        for ip_header in [b'x-forwarded-for', b'x-real-ip']:
            if ip_header in headers:
                del headers[ip_header]
        request.scope['headers'] = [(k, v) for k, v in headers.items()]
        return await call_next(request)

app.add_middleware(IPStrippingMiddleware)

# Register all routers under /api/v1
app.include_router(verify_router, prefix="/api/v1")
app.include_router(interactions_router, prefix="/api/v1")
app.include_router(drugs_router, prefix="/api/v1")
app.include_router(reports_router, prefix="/api/v1")
app.include_router(pharmacies_router, prefix="/api/v1")
app.include_router(caregiver_router, prefix="/api/v1")
app.include_router(voice_router, prefix="/api/v1")
app.include_router(cabinet_router, prefix="/api/v1")
app.include_router(prescription_router, prefix="/api/v1")
app.include_router(push_router, prefix="/api/v1")
app.include_router(clinic_router, prefix="/api/v1")
app.include_router(audit_export_router, prefix="/api/v1")
app.include_router(pvpi_router, prefix="/api/v1")
app.include_router(doctors_router, prefix="/api/v1")
app.include_router(safety_cases_router, prefix="/api/v1")


# ═══════════════════════════════════════════════════
# Health & System Endpoints
# ═══════════════════════════════════════════════════

@app.get("/api/v1/health", tags=["system"])
async def health_check(details: bool = False):
    """Fast liveness check; optional details avoid blocking deployment probes."""
    from services.audit import get_chain_length
    from services.supabase import get_supabase

    db = get_supabase()
    
    # Read database freshness timestamps
    import sqlite3
    from pathlib import Path
    
    cdsco_updated = "unknown"
    drugbank_updated = "unknown"
    data_dir = Path(__file__).parent / "data"
    
    try:
        if (data_dir / "cdsco_registry.db").exists():
            with sqlite3.connect(data_dir / "cdsco_registry.db") as conn:
                res = conn.execute("SELECT value FROM metadata WHERE key='last_updated'").fetchone()
                if res: cdsco_updated = res[0]
    except Exception:
        pass
        
    try:
        if (data_dir / "drugbank_ce.db").exists():
            with sqlite3.connect(data_dir / "drugbank_ce.db") as conn:
                res = conn.execute("SELECT value FROM metadata WHERE key='last_updated'").fetchone()
                if res: drugbank_updated = res[0]
    except Exception:
        pass

    cabinet_stats = {
        "total_medicines": 0,
        "total_members": 0,
        "last_safety_check": None
    }


@app.get("/api/v1/capabilities", tags=["system"])
async def capabilities():
    """Machine-readable feature contract for the frontend and deployment checks."""
    return {
        "verification": {
            "record_lookup": True,
            "physical_pack_authentication": bool(settings.manufacturer_verification_url),
            "requires_review_without_serial_check": True,
            "max_image_upload_bytes": settings.max_image_upload_bytes,
        },
        "clinical": {
            "interaction_provider": bool(settings.clinical_interaction_provider_url),
            "automated_dose_recommendations": False,
            "clinician_review_required": True,
        },
        "data": {
            "max_external_data_age_hours": settings.external_data_max_age_hours,
            "cdsco_registry": True,
            "regulatory_alerts": True,
        },
        "safety": {
            "unsupported_input_behavior": "review_required",
            "audit_trail": True,
            "safety_case_workflow": True,
        },
    }
    # Health probes must not wait on a remote database. Operators can explicitly
    # request details when they need live aggregate metrics.
    if details and db.cloud_available:
        try:
            mems = await db.query("family_members", limit=10000)
            if mems: cabinet_stats["total_members"] = len(mems)
            meds = await db.query("medicine_cabinet", limit=10000)
            if meds: cabinet_stats["total_medicines"] = len(meds)
            logs = await db.query("safety_check_log", limit=1, order_by="checked_at", order_desc=True)
            if logs: cabinet_stats["last_safety_check"] = logs[0].get("checked_at")
        except Exception:
            pass

    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version,
        "audit_chain_length": await get_chain_length() if details and db.cloud_available else None,
        "cabinet_stats": cabinet_stats,
        "databases": {
            "cdsco_last_updated": cdsco_updated,
            "drugbank_last_updated": drugbank_updated
        },
        "services": {
            "barcode": "local",
            "openfda": "on_demand",
            "recalls": "on_demand",
            "interactions": "configured" if settings.clinical_interaction_provider_url else "review_required",
            "manufacturer_serial": "configured" if settings.manufacturer_verification_url else "not configured",
            "groq_ai": "connected" if settings.groq_api_key else "not configured",
            "supabase": "configured" if db.cloud_available else "offline_fallback",
        }
    }

_stats_cache = {"timestamp": 0, "data": None}

@app.get("/api/v1/home/stats", tags=["system"])
async def get_home_stats():
    """Live stats for the homepage."""
    import time
    global _stats_cache
    
    if time.time() - _stats_cache["timestamp"] < 60 and _stats_cache["data"]:
        return _stats_cache["data"]

    from services.supabase import get_supabase
    db = get_supabase()
    
    stats = {
        "verifications_performed": 0,
        "counterfeits_flagged": 0,
        "active_recalls": 0
    }
    
    if db.available:
        try:
            # We fetch up to a limit and count. In a real PostgREST client, we'd use select(count=exact)
            verifs = await db.query("verifications", limit=15000)
            if verifs:
                stats["verifications_performed"] = len(verifs)
                stats["counterfeits_flagged"] = sum(1 for v in verifs if v.get("verdict") in ["counterfeit", "suspicious"])
        except Exception:
            pass
            
    _stats_cache = {"timestamp": time.time(), "data": stats}
    return stats


# ═══════════════════════════════════════════════════
# Audit Chain Endpoints
# ═══════════════════════════════════════════════════

@app.get("/api/v1/audit/verify", tags=["audit"])
async def verify_audit_chain():
    """Verify the integrity of the SHA-256 hash-chained audit log."""
    from services.audit import verify_chain
    return verify_chain()


@app.get("/api/v1/audit/log", tags=["audit"])
async def get_audit_log(limit: int = Query(50, le=200)):
    """Get audit log entries."""
    from services.audit import _audit_chain
    return {"records": _audit_chain[-limit:], "total": len(_audit_chain)}


# ═══════════════════════════════════════════════════
# Cold Chain (Open-Meteo API)
# ═══════════════════════════════════════════════════

@app.get("/api/v1/cold-chain", tags=["cold-chain"])
async def cold_chain_check(lat: float, lng: float):
    """Check drug storage conditions at a location using Open-Meteo free weather API."""
    from services.cold_chain import check_cold_chain
    return await check_cold_chain(lat, lng)


# ═══════════════════════════════════════════════════
# Translation (LibreTranslate API)
# ═══════════════════════════════════════════════════

@app.get("/api/v1/translate/languages", tags=["translation"])
async def get_languages():
    """Get all supported translation languages."""
    from services.translation import get_supported_languages
    return {"languages": get_supported_languages()}


@app.post("/api/v1/translate", tags=["translation"])
@limiter.limit("20/minute")
async def translate(request: Request, text: str, target: str, source: str = "en"):
    """Translate text to any supported language via LibreTranslate (free, no API key)."""
    from services.translation import translate_text
    translated = await translate_text(text, target, source)
    return {
        "original": text,
        "translated": translated,
        "source_language": source,
        "target_language": target
    }


# ═══════════════════════════════════════════════════
# GTIN / Barcode Validation (WHO GS1)
# ═══════════════════════════════════════════════════

@app.post("/api/v1/barcode/validate", tags=["barcode"])
@limiter.limit("60/minute")
async def validate_barcode(request: Request, barcode: str):
    """Validate a GTIN/EAN/UPC barcode using GS1 check-digit algorithm.
    Detects country of origin and extracts NDC if present."""
    from services.gtin import validate_gtin
    return validate_gtin(barcode)


@app.post("/api/v1/barcode/parse-gs1", tags=["barcode"])
@limiter.limit("60/minute")
async def parse_gs1(request: Request, data: str):
    """Parse a GS1 DataMatrix barcode — extracts GTIN, lot, expiry, serial number."""
    from services.gtin import parse_gs1_datamatrix
    return parse_gs1_datamatrix(data)


# ═══════════════════════════════════════════════════
# Vision AI (GPT-4o Vision)
# ═══════════════════════════════════════════════════

@app.post("/api/v1/vision/analyze", tags=["vision"])
@limiter.limit("10/minute")
async def analyze_image(request: Request, image: str):
    """Analyze a pill/packaging photo using GPT-4o Vision.
    Requires OPENAI_API_KEY. Returns shape, color, imprint, and suspicion level."""
    from services.vision import analyze_pill_image
    return await analyze_pill_image(image)


@app.post("/api/v1/vision/identify", tags=["vision"])
@limiter.limit("10/minute")
async def identify_pill(request: Request, description: str):
    """Identify a pill from a text description using GPT-4o.
    Example: 'small round white pill with M on one side and 523 on the other'"""
    from services.vision import analyze_pill_description
    return await analyze_pill_description(description)


# ═══════════════════════════════════════════════════
# Refill Reminders
# ═══════════════════════════════════════════════════

@app.get("/api/v1/refill/schedule", tags=["refill"])
@limiter.limit("30/minute")
async def get_refill_schedule(request: Request):
    """
    Get refill schedule based on user's scan history via VerificationRepository.
    """
    from routers.verify import verification_repo
    from datetime import datetime

    schedules = []
    seen_drugs = set()

    try:
        verifs = await verification_repo.list_all(limit=100)
        for v in verifs:
            drug = v.get("drug_info", {})
            name = drug.get("brand_name") or drug.get("generic_name") or v.get("medicine_name_resolved")
            if name and name != "unknown" and name not in seen_drugs:
                seen_drugs.add(name)
                schedules.append({
                    "drug": name,
                    "ndc": drug.get("ndc"),
                    "last_verified": str(v.get("id", ""))[:8],
                    "verified_at": v.get("created_at", datetime.now().isoformat()),
                    "confidence": v.get("confidence", 0)
                })
            if len(schedules) >= 10:
                break
    except Exception as e:
        logger.error("refill_schedule_fetch_error", error=str(e))

    return {"schedules": schedules, "total": len(schedules)}


# ═══════════════════════════════════════════════════
# OpenFDA Adverse Events (FAERS)
# ═══════════════════════════════════════════════════

@app.get("/api/v1/adverse-events/{drug_name}", tags=["adverse-events"])
@limiter.limit("30/minute")
async def get_adverse_events(request: Request, drug_name: str, limit: int = Query(10, le=50)):
    """Query FDA Adverse Event Reporting System (FAERS) for a drug."""
    from services.openfda import get_adverse_events
    events = await get_adverse_events(drug_name, limit=limit, api_key=settings.openfda_api_key)
    return {
        "drug": drug_name,
        "total_events": len(events),
        "events": events
    }


# ═══════════════════════════════════════════════════
# AI Intelligence (Groq — Llama 3.3 70B)
# ═══════════════════════════════════════════════════

@app.post("/api/v1/ai/explain-interaction", tags=["ai"])
@limiter.limit("20/minute")
async def ai_explain_interaction(request: Request, drug_a: str, drug_b: str, known_effect: str = ""):
    """Use Groq/Llama to generate a patient-friendly explanation of a drug interaction."""
    from services.groq_ai import ai_explain_interaction
    result = await ai_explain_interaction(drug_a, drug_b, known_effect)
    if result:
        return {"available": True, **result}
    return {"available": False, "reason": "Groq API key not configured or request failed"}


@app.post("/api/v1/ai/analyze-drug", tags=["ai"])
@limiter.limit("20/minute")
async def ai_analyze_drug(request: Request, drug_name: str):
    """Use Groq/Llama for comprehensive drug analysis (food interactions, timing, storage)."""
    from services.groq_ai import ai_analyze_drug
    result = await ai_analyze_drug(drug_name)
    if result:
        return {"available": True, **result}
    return {"available": False, "reason": "Groq API key not configured or request failed"}


# ═══════════════════════════════════════════════════
# LangGraph Agent Pipeline
# ═══════════════════════════════════════════════════

@app.post("/api/v1/agents/verify", tags=["agents"])
@limiter.limit("10/minute")
async def agent_verify(request: Request, barcode: str, drug_names: list[str] = Query(default=[]),
                        patient_age: int = None, patient_weight: float = None,
                        kidney_function: str = None):
    """
    Run the full 6-agent LangGraph verification pipeline.
    Agents: Barcode → FDA Lookup → Recall Check → Interaction Scan → Safety Verdict → AI Report.
    """
    from services.langgraph_pipeline import run_full_verification
    result = await run_full_verification(
        barcode=barcode,
        drug_names=drug_names,
        patient_age=patient_age,
        patient_weight=patient_weight,
        kidney_function=kidney_function
    )
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
