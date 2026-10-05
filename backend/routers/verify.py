"""Drug verification router: barcode/QR, image, batch, offline sync.

Fixes audit findings P1, P3, P4, S2, S6, S14, S15, S16 and integrates Pack Check, regulator
batch alerts and the LASA guard. Safety invariants (tests/test_verify_router.py):

* Only an authoritative serial response can yield ``authentic`` / ``counterfeit``.
* An active recall from ANY source is never hidden by another source being unavailable.
* Unknown recall status is reported as ``inconclusive`` and never as clear.
* Every response carries ``requires_human_review=True`` unless serial-verified.
* A failed audit write is reported (``audit_status="failed"``), never faked.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.requests import Request

from config import get_settings
from dependencies import get_current_user, require_current_user
from models.schemas import (
    BarcodeVerifyRequest,
    BatchAuditRequest,
    BatchVerifyRequest,
    CurrentUser,
    EvidenceItem,
    ImageVerifyRequest,
    InteractionsPhotoRequest,
    OfflineSyncRequest,
    SymptomSafetyRequest,
    VerificationResponse,
)
from repositories.entities import VerificationRepository
from services import gs1, tasks
from services.audit import try_add_audit_record
from services.cdsco import check_cdsco_recall, lookup_indian_drug
from services.cold_chain import check_cold_chain
from services.confidence import SUSPICION_CODES, assess_verdict, compute_confidence
from services.drug_resolver import resolve_drug_name
from services.gtin import parse_cdsco_barcode, validate_gtin
from services.interactions import check_all_interactions
from services.limiter import limiter
from services.manufacturer_verification import verify_serialized_package
from services.openfda import check_drug_shortage, check_recalls, extract_openfda_info, get_drug_label, lookup_by_ndc
from services.side_effects import extract_side_effects_from_label
from services.vision import analyze_multiple_pills_image, analyze_pill_image

logger = structlog.get_logger()
router = APIRouter(prefix="/verify", tags=["verification"])
verification_repo = VerificationRepository()

PRIVILEGED_ROLES = ("admin", "regulator", "auditor")
APPROXIMATE_SOURCES = {"rxnorm_suggest", "cdsco_fuzzy", "drugbank_fuzzy", "vernacular_fuzzy", "llm"}
ANON_BATCH_LIMIT = 10


# ─────────────────────────────── pure helpers ───────────────────────────────
def merge_recall_status(fda_result: Any, cdsco_result: Any) -> tuple[str, list[dict[str, Any]]]:
    """Combine recall sources. Returns (status, active_recalls).

    status: ``active`` if any reachable source reports a recall (even if another source is
    down); ``none_found`` only if every source answered and none reported one; otherwise
    ``inconclusive``.
    """
    fda_ok = isinstance(fda_result, list) and not any(isinstance(r, dict) and r.get("error") for r in fda_result)
    fda_active = [r for r in fda_result if isinstance(r, dict) and not r.get("error")] if isinstance(fda_result, list) else []
    cdsco_ok = isinstance(cdsco_result, dict) and bool(cdsco_result.get("available"))
    recalls = list(fda_active)
    if isinstance(cdsco_result, dict) and cdsco_result.get("has_cdsco_recall"):
        recalls.append({
            "source": "CDSCO",
            "status": "Ongoing",
            "reason_for_recall": cdsco_result.get("recall_reason", "CDSCO safety alert"),
            "report_date": cdsco_result.get("recall_date"),
        })
    if recalls:
        return "active", recalls
    if fda_ok and cdsco_ok:
        return "none_found", []
    return "inconclusive", []


def _no_active_recall(status: str) -> bool | None:
    return {"active": False, "none_found": True}.get(status)


def _evidence_dump(evidence: list[EvidenceItem]) -> list[dict[str, Any]]:
    return [e.model_dump() for e in evidence]


def _looks_like_gtin(code: str) -> bool:
    return code.isdigit() and len(code) in (8, 12, 13, 14)


def _is_gs1(code: str) -> bool:
    c = code.strip()
    return c.startswith(("(01)", "]d2", "]C1", "]Q3")) or "/01/" in c or (c.startswith("01") and len(c) > 16 and not c.isdigit())


async def _audit(verification_id: str, data: dict[str, Any], user: CurrentUser | None, evidence: list[EvidenceItem] | None = None) -> tuple[str | None, str]:
    record = await try_add_audit_record(verification_id, {
        **data,
        "actor": user.user_id if user else None,
        "actor_role": user.role if user else "anonymous",
        "clinic_id": user.clinic_id if user else None,
    })
    if record is None:
        if evidence is not None:
            evidence.append(EvidenceItem(check="audit_trail", status="warn", description="This result could not be written to the audit trail. Treat it as unrecorded.", weight=0.0))
        return None, "failed"
    return record["audit_hash"], "recorded"


async def _persist(row: dict[str, Any]) -> None:
    try:
        await verification_repo.create(row)
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort; audit is the record of truth
        logger.error("verification_persist_failed", verification_id=row.get("id"), error=repr(exc))


# ─────────────────────────────── barcode core ───────────────────────────────
async def verify_barcode_core(body: BarcodeVerifyRequest, user: CurrentUser | None) -> VerificationResponse:
    settings = get_settings()
    barcode = body.barcode.strip()
    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")
    flags: list[str] = []
    evidence_extra: list[EvidenceItem] = []

    # 1. Parse: India GSR 823(E) QR → GS1 → plain GTIN/NDC/name
    qr = parse_cdsco_barcode(barcode)
    gs1_data: dict[str, Any] = {}
    gtin_result: dict[str, Any] = {}
    if qr["valid"]:
        lookup_key = qr["gtin"] or qr["brand_name"] or qr["generic_name"] or barcode
        batch_no = qr["batch_no"]
    elif _is_gs1(barcode):
        gs1_data = gs1.parse(barcode)
        lookup_key = gs1_data.get("gtin") or barcode
        batch_no = gs1_data.get("lot")
        if gs1_data.get("gtin_check_digit_valid") is False:
            flags.append("invalid_check_digit")
    else:
        gtin_result = validate_gtin(barcode)
        lookup_key = gtin_result.get("ndc_extracted") or barcode
        batch_no = None
        if _looks_like_gtin(barcode) and not gs1.gtin_check_digit_ok(barcode):
            flags.append("invalid_check_digit")
    barcode_valid = bool(qr["valid"] or gs1_data.get("valid") or gtin_result.get("valid"))
    if body.printed and body.printed.batch_no and not batch_no:
        batch_no = body.printed.batch_no

    # 2. Registry lookups (OpenFDA → CDSCO → resolver)
    ndc_result = await lookup_by_ndc(lookup_key, api_key=settings.openfda_api_key)
    if isinstance(ndc_result, dict) and ndc_result.get("error"):
        ndc_result = None
    cdsco_drug = resolved = None
    if not ndc_result:
        cdsco_drug = await lookup_indian_drug(lookup_key)
        if not cdsco_drug and " " in lookup_key and len(first := lookup_key.split()[0]) >= 4:
            cdsco_drug = await lookup_indian_drug(first)
        if not cdsco_drug:
            raw = await resolve_drug_name(lookup_key)
            if raw and raw.get("source") != "unresolved":
                resolved = raw
    registry_match = bool(ndc_result or cdsco_drug or resolved)
    approximate = bool(resolved and (resolved.get("source") in APPROXIMATE_SOURCES or float(resolved.get("confidence", 0)) < 0.95))

    if ndc_result:
        drug_info = extract_openfda_info(ndc_result)
    elif cdsco_drug:
        drug_info = {
            "brand_name": cdsco_drug.get("brand_name"), "generic_name": cdsco_drug.get("generic_name"),
            "manufacturer": cdsco_drug.get("manufacturer"), "ndc": cdsco_drug.get("ndc"),
            "product_type": None, "route": cdsco_drug.get("route"),
            "active_ingredients": cdsco_drug.get("generic_name"), "substance_name": cdsco_drug.get("generic_name"),
        }
    elif resolved:
        drug_info = {
            "brand_name": resolved.get("brand_name") or lookup_key, "generic_name": resolved.get("generic_name"),
            "manufacturer": resolved.get("manufacturer"), "ndc": str(resolved.get("rxcui") or "") or None,
            "product_type": None, "route": None,
            "active_ingredients": resolved.get("generic_name"), "substance_name": resolved.get("generic_name"),
        }
    else:
        drug_info = {
            "brand_name": qr.get("brand_name"), "generic_name": qr.get("generic_name"), "manufacturer": qr.get("manufacturer"),
            "ndc": None, "product_type": None, "route": None, "active_ingredients": None, "substance_name": qr.get("generic_name"),
        }
    # A registry miss is negative evidence only where the consulted registry is authoritative
    # for that code type: US NDC / NDC-bearing UPC-A (prefix 3) vs openFDA. For Indian and
    # other GTINs our registries have large coverage gaps, so a miss is "unknown", not suspicious.
    digits = barcode.replace("-", "")
    ndc_like = gtin_result.get("format") == "NDC" or (digits.isdigit() and (len(digits) in (10, 11) or (len(digits) == 12 and digits.startswith("3"))))
    registry_match_flag: bool | None = True if registry_match else (False if ndc_like else None)
    if not registry_match and not ndc_like:
        evidence_extra.append(EvidenceItem(check="registry_coverage", status="warn", description="Not found in the consulted registries. Their coverage of this code type is incomplete, so this is not evidence either way.", weight=0.0))
    brand = drug_info.get("brand_name") or ""
    generic = drug_info.get("substance_name") or drug_info.get("generic_name") or ""

    # 3. Recalls (FDA + CDSCO) and shortage, in parallel
    async def _no_shortage() -> dict[str, Any]:
        return {"in_shortage": False}

    fda_res, cdsco_res, shortage = await asyncio.gather(
        check_recalls(ndc=drug_info.get("ndc"), drug_name=brand or generic, api_key=settings.openfda_api_key),
        check_cdsco_recall(drug_name=brand or generic, batch_no=batch_no),
        check_drug_shortage(generic, api_key=settings.openfda_api_key) if generic else _no_shortage(),
        return_exceptions=True,
    )
    recall_status, _recalls = merge_recall_status(fda_res, cdsco_res)

    # 4. Regulator batch alerts + pack consistency (feature-flagged)
    batch_alerts = pack = None
    if settings.feature_batch_alerts:
        from services.batch_alerts import get_index
        batch_alerts = get_index().match(batch_no, brand, generic)
        flags.extend(batch_alerts["integrity_flags"])
    if settings.feature_pack_check and (qr["valid"] or gs1_data.get("gtin") or body.printed):
        from services.pack_check import check_pack
        pack = check_pack(qr_payload=barcode if (qr["valid"] or gs1_data) else None,
                          printed=body.printed.model_dump() if body.printed else None)
        flags.extend(f for f in pack["integrity_flags"] if f != "batch_alert")

    # 5. Label, side effects, cold chain
    label = await get_drug_label(ndc=drug_info.get("ndc"), drug_name=brand or generic or None, api_key=settings.openfda_api_key)
    side_effects = await extract_side_effects_from_label(label, brand or generic or lookup_key) if label else []
    cold: dict[str, Any] = {}
    cold_chain_ok = None
    if body.location:
        cold = await check_cold_chain(body.location.lat, body.location.lng, label=label)
        if cold.get("available"):
            cold_chain_ok = cold.get("ok", True)

    confidence, evidence = compute_confidence(
        barcode_valid=barcode_valid, openfda_match=registry_match, recall_status=_no_active_recall(recall_status),
        image_match=None, cold_chain_ok=cold_chain_ok,
    )
    evidence.extend(evidence_extra)

    # 6. Authoritative serial verification (only source of authentic/counterfeit)
    serial = await verify_serialized_package(
        gtin=gs1_data.get("gtin") or qr.get("gtin"), serial_number=gs1_data.get("serial_number"), lot=batch_no,
    )
    if serial.get("verified") is True:
        confidence = 100.0
        evidence.append(EvidenceItem(check="authoritative_serial", status="pass", description="Package serial confirmed by the authorised verification service.", weight=100.0))
    elif serial.get("verified") is False:
        evidence.append(EvidenceItem(check="authoritative_serial", status="fail", description="Package serial REJECTED by the authorised verification service. Do not use or dispense; escalate.", weight=100.0))
    else:
        evidence.append(EvidenceItem(check="authoritative_serial", status="warn", description="No authoritative serial check was available. This is a record match only, not proof of authenticity.", weight=0.0))
    if recall_status == "inconclusive":
        evidence.append(EvidenceItem(check="recall_coverage", status="warn", description="One or more recall sources were unavailable, so recall status is inconclusive.", weight=0.0))
    if approximate:
        evidence.append(EvidenceItem(check="name_match", status="warn", description=f"The name was matched approximately to '{brand or generic}'. Confirm the exact name on the pack.", weight=0.0))
    for code in dict.fromkeys(flags):
        evidence.append(EvidenceItem(check=code, status="fail", description=SUSPICION_CODES.get(code, code), weight=0.0))

    verdict, reasons = assess_verdict(
        serial_verification=serial.get("verified"), no_active_recall=_no_active_recall(recall_status),
        registry_match=registry_match_flag, integrity_flags=flags, confidence=confidence,
    )

    lasa = None
    if settings.feature_lasa_guard and (brand or generic):
        from services.lasa import check_name
        lasa = check_name(brand or generic, generic or None)

    # 7. Audit + persist
    verification_id = str(uuid.uuid4())
    audit_hash, audit_status = await _audit(verification_id, {
        "event_type": "verification", "method": "barcode", "verdict": verdict, "confidence": confidence,
        "drug": brand or generic or None, "barcode": barcode, "batch_number": batch_no, "source": body.source,
        "client_reported_at": body.verified_at, "verification_scope": "authoritative_serial" if serial.get("verified") is not None else "record_match_only",
        "evidence": _evidence_dump(evidence), "reasons": reasons, "recall_status": recall_status,
    }, user, evidence)
    await _persist({
        "id": verification_id, "barcode": barcode, "method": "barcode", "verdict": verdict, "confidence": confidence,
        "brand_name": brand or None, "generic_name": drug_info.get("generic_name"), "manufacturer": drug_info.get("manufacturer"),
        "ndc": drug_info.get("ndc"), "has_recall": recall_status != "none_found", "evidence": _evidence_dump(evidence),
        "audit_hash": audit_hash, "gtin_data": gtin_result or gs1_data or None,
        "temperature_c": cold.get("temperature_c"), "humidity_pct": cold.get("humidity_pct"),
        "location": body.location.wkt() if body.location else None,
        "clinic_id": user.clinic_id if user else None, "user_id": user.user_id if user else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    if settings.feature_passive_alias_learning and user and drug_info.get("generic_name") and not approximate:
        from services.vernacular_resolver import learn_from_verification
        tasks.spawn(learn_from_verification(
            query=barcode, brand_name=brand, generic_name=drug_info["generic_name"],
            active_ingredients=[drug_info["generic_name"]],
        ), name="alias_learning")

    return VerificationResponse(
        verification_id=verification_id, verdict=verdict, confidence=confidence,
        brand_name=drug_info.get("brand_name"), generic_name=drug_info.get("generic_name"),
        manufacturer=drug_info.get("manufacturer"), ndc=drug_info.get("ndc"), product_type=drug_info.get("product_type"),
        route=drug_info.get("route"), active_ingredients=drug_info.get("active_ingredients"),
        has_recall=recall_status != "none_found", recall_status=recall_status,
        evidence=evidence, side_effects=side_effects, audit_hash=audit_hash, audit_status=audit_status,
        shortage=shortage if isinstance(shortage, dict) else {"in_shortage": False},
        requires_human_review=serial.get("verified") is not True,
        verification_scope="authoritative_serial" if serial.get("verified") is not None else "record_match_only",
        data_freshness={"external_data_max_age_hours": settings.external_data_max_age_hours, "authoritative_serial_available": serial.get("available", False)},
        verdict_reasons=reasons, pack_check=pack, batch_alerts=batch_alerts, lasa=lasa, name_match_approximate=approximate,
    )


@router.post("/barcode", response_model=VerificationResponse)
@limiter.limit("30/minute")
async def verify_barcode(request: Request, body: BarcodeVerifyRequest, user: CurrentUser | None = Depends(get_current_user)):
    """Verify by barcode, GS1 DataMatrix, India GSR 823(E) QR, NDC or name."""
    return await verify_barcode_core(body, user)


# ─────────────────────────────── image ───────────────────────────────
@router.post("/image", response_model=VerificationResponse)
@limiter.limit("10/minute")
async def verify_image(request: Request, body: ImageVerifyRequest, user: CurrentUser | None = Depends(get_current_user)):
    """Identify from a pack/pill photo (OCR + optional vision AI). Always requires review."""
    settings = get_settings()
    vision = await analyze_pill_image(body.image, body.extracted_text)
    analysed = bool(vision.get("available"))
    analysis = vision.get("analysis", {}) if analysed else {}
    source_method = vision.get("source_method", "OCR")
    flags: list[str] = []

    expiry_info = None
    if body.extracted_text:
        from services.expiry import extract_expiry_date
        expiry_info = extract_expiry_date(body.extracted_text)
        if expiry_info and expiry_info.get("status") == "expired":
            flags.append("expired")

    suspicion = str(analysis.get("SUSPICION_LEVEL", analysis.get("suspicion_level", ""))).lower()
    if suspicion == "high":
        flags.append("vision_high_suspicion")

    query = body.extracted_text or analysis.get("possible_drug")
    registry_match: bool | None = None
    info: dict[str, Any] = {}
    approximate = False
    if query:
        registry_match = False
        ndc = await lookup_by_ndc(query, api_key=settings.openfda_api_key)
        if isinstance(ndc, dict) and not ndc.get("error"):
            info, registry_match = extract_openfda_info(ndc), True
        if not registry_match:
            cd = await lookup_indian_drug(query)
            if not cd and " " in query and len(first := query.split()[0]) >= 4:
                cd = await lookup_indian_drug(first)
            if cd:
                info, registry_match = cd, True
        if not registry_match:
            raw = await resolve_drug_name(query)
            if raw and raw.get("source") != "unresolved":
                info = {"brand_name": raw.get("brand_name") or query, "generic_name": raw.get("generic_name"), "manufacturer": raw.get("manufacturer")}
                registry_match, approximate = True, True

    cold: dict[str, Any] = {}
    cold_ok = None
    if body.location:
        cold = await check_cold_chain(body.location.lat, body.location.lng)
        if cold.get("available"):
            cold_ok = cold.get("ok", True)

    confidence, evidence = compute_confidence(barcode_valid=False, openfda_match=bool(registry_match), recall_status=None, cold_chain_ok=cold_ok)
    evidence.append(EvidenceItem(
        check="vision_analysis", status="warn",
        description=(f"{source_method} (AI-generated, unverified): {analysis.get('REASONING', analysis.get('reasoning', 'analysis complete'))}"
                     if analysed else f"Vision analysis unavailable: {vision.get('reason', 'not configured')}"),
        weight=0.0,
    ))
    if approximate:
        evidence.append(EvidenceItem(check="name_match", status="warn", description="Name matched approximately; confirm the exact name on the pack.", weight=0.0))
    verdict, reasons = assess_verdict(registry_match=registry_match, integrity_flags=flags)
    brand = info.get("brand_name") or analysis.get("possible_drug") or body.extracted_text

    lasa = None
    if settings.feature_lasa_guard and brand:
        from services.lasa import check_name
        lasa = check_name(str(brand)[:120], info.get("generic_name"))

    # Auto-save to the *caller's own* cabinet only (anonymous users are never pooled; audit S15).
    if user and expiry_info and expiry_info.get("status") != "unknown" and brand:
        try:
            from routers.cabinet import Medicine, add_medicine
            await add_medicine(Medicine(user_id=user.user_id, medicine_name=str(brand)[:200], expiry_date=expiry_info["raw_date"]), user)
        except Exception as exc:  # noqa: BLE001 - convenience feature must not fail verification
            logger.warning("cabinet_autosave_failed", error=repr(exc))

    verification_id = str(uuid.uuid4())
    audit_hash, audit_status = await _audit(verification_id, {
        "event_type": "verification", "method": "image", "verdict": verdict, "confidence": confidence,
        "drug": str(brand) if brand else None, "source": body.source, "client_reported_at": body.verified_at,
        "verification_scope": "image_or_record_match_only", "reasons": reasons, "vision_available": analysed,
    }, user, evidence)
    await _persist({
        "id": verification_id, "method": "image", "verdict": verdict, "confidence": confidence, "brand_name": brand,
        "evidence": _evidence_dump(evidence), "audit_hash": audit_hash,
        "temperature_c": cold.get("temperature_c"), "humidity_pct": cold.get("humidity_pct"),
        "location": body.location.wkt() if body.location else None,
        "clinic_id": user.clinic_id if user else None, "user_id": user.user_id if user else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    return VerificationResponse(
        verification_id=verification_id, verdict=verdict, confidence=confidence, evidence=evidence,
        audit_hash=audit_hash, audit_status=audit_status, identification_source=source_method if analysed else "OCR registry match",
        brand_name=brand, generic_name=info.get("generic_name"), manufacturer=info.get("manufacturer"),
        product_type=info.get("product_type"), route=info.get("route"),
        active_ingredients=info.get("active_ingredients", info.get("generic_name")),
        expiry_info=expiry_info, ai_generated=analysed, requires_human_review=True,
        verification_scope="image_or_record_match_only", has_recall=True, recall_status="inconclusive",
        verdict_reasons=reasons, lasa=lasa, name_match_approximate=approximate,
    )


# ─────────────────────────────── AI helpers ───────────────────────────────
@router.post("/interactions-photo")
@limiter.limit("5/minute")
async def verify_interactions_photo(request: Request, body: InteractionsPhotoRequest, user: CurrentUser | None = Depends(get_current_user)):
    """Identify several strips in one photo, then run the interaction checker. AI output; review required."""
    vision = await analyze_multiple_pills_image(body.image)
    if not vision.get("available") or not vision.get("medications"):
        raise HTTPException(status_code=422, detail="Could not identify medicines in the image. " + str(vision.get("reason", "")))
    meds = vision["medications"]
    names = [n for m in meds if (n := m.get("generic_name") or m.get("brand_name"))]
    notice = "Medicine names were identified by AI from a photo and may be wrong. Confirm each name before relying on this check."
    if len(names) < 2:
        return {"identified_medicines": meds, "overall_risk": {"value": "unknown"}, "interactions": [],
                "message": "Fewer than two medicines identified.", "ai_generated": True, "safety_notice": notice}
    result = await check_all_interactions(names)
    return {"identified_medicines": meds, "overall_risk": result.get("overall_risk", {"value": "unknown"}),
            "interactions": result.get("interactions", []), "ai_generated": True,
            "clinical_review_required": True, "safety_notice": notice}


@router.post("/symptom-safety")
@limiter.limit("10/minute")
async def verify_symptom_safety(request: Request, body: SymptomSafetyRequest, user: CurrentUser | None = Depends(get_current_user)):
    """Cross-check OTC options against current medicines. Informational only; not a recommendation."""
    from services.symptom_graph import symptom_safety_app
    result = await symptom_safety_app.ainvoke({
        "symptoms": body.symptoms, "current_medications": body.current_medications, "suggested_otcs": [],
        "interactions_results": {}, "safe_options": [], "unsafe_options": [], "summary": "",
    })
    return {
        "suggested_otcs": result.get("suggested_otcs", []), "safe_options": result.get("safe_options", []),
        "unsafe_options": result.get("unsafe_options", []), "summary": result.get("summary", ""),
        "ai_generated": True, "not_medical_advice": True, "clinical_review_required": True,
        "safety_notice": "This is AI-generated general information, not a diagnosis or prescription. "
                         "Ask a pharmacist or doctor before taking any medicine, especially if symptoms are severe, "
                         "persistent, or you are pregnant, a child, elderly, or have other conditions.",
    }


# ─────────────────────────────── batch ───────────────────────────────
@router.post("/batch")
@limiter.limit("5/minute")
async def verify_batch(request: Request, body: BatchVerifyRequest, user: CurrentUser | None = Depends(get_current_user)):
    """Verify many codes concurrently; streams NDJSON items then a summary."""
    limit = get_settings().max_batch_items if user else ANON_BATCH_LIMIT
    if len(body.barcodes) > limit:
        raise HTTPException(status_code=413, detail=f"At most {limit} items per batch" + ("" if user else " without signing in"))
    sem = asyncio.Semaphore(8)

    async def one(code: str) -> dict[str, Any]:
        async with sem:
            try:
                res = await verify_barcode_core(BarcodeVerifyRequest(barcode=code, source="batch"), user)
                return {"type": "item", "data": {"barcode": code, **res.model_dump()}}
            except HTTPException as exc:
                return {"type": "item", "data": {"barcode": code, "verdict": "unknown", "error": exc.detail, "processing_error": True}}
            except Exception as exc:  # noqa: BLE001 - one bad item must not abort the stream
                logger.error("batch_item_failed", barcode=code, error=repr(exc))
                return {"type": "item", "data": {"barcode": code, "verdict": "unknown", "error": "processing failed", "processing_error": True}}

    async def generate():
        jobs = [asyncio.create_task(one(b)) for b in body.barcodes]
        results = []
        for fut in asyncio.as_completed(jobs):
            res = await fut
            results.append(res["data"])
            yield json.dumps(res, default=str) + "\n"
        processed = [r for r in results if not r.get("processing_error")]
        flagged = [r for r in processed if r.get("verdict") in ("suspicious", "counterfeit")]
        recalls = sum(1 for r in processed if r.get("recall_status") == "active")
        by_mfr: dict[str, int] = {}
        for r in flagged:
            if m := r.get("manufacturer"):
                by_mfr[m] = by_mfr.get(m, 0) + 1
        flags = []
        if processed and len(flagged) / len(processed) > 0.15:
            flags.append("High share of flagged items (>15%)")
        if recalls >= 2:
            flags.append("Multiple items with active recalls")
        flags += [f"Multiple flagged items from manufacturer: {m}" for m, c in by_mfr.items() if c >= 2]
        if len(processed) < len(results):
            flags.append(f"{len(results) - len(processed)} item(s) could not be processed; they are NOT counted as failures")
        yield json.dumps({"type": "summary", "data": {
            "total": len(results), "processed": len(processed), "flagged_count": len(flagged),
            "fail_count": len(flagged), "error_count": len(results) - len(processed),
            "active_recall_count": recalls, "flags": flags,
        }}) + "\n"

    return StreamingResponse(generate(), media_type="application/x-ndjson", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/batch-audit")
@limiter.limit("10/minute")
async def batch_audit(request: Request, body: BatchAuditRequest, user: CurrentUser = Depends(require_current_user)):
    """Bind an exported batch report into the audit chain (authenticated only)."""
    verification_id = str(uuid.uuid4())
    audit_hash, status = await _audit(verification_id, {"event_type": "batch_export", "method": "batch_pdf_export", "items": body.items}, user)
    if status == "failed":
        raise HTTPException(status_code=503, detail="Audit trail unavailable; the export was not recorded.")
    return {"audit_hash": audit_hash, "verification_id": verification_id}


# ─────────────────────────────── history & lookup ───────────────────────────────
def _redact(row: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in row.items() if k not in ("location", "clinic_id", "user_id", "temperature_c", "humidity_pct")}


@router.get("/history")
async def get_verification_history(user: CurrentUser = Depends(require_current_user)):
    """The caller's own history (clinic admins: their clinic; regulators/admins: all)."""
    if user.role in PRIVILEGED_ROLES:
        rows = await verification_repo.list_all(limit=50)
    elif user.role == "clinic_admin" and user.clinic_id:
        rows = await verification_repo.list_all(filters={"clinic_id": user.clinic_id}, limit=50)
    else:
        rows = await verification_repo.list_by_user(user.user_id, limit=50)
    return {"verifications": rows}


@router.post("/offline-sync")
@limiter.limit("60/minute")
async def sync_offline_verification(request: Request, body: OfflineSyncRequest, user: CurrentUser = Depends(require_current_user)):
    """Record a scan made offline. The client's verdict is stored as an unverified claim."""
    verification_id = body.verification_id or str(uuid.uuid4())
    client_version = request.headers.get("If-Match")
    if client_version:
        existing = await verification_repo.find_by_id(verification_id)
        if existing:
            server_version = str(existing.get("updated_at") or existing.get("created_at") or "")
            if server_version != client_version:
                return JSONResponse(status_code=409, content={
                    "error": "CONFLICT", "message": "Record changed on the server while you were offline.",
                    "client_version": client_version, "server_version": server_version,
                    "server_state": {"verification_id": existing.get("id"), "verdict": existing.get("verdict")},
                    "resolution": "manual_review_required",
                })
    audit_hash, status = await _audit(verification_id, {
        "event_type": "offline_client_report", "method": "offline_cache", "verdict": "unverified_client_claim",
        "drug": body.brand_name, "barcode": body.barcode, "source": body.source, "client_reported_at": body.verified_at,
        "client_claimed_verdict": body.verdict, "client_claimed_confidence": body.confidence,
    }, user)
    if status == "failed":
        raise HTTPException(status_code=503, detail="Audit trail unavailable; retry later.")
    return {"status": "synced", "audit_hash": audit_hash, "recorded_as": "unverified_client_claim"}


@router.get("/{verification_id}")
async def get_verification(verification_id: str, user: CurrentUser | None = Depends(get_current_user)):
    v = await verification_repo.find_by_id(verification_id)
    if not v:
        raise HTTPException(status_code=404, detail="Verification not found")
    owner = v.get("user_id")
    if owner is None:
        return _redact(v)
    if user and (user.user_id == owner or user.role in PRIVILEGED_ROLES or (user.clinic_id and user.clinic_id == v.get("clinic_id"))):
        return v
    raise HTTPException(status_code=404, detail="Verification not found")
