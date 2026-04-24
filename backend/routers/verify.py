"""
Drug verification router — barcode scanning, image analysis, batch mode.
Integrates: OpenFDA, WHO GTIN, GPT-4o Vision, Open-Meteo cold chain, SHA-256 audit.
"""
import uuid
from fastapi import APIRouter, HTTPException
from models.schemas import (
    BarcodeVerifyRequest, ImageVerifyRequest, BatchVerifyRequest,
    VerificationResponse, EvidenceItem
)
from services.openfda import lookup_by_ndc, get_drug_label, check_recalls, extract_openfda_info
from services.confidence import compute_confidence, determine_verdict
from services.side_effects import extract_side_effects_from_label
from services.audit import add_audit_record
from services.cold_chain import check_cold_chain
from services.gtin import validate_gtin
from services.vision import analyze_pill_image
from config import get_settings

router = APIRouter(prefix="/verify", tags=["verification"])

# In-memory verification history
_verifications: list[dict] = []


@router.post("/barcode", response_model=VerificationResponse)
async def verify_barcode(request: BarcodeVerifyRequest):
    """
    Verify a drug by barcode/NDC number.
    Pipeline: GTIN validate → OpenFDA lookup → Recall check → Label parse → Cold chain → Score.
    """
    settings = get_settings()
    barcode = request.barcode.strip()

    if not barcode:
        raise HTTPException(status_code=400, detail="Barcode is required")

    # Step 1: WHO GTIN barcode validation
    gtin_result = validate_gtin(barcode)
    barcode_valid = gtin_result.get("valid", False) or len(barcode.replace("-", "").replace(" ", "")) >= 8

    # If GTIN extracted an NDC, use that for lookup
    ndc_to_lookup = gtin_result.get("ndc_extracted") or barcode

    # Step 2: Look up in OpenFDA
    ndc_result = await lookup_by_ndc(ndc_to_lookup, api_key=settings.openfda_api_key)
    openfda_match = ndc_result is not None

    # Step 3: Extract drug info
    drug_info = extract_openfda_info(ndc_result) if ndc_result else {
        "brand_name": None, "generic_name": None, "manufacturer": None,
        "ndc": barcode, "product_type": None, "route": None,
        "active_ingredients": None, "substance_name": None
    }

    # Step 4: Check recalls
    recalls = await check_recalls(
        ndc=drug_info.get("ndc"),
        drug_name=drug_info.get("brand_name"),
        api_key=settings.openfda_api_key
    )
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
            request.location["lng"]
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
    audit_record = add_audit_record(verification_id, {
        "barcode": barcode,
        "verdict": verdict,
        "confidence": confidence,
        "drug": drug_info.get("brand_name") or drug_info.get("generic_name"),
        "method": "barcode",
        "gtin_format": gtin_result.get("format"),
        "gtin_country": gtin_result.get("country")
    })

    # Store in history
    _verifications.append({
        "id": verification_id,
        "barcode": barcode,
        "verdict": verdict,
        "confidence": confidence,
        "drug_info": drug_info,
        "gtin": gtin_result
    })

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
        audit_hash=audit_record["record_hash"]
    )


@router.post("/image", response_model=VerificationResponse)
async def verify_image(request: ImageVerifyRequest):
    """
    Verify a drug by pill/packaging photo.
    Uses GPT-4o Vision API if configured, otherwise returns image-not-analyzed status.
    """
    verification_id = str(uuid.uuid4())

    # Try GPT-4o Vision analysis
    vision_result = await analyze_pill_image(request.image)
    image_analyzed = vision_result.get("available", False)

    # Determine image match from vision analysis
    image_match = None
    if image_analyzed and vision_result.get("analysis"):
        analysis = vision_result["analysis"]
        suspicion = analysis.get("SUSPICION_LEVEL", "").lower()
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
        evidence.append(EvidenceItem(
            check="vision_analysis",
            status="pass" if image_match else ("fail" if image_match is False else "warn"),
            description=f"GPT-4o Vision: {analysis.get('REASONING', 'Analysis complete')}",
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

    audit_record = add_audit_record(verification_id, {
        "method": "image",
        "verdict": verdict,
        "confidence": confidence,
        "vision_available": image_analyzed
    })

    return VerificationResponse(
        verification_id=verification_id,
        verdict=verdict,
        confidence=confidence,
        evidence=evidence,
        audit_hash=audit_record["record_hash"]
    )


@router.post("/batch")
async def batch_verify(request: BatchVerifyRequest):
    """Verify multiple barcodes in batch mode for health workers. Each goes through the full pipeline."""
    results = []
    for barcode in request.barcodes:
        try:
            req = BarcodeVerifyRequest(barcode=barcode)
            result = await verify_barcode(req)
            results.append(result.model_dump())
        except Exception as e:
            results.append({
                "barcode": barcode,
                "verdict": "unknown",
                "confidence": 0,
                "error": str(e)
            })
    return {"results": results, "total": len(results)}


@router.get("/history")
async def get_verification_history():
    """Get verification history (most recent 50)."""
    return {"verifications": _verifications[-50:]}


@router.get("/{verification_id}")
async def get_verification(verification_id: str):
    """Get a specific verification by ID."""
    for v in _verifications:
        if v["id"] == verification_id:
            return v
    raise HTTPException(status_code=404, detail="Verification not found")
