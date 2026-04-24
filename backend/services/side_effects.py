"""
Side effect explainer — rewrites drug label warnings in plain language
at a 6th-grade reading level with severity labeling.
"""
import re
from typing import Optional
from models.schemas import SideEffect


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


def extract_side_effects_from_label(label_data: dict) -> list[SideEffect]:
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

    raw_text = ""
    for field in fields_to_check:
        values = label_data.get(field, [])
        if isinstance(values, list):
            raw_text += " ".join(values) + " "
        elif isinstance(values, str):
            raw_text += values + " "

    raw_text = raw_text.lower()

    # Match known side effects
    found = set()
    for keyword, info in COMMON_SIDE_EFFECTS.items():
        if keyword in raw_text and keyword not in found:
            found.add(keyword)
            side_effects.append(SideEffect(
                description=info["plain"],
                severity=info["severity"],
                frequency=info["frequency"]
            ))

    # Sort by severity (severe first)
    severity_order = {"severe": 0, "moderate": 1, "mild": 2}
    side_effects.sort(key=lambda x: severity_order.get(x.severity, 3))

    # If no known side effects found, add a generic note
    if not side_effects:
        side_effects.append(SideEffect(
            description="Side effect information could not be parsed from the drug label. Consult your pharmacist or doctor for details.",
            severity="mild",
            frequency=None
        ))

    return side_effects
