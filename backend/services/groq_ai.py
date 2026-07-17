"""
Groq LLM service for fast AI inference.
Uses Llama 3.3 70B for drug analysis, side-effect rewriting, and interaction explanation.
Groq provides free tier with extremely fast inference (~500 tok/s).
"""
import httpx
import json
from typing import Optional
from config import get_settings
from services.circuit_breaker import circuit_breaker
from services.compliance import sanitize_phi, restore_phi

GROQ_BASE = "https://api.groq.com/openai/v1"


@circuit_breaker(name="groq", failure_threshold=3, recovery_timeout=30.0)
async def _groq_chat(messages: list[dict], max_tokens: int = 500, json_mode: bool = True) -> Optional[dict]:
    """Make a Groq chat completion call."""
    settings = get_settings()
    if not settings.groq_api_key:
        return None

    try:
        # PHI Tokenization Gateway: sanitize user messages before LLM transmission
        token_maps = []
        sanitized_messages = []
        for msg in messages:
            if msg.get("role") == "user":
                sanitized_content, t_map = sanitize_phi(msg.get("content", ""))
                token_maps.append(t_map)
                sanitized_messages.append({**msg, "content": sanitized_content})
            else:
                sanitized_messages.append(msg)

        body = {
            "model": "llama-3.3-70b-versatile",
            "messages": sanitized_messages,
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
                res_obj = None
                if json_mode:
                    clean_content = content.strip()
                    if clean_content.startswith("```json"):
                        clean_content = clean_content[7:]
                    if clean_content.startswith("```"):
                        clean_content = clean_content[3:]
                    if clean_content.endswith("```"):
                        clean_content = clean_content[:-3]
                    clean_content = clean_content.strip()
                    try:
                        res_obj = json.loads(clean_content)
                    except json.JSONDecodeError:
                        res_obj = {"raw": content}
                else:
                    res_obj = {"text": content}

                # Restore PHI into output text/dict
                if res_obj and isinstance(res_obj, dict):
                    for t_map in token_maps:
                        for k, v in res_obj.items():
                            if isinstance(v, str):
                                res_obj[k] = restore_phi(v, t_map)
                return res_obj
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
    common concerns, food interactions, and timing advice,
    backed by a persistent 30-day semantic cache layer.
    """
    import time
    from services.supabase import get_supabase
    db = get_supabase()
    
    cache_key = drug_name.strip().lower()
    
    # 1. Check persistent 30-day semantic cache if no custom patient context is overriding standard analysis
    if not patient_info:
        try:
            cached_rows = await db.query("ai_cache", filters={"drug_name": cache_key}, limit=1)
            if cached_rows and len(cached_rows) > 0:
                cached_item = cached_rows[0]
                created_ts = cached_item.get("created_ts", 0)
                if time.time() - created_ts < 2592000: # 30 days TTL (30 * 24 * 3600 seconds)
                    if cached_item.get("analysis_data"):
                        return cached_item["analysis_data"]
        except Exception:
            pass

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

    # 2. Store valid standard analysis in 30-day semantic cache
    if result and not patient_info:
        try:
            await db.insert("ai_cache", {
                "id": f"cache_{cache_key}_{int(time.time())}",
                "drug_name": cache_key,
                "analysis_data": result,
                "created_ts": int(time.time()),
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            })
        except Exception:
            pass

    return result


async def ai_normalize_conditions(conditions_text: str) -> list[str]:
    """
    Use Groq/Llama to map raw user condition text (e.g. "high bp, sugar") 
    into standard MED-RT or clinical terminology (e.g. ["Hypertension", "Diabetes Mellitus"]).
    """
    if not conditions_text or len(conditions_text.strip()) < 2:
        return []

    result = await _groq_chat([
        {
            "role": "system",
            "content": """You are a medical terminologist. Map colloquial patient symptoms/conditions to standard MED-RT/MeSH terms.
Return JSON:
{
  "normalized_conditions": ["Term 1", "Term 2"]
}
Example: "high bp, bad liver" -> ["Hypertension", "Hepatic Impairment"]"""
        },
        {"role": "user", "content": f"Conditions: {conditions_text}"}
    ], max_tokens=150)

    if result and "normalized_conditions" in result:
        return [c for c in result["normalized_conditions"] if isinstance(c, str)]
    return []


async def ai_classify_drug(drug_name: str) -> dict:
    """
    Use Groq/Llama to determine the pharmacological class and clearance mechanisms
    of a drug to avoid hardcoded string matching in dosage evaluation.
    """
    result = await _groq_chat([
        {
            "role": "system",
            "content": """Classify this drug for dosage safety evaluation. Return JSON:
{
  "is_nsaid": true/false,
  "is_benzodiazepine": true/false,
  "is_metformin": true/false,
  "kidney_cleared": true/false,
  "pediatric_contraindicated": true/false
}"""
        },
        {"role": "user", "content": f"Drug: {drug_name}"}
    ], max_tokens=150)
    return result or {}


async def groq_available() -> bool:
    """Check if Groq API key is configured."""
    settings = get_settings()
    return bool(settings.groq_api_key)
