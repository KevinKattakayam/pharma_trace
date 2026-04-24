"""
Groq LLM service for fast AI inference.
Uses Llama 3.3 70B for drug analysis, side-effect rewriting, and interaction explanation.
Groq provides free tier with extremely fast inference (~500 tok/s).
"""
import httpx
import json
from typing import Optional
from config import get_settings

GROQ_BASE = "https://api.groq.com/openai/v1"


async def _groq_chat(messages: list[dict], max_tokens: int = 500, json_mode: bool = True) -> Optional[dict]:
    """Make a Groq chat completion call."""
    settings = get_settings()
    if not settings.groq_api_key:
        return None

    try:
        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": 0.3
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}

        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                f"{GROQ_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json"
                },
                json=body
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                if json_mode:
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        return {"raw": content}
                return {"text": content}
            else:
                return None
    except Exception:
        return None


async def ai_rewrite_side_effects(side_effects_raw: list[str], drug_name: str = "") -> list[dict]:
    """
    Use Groq/Llama to rewrite raw FDA side-effect text into plain language
    at a 6th-grade reading level with severity classification.
    """
    if not side_effects_raw:
        return []

    text = "\n".join(f"- {se}" for se in side_effects_raw[:20])

    result = await _groq_chat([
        {
            "role": "system",
            "content": """You are a patient-friendly pharmacist. Rewrite drug side effects at a 6th-grade reading level.
For each side effect, return JSON:
{
  "side_effects": [
    {
      "description": "plain language description a child could understand",
      "severity": "mild|moderate|severe",
      "frequency": "Common|Uncommon|Rare",
      "action": "what the patient should do"
    }
  ]
}
Classify severity:
- mild: uncomfortable but not dangerous (e.g., headache, mild nausea)
- moderate: should tell your doctor (e.g., persistent dizziness, rash)
- severe: STOP taking and get help immediately (e.g., breathing trouble, allergic reaction, seizures)"""
        },
        {
            "role": "user",
            "content": f"Drug: {drug_name}\n\nSide effects from FDA label:\n{text}"
        }
    ], max_tokens=800)

    if result and "side_effects" in result:
        return result["side_effects"]
    return []


async def ai_explain_interaction(drug_a: str, drug_b: str, known_effect: str = "") -> Optional[dict]:
    """
    Use Groq/Llama to generate a patient-friendly explanation of a drug interaction.
    """
    prompt = f"Explain the interaction between {drug_a} and {drug_b} to a patient."
    if known_effect:
        prompt += f"\nKnown clinical effect: {known_effect}"

    result = await _groq_chat([
        {
            "role": "system",
            "content": """You are a pharmacist explaining drug interactions to patients.
Return JSON:
{
  "explanation": "2-3 sentence plain-language explanation",
  "risk_level": "low|moderate|high|critical",
  "what_to_do": "specific action the patient should take",
  "mechanism": "brief scientific mechanism"
}"""
        },
        {"role": "user", "content": prompt}
    ], max_tokens=300)

    return result


async def ai_analyze_drug(drug_name: str, patient_info: dict = None) -> Optional[dict]:
    """
    Use Groq/Llama for comprehensive drug analysis including
    common concerns, food interactions, and timing advice.
    """
    patient_ctx = ""
    if patient_info:
        patient_ctx = f"\nPatient: age {patient_info.get('age', 'unknown')}, weight {patient_info.get('weight_kg', 'unknown')}kg, kidney function: {patient_info.get('kidney_function', 'normal')}"

    result = await _groq_chat([
        {
            "role": "system",
            "content": """You are a clinical pharmacist. Analyze this drug for a patient.
Return JSON:
{
  "summary": "1-2 sentence overview of what this drug does",
  "food_interactions": ["foods to avoid or take with"],
  "timing_advice": "when to take (morning/night, with/without food)",
  "common_concerns": ["things patients often worry about"],
  "storage": "how to store properly",
  "missed_dose": "what to do if you miss a dose"
}"""
        },
        {"role": "user", "content": f"Drug: {drug_name}{patient_ctx}"}
    ], max_tokens=500)

    return result


async def groq_available() -> bool:
    """Check if Groq API key is configured."""
    settings = get_settings()
    return bool(settings.groq_api_key)
