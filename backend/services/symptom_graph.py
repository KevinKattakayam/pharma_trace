"""
Symptom-to-drug safety checker using LangGraph and Groq.
Identifies OTC medicines for symptoms, screens against India Schedule H/H1/X restrictions,
and evaluates cumulative regimen safety (therapeutic duplication, eGFR/hepatic contraindications).
"""
from typing import Optional, TypedDict

import structlog
from langgraph.graph import END, StateGraph

from config import get_settings
from services.groq_ai import _groq_chat

logger = structlog.get_logger()

class SymptomSafetyState(TypedDict, total=False):
    symptoms: str
    current_medications: list[str]
    patient_info: Optional[dict]
    
    # Intermediate
    suggested_otcs: list[str]
    interactions_results: dict
    error: Optional[str]
    
    # Output
    safe_options: list[dict]
    unsafe_options: list[dict]
    summary: str


async def otc_suggester_node(state: SymptomSafetyState) -> dict:
    """Agent: Suggests OTC medications based on symptoms with patient health profile context."""
    settings = get_settings()
    
    if not settings.groq_api_key:
        logger.warning("symptom_graph_missing_api_key", detail="AI clinical advisory service unconfigured")
        return {"suggested_otcs": [], "error": "AI clinical advisory service unconfigured"}
        
    raw_symptoms = state.get("symptoms", "").strip()
    if not raw_symptoms:
        return {"suggested_otcs": [], "error": "No symptoms provided for clinical analysis."}

    # 1. SEMANTIC CACHING: Check if a semantically equivalent query was recently processed (<5ms)
    from services.semantic_cache import get_semantic_cache
    semantic_cache = get_semantic_cache()
    cached_response = await semantic_cache.get_semantic_match("symptom_graph", raw_symptoms)
    if cached_response and isinstance(cached_response, dict) and cached_response.get("suggested_otcs"):
        logger.info("symptom_graph_cache_hit", symptoms=raw_symptoms[:50])
        return cached_response

    patient_info = state.get("patient_info", {})
    patient_ctx = ""
    if patient_info:
        age = patient_info.get("age", "Unknown")
        egfr = patient_info.get("egfr", "Normal")
        hepatic = patient_info.get("hepatic_status", "Normal")
        preg = patient_info.get("pregnancy", "None")
        patient_ctx = (
            f"\nPATIENT HEALTH PROFILE:\n- Age: {age}\n- Renal eGFR: {egfr} mL/min/1.73m²\n"
            f"- Hepatic Status: {hepatic}\n- Pregnancy/Lactation: {preg}\n\n"
            "CRITICAL SAFETY RULE: If renal eGFR < 30 or hepatic impairment is indicated, strictly avoid "
            "hepatotoxic or nephrotoxic OTCs (e.g., high-dose NSAIDs or excessive Paracetamol)."
        )

    prompt = f"""You are a clinical pharmacist AI specializing in Indian pharmaceutical regulations (CDSCO/DPCO).
The patient reports these symptoms: "{raw_symptoms}".{patient_ctx}

What are 3-5 common over-the-counter (OTC) active ingredients (generic names) that treat these symptoms and are legally available WITHOUT a prescription in India?

IMPORTANT regulatory constraints:
- Only suggest drugs classified as OTC or General Sale List (GSL) in India.
- Do NOT suggest drugs on India's Schedule H, H1, or X lists (these require mandatory prescriptions in India).
- Note that some NSAIDs or antihistamines available OTC in the US/UK are prescription-only in India — verify carefully.
- Use INN (International Nonproprietary Name) generic names, not brand names.

Return ONLY a JSON object with an "otcs" key containing an array of strings.
Example: {{"otcs": ["Paracetamol", "Cetirizine", "Oral Rehydration Salts"]}}"""
    
    try:
        # Use centralized circuit-breakered, PHI-protected Groq chat client
        messages = [
            {"role": "system", "content": "You are a licensed clinical pharmacist specializing in Indian drug regulations."},
            {"role": "user", "content": prompt}
        ]
        result = await _groq_chat(messages, max_tokens=350, json_mode=True)
        
        if not result or not isinstance(result, dict):
            logger.warning("symptom_graph_llm_failure", detail="LLM returned empty or non-dict response")
            return {"suggested_otcs": [], "error": "AI clinical advisory service temporarily unavailable."}
            
        otcs = result.get("otcs", [])
        if not isinstance(otcs, list) or len(otcs) == 0:
            # Fallback check if LLM returned values directly under another key
            for v in result.values():
                if isinstance(v, list) and len(v) > 0:
                    otcs = v
                    break
                    
        if not isinstance(otcs, list) or len(otcs) == 0:
            logger.warning("symptom_graph_empty_otcs", result=result)
            return {"suggested_otcs": [], "error": "Could not identify definitive OTC options for these symptoms."}
            
        # Clean drug names
        otcs = [str(o).strip().title() for o in otcs if o and isinstance(o, str)]
            
        # 2. BLOOM FILTER & HARD GATE: O(1) screen against Schedule H, H1, X
        filtered_otcs = []
        from services.bloom_filter import get_bloom_service
        bloom = get_bloom_service()
        await bloom.initialize()

        from services.supabase import get_supabase
        db = get_supabase()
        
        for drug in otcs:
            clean_drug = drug.lower().strip()
            # If Bloom filter guarantees it is NOT restricted, skip DB query!
            if bloom.is_definitely_not_restricted(clean_drug):
                filtered_otcs.append(drug)
                continue

            try:
                # Fallback: Full DB query only if Bloom filter says it MIGHT be restricted
                res = await db.query(
                    "schedule_classifications",
                    select="schedule",
                    filters={"generic_name": clean_drug},
                    limit=1
                )
                if res and res[0].get("schedule") in ["H", "H1", "X"]:
                    logger.info("symptom_graph_filtered_restricted_drug", drug=drug, schedule=res[0].get("schedule"))
                    continue
                filtered_otcs.append(drug)
            except Exception as e:
                logger.error("symptom_graph_schedule_query_error", drug=drug, error=str(e))
                continue

        if not filtered_otcs:
            return {"suggested_otcs": [], "error": "All identified treatments require a valid doctor prescription (Schedule H/H1/X)."}
            
        res_payload = {"suggested_otcs": filtered_otcs, "error": None}
        # Store validated result in semantic cache
        await semantic_cache.set_semantic_match("symptom_graph", raw_symptoms, res_payload)
        logger.info("symptom_graph_otcs_suggested", otcs=filtered_otcs)
        return res_payload
    except Exception as e:
        logger.error("symptom_graph_otc_suggester_failed", error=str(e), exc_info=True)
        return {"suggested_otcs": [], "error": f"Clinical resolution error: {str(e)}"}


async def interaction_checker_node(state: SymptomSafetyState) -> dict:
    """Agent: Checks interactions and Cumulative Therapeutic Duplication between suggested OTCs and current medications."""
    # If previous node encountered an error or found no OTCs, short-circuit
    if state.get("error") or not state.get("suggested_otcs"):
        return {
            "interactions_results": {},
            "safe_options": [],
            "unsafe_options": []
        }

    from services.interactions import check_all_interactions
    
    current_meds = state.get("current_medications", [])
    suggested_otcs = state.get("suggested_otcs", [])
    patient_info = state.get("patient_info", {})
    
    interactions_results = {}
    safe_options = []
    unsafe_options = []
    
    # Cumulative Toxicity & Therapeutic Duplication screening classes
    nsaids = {"ibuprofen", "diclofenac", "aceclofenac", "naproxen", "aspirin", "mefenamic acid", "etoricoxib", "ketorolac"}
    acetaminophen = {"paracetamol", "acetaminophen", "dolo", "crocin", "calpol", "panadol", "tylenol", "sinarest", "saridon"}
    antihistamines = {"cetirizine", "levocetirizine", "loratadine", "desloratadine", "fexofenadine", "diphenhydramine", "chlorpheniramine"}
    
    for otc in suggested_otcs:
        otc_clean = otc.lower().strip()
        duplication_reason = ""
        dup_severity = 0
        
        # 1. Check Cumulative Therapeutic Duplication against current medications
        for cm in current_meds:
            cm_clean = cm.lower().strip()
            if otc_clean in nsaids and any(n in cm_clean for n in nsaids):
                duplication_reason = f"Therapeutic Duplication: Combining {otc.title()} with {cm.title()} drastically increases GI bleeding and acute renal injury risk."
                dup_severity = 4
            elif otc_clean in acetaminophen and any(a in cm_clean for a in acetaminophen):
                duplication_reason = f"Cumulative Toxicity: Combining {otc.title()} with {cm.title()} risks exceeding maximum safe acetaminophen dosage (4000 mg/day) and hepatotoxicity."
                dup_severity = 4
            elif otc_clean in antihistamines and any(h in cm_clean for h in antihistamines):
                duplication_reason = f"Therapeutic Duplication: Combining {otc.title()} with {cm.title()} increases additive sedation and CNS depression."
                dup_severity = 3
                
        # 2. Check Patient Profile Contraindications (Renal/Hepatic)
        if patient_info:
            egfr = patient_info.get("egfr")
            hepatic = str(patient_info.get("hepatic_status", "")).lower()
            if (egfr and isinstance(egfr, (int, float)) and egfr < 30) and otc_clean in nsaids:
                duplication_reason = f"Renal Contraindication: NSAIDs like {otc.title()} are contraindicated in severe renal impairment (eGFR < 30 mL/min/1.73m²)."
                dup_severity = 4
            elif ("impaired" in hepatic or "cirrhosis" in hepatic or "failure" in hepatic) and otc_clean in acetaminophen:
                duplication_reason = f"Hepatic Contraindication: High-dose {otc.title()} must be avoided in hepatic impairment/cirrhosis."
                dup_severity = 4

        # Check interactions between this OTC and all current meds
        drug_list = [otc] + current_meds
        result = await check_all_interactions(drug_list)
        interactions_results[otc] = result
        
        max_severity = dup_severity
        ixns = result.get("interactions", [])
        
        # We only care about interactions involving the OTC
        relevant_ixns = []
        for ix in ixns:
            if ix["drug_a"].lower() == otc.lower() or ix["drug_b"].lower() == otc.lower():
                relevant_ixns.append(ix)
                sev_raw = ix.get("severity", "")
                sev = sev_raw.get("value", "") if isinstance(sev_raw, dict) else str(sev_raw).lower()
                sev_val = {"minor": 1, "moderate": 2, "major": 3, "contraindicated": 4}.get(sev, 0)
                if sev_val > max_severity:
                    max_severity = sev_val
                    
        if max_severity >= 3:  # Major or Contraindicated
            sev_label = {1: "minor", 2: "moderate", 3: "major", 4: "contraindicated"}.get(max_severity, "unknown")
            reason_text = duplication_reason if duplication_reason else f"Interacts with current medication (Severity: {sev_label})"
            unsafe_options.append({
                "drug": otc,
                "reason": reason_text,
                "interactions": relevant_ixns
            })
        else:
            safe_options.append({
                "drug": otc,
                "interactions": relevant_ixns
            })
            
    logger.info("symptom_graph_interactions_checked", safe=len(safe_options), unsafe=len(unsafe_options))
    return {
        "interactions_results": interactions_results,
        "safe_options": safe_options,
        "unsafe_options": unsafe_options
    }


async def summary_node(state: SymptomSafetyState) -> dict:
    """Agent: Generates an enterprise clinical advisory report summarizing findings and safety warnings."""
    if state.get("error"):
        error_msg = state.get("error")
        summary = (
            "### 🚨 Clinical Advisory Alert\n\n"
            f"**Status:** Unable to complete automated over-the-counter (OTC) resolution.\n\n"
            f"**Clinical Note:** {error_msg}\n\n"
            "**Pharmacist Guidance:** Please consult a licensed physician or clinical pharmacist directly for personalized medical evaluation."
        )
        return {"summary": summary}

    suggested_otcs = state.get("suggested_otcs", [])
    if not suggested_otcs:
        summary = (
            "### ℹ️ Clinical Advisory Notice\n\n"
            "**Status:** No safe over-the-counter (OTC) options could be identified for the reported symptoms within Indian general sale regulations.\n\n"
            "**Pharmacist Guidance:** Your symptoms may require prescription-strength medical evaluation (Schedule H/H1/X screening). Please consult a healthcare professional."
        )
        return {"summary": summary}

    safe_options = state.get("safe_options", [])
    unsafe_options = state.get("unsafe_options", [])
    current_meds = state.get("current_medications", [])
    patient_info = state.get("patient_info", {})

    lines = ["### 🩺 Clinical OTC Resolution & Regimen Safety Report\n"]
    lines.append(f"**Reported Symptoms:** {state.get('symptoms', 'None reported')}")
    if current_meds:
        lines.append(f"**Current Regimen:** {', '.join([m.title() for m in current_meds])}")
    if patient_info:
        age = patient_info.get("age", "Unknown")
        egfr = patient_info.get("egfr", "Normal")
        hepatic = patient_info.get("hepatic_status", "Normal")
        lines.append(f"**Patient Profile:** Age: {age} | eGFR: {egfr} mL/min/1.73m² | Hepatic: {str(hepatic).title()}")
    lines.append("")

    if safe_options:
        lines.append("#### ✅ Recommended Safe OTC Options")
        for opt in safe_options:
            drug_name = opt["drug"].title()
            lines.append(f"- **{drug_name}**: Verified safe with current medication regimen and health profile.")
        lines.append("")

    if unsafe_options:
        lines.append("#### ⚠️ Contraindicated / Unsafe Options (DO NOT TAKE)")
        for opt in unsafe_options:
            drug_name = opt["drug"].title()
            reason = opt.get("reason", "Potential adverse drug interaction.")
            lines.append(f"- **{drug_name}**: {reason}")
        lines.append("")

    lines.append("#### 📋 Pharmacist Guidance")
    if safe_options:
        safe_names = [opt["drug"].title() for opt in safe_options]
        lines.append(
            f"Based on automated regulatory and pharmacological screening, **{', '.join(safe_names)}** "
            "may be considered for symptom relief. Always read official packaging labels and adhere strictly to standard dosing guidelines."
        )
    else:
        lines.append(
            "No suggested OTC medications were found to be completely safe with your current medication regimen and health profile. "
            "Please consult your physician before taking any new medication."
        )

    summary_text = "\n".join(lines)
    logger.info("symptom_graph_summary_generated", safe_count=len(safe_options), unsafe_count=len(unsafe_options))
    return {"summary": summary_text}


# Build the LangGraph
workflow = StateGraph(SymptomSafetyState)

workflow.add_node("otc_suggester", otc_suggester_node)
workflow.add_node("interaction_checker", interaction_checker_node)
workflow.add_node("summarizer", summary_node)

workflow.set_entry_point("otc_suggester")
workflow.add_edge("otc_suggester", "interaction_checker")
workflow.add_edge("interaction_checker", "summarizer")
workflow.add_edge("summarizer", END)

symptom_safety_app = workflow.compile()
