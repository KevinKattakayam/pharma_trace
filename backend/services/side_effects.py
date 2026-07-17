"""
Side effect explainer — rewrites drug label warnings in plain language
at a 6th-grade reading level with severity labeling.
"""
import re
from typing import Optional
from models.schemas import SideEffect
from services.groq_ai import ai_rewrite_side_effects


# Common side effects database with plain-language descriptions
COMMON_SIDE_EFFECTS = {
    "nausea": {"plain": "Feeling queasy or sick to your stomach", "severity": "mild", "frequency": "Common"},
    "vomiting": {"plain": "Throwing up", "severity": "moderate", "frequency": "Common"},
    "diarrhea": {"plain": "Loose or watery bowel movements", "severity": "mild", "frequency": "Common"},
    "headache": {"plain": "Head pain or pressure", "severity": "mild", "frequency": "Very common"},
    "dizziness": {"plain": "Feeling lightheaded or unsteady on your feet", "severity": "mild", "frequency": "Common"},
    "drowsiness": {"plain": "Feeling very sleepy during the day", "severity": "mild", "frequency": "Common"},
    "rash": {"plain": "Red, itchy spots or patches on your skin", "severity": "moderate", "frequency": "Uncommon"},
    "hives": {"plain": "Raised, itchy welts on your skin — this could be an allergic reaction", "severity": "severe", "frequency": "Rare"},
    "swelling": {"plain": "Parts of your body puffing up, especially face, lips, or throat", "severity": "severe", "frequency": "Rare"},
    "bleeding": {"plain": "Unusual bleeding or bruising that doesn't stop easily", "severity": "severe", "frequency": "Uncommon"},
    "stomach pain": {"plain": "Pain or cramping in your belly area", "severity": "mild", "frequency": "Common"},
    "constipation": {"plain": "Difficulty having a bowel movement", "severity": "mild", "frequency": "Common"},
    "fatigue": {"plain": "Feeling very tired or having no energy", "severity": "mild", "frequency": "Common"},
    "insomnia": {"plain": "Trouble falling or staying asleep", "severity": "mild", "frequency": "Common"},
    "dry mouth": {"plain": "Your mouth feels very dry, even after drinking water", "severity": "mild", "frequency": "Common"},
    "muscle pain": {"plain": "Aching or soreness in your muscles", "severity": "moderate", "frequency": "Uncommon"},
    "joint pain": {"plain": "Pain or stiffness in your joints", "severity": "moderate", "frequency": "Uncommon"},
    "chest pain": {"plain": "Pain or tightness in your chest — STOP the medicine and call for help right away", "severity": "severe", "frequency": "Rare"},
    "shortness of breath": {"plain": "Difficulty breathing or feeling like you can't get enough air — seek help immediately", "severity": "severe", "frequency": "Rare"},
    "seizure": {"plain": "Uncontrollable shaking or convulsions — this is a medical emergency", "severity": "severe", "frequency": "Very rare"},
    "liver damage": {"plain": "Yellowing of skin/eyes, dark urine, extreme fatigue — stop medicine and see doctor urgently", "severity": "severe", "frequency": "Rare"},
    "kidney damage": {"plain": "Very little urine, swelling in legs, confusion — see doctor urgently", "severity": "severe", "frequency": "Rare"},
    "anaphylaxis": {"plain": "Severe allergic reaction with throat swelling and trouble breathing — CALL 911 NOW", "severity": "severe", "frequency": "Very rare"},
    "tinnitus": {"plain": "Ringing or buzzing sounds in your ears", "severity": "moderate", "frequency": "Uncommon"},
    "blurred vision": {"plain": "Your eyesight becomes fuzzy or unclear", "severity": "moderate", "frequency": "Uncommon"},
    "weight gain": {"plain": "Gaining weight without eating more than usual", "severity": "mild", "frequency": "Common"},
    "decreased appetite": {"plain": "Not feeling hungry or wanting to eat less than normal", "severity": "mild", "frequency": "Common"},
    "hypoglycemia": {"plain": "Blood sugar drops too low — you may feel shaky, sweaty, confused, or faint", "severity": "moderate", "frequency": "Common with diabetes meds"},
}


async def extract_side_effects_from_label(label_data: dict, drug_name: str = "") -> list[SideEffect]:
    """Extract and simplify side effects from an OpenFDA drug label."""
    side_effects = []

    # Fields to check in the label
    fields_to_check = [
        "adverse_reactions",
        "warnings",
        "warnings_and_cautions",
        "do_not_use",
        "stop_use"
    ]

    raw_text_parts = []
    raw_text = ""
    for field in fields_to_check:
        values = label_data.get(field, [])
        if isinstance(values, list):
            raw_text_parts.extend(values)
            raw_text += " ".join(values) + " "
        elif isinstance(values, str):
            raw_text_parts.append(values)
            raw_text += values + " "
            
    # AI Dynamic Rewriting (Primary)
    if raw_text_parts:
        try:
            ai_res = await ai_rewrite_side_effects(raw_text_parts, drug_name)
            if ai_res:
                return [
                    SideEffect(
                        description=r.get("description", ""),
                        severity=r.get("severity", "mild"),
                        frequency=r.get("frequency", "Unknown")
                    )
                    for r in ai_res
                ]
        except Exception:
            pass # Fallback to authoritative label sentence extraction

    # Authoritative FDA Label Sentence Extraction (When AI is offline or unavailable)
    found = set()
    if raw_text_parts:
        for part in raw_text_parts:
            # Clean and split into individual warning sentences or bullet points
            sentences = [s.strip() for s in re.split(r'\. |\n|•|- |\*|; ', part) if len(s.strip()) > 15]
            for s in sentences[:20]:
                clean_s = s.capitalize()
                if not clean_s.endswith("."): clean_s += "."
                if clean_s.lower() in found: continue
                found.add(clean_s.lower())
                
                # Classify severity heuristically from real FDA warning wording
                sev = "mild"
                s_lower = clean_s.lower()
                if any(w in s_lower for w in ["fatal", "death", "severe", "anaphylax", "emergency", "stop use", "call doctor", "hospital", "seizure", "bleeding", "contraindicat"]):
                    sev = "severe"
                elif any(w in s_lower for w in ["warning", "caution", "consult", "doctor", "rash", "fever", "vomit", "dizzy", "pain"]):
                    sev = "moderate"
                side_effects.append(SideEffect(
                    description=clean_s,
                    severity=sev,
                    frequency="Reported in FDA regulatory label"
                ))

    raw_text = raw_text.lower()
    # Also check MedDRA critical safety terms so severe warnings are never missed
    from services.meddra_gate import MEDDRA_CRITICAL_SAFETY_TERMS
    for term in MEDDRA_CRITICAL_SAFETY_TERMS:
        if term in raw_text and not any(term in str(se.description).lower() for se in side_effects):
            side_effects.append(SideEffect(
                description=f"Critical safety warning: {term.title()} reported in regulatory label.",
                severity="severe",
                frequency="Reported in clinical surveillance"
            ))

    # Sort by severity (severe first)
    severity_order = {"severe": 0, "moderate": 1, "mild": 2}
    side_effects.sort(key=lambda x: severity_order.get(x.severity, 3))

    # If no side effects found in label, add a generic guidance note
    if not side_effects:
        side_effects.append(SideEffect(
            description="Specific side effect text could not be extracted from this label. Consult your pharmacist or doctor for details.",
            severity="mild",
            frequency=None
        ))

    return side_effects[:25]
