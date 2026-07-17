"""
Drug verification router — barcode scanning, image analysis, batch mode.
Integrates: OpenFDA, WHO GTIN, GPT-4o Vision, Open-Meteo cold chain, SHA-256 audit.
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from dependencies import get_current_user
from models.schemas import (
    BarcodeVerifyRequest, ImageVerifyRequest, BatchVerifyRequest,
    VerificationResponse, EvidenceItem, InteractionsPhotoRequest,
    SymptomSafetyRequest, CurrentUser
)
from services.openfda import lookup_by_ndc, get_drug_label, check_recalls, extract_openfda_info, check_drug_shortage
import asyncio
from services.confidence import compute_confidence, determine_verdict
from services.side_effects import extract_side_effects_from_label
from services.audit import add_audit_record
from services.cold_chain import check_cold_chain
from services.gtin import validate_gtin, parse_gs1_datamatrix, parse_cdsco_barcode
from services.vision import analyze_pill_image, analyze_multiple_pills_image
from services.interactions import check_all_interactions
from config import get_settings
from starlette.requests import Request
from services.limiter import limiter
from services.sanitize import sanitize_drug_input

router = APIRouter(prefix="/verify", tags=["verification"])

from repositories.entities import VerificationRepository

verification_repo = VerificationRepository()


@router.post("/barcode", response_model=VerificationResponse)
@limiter.limit("30/minute")
async def verify_barcode(request: Request, body: BarcodeVerifyRequest, user: Optional[CurrentUser] = Depends(get_current_user)):
    """
    Verify a drug by barcode/NDC number.
    Pipeline: GTIN validate → OpenFDA lookup → Recall check → Label parse → Cold chain → Score.
    """
    settings = get_settings()
    barcode = body.barcode.strip()

    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")

    # Step 1: Parse Barcode (CDSCO -> GS1 Datamatrix -> GTIN)
    cdsco_result = parse_cdsco_barcode(barcode)
    gs1_result = None
    gtin_result: Dict[str, Any] = {}
    
    barcode_valid = False
    ndc_to_lookup = barcode
    
    if cdsco_result.get("valid"):
        barcode_valid = True
        ndc_to_lookup = cdsco_result.get("gtin") or cdsco_result.get("brand_name") or cdsco_result.get("generic_name") or barcode
    else:
        # Try GS1 DataMatrix (has AIs like 01, 10, 17)
        if "(01)" in barcode or len(barcode) > 20:
            gs1_result = parse_gs1_datamatrix(barcode)
            if gs1_result.get("gtin"):
                barcode_valid = True
                ndc_to_lookup = gs1_result["gtin"]
                
        # Fallback to standard GTIN validation
        if not barcode_valid:
            gtin_result = validate_gtin(barcode)
            barcode_valid = gtin_result.get("valid", False)
            ndc_to_lookup = gtin_result.get("ndc_extracted") or barcode

    # Step 2: Look up in OpenFDA, CDSCO India, & Multi-Tier Resolver
    from services.cdsco import lookup_indian_drug
    from services.drug_resolver import resolve_drug_name
    
    ndc_result = await lookup_by_ndc(ndc_to_lookup, api_key=settings.openfda_api_key)
    cdsco_drug = None
    resolved_drug = None
    
    if isinstance(ndc_result, dict) and ndc_result.get("error"):
        ndc_result = None
    if not ndc_result:
        cdsco_drug = await lookup_indian_drug(ndc_to_lookup)
        if not cdsco_drug and " " in ndc_to_lookup:
            fw = ndc_to_lookup.split()[0].strip()
            if len(fw) >= 4:
                cdsco_drug = await lookup_indian_drug(fw)
                if not cdsco_drug:
                    ndc_result = await lookup_by_ndc(fw, api_key=settings.openfda_api_key)
        if not cdsco_drug and not ndc_result:
            res_raw = await resolve_drug_name(ndc_to_lookup)
            if res_raw and res_raw.get("source") != "unresolved":
                resolved_drug = res_raw
                    
    openfda_match = (ndc_result is not None) or (cdsco_drug is not None) or (resolved_drug is not None)

    # Step 3: Extract drug info
    if ndc_result:
        drug_info = extract_openfda_info(ndc_result)
    elif cdsco_drug:
        drug_info = {
            "brand_name": cdsco_drug.get("brand_name"),
            "generic_name": cdsco_drug.get("generic_name"),
            "manufacturer": cdsco_drug.get("manufacturer"),
            "ndc": cdsco_drug.get("ndc", ndc_to_lookup),
            "product_type": "HUMAN PRESCRIPTION DRUG",
            "route": cdsco_drug.get("route", "ORAL"),
            "active_ingredients": cdsco_drug.get("generic_name"),
            "substance_name": cdsco_drug.get("generic_name")
        }
    elif resolved_drug:
        drug_info = {
            "brand_name": resolved_drug.get("brand_name", ndc_to_lookup),
            "generic_name": resolved_drug.get("generic_name", "Verified Drug"),
            "manufacturer": resolved_drug.get("manufacturer", "Official Registry Match"),
            "ndc": str(resolved_drug.get("rxcui", ndc_to_lookup)),
            "product_type": "HUMAN PRESCRIPTION DRUG",
            "route": "ORAL",
            "active_ingredients": resolved_drug.get("generic_name", ""),
            "substance_name": resolved_drug.get("generic_name", "")
        }
    else:
        drug_info = {
            "brand_name": cdsco_result.get("brand_name"), 
            "generic_name": cdsco_result.get("generic_name"), 
            "manufacturer": cdsco_result.get("manufacturer"),
            "ndc": ndc_to_lookup, "product_type": None, "route": None,
            "active_ingredients": None, "substance_name": cdsco_result.get("generic_name")
        }

    # Step 4: Check recalls (FDA + CDSCO) + shortage in parallel
    active_ingredient = drug_info.get("substance_name") or drug_info.get("generic_name") or ""
    brand_name = drug_info.get("brand_name") or ""
    
    recall_task = check_recalls(
        ndc=drug_info.get("ndc"),
        drug_name=brand_name,
        api_key=settings.openfda_api_key
    )
    
    from services.cdsco import check_cdsco_recall
    cdsco_task = check_cdsco_recall(drug_name=brand_name, batch_no=None)
    shortage_task = check_drug_shortage(active_ingredient, api_key=settings.openfda_api_key) if active_ingredient else asyncio.ensure_future(asyncio.sleep(0))
    
    recalls, cdsco_res, shortage_raw = await asyncio.gather(recall_task, cdsco_task, shortage_task, return_exceptions=True)
    
    fda_recall_available = not isinstance(recalls, Exception) and not (isinstance(recalls, list) and any(isinstance(r, dict) and r.get("error") for r in recalls))
    cdsco_recall_available = isinstance(cdsco_res, dict) and cdsco_res.get("available", False)
    if not fda_recall_available:
        no_recalls = None  # Inconclusive check due to service outage
        recalls = [r for r in (recalls if isinstance(recalls, list) else []) if not r.get("error")]
    else:
        if isinstance(cdsco_res, dict) and cdsco_res.get("has_cdsco_recall"):
            recalls.append({
                "status": "Ongoing",
                "reason_for_recall": cdsco_res.get("recall_reason", "CDSCO Safety Alert"),
                "report_date": cdsco_res.get("recall_date", "Recent")
            })
        no_recalls = len(recalls) == 0 if cdsco_recall_available else None

    shortage = shortage_raw if isinstance(shortage_raw, dict) else {"in_shortage": False}

    # Step 5: Get drug label for side effects
    label = await get_drug_label(
        ndc=drug_info.get("ndc"),
        drug_name=drug_info.get("brand_name") or drug_info.get("generic_name"),
        api_key=settings.openfda_api_key
    )
    final_drug_name = drug_info.get("brand_name") or drug_info.get("generic_name") or ndc_to_lookup
    side_effects = await extract_side_effects_from_label(label, final_drug_name) if label else []

    # Step 6: Cold chain check (if location provided, via Open-Meteo free API)
    cold_chain_ok = None
    if body.location and body.location.get("lat") and body.location.get("lng"):
        cold_result = await check_cold_chain(
            body.location["lat"],
            body.location["lng"],
            label=label
        )
        if cold_result.get("available"):
            cold_chain_ok = cold_result.get("ok", True)

    # Step 7: Compute confidence score (weighted evidence aggregation)
    confidence, evidence = compute_confidence(
        barcode_valid=barcode_valid,
        openfda_match=openfda_match,
        recall_status=no_recalls,
        image_match=None,
        cold_chain_ok=cold_chain_ok,
        report_history_clean=True
    )

    # Step 7b: authoritative serial verification. A check digit or NDC match
    # only proves formatting/record existence, never physical authenticity.
    serialized = gs1_result or {}
    from services.manufacturer_verification import verify_serialized_package
    serial_check = await verify_serialized_package(
        gtin=serialized.get("gtin") or cdsco_result.get("gtin"),
        serial_number=serialized.get("serial_number"),
        lot=serialized.get("lot") or cdsco_result.get("batch_no"),
    )
    if serial_check.get("verified") is True:
        confidence = 100.0
        evidence.append(EvidenceItem(check="authoritative_serial", status="pass", description="Package serial was confirmed by the authorised verification service.", weight=100.0))
    elif serial_check.get("verified") is False:
        evidence.append(EvidenceItem(check="authoritative_serial", status="fail", description="Package serial was rejected by the authorised verification service. Do not dispense; escalate immediately.", weight=100.0))
    else:
        evidence.append(EvidenceItem(check="authoritative_serial", status="warn", description="No authoritative package-serial verification was available. This is a record match only, not proof of authenticity.", weight=0.0))
    if no_recalls is None:
        evidence.append(EvidenceItem(check="recall_coverage", status="warn", description="One or more recall sources were unavailable, so recall status is inconclusive.", weight=0.0))

    # Add GTIN evidence
    if gtin_result.get("format") and gtin_result.get("format") != "NDC":
        evidence.append(EvidenceItem(
            check="gtin_validation",
            status="pass" if gtin_result["check_digit_valid"] else "fail",
            description=f"{gtin_result['format']} barcode — check digit {'valid' if gtin_result['check_digit_valid'] else 'INVALID'}",
            weight=5.0
        ))
        if gtin_result.get("country"):
            evidence.append(EvidenceItem(
                check="country_of_origin",
                status="pass",
                description=f"Registered in: {gtin_result['country']}",
                weight=0.0
            ))

    verdict = determine_verdict(
        confidence,
        serial_verification=serial_check.get("verified"),
        no_active_recall=no_recalls,
    )

    # Step 8: Create verification record & audit chain entry
    verification_id = str(uuid.uuid4())
    verified_at_time = body.verified_at if body.verified_at else datetime.now(timezone.utc).isoformat()
    
    audit_record = await add_audit_record(verification_id, {
        "barcode": barcode,
        "verdict": verdict,
        "confidence": confidence,
        "drug": drug_info.get("brand_name") or drug_info.get("generic_name"),
        "method": "barcode",
        "source": body.source,
        "verified_at": verified_at_time,
        "gtin_format": gtin_result.get("format"),
        "gtin_country": gtin_result.get("country"),
        "evidence": [e.model_dump() if hasattr(e, "model_dump") else getattr(e, "__dict__", str(e)) for e in evidence],
        "priors": {"base": 0.5, "prior_name": "Standard baseline prior"},
        "databases_queried": ["WHO GTIN", "OpenFDA", "CDSCO India"]
    })

    # Persist to database via VerificationRepository (automatically uses local SQLite when offline)
    try:
        loc = None
        if body.location and body.location.get("lat") and body.location.get("lng"):
            loc = f"POINT({body.location['lng']} {body.location['lat']})"
            
        await verification_repo.create({
            "id": verification_id,
            "barcode": barcode,
            "method": "barcode",
            "verdict": verdict,
            "confidence": confidence,
            "brand_name": drug_info.get("brand_name"),
            "generic_name": drug_info.get("generic_name"),
            "manufacturer": drug_info.get("manufacturer"),
            "ndc": drug_info.get("ndc"),
            "has_recall": not no_recalls,
            "evidence": [e.model_dump() if hasattr(e, "model_dump") else getattr(e, "__dict__", str(e)) for e in evidence],
            "audit_hash": audit_record.get("audit_hash", ""),
            "gtin_data": gtin_result,
            "temperature_c": cold_result.get("temperature_c") if cold_chain_ok is not None and 'cold_result' in locals() else None,
            "humidity_pct": cold_result.get("humidity_pct") if cold_chain_ok is not None and 'cold_result' in locals() else None,
            "location": loc,
            "clinic_id": user.clinic_id if user else None
        })
    except Exception as e:
        import structlog
        structlog.get_logger().error("verification_persist_failed", error=str(e))

    # Pipeline B: Passive learning — teach the alias table from real traffic
    if drug_info.get("generic_name"):
        try:
            from services.vernacular_resolver import learn_from_verification
            asyncio.create_task(learn_from_verification(
                query=barcode,
                brand_name=drug_info.get("brand_name", ""),
                generic_name=drug_info.get("generic_name", ""),
                active_ingredients=drug_info.get("active_ingredients") or [drug_info.get("generic_name", "")]
            ))
        except Exception:
            pass  # Non-critical — don't break the verification pipeline

    return VerificationResponse(
        verification_id=verification_id,
        verdict=verdict,
        confidence=confidence,
        brand_name=drug_info.get("brand_name"),
        generic_name=drug_info.get("generic_name"),
        manufacturer=drug_info.get("manufacturer"),
        ndc=drug_info.get("ndc"),
        product_type=drug_info.get("product_type"),
        route=drug_info.get("route"),
        active_ingredients=drug_info.get("active_ingredients"),
        has_recall=not no_recalls,
        evidence=evidence,
        side_effects=side_effects,
        audit_hash=audit_record.get("audit_hash", ""),
        shortage=shortage if isinstance(shortage, dict) else {"in_shortage": False},
        requires_human_review=serial_check.get("verified") is not True,
        verification_scope="authoritative_serial" if serial_check.get("verified") is not None else "record_match_only",
        data_freshness={"external_data_max_age_hours": settings.external_data_max_age_hours, "authoritative_serial_available": serial_check.get("available", False)}
    )


@router.post("/image", response_model=VerificationResponse)
@limiter.limit("30/minute")
async def verify_image(request: Request, body: ImageVerifyRequest, user: Optional[CurrentUser] = Depends(get_current_user)):
    """
    Verify a drug by pill/packaging photo.
    Uses Hybrid Pipeline: Tesseract Text -> RxNav -> CDSCO -> GPT-4o Vision.
    """
    verification_id = str(uuid.uuid4())

    # Try Hybrid vision analysis
    vision_result = await analyze_pill_image(body.image, body.extracted_text)
    image_analyzed = vision_result.get("available", False)
    
    source_method = vision_result.get("source_method", "Unknown Source")

    # Extract expiry date if text was sent
    expiry_info = None
    if body.extracted_text:
        from services.expiry import extract_expiry_date
        expiry_info = extract_expiry_date(body.extracted_text)

    # Determine image match from vision analysis
    image_match = None
    if image_analyzed and vision_result.get("analysis"):
        analysis = vision_result["analysis"]
        suspicion = analysis.get("SUSPICION_LEVEL", analysis.get("suspicion_level", "")).lower()
        if suspicion == "low":
            image_match = True
        elif suspicion == "high":
            image_match = False

    query_text = body.extracted_text or (vision_result.get("analysis", {}).get("possible_drug") if image_analyzed else None)
    registry_match = False
    resolved_info = {}
    if query_text:
        settings = get_settings()
        ndc_res = await lookup_by_ndc(query_text, api_key=settings.openfda_api_key)
        if isinstance(ndc_res, dict) and not ndc_res.get("error"):
            resolved_info = extract_openfda_info(ndc_res)
            registry_match = True
        if not registry_match:
            cdsco_res = await lookup_indian_drug(query_text)
            if not cdsco_res and " " in query_text:
                fw = query_text.split()[0].strip()
                if len(fw) >= 4:
                    cdsco_res = await lookup_indian_drug(fw)
            if cdsco_res:
                resolved_info = cdsco_res
                registry_match = True
        if not registry_match:
            res_raw = await resolve_drug_name(query_text)
            if res_raw and res_raw.get("source") != "unresolved":
                resolved_info = {
                    "brand_name": res_raw.get("brand_name", query_text),
                    "generic_name": res_raw.get("generic_name", "Verified Drug"),
                    "manufacturer": res_raw.get("manufacturer", "Official Registry Match"),
                }
                registry_match = True

    # Cold chain check
    cold_chain_ok = None
    if body.location and body.location.get("lat") and body.location.get("lng"):
        cold_result = await check_cold_chain(body.location["lat"], body.location["lng"])
        if cold_result.get("available"):
            cold_chain_ok = cold_result.get("ok", True)

    confidence, evidence = compute_confidence(
        barcode_valid=False,
        openfda_match=registry_match,
        recall_status=None,
        image_match=image_match if image_analyzed else (True if registry_match else None),
        cold_chain_ok=cold_chain_ok,
        report_history_clean=True
    )

    if registry_match:
        evidence.append(EvidenceItem(
            check="drug_registry_check",
            status="pass",
            description=f"Verified via Registry Match: {resolved_info.get('brand_name', query_text)} ({resolved_info.get('generic_name', '')})",
            weight=40.0
        ))

    # Add vision evidence
    if image_analyzed:
        analysis = vision_result.get("analysis", {})
        reasoning = analysis.get('REASONING', analysis.get('reasoning', 'Analysis complete'))
        evidence.append(EvidenceItem(
            check="vision_analysis",
            status="pass" if image_match else ("fail" if image_match is False else "warn"),
            description=f"{source_method}: {reasoning}",
            weight=20.0
        ))
    else:
        evidence.append(EvidenceItem(
            check="vision_analysis",
            status="warn",
            description=f"Vision analysis unavailable: {vision_result.get('reason', 'API key not configured')}",
            weight=0.0
        ))

    verdict = determine_verdict(confidence)
    brand_name = resolved_info.get("brand_name") or (vision_result.get("analysis", {}).get("possible_drug") if image_analyzed else body.extracted_text)

    # Auto-save to cabinet if expiry is found and drug is identified
    if expiry_info and expiry_info.get("status") != "unknown" and brand_name:
        try:
            from routers.cabinet import add_medicine, Medicine
            await add_medicine(Medicine(
                user_id=user.user_id if user else "anonymous",
                medicine_name=brand_name,
                expiry_date=expiry_info["raw_date"]
            ))
        except Exception as e:
            import structlog
            structlog.get_logger().error("cabinet_autosave_failed", error=str(e))

    verified_at_time = body.verified_at if body.verified_at else datetime.now(timezone.utc).isoformat()
    audit_record = await add_audit_record(verification_id, {
        "method": "image",
        "verdict": verdict,
        "confidence": confidence,
        "vision_available": image_analyzed,
        "identification_source": source_method if image_analyzed else "OCR Registry Lookup",
        "source": body.source,
        "verified_at": verified_at_time
    })

    try:
        loc = None
        if body.location and body.location.get("lat") and body.location.get("lng"):
            loc = f"POINT({body.location['lng']} {body.location['lat']})"
            
        await verification_repo.create({
            "id": verification_id,
            "method": "image",
            "verdict": verdict,
            "confidence": confidence,
            "brand_name": brand_name,
            "evidence": [e.model_dump() if hasattr(e, "model_dump") else getattr(e, "__dict__", str(e)) for e in evidence],
            "audit_hash": audit_record.get("audit_hash", ""),
            "temperature_c": cold_result.get("temperature_c") if cold_chain_ok is not None and 'cold_result' in locals() else None,
            "humidity_pct": cold_result.get("humidity_pct") if cold_chain_ok is not None and 'cold_result' in locals() else None,
            "location": loc,
            "clinic_id": user.clinic_id if user else None
        })
    except Exception as e:
        import structlog
        structlog.get_logger().error("image_verification_persist_failed", error=str(e))

    return VerificationResponse(
        verification_id=verification_id,
        verdict=verdict,
        confidence=confidence,
        evidence=evidence,
        audit_hash=audit_record.get("audit_hash", ""),
        identification_source=source_method if image_analyzed else "OCR Registry Match",
        brand_name=brand_name,
        generic_name=resolved_info.get("generic_name"),
        manufacturer=resolved_info.get("manufacturer"),
        product_type=resolved_info.get("product_type", "HUMAN PRESCRIPTION DRUG"),
        route=resolved_info.get("route", "ORAL"),
        active_ingredients=resolved_info.get("active_ingredients", resolved_info.get("generic_name")),
        expiry_info=expiry_info,
        ai_generated=True,
        requires_human_review=True,
        verification_scope="image_or_record_match_only"
    )


import json

from fastapi.responses import StreamingResponse, JSONResponse

@router.post("/interactions-photo")
async def verify_interactions_photo(request: InteractionsPhotoRequest, user: Optional[CurrentUser] = Depends(get_current_user)):
    """
    Medicine interaction photo check.
    Takes a photo of multiple medicine strips, identifies all of them,
    and automatically runs the interaction checker on all pairs.
    """
    # 1. Identify all medicines in the photo
    vision_result = await analyze_multiple_pills_image(request.image)
    if not vision_result.get("available") or not vision_result.get("medications"):
        raise HTTPException(status_code=400, detail="Could not identify multiple medications in the image. " + vision_result.get("reason", ""))
        
    meds = vision_result["medications"]
    drug_names = []
    for m in meds:
        name = m.get("generic_name") or m.get("brand_name")
        if name:
            drug_names.append(name)
            
    if len(drug_names) < 2:
        return {
            "identified_medicines": meds,
            "overall_risk": {"value": "low"},
            "interactions": [],
            "message": "Only one medication clearly identified. Need at least two to check interactions."
        }
        
    # 2. Run interactions check
    interactions_result = await check_all_interactions(drug_names)
    
    return {
        "identified_medicines": meds,
        "overall_risk": interactions_result.get("overall_risk", {"value": "low"}),
        "interactions": interactions_result.get("interactions", []),
        "ai_generated": True
    }


@router.post("/symptom-safety")
async def verify_symptom_safety(request: SymptomSafetyRequest, user: Optional[CurrentUser] = Depends(get_current_user)):
    """
    Symptom-to-drug safety checker.
    Suggests OTC medications for the given symptoms, and immediately
    cross-checks them against the patient's current medications.
    Powered by LangGraph.
    """
    from services.symptom_graph import symptom_safety_app
    
    initial_state = {
        "symptoms": request.symptoms,
        "current_medications": request.current_medications,
        "suggested_otcs": [],
        "interactions_results": {},
        "safe_options": [],
        "unsafe_options": [],
        "summary": ""
    }
    
    result = await symptom_safety_app.ainvoke(initial_state)
    
    return {
        "suggested_otcs": result.get("suggested_otcs", []),
        "safe_options": result.get("safe_options", []),
        "unsafe_options": result.get("unsafe_options", []),
        "summary": result.get("summary", ""),
        "ai_generated": True
    }


@router.post("/batch")
async def verify_batch(request: BatchVerifyRequest, user: Optional[CurrentUser] = Depends(get_current_user)):
    """Verify multiple barcodes concurrently with a semaphore, returning a streaming response."""
    sem = asyncio.Semaphore(10)
    
    async def process_item(barcode):
        async with sem:
            try:
                req_model = BarcodeVerifyRequest(barcode=barcode)
                result = await verify_barcode(req_model, user)
                return {"type": "item", "data": result.model_dump()}
            except Exception as e:
                return {"type": "item", "data": {
                    "barcode": barcode,
                    "verdict": "unknown",
                    "confidence": 0,
                    "error": str(e)
                }}
                
    async def generate():
        tasks = [asyncio.create_task(process_item(b)) for b in request.barcodes]
        results = []
        for f in asyncio.as_completed(tasks):
            res = await f
            results.append(res["data"])
            yield json.dumps(res) + "\n"
            
        # Batch summary logic
        fail_count = sum(1 for r in results if r.get("verdict") in ["suspicious", "counterfeit", "unknown", "fail"])
        recall_count = sum(1 for r in results if r.get("has_recall"))
        
        manufacturers = {}
        for r in results:
            if r.get("verdict") in ["suspicious", "counterfeit", "fail"]:
                mfg = r.get("manufacturer")
                if mfg:
                    manufacturers[mfg] = manufacturers.get(mfg, 0) + 1
                    
        mfg_flags = [mfg for mfg, count in manufacturers.items() if count >= 2]
        
        flags = []
        if len(results) > 0 and (fail_count / len(results)) > 0.15:
            flags.append("High batch failure rate (>15%)")
        if recall_count >= 2:
            flags.append("Multiple recalled items detected")
        for mfg in mfg_flags:
            flags.append(f"Multiple failures from manufacturer: {mfg}")
            
        summary = {
            "type": "summary",
            "data": {
                "total": len(results),
                "fail_count": fail_count,
                "flags": flags
            }
        }
        yield json.dumps(summary) + "\n"

    return StreamingResponse(
        generate(), 
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no"
        }
    )

@router.post("/batch-audit")
async def batch_audit(request: dict):
    """Hash the final batch payload for PDF integrity."""
    verification_id = str(uuid.uuid4())
    audit_record = await add_audit_record(verification_id, {
        "method": "batch_pdf_export",
        "items": request.get("items", []),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"audit_hash": audit_record.get("audit_hash", "")}


@router.get("/history")
async def get_verification_history():
    """Get verification history (most recent 50) via VerificationRepository."""
    records = await verification_repo.list_all(limit=50)
    return {"verifications": records}

@router.post("/offline-sync")
async def sync_offline_verification(request: Request, body: dict):
    """
    Endpoint for the PWA Background Sync to submit offline cache hits.
    Supports Optimistic Concurrency Control (OCC) via If-Match header.
    Returns 409 Conflict if the entity was modified server-side while the client was offline.
    """
    payload = body
    verification_id = payload.get("verification_id") or str(uuid.uuid4())
    verified_at = payload.get("verified_at", datetime.now(timezone.utc).isoformat())
    source = payload.get("source", "offline_cache")

    # OCC: Check If-Match entity version for conflict detection
    client_version = request.headers.get("If-Match")
    if client_version and verification_id != f"offline-{verification_id}":
        # Check if this verification_id already exists with a different version
        existing = await verification_repo.find_by_id(verification_id)
        if existing:
            server_updated = existing.get("updated_at") or existing.get("created_at", "")
            return JSONResponse(
                status_code=409,
                content={
                    "error": "CONFLICT",
                    "message": "Entity was modified on the server while you were offline.",
                    "client_version": client_version,
                    "server_version": server_updated,
                    "server_state": {
                        "verification_id": existing.get("id"),
                        "verdict": existing.get("verdict"),
                        "confidence": existing.get("confidence"),
                        "updated_at": server_updated
                    },
                    "client_state": {
                        "verification_id": verification_id,
                        "verdict": payload.get("verdict"),
                        "confidence": payload.get("confidence"),
                        "verified_at": verified_at
                    },
                    "resolution": "manual_review_required"
                }
            )

    audit_record = await add_audit_record(verification_id, {
        "barcode": payload.get("brand_name", "unknown"),
        "verdict": payload.get("verdict", "unverified"),
        "confidence": payload.get("confidence", 0),
        "drug": payload.get("brand_name", "unknown"),
        "method": "offline_cache",
        "source": source,
        "verified_at": verified_at
    })
    
    return {"status": "synced", "audit_hash": audit_record.get("audit_hash", "")}


@router.get("/{verification_id}")
async def get_verification(verification_id: str):
    """Get a specific verification by ID via VerificationRepository."""
    v = await verification_repo.find_by_id(verification_id)
    if v:
        return v
    raise HTTPException(status_code=404, detail="Verification not found")
