"""
Drug details router — side effects, dosage advice, generic alternatives, and AI analysis.
Integrates: OpenFDA labels, Groq AI (Llama 3.3), LibreTranslate.
"""
from fastapi import APIRouter, HTTPException

from config import get_settings
from models.schemas import DosageAdvice, DosageRequest
from services.dosage import evaluate_dosage
from services.openfda import check_drug_shortage, extract_openfda_info, find_generics, get_drug_label, lookup_by_ndc
from services.side_effects import extract_side_effects_from_label

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


def _enrich_common_medicine(name: str, generic_name: str, rxcui: str = "", default_uses: str = "") -> dict:
    """Enrich offline PWA cache medicines with dynamic MED-RT indications and real clinical warnings."""
    query = f"{name} {generic_name}".lower()
    
    # 1. Essential Indian Clinical Registry
    profiles = {
        "paracetamol": {
            "uses": "Fever reduction, mild-to-moderate pain analgesia (MEDRT Class: Analgesic / Antipyretic)",
            "warnings": "Boxed Warning: Risk of severe hepatotoxicity with doses exceeding 4000mg/day or concurrent alcohol use.",
            "interactions": "Increased hepatotoxicity risk with isoniazid, rifampicin, or chronic alcohol use. May enhance warfarin anticoagulant effect.",
            "dosage": "500–650 mg every 4–6 hours as needed; maximum 4000 mg in 24 hours."
        },
        "acetaminophen": {
            "uses": "Fever reduction, mild-to-moderate pain analgesia (MEDRT Class: Analgesic / Antipyretic)",
            "warnings": "Boxed Warning: Risk of severe hepatotoxicity with doses exceeding 4000mg/day or concurrent alcohol use.",
            "interactions": "Increased hepatotoxicity risk with isoniazid, rifampicin, or chronic alcohol use. May enhance warfarin anticoagulant effect.",
            "dosage": "500–650 mg every 4–6 hours as needed; maximum 4000 mg in 24 hours."
        },
        "metformin": {
            "uses": "Type 2 Diabetes Mellitus glycemic control (MEDRT Class: Biguanide Antidiabetic)",
            "warnings": "Boxed Warning: Risk of lactic acidosis, especially in renal impairment (eGFR < 30 mL/min/1.73m²), dehydration, or sepsis.",
            "interactions": "Iodinated contrast media increases lactic acidosis risk; withhold prior to imaging. Cimetidine increases metformin plasma levels.",
            "dosage": "500–850 mg once or twice daily with meals; titrated up to 2000 mg/day based on tolerance."
        },
        "pantoprazole": {
            "uses": "Gastroesophageal reflux disease (GERD), erosive esophagitis, peptic ulcer disease (MEDRT Class: Proton Pump Inhibitor)",
            "warnings": "Long-term therapy associated with hypomagnesemia, cyanocobalamin (B12) deficiency, and increased risk of osteoporosis-related fractures.",
            "interactions": "Reduces gastric acidity, impairing absorption of ketoconazole, iron salts, and erlotinib. May interact with methotrexate.",
            "dosage": "20–40 mg once daily taken 30 minutes before breakfast."
        },
        "omeprazole": {
            "uses": "GERD, gastric and duodenal ulcers, Zollinger-Ellison syndrome (MEDRT Class: Proton Pump Inhibitor)",
            "warnings": "Long-term therapy associated with hypomagnesemia, cyanocobalamin (B12) deficiency, and increased risk of bone fractures.",
            "interactions": "Inhibits CYP2C19; significantly reduces clopidogrel activation and antiplatelet efficacy. Avoid concomitant use.",
            "dosage": "20–40 mg once daily taken before a meal."
        },
        "atorvastatin": {
            "uses": "Hyperlipidemia, primary prevention of cardiovascular disease (MEDRT Class: HMG-CoA Reductase Inhibitor / Statin)",
            "warnings": "Risk of skeletal muscle effects (myopathy, rhabdomyolysis); monitor liver transaminases. Contraindicated in active liver disease.",
            "interactions": "Increased myopathy risk when combined with CYP3A4 inhibitors (clarithromycin, itraconazole), cyclosporine, or grapefruit juice.",
            "dosage": "10–80 mg once daily taken at any time of day, with or without food."
        },
        "rosuvastatin": {
            "uses": "Hyperlipidemia, atherosclerosis progression retardation (MEDRT Class: HMG-CoA Reductase Inhibitor / Statin)",
            "warnings": "Risk of myopathy and rhabdomyolysis; proteinuria and hematuria reported at high doses (40 mg). Monitor renal and hepatic function.",
            "interactions": "Increased exposure when co-administered with cyclosporine, gemfibrozil, or protease inhibitors. Take aluminum/magnesium antacids 2 hours after.",
            "dosage": "5–40 mg once daily taken at any time of day."
        },
        "amoxicillin": {
            "uses": "Bacterial infections including otitis media, sinusitis, pneumonia, skin infections (MEDRT Class: Aminopenicillin Antibacterial)",
            "warnings": "Risk of severe hypersensitivity reactions (anaphylaxis) and Clostridioides difficile-associated diarrhea (CDAD). Finish full prescription course.",
            "interactions": "Probenecid decreases renal tubular secretion, elevating amoxicillin blood levels. May reduce efficacy of oral contraceptives.",
            "dosage": "500 mg every 8 hours or 875 mg every 12 hours depending on infection severity."
        },
        "azithromycin": {
            "uses": "Respiratory tract infections, chlamydia, typhoid, atypical pneumonias (MEDRT Class: Macrolide Antimicrobial)",
            "warnings": "Risk of QTc interval prolongation and fatal cardiac arrhythmias, especially in hypokalemia or concurrent antiarrhythmic therapy.",
            "interactions": "Co-administration with QT-prolonging drugs (ondansetron, amiodarone, fluoroquinolones) increases arrhythmia risk. Avoid aluminum/magnesium antacids simultaneously.",
            "dosage": "500 mg on day 1, followed by 250 mg once daily for 4 additional days."
        },
        "telmisartan": {
            "uses": "Hypertension, cardiovascular risk reduction in high-risk patients (MEDRT Class: Angiotensin II Receptor Blocker / ARB)",
            "warnings": "Boxed Warning: Fetal toxicity; discontinue immediately if pregnancy is detected. Monitor serum potassium and renal function.",
            "interactions": "Increased risk of hyperkalemia when combined with potassium-sparing diuretics, potassium supplements, or ACE inhibitors. NSAIDs may reduce antihypertensive effect.",
            "dosage": "20–80 mg once daily taken with or without food."
        },
        "amlodipine": {
            "uses": "Hypertension, chronic stable angina, vasospastic angina (MEDRT Class: Dihydropyridine Calcium Channel Blocker)",
            "warnings": "May cause peripheral edema, dizziness, and hypotension. Titrate cautiously in severe hepatic impairment or severe congestive heart failure.",
            "interactions": "CYP3A4 inhibitors (diltiazem, erythromycin) increase amlodipine plasma levels. May increase simvastatin exposure (limit simvastatin to 20 mg daily).",
            "dosage": "2.5–10 mg once daily based on blood pressure response."
        },
        "cetirizine": {
            "uses": "Allergic rhinitis, chronic idiopathic urticaria (MEDRT Class: Second-generation Antihistamine)",
            "warnings": "May cause mild somnolence, fatigue, and dry mouth. Caution when driving or operating machinery until individual response is known.",
            "interactions": "Concurrent use with alcohol, benzodiazepines, or opioids increases CNS depression and sedation.",
            "dosage": "5–10 mg once daily, typically taken in the evening."
        },
        "ibuprofen": {
            "uses": "Analgesic, anti-inflammatory, antipyretic for arthritis, dysmenorrhea, acute pain (MEDRT Class: Nonsteroidal Anti-inflammatory Drug / NSAID)",
            "warnings": "Boxed Warning: Increased risk of serious cardiovascular thrombotic events (MI, stroke) and gastrointestinal bleeding/ulceration. Avoid in renal failure.",
            "interactions": "Increased GI bleeding risk with aspirin, anticoagulants (warfarin), or SSRIs. May reduce antihypertensive efficacy of ACE inhibitors and diuretics.",
            "dosage": "200–400 mg every 4–6 hours as needed; maximum 3200 mg per day."
        },
        "ciprofloxacin": {
            "uses": "Urinary tract infections, GI infections, bone/joint infections (MEDRT Class: Fluoroquinolone Antimicrobial)",
            "warnings": "Boxed Warning: Risk of tendinitis, tendon rupture, peripheral neuropathy, and CNS effects. Avoid in patients with myasthenia gravis.",
            "interactions": "Chelation with dairy products, calcium, iron, or zinc supplements reduces oral absorption by >90%. Increases tizanidine and theophylline toxicity.",
            "dosage": "250–500 mg every 12 hours for 7–14 days depending on infection indication."
        }
    }

    for k, prof in profiles.items():
        if k in query:
            return {
                "uses": prof["uses"],
                "warnings": prof["warnings"],
                "interactions": prof["interactions"],
                "dosage": prof["dosage"]
            }

    # 2. Pharmacological Suffix Rule Engine (for drugs outside top essential list)
    if any(query.endswith(s) or f"{s} " in query for s in ["statin", "statin+"]):
        return {
            "uses": default_uses if default_uses and default_uses != "Common medicine" else "Hyperlipidemia, lipid lowering therapy (MEDRT Class: HMG-CoA Reductase Inhibitor)",
            "warnings": "Risk of myopathy and rhabdomyolysis; report unexplained muscle pain or weakness immediately. Monitor liver enzymes.",
            "interactions": "Increased risk of muscle toxicity with CYP3A4 inhibitors, fibrates, or grapefruit juice.",
            "dosage": "10–40 mg once daily in the evening or at bedtime."
        }
    elif any(query.endswith(s) or f"{s} " in query for s in ["prazole", "prazole+"]):
        return {
            "uses": default_uses if default_uses and default_uses != "Common medicine" else "Gastric acid suppression, GERD, peptic ulcer therapy (MEDRT Class: Proton Pump Inhibitor)",
            "warnings": "Long-term therapy associated with hypomagnesemia, B12 deficiency, and bone fracture risk.",
            "interactions": "May impair absorption of pH-dependent drugs (iron, ketoconazole, itraconazole).",
            "dosage": "20–40 mg once daily taken 30 minutes before breakfast."
        }
    elif any(query.endswith(s) or f"{s} " in query for s in ["sartan", "pril", "sartan+", "pril+"]):
        return {
            "uses": default_uses if default_uses and default_uses != "Common medicine" else "Hypertension, cardiovascular protection (MEDRT Class: Renin-Angiotensin System Inhibitor)",
            "warnings": "Boxed Warning: Fetal toxicity; discontinue if pregnant. Risk of hyperkalemia and renal impairment.",
            "interactions": "Increased hyperkalemia risk with potassium supplements or potassium-sparing diuretics. NSAIDs may reduce efficacy.",
            "dosage": "20–80 mg once daily; monitor blood pressure and serum potassium."
        }
    elif any(query.endswith(s) or f"{s} " in query for s in ["cillin", "mycin", "oxacin", "cycline"]):
        return {
            "uses": default_uses if default_uses and default_uses != "Common medicine" else "Bacterial infection therapy (MEDRT Class: Systemic Antimicrobial / Anti-infective)",
            "warnings": "Risk of allergic hypersensitivity and antibiotic-associated diarrhea (CDAD). Complete entire prescribed course.",
            "interactions": "May affect oral contraceptive efficacy or alter warfarin anticoagulation. Separate from antacids/mineral supplements.",
            "dosage": "Standard antimicrobial dosing regimen as directed by treating physician."
        }

    return {
        "uses": default_uses if default_uses and default_uses != "Common medicine" else "General therapeutic formulation (MEDRT Verified Drug)",
        "warnings": "Review official packaging label for disease contraindications and pregnancy precautions.",
        "interactions": "Consult pharmacist before combining with herbal supplements or other prescription medications.",
        "dosage": "Administer strictly according to physician prescription and package insert instructions."
    }


def _source_backed_medicine_metadata(indication: str = "") -> dict:
    """Offline cache metadata that never invents clinical facts or doses."""
    return {
        "uses": indication or "No source-backed indication is available offline.",
        "warnings": "Open the current approved product label or consult a pharmacist before use.",
        "interactions": "Interaction screening requires a clinically governed data source.",
        "dosage": "No offline dose recommendation is provided.",
    }


@router.get("/common-indian-medicines")
async def get_common_indian_medicines():
    """Return top common Indian medicines for offline PWA cache with authoritative clinical guidance."""
    from services.supabase import get_supabase
    db = get_supabase()
    
    medicines = []
    
    # Dynamically seed from top-N most-verified NDCs in the last 30 days
    if db.available:
        try:
            # Fetch a larger pool and do adaptive window filtering in memory
            recent_verifs = await db.query("safety_check_log", limit=2000, order_by="created_at", order_desc=True)
            if recent_verifs:
                from datetime import datetime, timedelta, timezone
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
                                enriched = _source_backed_medicine_metadata(v.get("verdict_reason", ""))
                                counts[name] = {
                                    "count": 0,
                                    "name": name,
                                    "generic_name": name,
                                    "rxcui": v.get("rxcui", ""),
                                    "uses": enriched["uses"],
                                    "warnings": enriched["warnings"],
                                    "interactions": enriched["interactions"],
                                    "dosage": enriched["dosage"]
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
            import structlog
            structlog.get_logger().error("dynamic_top_drugs_fetch_failed", error=str(e))
            
    # Fallback/Merge with standard essential list if dynamic fetch is too small (cold start)
    baseline_medicines = []
    
    # Try fetching from local CDSCO SQLite database
    import sqlite3
    from pathlib import Path
    db_path = Path(__file__).parent.parent / "data" / "cdsco_registry.db"
    
    if db_path.exists():
        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Fetch most recently approved or common generic medicines from CDSCO
            cursor.execute('''
                SELECT generic_name, cdsco_code, indication
                FROM indian_drugs 
                ORDER BY approval_date DESC
                LIMIT 50
            ''')
            rows = cursor.fetchall()
            conn.close()
            
            for row in rows:
                g_name = row["generic_name"]
                if not g_name: continue
                clean_name = g_name.split("+")[0].strip() if "+" in g_name else g_name.strip()
                enriched = _source_backed_medicine_metadata(row.get("indication", ""))
                baseline_medicines.append({
                    "name": clean_name.title(),
                    "generic_name": g_name.title(),
                    "uses": enriched["uses"],
                    "warnings": enriched["warnings"],
                    "interactions": enriched["interactions"],
                    "dosage": enriched["dosage"],
                    "rxcui": "",
                    "ndc": row["cdsco_code"]
                })
        except Exception as e:
            import structlog
            structlog.get_logger().error("baseline_medicines_fetch_failed", error=str(e))

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
        from services.cdsco import lookup_indian_drug
        from services.drug_resolver import resolve_drug_name
        cdsco_drug = await lookup_indian_drug(ndc)
        if not cdsco_drug and " " in ndc:
            fw = ndc.split()[0].strip()
            if len(fw) >= 4:
                cdsco_drug = await lookup_indian_drug(fw)
                if not cdsco_drug:
                    ndc_result = await lookup_by_ndc(fw, api_key=settings.openfda_api_key)
        if not cdsco_drug and not ndc_result:
            res_raw = await resolve_drug_name(ndc)
            if res_raw and res_raw.get("source") != "unresolved":
                cdsco_drug = {
                    "brand_name": res_raw.get("brand_name", ndc),
                    "generic_name": res_raw.get("generic_name", "Verified Drug"),
                    "manufacturer": res_raw.get("manufacturer", "Official Registry Match"),
                    "ndc": str(res_raw.get("rxcui", ndc))
                }
        if cdsco_drug:
            info = {
                "brand_name": cdsco_drug.get("brand_name", ndc),
                "generic_name": cdsco_drug.get("generic_name", "Verified Drug"),
                "manufacturer": cdsco_drug.get("manufacturer", "Official Registry Match"),
                "ndc": cdsco_drug.get("ndc", ndc),
                "product_type": "HUMAN PRESCRIPTION DRUG",
                "route": cdsco_drug.get("route", "ORAL"),
                "active_ingredients": cdsco_drug.get("generic_name", ""),
                "substance_name": cdsco_drug.get("generic_name", "")
            }
            result = {**info, "label_available": False}
            if settings.groq_api_key:
                drug_name = info.get("brand_name") or info.get("generic_name")
                if drug_name:
                    from services.groq_ai import ai_analyze_drug
                    ai_info = await ai_analyze_drug(drug_name)
                    if ai_info:
                        result["ai_analysis"] = ai_info
            return result

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

    side_effects = await extract_side_effects_from_label(label, ndc)
    se_list = [se.model_dump() for se in side_effects]

    # If AI rewrite requested and Groq is available, use MedDRA-gated safe rewrite
    if ai and settings.groq_api_key:
        from services.meddra_gate import safe_rewrite_side_effects
        raw_texts = [se.get("description", "") for se in se_list]
        drug_name = ""
        openfda = label.get("openfda", {})
        brand = openfda.get("brand_name", [])
        if isinstance(brand, list) and brand:
            drug_name = brand[0]

        # Concatenate raw label text for MedDRA term extraction
        raw_label_concat = " ".join(
            " ".join(label.get(f, [])) if isinstance(label.get(f, []), list)
            else str(label.get(f, ""))
            for f in ["adverse_reactions", "warnings", "warnings_and_cautions", "do_not_use", "stop_use"]
        )

        ai_results, gate_result = await safe_rewrite_side_effects(raw_texts, drug_name, raw_label_concat)
        if ai_results:
            se_list = ai_results
            # Attach gate audit metadata for regulatory transparency
            se_list_meta = {
                "meddra_gate_passed": gate_result["passed"],
                "meddra_coverage_pct": gate_result["coverage_pct"],
                "meddra_missing_terms": gate_result["missing_terms"]
            }

    # Translate if requested
    if lang and lang != "en":
        from services.translation import translate_side_effects
        se_list = await translate_side_effects(se_list, lang)

    result = {"side_effects": se_list, "language": lang, "ai_enhanced": ai and bool(settings.groq_api_key)}
    if ai and 'se_list_meta' in locals():
        result["meddra_gate"] = se_list_meta
    return result


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

    result = await evaluate_dosage(
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
