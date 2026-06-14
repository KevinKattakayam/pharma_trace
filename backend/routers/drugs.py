"""
Drug details router — side effects, dosage advice, generic alternatives, and AI analysis.
Integrates: OpenFDA labels, Groq AI (Llama 3.3), LibreTranslate.
"""
from fastapi import APIRouter, HTTPException
from models.schemas import DosageRequest, DosageAdvice, GenericAlternative
from services.openfda import get_drug_label, lookup_by_ndc, find_generics, extract_openfda_info, check_drug_shortage
from services.side_effects import extract_side_effects_from_label
from services.dosage import evaluate_dosage
from config import get_settings

router = APIRouter(prefix="/drugs", tags=["drugs"])

@router.get("/shortages/{active_ingredient}")
async def get_drug_shortage(active_ingredient: str):
    """Check FDA Drug Shortage status for an active ingredient."""
    settings = get_settings()
    result = await check_drug_shortage(active_ingredient, api_key=settings.openfda_api_key)
    return result

@router.get("/{ndc}/cold-chain-history")
async def get_cold_chain_history(ndc: str, lat: float = 0, lng: float = 0):
    """Get cold chain history for an NDC within 50km radius."""
    from services.supabase import get_supabase
    db = get_supabase()
    
    if not db.available:
        return {"readings": [], "breach_rate": 0, "total": 0, "message": "Database not configured"}
    
    try:
        # Query verifications for this NDC with temperature data
        verifs = await db.query("verifications", limit=500)
        if not verifs:
            return {"readings": [], "breach_rate": 0, "total": 0}
        
        readings = []
        for v in verifs:
            if v.get("ndc") == ndc and v.get("temperature_c") is not None:
                readings.append({
                    "temperature_c": v.get("temperature_c"),
                    "humidity_pct": v.get("humidity_pct"),
                    "created_at": v.get("created_at")
                })
        
        readings = readings[:30]  # Last 30
        
        breaches = sum(1 for r in readings if (r["temperature_c"] or 0) > 25)
        breach_rate = round(breaches / len(readings) * 100) if readings else 0
        
        return {
            "readings": readings,
            "breach_rate": breach_rate,
            "total": len(readings),
            "warning": f"This medicine exceeded safe storage conditions in {breach_rate}% of recent regional verifications." if breach_rate > 30 else None
        }
    except Exception as e:
        return {"readings": [], "breach_rate": 0, "total": 0, "error": str(e)}

@router.get("/common-indian-medicines")
async def get_common_indian_medicines():
    """Return top common Indian medicines for offline PWA cache."""
    from services.supabase import get_supabase
    db = get_supabase()
    
    medicines = []
    
    # Dynamically seed from top-N most-verified NDCs in the last 30 days
    if db.available:
        try:
            # Fetch a larger pool and do adaptive window filtering in memory
            recent_verifs = await db.query("safety_check_log", limit=2000, order_by="created_at", order_desc=True)
            if recent_verifs:
                from datetime import datetime, timezone, timedelta
                now = datetime.now(timezone.utc)
                
                def extract_counts_for_window(days: int):
                    counts = {}
                    threshold = now - timedelta(days=days)
                    for v in recent_verifs:
                        created_at_str = v.get("created_at")
                        if not created_at_str: continue
                        try:
                            # Handle ISO format from Supabase
                            dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                            if dt < threshold:
                                continue
                        except ValueError:
                            pass
                        
                        name = v.get("medicine_name_resolved") or v.get("medicine_name_raw")
                        if name:
                            if name not in counts:
                                counts[name] = {
                                    "count": 0,
                                    "name": name,
                                    "generic_name": name,
                                    "rxcui": v.get("rxcui", ""),
                                    "uses": v.get("verdict_reason", "Common medicine"),
                                    "warnings": "Consult physician for details",
                                    "interactions": "Check with pharmacist",
                                    "dosage": "Standard adult dose unless directed otherwise"
                                }
                            counts[name]["count"] += 1
                    
                    sorted_meds = sorted(counts.values(), key=lambda x: x["count"], reverse=True)
                    return [m for m in sorted_meds[:50]]
                
                # Adaptive windowing
                for window_days in [30, 60, 90, 365]:
                    medicines = extract_counts_for_window(window_days)
                    if len(medicines) >= 20:
                        break
        except Exception as e:
            print("Failed to fetch dynamic top drugs from Supabase:", e)
            
    # Fallback/Merge with standard essential list if dynamic fetch is too small (cold start)
    baseline_medicines = [
        {
            "name": "Paracetamol 500mg", 
            "generic_name": "Acetaminophen", 
            "uses": "Fever, Pain relief", 
            "warnings": "Liver damage in overdose", 
            "interactions": "Alcohol, Warfarin", 
            "dosage": "500mg-1000mg every 4-6 hours",
            "rxcui": "198440",
            "ndc": "50580-449-10"
        },
        {
            "name": "Metformin HCl 500mg", 
            "generic_name": "Metformin", 
            "uses": "Type 2 Diabetes", 
            "warnings": "Lactic acidosis", 
            "interactions": "Iodinated contrast", 
            "dosage": "500mg twice daily",
            "rxcui": "860975",
            "ndc": "00093-7212-01"
        },
        {
            "name": "Amoxicillin 500mg", 
            "generic_name": "Amoxicillin", 
            "uses": "Bacterial infections", 
            "warnings": "Penicillin allergy", 
            "interactions": "Methotrexate", 
            "dosage": "500mg every 8 hours",
            "rxcui": "308182",
            "ndc": "00093-3109-01"
        },
        {
            "name": "Ibuprofen 400mg", 
            "generic_name": "Ibuprofen", 
            "uses": "Pain, inflammation", 
            "warnings": "Stomach ulcers, GI bleeding", 
            "interactions": "Aspirin, blood thinners", 
            "dosage": "400mg every 6-8 hours",
            "rxcui": "5640",
            "ndc": "00093-0047-01"
        },
        {
            "name": "Omeprazole 20mg", 
            "generic_name": "Omeprazole", 
            "uses": "Acid reflux, GERD", 
            "warnings": "Low magnesium with long-term use", 
            "interactions": "Clopidogrel", 
            "dosage": "20mg once daily before meal",
            "rxcui": "7646",
            "ndc": "00093-0058-01"
        },
        {
            "name": "Atorvastatin 40mg", 
            "generic_name": "Atorvastatin", 
            "uses": "High cholesterol", 
            "warnings": "Muscle pain, liver problems", 
            "interactions": "Grapefruit juice", 
            "dosage": "40mg once daily",
            "rxcui": "83367",
            "ndc": "00093-0155-01"
        },
        {
            "name": "Amlodipine 5mg", 
            "generic_name": "Amlodipine", 
            "uses": "High blood pressure", 
            "warnings": "Swelling of ankles/feet", 
            "interactions": "Simvastatin", 
            "dosage": "5mg once daily",
            "rxcui": "1760",
            "ndc": "00093-0026-01"
        },
        {
            "name": "Cetirizine 10mg", 
            "generic_name": "Cetirizine", 
            "uses": "Allergies", 
            "warnings": "May cause drowsiness", 
            "interactions": "Alcohol, sedatives", 
            "dosage": "10mg once daily",
            "rxcui": "20610",
            "ndc": "00093-0010-01"
        },
        {
            "name": "Losartan 50mg", 
            "generic_name": "Losartan", 
            "uses": "High blood pressure", 
            "warnings": "Fetal toxicity", 
            "interactions": "Potassium supplements", 
            "dosage": "50mg once daily",
            "rxcui": "52175",
            "ndc": "00093-0080-01"
        },
        {
            "name": "Pantoprazole 40mg", 
            "generic_name": "Pantoprazole", 
            "uses": "Acid reflux", 
            "warnings": "Bone fractures", 
            "interactions": "Methotrexate", 
            "dosage": "40mg once daily",
            "rxcui": "38221",
            "ndc": "00093-0040-01"
        }
    ]

    if len(medicines) < 20:
        # Merge, prioritizing dynamic results
        existing_names = {m["name"].lower() for m in medicines}
        for bm in baseline_medicines:
            if bm["name"].lower() not in existing_names:
                medicines.append(bm)

    return {"medicines": medicines}


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
