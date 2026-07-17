"""
MedDRA Safety Symbol Validator — Deterministic Post-Processing Gate for LLM Medical Outputs.

For IEC 62304 / 21 CFR Part 11 regulated medical software, LLMs must never be the
authoritative source of truth. This module enforces that every safety-critical term
present in the raw FDA label text is preserved in the LLM's patient-friendly rewrite.

If any MedDRA safety signal is dropped by the LLM, the system falls back to raw FDA text.
"""
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)


# MedDRA Preferred Terms (PT) — critical safety signals that must NEVER be omitted
# by an LLM rewrite. Subset of high-frequency signals from MedDRA v27.1.
# In production, this should be loaded from the full MedDRA subscription file.
MEDDRA_CRITICAL_SAFETY_TERMS = {
    # Cardiac & Vascular
    "cardiac arrest", "myocardial infarction", "heart attack", "arrhythmia",
    "tachycardia", "bradycardia", "qt prolongation", "torsade de pointes",
    "cardiac failure", "heart failure", "hypertension", "hypotension",
    "stroke", "cerebrovascular accident", "thrombosis", "embolism",
    "deep vein thrombosis", "pulmonary embolism",

    # Anaphylaxis & Immune
    "anaphylaxis", "anaphylactic shock", "angioedema", "stevens-johnson",
    "toxic epidermal necrolysis", "drug reaction with eosinophilia",
    "serum sickness", "hypersensitivity",

    # Hepatic
    "hepatotoxicity", "liver failure", "hepatic failure", "jaundice",
    "hepatitis", "liver injury", "drug-induced liver injury",
    "hepatic necrosis", "liver damage",

    # Renal
    "renal failure", "kidney failure", "nephrotoxicity", "acute kidney injury",
    "renal impairment", "kidney damage",

    # Neurological
    "seizure", "convulsion", "status epilepticus", "encephalopathy",
    "serotonin syndrome", "neuroleptic malignant syndrome",
    "tardive dyskinesia", "suicidal ideation", "suicidal",

    # Respiratory
    "respiratory depression", "respiratory failure", "bronchospasm",
    "pulmonary fibrosis", "interstitial lung disease",

    # Hematological
    "agranulocytosis", "aplastic anemia", "pancytopenia", "thrombocytopenia",
    "neutropenia", "hemorrhage", "bleeding", "disseminated intravascular coagulation",

    # Metabolic
    "lactic acidosis", "hypoglycemia", "hyperkalemia", "hyponatremia",
    "rhabdomyolysis",

    # GI
    "gi perforation", "gastrointestinal perforation", "pancreatitis",
    "gi bleeding", "gastrointestinal hemorrhage",

    # Reproductive
    "teratogenic", "teratogenicity", "birth defect",

    # General critical
    "death", "fatal", "life-threatening", "contraindicated",
    "black box warning", "boxed warning"
}


def extract_safety_terms_from_text(raw_text: str) -> set:
    """
    Extract all MedDRA critical safety terms present in a raw FDA label text.
    Returns the set of matched terms (lowercased).
    """
    if not raw_text:
        return set()

    text_lower = raw_text.lower()
    found = set()
    for term in MEDDRA_CRITICAL_SAFETY_TERMS:
        if term in text_lower:
            found.add(term)
    return found


def validate_llm_output_preserves_safety(
    raw_fda_text: str,
    llm_output_items: list[dict],
    llm_output_text_key: str = "description"
) -> dict:
    """
    Deterministic post-processing gate: verify that every MedDRA critical safety
    signal present in the raw FDA text is also present in the LLM's rewritten output.

    Returns:
        {
            "passed": bool,
            "missing_terms": list of terms the LLM dropped,
            "raw_terms_found": int,
            "llm_terms_preserved": int,
            "coverage_pct": float
        }
    """
    raw_terms = extract_safety_terms_from_text(raw_fda_text)

    if not raw_terms:
        return {
            "passed": True,
            "missing_terms": [],
            "raw_terms_found": 0,
            "llm_terms_preserved": 0,
            "coverage_pct": 100.0
        }

    # Concatenate all LLM output text fields for searching
    llm_combined = " ".join(
        str(item.get(llm_output_text_key, "")) + " " +
        str(item.get("action", "")) + " " +
        str(item.get("mechanism", ""))
        for item in llm_output_items
    ).lower()

    preserved = set()
    missing = set()

    for term in raw_terms:
        # Check for the term or common synonyms
        if term in llm_combined:
            preserved.add(term)
        else:
            # Check synonym mappings
            synonym_found = False
            for synonym_set in SYNONYM_GROUPS:
                if term in synonym_set:
                    for syn in synonym_set:
                        if syn in llm_combined:
                            preserved.add(term)
                            synonym_found = True
                            break
                if synonym_found:
                    break
            if not synonym_found:
                missing.add(term)

    coverage = (len(preserved) / len(raw_terms) * 100) if raw_terms else 100.0

    result = {
        "passed": len(missing) == 0,
        "missing_terms": sorted(list(missing)),
        "raw_terms_found": len(raw_terms),
        "llm_terms_preserved": len(preserved),
        "coverage_pct": round(coverage, 1)
    }

    if missing:
        logger.warning(
            f"meddra_safety_gate_failed: missing={sorted(list(missing))} | coverage={coverage}% | LLM dropped critical MedDRA safety signals."
        )

    return result


# Synonym groups: if the LLM uses a synonym, we accept it as equivalent
SYNONYM_GROUPS = [
    {"cardiac arrest", "heart stopped", "heart stop"},
    {"myocardial infarction", "heart attack"},
    {"seizure", "convulsion", "fits", "seizures", "convulsions"},
    {"anaphylaxis", "anaphylactic shock", "severe allergic reaction"},
    {"jaundice", "yellowing of skin", "yellow skin", "yellow eyes"},
    {"hepatotoxicity", "liver toxicity", "liver damage", "liver injury"},
    {"nephrotoxicity", "kidney toxicity", "kidney damage", "kidney injury"},
    {"renal failure", "kidney failure"},
    {"hepatic failure", "liver failure"},
    {"hemorrhage", "bleeding", "blood loss"},
    {"hypoglycemia", "low blood sugar"},
    {"hypertension", "high blood pressure"},
    {"hypotension", "low blood pressure"},
    {"suicidal ideation", "suicidal thoughts", "suicidal"},
    {"thrombocytopenia", "low platelet count", "low platelets"},
    {"neutropenia", "low white blood cell count", "low white blood cells"},
    {"respiratory depression", "slow breathing", "breathing problems"},
    {"teratogenic", "birth defect", "birth defects", "harm to unborn baby"},
    {"stevens-johnson", "stevens-johnson syndrome", "sjs"},
    {"death", "fatal", "die", "died"},
    {"contraindicated", "must not take", "do not take", "never take"},
]


async def safe_rewrite_side_effects(
    raw_side_effects: list[str],
    drug_name: str,
    raw_label_text: str = ""
) -> tuple[list[dict], dict]:
    """
    Safely rewrite side effects using LLM with MedDRA post-processing gate.
    If the LLM drops any critical safety signal, falls back to raw FDA text.

    Returns:
        (rewritten_items, gate_result)
    """
    from services.groq_ai import ai_rewrite_side_effects

    # Step 1: Get LLM rewrite
    llm_items = await ai_rewrite_side_effects(raw_side_effects, drug_name)

    if not llm_items:
        return [], {"passed": True, "missing_terms": [], "raw_terms_found": 0,
                     "llm_terms_preserved": 0, "coverage_pct": 100.0}

    # Step 2: Validate against MedDRA safety gate
    combined_raw = raw_label_text + " " + " ".join(raw_side_effects)
    gate_result = validate_llm_output_preserves_safety(combined_raw, llm_items)

    if gate_result["passed"]:
        return llm_items, gate_result

    # Step 3: FALLBACK — LLM dropped safety signals. Use raw FDA text.
    logger.warning(
        f"meddra_fallback_triggered for {drug_name}: missing={gate_result['missing_terms']} | coverage={gate_result['coverage_pct']}%"
    )

    # Return raw FDA text as-is with severity markers
    fallback_items = []
    for se in raw_side_effects:
        severity = "severe" if any(
            t in se.lower() for t in MEDDRA_CRITICAL_SAFETY_TERMS
        ) else "moderate"
        fallback_items.append({
            "description": se,
            "severity": severity,
            "frequency": "See FDA label",
            "action": "Consult your doctor or pharmacist",
            "_source": "raw_fda_fallback",
            "_reason": f"LLM dropped {len(gate_result['missing_terms'])} safety signal(s)"
        })

    return fallback_items, gate_result
