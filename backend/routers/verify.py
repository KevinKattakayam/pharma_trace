"""
Drug verification router — barcode scanning, image analysis, batch mode.
Integrates: OpenFDA, WHO GTIN, GPT-4o Vision, Open-Meteo cold chain, SHA-256 audit.
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends
from dependencies import get_current_user
from models.schemas import (
    BarcodeVerifyRequest, ImageVerifyRequest, BatchVerifyRequest,
    VerificationResponse, EvidenceItem, InteractionsPhotoRequest,
    SymptomSafetyRequest
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

router = APIRouter(prefix="/verify", tags=["verification"])

# In-memory verification history
_verifications: list[dict] = []


@router.post("/barcode", response_model=VerificationResponse)
async def verify_barcode(request: BarcodeVerifyRequest, user: dict = Depends(get_current_user)):
    """
    Verify a drug by barcode/NDC number.
    Pipeline: GTIN validate → OpenFDA lookup → Recall check → Label parse → Cold chain → Score.
    """
    settings = get_settings()
    barcode = request.barcode.strip()

    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")

    # Step 1: Parse Barcode (CDSCO -> GS1 Datamatrix -> GTIN)
    cdsco_result = parse_cdsco_barcode(barcode)
    gs1_result = None
    gtin_result = None
    
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
            barcode_valid = gtin_result.get("valid", False) or len(barcode.replace("-", "").replace(" ", "")) >= 8
            ndc_to_lookup = gtin_result.get("ndc_extracted") or barcode

    # Step 2: Look up in OpenFDA
    ndc_result = await lookup_by_ndc(ndc_to_lookup, api_key=settings.openfda_api_key)
    openfda_match = ndc_result is not None

    # Step 3: Extract drug info
    drug_info = extract_openfda_info(ndc_result) if ndc_result else {
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
    
    if isinstance(recalls, Exception): recalls = []
    if isinstance(cdsco_res, dict) and cdsco_res.get("has_cdsco_recall"):
        recalls.append({
            "status": "Ongoing",
            "reason_for_recall": cdsco_res.get("recall_reason", "CDSCO Safety Alert"),
            "report_date": cdsco_res.get("recall_date", "Recent")
        })
        
    shortage = shortage_raw if isinstance(shortage_raw, dict) else {"in_shortage": False}
    no_recalls = len(recalls) == 0

    # Step 5: Get drug label for side effects
    label = await get_drug_label(
        ndc=drug_info.get("ndc"),
        drug_name=drug_info.get("brand_name") or drug_info.get("generic_name"),
        api_key=settings.openfda_api_key
    )
    side_effects = extract_side_effects_from_label(label) if label else []

    # Step 6: Cold chain check (if location provided, via Open-Meteo free API)
    cold_chain_ok = None
    if request.location and request.location.get("lat"):
        cold_result = await check_cold_chain(
            request.location["lat"],
            request.location["lng"],
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

    verdict = determine_verdict(confidence)

    # Step 8: Create verification record & audit chain entry
    verification_id = str(uuid.uuid4())
    verified_at_time = request.verified_at if request.verified_at else datetime.now(timezone.utc).isoformat()
    
    audit_record = add_audit_record(verification_id, {
        "barcode": barcode,
        "verdict": verdict,
        "confidence": confidence,
        "drug": drug_info.get("brand_name") or drug_info.get("generic_name"),
        "method": "barcode",
        "source": request.source,
        "verified_at": verified_at_time,
        "gtin_format": gtin_result.get("format"),
        "gtin_country": gtin_result.get("country")
    })

    # Store in history (memory)
    _verifications.append({
        "id": verification_id,
        "barcode": barcode,
        "verdict": verdict,
        "confidence": confidence,
        "drug_info": drug_info,
        "gtin": gtin_result
    })

    # Persist to database for cold chain history and stats
    from services.supabase import get_supabase
    db = get_supabase()
    if db.available:
        try:
            loc = None
            if request.location and request.location.get("lat") and request.location.get("lng"):
                loc = f"POINT({request.location['lng']} {request.location['lat']})"
                
            await db.insert("verifications", {
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
                "evidence": [e.model_dump() for e in evidence],
                "audit_hash": audit_record["record_hash"],
                "gtin_data": gtin_result,
                "temperature_c": cold_result.get("temperature_c") if cold_chain_ok is not None and 'cold_result' in locals() else None,
                "humidity_pct": cold_result.get("humidity_pct") if cold_chain_ok is not None and 'cold_result' in locals() else None,
                "location": loc,
                "clinic_id": user.get("clinic_id")
            })
        except Exception as e:
            print("Failed to persist verification:", e)

    # Pipeline B: Passive learning — teach the alias table from real traffic
    if drug_info.get("generic_name"):
        try:
            import asyncio
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
        audit_hash=audit_record["record_hash"],
        shortage=shortage if isinstance(shortage, dict) else {"in_shortage": False}
    )


@router.post("/image", response_model=VerificationResponse)
async def verify_image(request: ImageVerifyRequest, user: dict = Depends(get_current_user)):
    """
    Verify a drug by pill/packaging photo.
    Uses Hybrid Pipeline: Tesseract Text -> RxNav -> CDSCO -> GPT-4o Vision.
    """
    verification_id = str(uuid.uuid4())

    # Try Hybrid vision analysis
    vision_result = await analyze_pill_image(request.image, request.extracted_text)
    image_analyzed = vision_result.get("available", False)
    
    source_method = vision_result.get("source_method", "Unknown Source")

    # Extract expiry date if text was sent
    expiry_info = None
    if request.extracted_text:
        from services.expiry import extract_expiry_date
        expiry_info = extract_expiry_date(request.extracted_text)

    # Determine image match from vision analysis
    image_match = None
    if image_analyzed and vision_result.get("analysis"):
        analysis = vision_result["analysis"]
        suspicion = analysis.get("SUSPICION_LEVEL", analysis.get("suspicion_level", "")).lower()
        if suspicion == "low":
            image_match = True
        elif suspicion == "high":
            image_match = False

    # Cold chain check
    cold_chain_ok = None
    if request.location and request.location.get("lat"):
        cold_result = await check_cold_chain(request.location["lat"], request.location["lng"])
        if cold_result.get("available"):
            cold_chain_ok = cold_result.get("ok", True)

    confidence, evidence = compute_confidence(
        barcode_valid=False,
        openfda_match=False,
        recall_status=True,
        image_match=image_match,
        cold_chain_ok=cold_chain_ok,
        report_history_clean=True
    )

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
    brand_name = vision_result.get("analysis", {}).get("possible_drug") if image_analyzed else None

    # Auto-save to cabinet if expiry is found and drug is identified
    if expiry_info and expiry_info.get("status") != "unknown" and brand_name:
        try:
            from routers.cabinet import add_medicine, Medicine
            await add_medicine(Medicine(
                user_id="demo-user-123",
                medicine_name=brand_name,
                expiry_date=expiry_info["raw_date"]
            ))
        except Exception as e:
            print("Failed to auto-save to cabinet:", str(e))

    verified_at_time = request.verified_at if request.verified_at else datetime.now(timezone.utc).isoformat()
    audit_record = add_audit_record(verification_id, {
        "method": "image",
        "verdict": verdict,
        "confidence": confidence,
        "vision_available": image_analyzed,
        "identification_source": source_method,
        "source": request.source,
        "verified_at": verified_at_time
    })

    from services.supabase import get_supabase
    db = get_supabase()
    if db.available:
        try:
            loc = None
            if request.location and request.location.get("lat") and request.location.get("lng"):
                loc = f"POINT({request.location['lng']} {request.location['lat']})"
                
            await db.insert("verifications", {
                "id": verification_id,
                "method": "image",
                "verdict": verdict,
                "confidence": confidence,
                "brand_name": brand_name,
                "evidence": [e.model_dump() for e in evidence],
                "audit_hash": audit_record["record_hash"],
                "temperature_c": cold_result.get("temperature_c") if cold_chain_ok is not None and 'cold_result' in locals() else None,
                "humidity_pct": cold_result.get("humidity_pct") if cold_chain_ok is not None and 'cold_result' in locals() else None,
                "location": request.location,
                "clinic_id": user.get("clinic_id")
            })
        except Exception as e:
            print("Failed to persist image verification:", e)

    return VerificationResponse(
        verification_id=verification_id,
        verdict=verdict,
        confidence=confidence,
        evidence=evidence,
        audit_hash=audit_record["record_hash"],
        identification_source=source_method,
        brand_name=brand_name,
        expiry_info=expiry_info,
        ai_generated=True
    )


import json
import asyncio
from fastapi.responses import StreamingResponse

@router.post("/interactions-photo")
async def verify_interactions_photo(request: InteractionsPhotoRequest, user: dict = Depends(get_current_user)):
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
async def verify_symptom_safety(request: SymptomSafetyRequest, user: dict = Depends(get_current_user)):
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
async def verify_batch(request: BatchVerifyRequest, user: dict = Depends(get_current_user)):
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
    audit_record = add_audit_record(verification_id, {
        "method": "batch_pdf_export",
        "items": request.get("items", []),
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    return {"audit_hash": audit_record["record_hash"]}


@router.get("/history")
async def get_verification_history():
    """Get verification history (most recent 50)."""
    return {"verifications": _verifications[-50:]}

@router.post("/offline-sync")
async def sync_offline_verification(request: dict):
    """
    Endpoint for the PWA Background Sync to submit offline cache hits.
    These bypass the OpenFDA pipeline because they were determined deterministically offline.
    """
    verification_id = request.get("verification_id") or str(uuid.uuid4())
    verified_at = request.get("verified_at", datetime.now(timezone.utc).isoformat())
    source = request.get("source", "offline_cache")
        
    audit_record = add_audit_record(verification_id, {
        "barcode": request.get("brand_name", "unknown"),
        "verdict": request.get("verdict", "authentic"),
        "confidence": request.get("confidence", 100),
        "drug": request.get("brand_name", "unknown"),
        "method": "offline_cache",
        "source": source,
        "verified_at": verified_at
    })
    
    return {"status": "synced", "audit_hash": audit_record["record_hash"]}


@router.get("/{verification_id}")
async def get_verification(verification_id: str):
    """Get a specific verification by ID."""
    for v in _verifications:
        if v["id"] == verification_id:
            return v
    raise HTTPException(status_code=404, detail="Verification not found")
