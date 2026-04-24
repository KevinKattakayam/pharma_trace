"""
Vision AI service using OpenRouter (GPT-4o Vision) for pill/packaging analysis.
OpenRouter provides access to GPT-4o, Claude, Gemini etc. via a single API.
"""
import httpx
import json
from typing import Optional
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


async def analyze_pill_image(image_base64: str) -> dict:
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
                error_body = resp.text
                return {
                    "available": False,
                    "reason": f"API returned {resp.status_code}: {error_body[:200]}",
                    "analysis": None
                }
    except Exception as e:
        return {
            "available": False,
            "reason": str(e),
            "analysis": None
        }


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
