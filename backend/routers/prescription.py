from fastapi import APIRouter
from pydantic import BaseModel
from starlette.requests import Request

from services.drug_resolver import resolve_all_drugs
from services.interactions import check_interactions_enterprise
from services.limiter import limiter
from services.prescription import generate_summaries
from services.sanitize import sanitize_drug_input
from services.translation import translate_medical_text

router = APIRouter(prefix="/prescription", tags=["prescription"])

class PrescriptionRequest(BaseModel):
    medicines: list[str]           # raw spoken names
    language: str = "en"           # ISO 639-1 target language
    patient_age: int | None = None
    patient_weight_kg: float | None = None
    conditions: list[str] = []
    gfr: float | None = None       # renal function for dosage flagging

class PrescriptionResponse(BaseModel):
    summaries: list[dict]
    interactions: list[dict]
    unresolved_drugs: list[str]    # drugs we couldn't identify
    confidence_overall: float
    language: str
    audio_script: str              # plain text for TTS playback
    pdf_text: str                  # formatted for PDF generation

class ImageExtractRequest(BaseModel):
    image: str

@router.post("/extract-image")
async def extract_image(req: ImageExtractRequest):
    """Extract medicine list from a prescription photo (Stage 1)."""
    from services.vision import extract_prescription_medicines
    # Base64 string might have prefix
    img_data = req.image
    if "base64," in img_data:
        img_data = img_data.split("base64,")[1]
    
    res = await extract_prescription_medicines(img_data)
    if not res["available"]:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=res.get("reason", "Extraction failed"))
    
    extracted = res.get("medicines", [])
    if not extracted:
        return {"medicines": []}
        
    resolved = await resolve_all_drugs(extracted)
    
    formatted = []
    for r in resolved:
        is_verified = r["source"] != "unresolved"
        formatted.append({
            "original_name": r["raw_name"],
            "resolved_name": r.get("generic_name") or r.get("brand_name") or r["raw_name"],
            "is_verified": is_verified,
            "confidence": r.get("confidence", 0)
        })
        
    return {"medicines": formatted}

@router.post("/summarize", response_model=PrescriptionResponse)
@limiter.limit("30/minute")
async def summarize_prescription(request: Request, body: PrescriptionRequest):
    req = body
    sanitized_meds = [sanitize_drug_input(m, "prescription_summarize") for m in req.medicines]
    # Step 1: Resolve drug names
    resolved = await resolve_all_drugs(sanitized_meds)
    unresolved = [r["raw_name"] for r in resolved if r["source"] == "unresolved"]

    # Step 2: Get RxCUIs for verified drugs
    verified = [r for r in resolved if r.get("rxcui")]
    rxcuis = [r["rxcui"] for r in verified]

    # Step 3: Check interactions
    interactions = []
    if len(rxcuis) >= 2:
        interactions = await check_interactions_enterprise(rxcuis)

    # Step 4: Generate summaries
    patient_ctx = {
        "age": req.patient_age,
        "weight_kg": req.patient_weight_kg,
        "conditions": req.conditions,
        "renal_gfr": req.gfr
    }
    summaries = await generate_summaries(resolved, interactions, patient_ctx, req.language)

    # Step 5: Translate everything
    translated_summaries = []
    for s in summaries:
        d = s.model_dump()
        if req.language != "en":
            d["treats"] = await translate_medical_text(d["treats"], req.language)
            d["when_to_take"] = await translate_medical_text(d["when_to_take"], req.language)
            d["warning"] = await translate_medical_text(d["warning"], req.language)
        translated_summaries.append(d)

    # Step 6: Build audio script (for browser TTS)
    audio_script = "\n\n".join([
        f"{s['drug_name']}: {s['treats']}. Take {s['when_to_take']}. Warning: {s['warning']}."
        for s in translated_summaries
    ])

    # Step 7: PDF-ready plain text
    pdf_lines = ["YOUR PRESCRIPTION SUMMARY", "=" * 40]
    for s in translated_summaries:
        pdf_lines += [
            f"\n{s['drug_name']} ({s['active_ingredient']})",
            f"  Treats: {s['treats']}",
            f"  When: {s['when_to_take']} for {s['duration']}",
            f"  Warning: {s['warning']}"
        ]

    overall_confidence = (
        sum(r.get("confidence", 0) for r in resolved) / len(resolved)
        if resolved else 0.0
    )

    return PrescriptionResponse(
        summaries=translated_summaries,
        interactions=[{
            "drug_a": i.drug_a,
            "drug_b": i.drug_b,
            "severity": i.severity,
            "clinical_effect": i.clinical_effect,
            "management": i.management,
            "signal_strength": i.signal_strength
        } for i in interactions],
        unresolved_drugs=unresolved,
        confidence_overall=round(overall_confidence, 2),
        language=req.language,
        audio_script=audio_script,
        pdf_text="\n".join(pdf_lines)
    )
