"""
Vision AI service using OpenRouter (GPT-4o Vision) for pill/packaging analysis.
OpenRouter provides access to GPT-4o, Claude, Gemini etc. via a single API.
"""
import json

import httpx

from config import get_settings

OPENROUTER_BASE = "https://openrouter.ai/api/v1"

VISION_PROMPT = """You are a pharmaceutical verification AI. Analyze this drug/pill image and return a JSON object with these exact fields:

{
  "pill_shape": "round/oval/capsule/diamond/oblong/other",
  "pill_color": "primary color, secondary color if any",
  "imprint": "any text, numbers, or logos visible on the pill",
  "packaging_info": "any brand name, NDC, manufacturer, or lot number visible",
  "condition": "description of physical condition — damage, discoloration, moisture",
  "suspicion_level": "low/medium/high",
  "reasoning": "1-2 sentence explanation of your assessment",
  "possible_drug": "best guess at the drug identity based on visual features, or null"
}

Be specific and factual. If you cannot determine something, use null rather than guessing."""

MULTI_VISION_PROMPT = """You are a pharmaceutical verification AI. Analyze this image containing multiple medicine strips or boxes.
Identify up to 8 distinct medications you can see (maximum 8, prioritize those most clearly visible).
Return a JSON array of objects with these exact fields:
[
  {
    "brand_name": "visible brand name, or null",
    "generic_name": "active ingredient/generic name, or null",
    "strength": "dosage/strength (e.g. 500mg), or null",
    "confidence": "high/medium/low"
  }
]
Return ONLY the JSON array, nothing else. Maximum 8 items."""


async def _analyze_pill_image_vision(image_base64: str) -> dict:
    """Analyze a pill/packaging photo using GPT-4o Vision via OpenRouter."""
    settings = get_settings()

    api_key = settings.openrouter_api_key or settings.openai_api_key

    if not api_key:
        return {
            "available": False,
            "reason": "No vision API configured. Set OPENROUTER_API_KEY or OPENAI_API_KEY in .env",
            "analysis": None
        }

    # Determine endpoint and headers
    if settings.openrouter_api_key:
        url = f"{OPENROUTER_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://pharmatrace.app",
            "X-Title": "PharmaTrace"
        }
        model = "openai/gpt-4o"
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        model = "gpt-4o"

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 500
            })

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                # Parse JSON from response (handle markdown code blocks)
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                try:
                    analysis = json.loads(cleaned)
                except json.JSONDecodeError:
                    analysis = {"raw_response": content}

                return {
                    "available": True,
                    "analysis": analysis,
                    "model": model,
                    "provider": "openrouter" if settings.openrouter_api_key else "openai"
                }
            else:
                return {"available": False, "reason": f"API Error: {resp.status_code} {resp.text}"}
    except Exception as e:
        return {"available": False, "reason": str(e)}

async def analyze_multiple_pills_image(image_base64: str) -> dict:
    """Analyze a photo with multiple medicine strips/boxes to identify all of them."""
    settings = get_settings()
    api_key = settings.openrouter_api_key or settings.openai_api_key

    if not api_key:
        return {
            "available": False,
            "reason": "No vision API configured.",
            "medications": []
        }

    if settings.openrouter_api_key:
        url = f"{OPENROUTER_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://pharmatrace.app",
            "X-Title": "PharmaTrace"
        }
        model = "openai/gpt-4o"
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json"
        }
        model = "gpt-4o"

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": MULTI_VISION_PROMPT},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 1000
            })

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()

                try:
                    meds = json.loads(cleaned)
                    if not isinstance(meds, list):
                        meds = []
                except json.JSONDecodeError:
                    meds = []

                # Hard cap at 8 medicines — prevents interaction pair explosion
                # C(8,2) = 28 pairs is manageable; C(15,2) = 105 is not
                meds = meds[:8]

                return {
                    "available": True,
                    "medications": meds,
                    "model": model
                }
            else:
                return {"available": False, "reason": f"API Error: {resp.status_code} {resp.text}", "medications": []}
    except Exception as e:
        return {"available": False, "reason": str(e), "medications": []}

async def extract_prescription_medicines(image_base64: str) -> dict:
    """Analyze a handwritten or printed prescription photo to extract medicines."""
    settings = get_settings()
    api_key = settings.openrouter_api_key or settings.openai_api_key

    if not api_key:
        return {"available": False, "reason": "No vision API configured", "medicines": []}

    if settings.openrouter_api_key:
        url = f"{OPENROUTER_BASE}/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"}
        model = "openai/gpt-4o"
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}
        model = "gpt-4o"

    prompt = """You are a clinical AI assistant. Analyze this prescription image.
Extract all medications prescribed.
Return a JSON object with this exact field:
{
  "medicines": ["Medicine Name 1", "Medicine Name 2"]
}
If no medicines are found or illegible, return {"medicines": []}.
Be highly accurate. Correct obvious spelling mistakes if you are certain of the drug."""

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, headers=headers, json={
                "model": model,
                "messages": [{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}", "detail": "high"}}
                    ]
                }],
                "response_format": { "type": "json_object" },
                "max_tokens": 500
            })

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    analysis = json.loads(cleaned)
                    return {"available": True, "medicines": analysis.get("medicines", [])}
                except json.JSONDecodeError:
                    return {"available": True, "medicines": []}
            return {"available": False, "reason": f"API returned {resp.status_code}", "medicines": []}
    except Exception as e:
        return {"available": False, "reason": str(e), "medicines": []}


import asyncio
import difflib


def reconcile_ocr_vision(ocr_text: str, vision_text: str) -> dict:
    """Merge OCR and Vision outputs using edit-distance reconciliation."""
    ocr = (ocr_text or "").strip()
    vis = (vision_text or "").strip()
    
    if not ocr and not vis:
        return {"text": "", "flagged": False}
    if not ocr:
        return {"text": vis, "flagged": False}
    if not vis:
        return {"text": ocr, "flagged": False}
        
    seq = difflib.SequenceMatcher(None, ocr.lower(), vis.lower())
    ratio = seq.ratio()
    
    if ratio < 0.7:  # Diverges by > 30%
        return {"text": ocr, "flagged": True, "vision_text": vis, "reasoning": "OCR and Vision AI strongly disagree."}
        
    # Pick the longer one
    return {"text": ocr if len(ocr) > len(vis) else vis, "flagged": False}


async def analyze_pill_image(image_base64: str, extracted_text: str = None) -> dict:
    """Hybrid pill identification: Reconciles Tesseract OCR with GPT-4o Vision."""
    
    # Run Vision analysis in parallel
    vision_task = asyncio.create_task(_analyze_pill_image_vision(image_base64))
    
    # If we have OCR text, we can try fast lookups while vision runs
    text_clean = (extracted_text or "").strip()
    
    vision_result = await vision_task
    
    # Reconcile OCR and Vision text
    vision_drug_guess = ""
    if vision_result.get("analysis"):
        vision_drug_guess = vision_result["analysis"].get("possible_drug") or ""
        vision_drug_guess = str(vision_drug_guess).replace("null", "").strip()

    reconciled = reconcile_ocr_vision(text_clean, vision_drug_guess)
    final_text = reconciled["text"]
    is_flagged = reconciled["flagged"]
    
    if final_text:
        # Step 2: RxNav API Lookup using reconciled text
        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp_strict = await client.get(
                    "https://rxnav.nlm.nih.gov/REST/drugs.json",
                    params={"name": final_text}
                )
                drug_name = None
                if resp_strict.status_code == 200:
                    data = resp_strict.json()
                    groups = data.get("drugGroup", {}).get("conceptGroup", [])
                    for g in groups:
                        props = g.get("conceptProperties", [])
                        if props:
                            drug_name = props[0].get("name")
                            break
                            
                if not drug_name:
                    resp_fuzzy = await client.get(
                        "https://rxnav.nlm.nih.gov/REST/approximateTerm.json",
                        params={"term": final_text, "maxEntries": 1}
                    )
                    if resp_fuzzy.status_code == 200:
                        data = resp_fuzzy.json()
                        candidates = data.get("approximateGroup", {}).get("candidate", [])
                        if candidates:
                            drug_name = candidates[0].get("name", final_text)

                if drug_name:
                    analysis = vision_result.get("analysis", {})
                    analysis.update({
                        "possible_drug": drug_name,
                        "suspicion_level": "high" if is_flagged else "low",
                        "reasoning": "OCR/Vision divergence detected. Flagged for review." if is_flagged else "Reconciled text match via NIH RxNav database.",
                        "source_method": "Hybrid AI + NIH Database",
                        "flagged_for_review": is_flagged
                    })
                    return {
                        "available": True,
                        "analysis": analysis,
                        "provider": "rxnav+vision",
                        "source_method": "Hybrid AI + NIH Database"
                    }
            except Exception:
                pass
                
        # Step 3: CDSCO India Lookup
        try:
            from services.cdsco import lookup_indian_drug
            cdsco_result = await lookup_indian_drug(final_text)
            if cdsco_result:
                analysis = vision_result.get("analysis", {})
                analysis.update({
                    "possible_drug": f"{cdsco_result.get('brand_name')} ({cdsco_result.get('generic_name')})",
                    "suspicion_level": "high" if is_flagged else "low",
                    "reasoning": "OCR/Vision divergence detected. Flagged for review." if is_flagged else "Reconciled text match found in CDSCO registry.",
                    "source_method": "Hybrid AI + CDSCO Database",
                    "flagged_for_review": is_flagged
                })
                return {
                    "available": True,
                    "analysis": analysis,
                    "provider": "cdsco+vision",
                    "source_method": "Hybrid AI + CDSCO Database"
                }
        except Exception:
            pass

    # Step 4: Fallback to purely GPT-4o Vision
    vision_result["source_method"] = "Identified via AI Vision"
    if vision_result.get("analysis"):
        vision_result["analysis"]["source_method"] = "AI Vision"
        if is_flagged:
            vision_result["analysis"]["suspicion_level"] = "high"
            vision_result["analysis"]["flagged_for_review"] = True
            vision_result["analysis"]["reasoning"] = "OCR/Vision divergence detected. Flagged for review."
            
    return vision_result


async def analyze_pill_description(description: str) -> dict:
    """Identify a pill from a text description using Groq (fast) or OpenRouter."""
    settings = get_settings()

    # Prefer Groq for text-only tasks (much faster)
    if settings.groq_api_key:
        return await _groq_pill_identify(description, settings.groq_api_key)

    api_key = settings.openrouter_api_key or settings.openai_api_key
    if not api_key:
        return {"available": False, "reason": "No LLM API configured", "analysis": None}

    if settings.openrouter_api_key:
        url = f"{OPENROUTER_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://pharmatrace.app",
            "X-Title": "PharmaTrace"
        }
        model = "openai/gpt-4o-mini"
    else:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        model = "gpt-4o-mini"

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=headers, json={
                "model": model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a pharmacist AI. Based on the pill description, identify possible drugs. Return JSON: {\"possible_drugs\": [\"name1\", \"name2\"], \"confidence\": \"low/medium/high\", \"reasoning\": \"explanation\"}"
                    },
                    {"role": "user", "content": description}
                ],
                "max_tokens": 300
            })

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                cleaned = content.strip()
                if cleaned.startswith("```"):
                    cleaned = cleaned.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                try:
                    analysis = json.loads(cleaned)
                except json.JSONDecodeError:
                    analysis = {"raw_response": content}
                return {"available": True, "analysis": analysis}
    except Exception as e:
        return {"available": False, "reason": str(e), "analysis": None}

    return {"available": False, "reason": "Unknown error", "analysis": None}


async def _groq_pill_identify(description: str, api_key: str) -> dict:
    """Use Groq for fast pill identification from text."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a pharmacist AI. Based on the pill description, identify possible drugs. Return JSON: {\"possible_drugs\": [\"name1\", \"name2\"], \"confidence\": \"low/medium/high\", \"reasoning\": \"explanation\"}"
                        },
                        {"role": "user", "content": description}
                    ],
                    "max_tokens": 300,
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"}
                }
            )

            if resp.status_code == 200:
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                try:
                    analysis = json.loads(content)
                except json.JSONDecodeError:
                    analysis = {"raw_response": content}
                return {"available": True, "analysis": analysis, "model": "llama-3.3-70b-versatile", "provider": "groq"}
            else:
                return {"available": False, "reason": f"Groq API: {resp.status_code}", "analysis": None}
    except Exception as e:
        return {"available": False, "reason": str(e), "analysis": None}
