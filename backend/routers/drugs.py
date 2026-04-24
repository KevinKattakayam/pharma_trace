"""
Drug details router — side effects, dosage advice, generic alternatives, and AI analysis.
Integrates: OpenFDA labels, Groq AI (Llama 3.3), LibreTranslate.
"""
from fastapi import APIRouter, HTTPException
from models.schemas import DosageRequest, DosageAdvice, GenericAlternative
from services.openfda import get_drug_label, lookup_by_ndc, find_generics, extract_openfda_info
from services.side_effects import extract_side_effects_from_label
from services.dosage import evaluate_dosage
from config import get_settings

router = APIRouter(prefix="/drugs", tags=["drugs"])


@router.get("/{ndc}")
async def get_drug_details(ndc: str):
    """Get full drug details by NDC. If Groq is configured, includes AI analysis."""
    settings = get_settings()
    ndc_result = await lookup_by_ndc(ndc, api_key=settings.openfda_api_key)

    if not ndc_result:
        raise HTTPException(status_code=404, detail="Drug not found")

    info = extract_openfda_info(ndc_result)
    label = await get_drug_label(ndc=ndc, api_key=settings.openfda_api_key)

    result = {**info, "label_available": label is not None}

    # Add AI-powered drug analysis if Groq is available
    if settings.groq_api_key:
        drug_name = info.get("brand_name") or info.get("generic_name")
        if drug_name:
            from services.groq_ai import ai_analyze_drug
            ai_info = await ai_analyze_drug(drug_name)
            if ai_info:
                result["ai_analysis"] = ai_info

    return result


@router.get("/{ndc}/side-effects")
async def get_side_effects(ndc: str, lang: str = "en", ai: bool = False):
    """
    Get plain-language side effects. Pass ?lang=hi for Hindi, ?ai=true for AI rewrite.
    Pipeline: OpenFDA label → rule-based parse → (optional) Groq AI rewrite → (optional) LibreTranslate.
    """
    settings = get_settings()
    label = await get_drug_label(ndc=ndc, api_key=settings.openfda_api_key)

    if not label:
        ndc_result = await lookup_by_ndc(ndc, api_key=settings.openfda_api_key)
        if ndc_result:
            info = extract_openfda_info(ndc_result)
            label = await get_drug_label(drug_name=info.get("brand_name") or info.get("generic_name"),
                                         api_key=settings.openfda_api_key)

    if not label:
        raise HTTPException(status_code=404, detail="Drug label not found")

    side_effects = extract_side_effects_from_label(label)
    se_list = [se.model_dump() for se in side_effects]

    # If AI rewrite requested and Groq is available, use Llama for better explanations
    if ai and settings.groq_api_key:
        from services.groq_ai import ai_rewrite_side_effects
        raw_texts = [se.get("description", "") for se in se_list]
        drug_name = ""
        openfda = label.get("openfda", {})
        brand = openfda.get("brand_name", [])
        if isinstance(brand, list) and brand:
            drug_name = brand[0]
        ai_results = await ai_rewrite_side_effects(raw_texts, drug_name)
        if ai_results:
            se_list = ai_results

    # Translate if requested
    if lang and lang != "en":
        from services.translation import translate_side_effects
        se_list = await translate_side_effects(se_list, lang)

    return {"side_effects": se_list, "language": lang, "ai_enhanced": ai and bool(settings.groq_api_key)}


@router.post("/{ndc}/dosage", response_model=DosageAdvice)
async def get_dosage_advice(ndc: str, request: DosageRequest):
    """Get personalized dosage advice based on patient characteristics."""
    settings = get_settings()
    label = await get_drug_label(ndc=ndc, api_key=settings.openfda_api_key)

    standard_dose = "See drug label"
    drug_name = ndc

    if label:
        dosage_info = label.get("dosage_and_administration", [])
        if dosage_info:
            standard_dose = dosage_info[0][:200] if isinstance(dosage_info, list) else str(dosage_info)[:200]

        openfda = label.get("openfda", {})
        brand = openfda.get("brand_name", [])
        drug_name = brand[0] if isinstance(brand, list) and brand else ndc

    result = evaluate_dosage(
        drug_name=drug_name,
        standard_dose=standard_dose,
        age=request.age,
        weight_kg=request.weight_kg,
        kidney_function=request.kidney_function or "normal",
        current_dose=request.current_dose
    )
    return result


@router.get("/{ndc}/generics")
async def get_generic_alternatives(ndc: str):
    """Find generic alternatives with the same active ingredient."""
    settings = get_settings()
    ndc_result = await lookup_by_ndc(ndc, api_key=settings.openfda_api_key)

    if not ndc_result:
        raise HTTPException(status_code=404, detail="Drug not found")

    info = extract_openfda_info(ndc_result)

    substance = info.get("substance_name")
    if not substance:
        ingredients = ndc_result.get("active_ingredients", [])
        if ingredients:
            substance = ingredients[0].get("name", "")
    if not substance:
        substance = info.get("generic_name")
    if not substance:
        return {"generics": [], "original_drug": info.get("brand_name"), "active_ingredient": None, "message": "Active ingredient not identified in FDA records"}

    generics = await find_generics(substance, api_key=settings.openfda_api_key)

    return {
        "original_drug": info.get("brand_name"),
        "active_ingredient": substance,
        "generics": generics
    }
