from groq import AsyncGroq
from pydantic import BaseModel, field_validator
import json
from config import get_settings

client = AsyncGroq(api_key=get_settings().groq_api_key)

class MedicineSummary(BaseModel):
    drug_name: str
    active_ingredient: str
    treats: str
    when_to_take: str
    duration: str
    warning: str
    interaction_flag: bool
    whatsapp_text: str

    @field_validator("treats", "warning", "when_to_take")
    @classmethod
    def no_medical_jargon_check(cls, v):
        JARGON = ["contraindicated", "pharmacokinetic", "hepatotoxic",
                  "nephrotoxic", "bioavailability", "half-life"]
        for word in JARGON:
            if word.lower() in v.lower():
                raise ValueError(f"Jargon detected: {word}")
        return v

SYSTEM_PROMPT = """You are a patient-friendly pharmacist in India writing for someone's grandmother.
Rules:
- Every explanation under 3 lines
- Zero medical jargon. Say "liver" not "hepatic"
- Use ONLY the drug names provided to you. Never invent drugs.
- IMPORTANT DOSAGE FLAGS:
  - If age < 12, explicitly flag pediatric caution in warnings.
  - If age > 65, explicitly flag reduced dosage requirement for elderly.
  - If conditions mentions kidney issues or renal_gfr < 30, explicitly flag severe renal caution in warnings.
- whatsapp_text must include emoji and be under 200 characters
- Respond ONLY with a valid JSON array, no markdown, no preamble

Output schema per medicine:
{
  "drug_name": "exact name from input",
  "active_ingredient": "generic compound",
  "treats": "what condition it helps",
  "when_to_take": "Morning/Evening/with food etc",
  "duration": "how many days",
  "warning": "single most important safety point",
  "interaction_flag": true/false,
  "whatsapp_text": "emoji-friendly 1-line summary"
}"""

async def generate_summaries(
    resolved_drugs: list[dict],
    interactions: list,
    patient_context: dict,
    language: str = "en"
) -> list[MedicineSummary]:
    """
    resolved_drugs: output from resolve_all_drugs()
    patient_context: {age, weight_kg, conditions, renal_gfr}
    """
    # Build a grounded drug list — only verified names go to LLM
    verified_drugs = [d for d in resolved_drugs if d["confidence"] > 0.6]
    interaction_pairs = [
        f"{i.drug_a} + {i.drug_b}: {i.severity}" for i in interactions
        if i.severity in ("major", "contraindicated")
    ]

    user_content = f"""
Patient: age {patient_context.get('age', 'unknown')}, 
conditions: {', '.join(patient_context.get('conditions', []) or [])},
renal_gfr: {patient_context.get('renal_gfr', 'unknown')}

Drugs to summarise:
{json.dumps([{
    'name': d.get('generic_name', d.get('brand_name')),
    'brand': d.get('brand_name'),
    'rxcui': d.get('rxcui')
} for d in verified_drugs], indent=2)}

Active interactions (MUST mention in warnings):
{chr(10).join(interaction_pairs) if interaction_pairs else 'None detected'}

Generate one JSON object per drug. Respond with a JSON array only.
"""

    response = await client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content}
        ],
        temperature=0.1,   # low for medical accuracy
        max_tokens=2000,
        response_format={"type": "json_object"}  # Groq JSON mode
    )

    raw = response.choices[0].message.content.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    if raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    raw = raw.strip()
    import structlog
    logger = structlog.get_logger()
    
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.error("groq_json_decode_failed", raw_sample=raw[:100])
        return []

    # Validate each summary with Pydantic — catches hallucinations
    summaries = []
    items = parsed if isinstance(parsed, list) else parsed.get("medicines", [])
    for item in items:
        try:
            summaries.append(MedicineSummary(**item))
        except Exception as e:
            # Log validation failure but don't crash — partial results are better
            logger.warning("medicine_summary_validation_failed", drug=item.get('drug_name'), error=str(e))

    return summaries
