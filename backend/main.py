"""PharmaTrace API: medicine verification and safety platform (FastAPI).

Important: nothing this API returns proves a medicine is genuine unless an authoritative
manufacturer/distributor serial check confirms it, and nothing here is a diagnosis or a
prescription. See docs/SAFETY.md.
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import sentry_sdk
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from config import get_settings
from dependencies import require_current_user, require_role
from models.exceptions import DatabaseConnectionError, DatabaseReadError, DatabaseWriteError
from models.schemas import CurrentUser
from routers.audit_export import router as audit_export_router
from routers.cabinet import router as cabinet_router
from routers.caregiver import router as caregiver_router
from routers.clinic import router as clinic_router
from routers.doctors import router as doctors_router
from routers.drugs import router as drugs_router
from routers.interactions import router as interactions_router
from routers.pharmacies import router as pharmacies_router
from routers.prescription import router as prescription_router
from routers.push import router as push_router
from routers.pvpi import router as pvpi_router
from routers.reports import router as reports_router
from routers.safety_cases import router as safety_cases_router
from routers.safety_intel import router as safety_intel_router
from routers.verify import router as verify_router
from routers.voice import router as voice_router
from services import tasks
from services.limiter import limiter
from services.security import bearer_token, client_ip, decode_token, pseudonymise, subject_of

settings = get_settings()
DATA_DIR = Path(__file__).parent / "data"

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()


def _scrub_event(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any]:
    """Drop request bodies, cookies and auth headers before anything reaches Sentry (audit S18)."""
    req = event.get("request") or {}
    req.pop("data", None)
    req.pop("cookies", None)
    headers = req.get("headers") or {}
    for h in list(headers):
        if h.lower() in ("authorization", "cookie", "x-cron-secret", "x-forwarded-for", "x-real-ip"):
            headers[h] = "[redacted]"
    event.pop("user", None)
    return event


if settings.sentry_dsn:
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.environment,
        send_default_pii=False,
        before_send=_scrub_event,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.feature_batch_alerts:
        from services.batch_alerts import load_index
        idx = load_index()
        from services.batch_alerts import assert_no_sample_data
        assert_no_sample_data(idx, strict=settings.is_strict)
    if settings.feature_price_check:
        from services.price_check import load_index as load_prices
        prices = load_prices()
        if settings.is_strict and prices.coverage()["is_sample_data"]:
            raise RuntimeError("Refusing to start: SAMPLE ceiling-price data is loaded in staging/prod.")
        logger.info("ceiling_prices_loaded", **{k: v for k, v in prices.coverage().items() if k in ("status", "records", "is_sample_data")})
        logger.info("batch_alerts_loaded", **{k: v for k, v in idx.coverage().items() if k in ("status", "records", "is_sample_data")})
    logger.info("startup", environment=settings.environment, version=settings.app_version)
    yield
    abandoned = await tasks.drain(grace_period=10)
    from services.supabase import get_supabase
    await get_supabase().aclose()
    logger.info("shutdown", abandoned_background_tasks=abandoned)


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "Medicine verification and safety API for India and global users.\n\n"
        "**Safety scope.** A barcode, registry, OCR or AI result shows that a *record* exists or that "
        "a label is internally consistent; it is never proof that a physical pack is genuine. Only an "
        "authoritative manufacturer/distributor serial check can yield `authentic`/`counterfeit`. "
        "Clinical content is informational and requires professional review."
    ),
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan,
)


# ─────────────────────────── pure-ASGI middleware ───────────────────────────
class PrivacyMiddleware:
    """Derive a keyed, daily-rotating client pseudonym for rate limiting, then remove the IP
    and forwarding headers so nothing downstream can log or store it (audit S5)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            req = Request(scope)
            scope.setdefault("state", {})["client_key"] = pseudonymise(client_ip(req), purpose="ratelimit")
            if scope.get("client"):
                scope["client"] = None  # no IP (real or placeholder) reaches handlers or logs
            scope["headers"] = [(k, v) for k, v in scope["headers"] if k not in (b"x-forwarded-for", b"x-real-ip", b"forwarded")]
        await self.app(scope, receive, send)


class RequestContextMiddleware:
    """Request ID + verified user ID in structured logs; adds X-Request-ID to responses."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        req = Request(scope)
        incoming = req.headers.get("x-request-id", "")
        req_id = incoming if 8 <= len(incoming) <= 64 and incoming.replace("-", "").isalnum() else str(uuid.uuid4())
        token = bearer_token(req)
        claims = decode_token(token) if token else None
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=req_id, user_id=(subject_of(claims) if claims else None) or "anonymous", path=scope.get("path"))
        start = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)["X-Request-ID"] = req_id
                logger.info("request", method=scope.get("method"), status=message["status"], ms=round((time.perf_counter() - start) * 1000, 1))
            await send(message)

        await self.app(scope, receive, send_wrapper)


SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        is_docs = str(scope.get("path", "")).startswith(("/api/docs", "/api/redoc", "/openapi.json"))

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                for k, v in SECURITY_HEADERS.items():
                    if not (is_docs and k == "Content-Security-Policy"):
                        h.setdefault(k, v)
                if settings.is_strict:
                    h.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
            await send(message)

        await self.app(scope, receive, send_wrapper)


# Order: added last = outermost. Effective chain:
# CORS → SecurityHeaders → Privacy → RequestContext → SlowAPI → routes
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(PrivacyMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "If-Match", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(DatabaseConnectionError)
@app.exception_handler(DatabaseReadError)
@app.exception_handler(DatabaseWriteError)
async def db_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.error("database_error", error=str(exc))
    return JSONResponse(status_code=503, content={"error": "DATABASE_UNAVAILABLE", "detail": "The database is temporarily unavailable. Please retry."})


for r in (
    verify_router, interactions_router, drugs_router, reports_router, pharmacies_router, caregiver_router,
    voice_router, cabinet_router, prescription_router, push_router, clinic_router, audit_export_router,
    pvpi_router, doctors_router, safety_cases_router, safety_intel_router,
):
    app.include_router(r, prefix="/api/v1")


# ─────────────────────────── system ───────────────────────────
def _db_last_updated(name: str) -> str:
    path = DATA_DIR / name
    if not path.exists():
        return "missing"
    try:
        with sqlite3.connect(path) as conn:
            row = conn.execute("SELECT value FROM metadata WHERE key='last_updated'").fetchone()
            return row[0] if row else "unknown"
    except sqlite3.Error:
        return "unreadable"


@app.get("/api/v1/health", tags=["system"])
async def health_check() -> dict[str, Any]:
    """Liveness: the process is up. Cheap; never touches remote services."""
    return {"status": "ok", "service": settings.app_name, "version": settings.app_version}


@app.get("/api/v1/ready", tags=["system"])
async def readiness() -> JSONResponse:
    """Readiness: dependencies needed to serve traffic are usable."""
    from services.supabase import get_supabase

    checks: dict[str, Any] = {}
    db = get_supabase()
    try:
        await db.query("audit_chain", limit=1)
        checks["database"] = "ok" if db.cloud_available else "ok (local store)"
    except (DatabaseReadError, DatabaseConnectionError) as exc:
        checks["database"] = f"error: {exc}"[:200]
    checks["cdsco_registry"] = _db_last_updated("cdsco_registry.db")
    if settings.feature_batch_alerts:
        from services.batch_alerts import get_index
        cov = get_index().coverage()
        checks["batch_alerts"] = {"status": cov["status"], "latest_month": cov["latest_month"], "is_sample_data": cov["is_sample_data"]}
    ok = str(checks["database"]).startswith("ok")
    return JSONResponse(status_code=200 if ok else 503, content={"status": "ready" if ok else "not_ready", "checks": checks})


@app.get("/api/v1/capabilities", tags=["system"])
async def capabilities() -> dict[str, Any]:
    """Machine-readable feature contract for the frontend and deployment checks."""
    return {
        "api_version": "v1",
        "verification": {
            "record_lookup": True,
            "physical_pack_authentication": bool(settings.manufacturer_verification_url),
            "requires_review_without_serial_check": True,
            "max_image_upload_bytes": settings.max_image_upload_bytes,
            "supported_codes": ["GTIN/EAN/UPC", "NDC", "GS1 DataMatrix/HRI/Digital Link", "India GSR 823(E) QR"],
        },
        "clinical": {
            "interaction_provider": bool(settings.clinical_interaction_provider_url),
            "automated_dose_recommendations": False,
            "clinician_review_required": True,
        },
        "data": {"max_external_data_age_hours": settings.external_data_max_age_hours, "cdsco_registry": True, "regulatory_alerts": True},
        "features": {
            "price_check": settings.feature_price_check,
            "pack_check": settings.feature_pack_check,
            "batch_alerts": settings.feature_batch_alerts,
            "lasa_guard": settings.feature_lasa_guard,
        },
        "safety": {"unsupported_input_behavior": "review_required", "audit_trail": True, "safety_case_workflow": True},
    }


_stats_cache: dict[str, Any] = {"timestamp": 0.0, "data": None}


@app.get("/api/v1/home/stats", tags=["system"])
async def get_home_stats() -> dict[str, Any]:
    """Aggregate counts for the home page (cached 60 s). 'flagged' = suspicious or counterfeit verdicts."""
    if time.time() - _stats_cache["timestamp"] < 60 and _stats_cache["data"]:
        return _stats_cache["data"]
    from services.supabase import get_supabase
    stats = {"verifications_performed": 0, "counterfeits_flagged": 0, "active_recalls": 0}
    try:
        rows = await get_supabase().query("verifications", select="verdict,has_recall", limit=20000)
        stats["verifications_performed"] = len(rows)
        stats["counterfeits_flagged"] = sum(1 for v in rows if v.get("verdict") in ("counterfeit", "suspicious"))
    except (DatabaseReadError, DatabaseConnectionError) as exc:
        logger.warning("home_stats_unavailable", error=str(exc))
    _stats_cache.update(timestamp=time.time(), data=stats)
    return stats


# ─────────────────────────── audit (restricted) ───────────────────────────
@app.get("/api/v1/audit/verify", tags=["audit"])
async def verify_audit_chain(_user: CurrentUser = Depends(require_role("auditor", "regulator"))) -> dict[str, Any]:
    """Recompute the full hash chain and report the first broken link, if any."""
    from services.audit import verify_chain
    return await verify_chain()


@app.get("/api/v1/audit/log", tags=["audit"])
async def get_audit_log(limit: int = Query(50, ge=1, le=200), _user: CurrentUser = Depends(require_role("auditor", "regulator"))) -> dict[str, Any]:
    from services.audit import get_chain_length, list_records
    return {"records": await list_records(limit), "total": await get_chain_length()}


# ─────────────────────────── utilities ───────────────────────────
@app.get("/api/v1/cold-chain", tags=["cold-chain"])
@limiter.limit("30/minute")
async def cold_chain_check(request: Request, lat: float = Query(..., ge=-90, le=90), lng: float = Query(..., ge=-180, le=180)):
    """Local weather vs. labelled storage range (context only; not product handling history)."""
    from services.cold_chain import check_cold_chain
    return await check_cold_chain(lat, lng)


@app.get("/api/v1/translate/languages", tags=["translation"])
async def get_languages():
    from services.translation import get_supported_languages
    return {"languages": get_supported_languages()}


@app.post("/api/v1/translate", tags=["translation"])
@limiter.limit("20/minute")
async def translate(request: Request, text: str = Query(..., max_length=2000), target: str = Query(..., max_length=10), source: str = Query("en", max_length=10)):
    """Machine translation. Output is unverified; clinical text should be checked by a fluent reviewer."""
    from services.translation import translate_text
    translated = await translate_text(text, target, source)
    return {"original": text, "translated": translated, "source_language": source, "target_language": target, "machine_translated": True}


@app.post("/api/v1/barcode/validate", tags=["barcode"])
@limiter.limit("60/minute")
async def validate_barcode(request: Request, barcode: str = Query(..., max_length=64)):
    """GTIN/EAN/UPC structure and check-digit validation (not an authenticity check)."""
    from services.gtin import validate_gtin
    return validate_gtin(barcode)


@app.post("/api/v1/barcode/parse-gs1", tags=["barcode"])
@limiter.limit("60/minute")
async def parse_gs1(request: Request, data: str = Query(..., max_length=512)):
    """Parse GS1 element strings / HRI / Digital Link (GTIN, batch, expiry, serial)."""
    from services.gtin import parse_gs1_datamatrix
    return parse_gs1_datamatrix(data)


@app.post("/api/v1/vision/analyze", tags=["vision"])
@limiter.limit("10/minute")
async def analyze_image(request: Request, image: str = Query(..., max_length=7_000_000)):
    from services.vision import analyze_pill_image
    return {**(await analyze_pill_image(image)), "ai_generated": True, "requires_human_review": True}


@app.post("/api/v1/vision/identify", tags=["vision"])
@limiter.limit("10/minute")
async def identify_pill(request: Request, description: str = Query(..., max_length=500)):
    from services.vision import analyze_pill_description
    return {**(await analyze_pill_description(description)), "ai_generated": True, "requires_human_review": True}


@app.get("/api/v1/refill/schedule", tags=["refill"])
@limiter.limit("30/minute")
async def get_refill_schedule(request: Request, user: CurrentUser = Depends(require_current_user)):
    """The caller's recently verified medicines (previously returned every user's scans)."""
    from routers.verify import verification_repo
    schedules, seen = [], set()
    for v in await verification_repo.list_by_user(user.user_id, limit=100):
        name = v.get("brand_name") or v.get("generic_name")
        if name and name not in seen:
            seen.add(name)
            schedules.append({"drug": name, "ndc": v.get("ndc"), "verification_id": v.get("id"), "verified_at": v.get("created_at")})
        if len(schedules) >= 10:
            break
    return {"schedules": schedules, "total": len(schedules)}


@app.get("/api/v1/adverse-events/{drug_name}", tags=["adverse-events"])
@limiter.limit("30/minute")
async def get_adverse_events(request: Request, drug_name: str, limit: int = Query(10, ge=1, le=50)):
    """FAERS reports (US). Spontaneous reports do not establish that a drug caused an event."""
    from services.openfda import get_adverse_events as fetch
    events = await fetch(drug_name[:200], limit=limit, api_key=settings.openfda_api_key)
    return {"drug": drug_name, "total_events": len(events), "events": events,
            "interpretation_note": "FAERS reports are unverified and cannot establish causation or incidence."}


@app.post("/api/v1/ai/explain-interaction", tags=["ai"])
@limiter.limit("20/minute")
async def ai_explain_interaction(request: Request, drug_a: str = Query(..., max_length=120), drug_b: str = Query(..., max_length=120), known_effect: str = Query("", max_length=500)):
    from services.groq_ai import ai_explain_interaction as explain
    result = await explain(drug_a, drug_b, known_effect)
    if result:
        return {"available": True, **result, "ai_generated": True, "requires_human_review": True}
    return {"available": False, "reason": "AI provider not configured or request failed"}


@app.post("/api/v1/ai/analyze-drug", tags=["ai"])
@limiter.limit("20/minute")
async def ai_analyze_drug(request: Request, drug_name: str = Query(..., max_length=120)):
    from services.groq_ai import ai_analyze_drug as analyze
    result = await analyze(drug_name)
    if result:
        return {"available": True, **result, "ai_generated": True, "requires_human_review": True}
    return {"available": False, "reason": "AI provider not configured or request failed"}


@app.post("/api/v1/agents/verify", tags=["agents"])
@limiter.limit("10/minute")
async def agent_verify(request: Request, barcode: str = Query(..., max_length=512), drug_names: list[str] = Query(default=[]),
                       patient_age: int | None = Query(None, ge=0, le=120), patient_weight: float | None = Query(None, gt=0, le=400),
                       kidney_function: str | None = Query(None, max_length=20)):
    """Multi-step LangGraph pipeline. AI-assisted; never a dosing instruction."""
    if len(drug_names) > 10:
        raise HTTPException(status_code=422, detail="At most 10 drug names")
    from services.langgraph_pipeline import run_full_verification
    return await run_full_verification(barcode=barcode, drug_names=drug_names, patient_age=patient_age,
                                       patient_weight=patient_weight, kidney_function=kidney_function)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=settings.environment == "dev")
