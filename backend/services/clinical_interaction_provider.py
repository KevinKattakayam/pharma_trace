"""Adapter for a licensed, clinically governed interaction knowledge provider.

The provider contract is deliberately simple: POST ``{"drug_concepts": [...]}``
and return ``{"interactions": [...]}``, where each entry includes drug_a,
drug_b, severity, clinical_effect, recommendation, and source. Deployments own
the mapping from their licensed vendor SDK/API to this contract.
"""
import httpx
from config import get_settings


async def lookup_interactions(drug_concepts: list[str]) -> dict:
    settings = get_settings()
    if not settings.clinical_interaction_provider_url:
        return {"available": False, "interactions": [], "reason": "No clinically governed interaction provider is configured."}

    headers = {"Accept": "application/json"}
    if settings.clinical_interaction_provider_token:
        headers["Authorization"] = f"Bearer {settings.clinical_interaction_provider_token}"
    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            response = await client.post(settings.clinical_interaction_provider_url, json={"drug_concepts": drug_concepts}, headers=headers)
        if response.status_code != 200:
            return {"available": False, "interactions": [], "reason": f"Clinical provider returned {response.status_code}."}
        payload = response.json()
        interactions = payload.get("interactions")
        if not isinstance(interactions, list):
            return {"available": False, "interactions": [], "reason": "Clinical provider returned an invalid payload."}
        return {"available": True, "interactions": interactions, "provider": payload.get("provider", "licensed_clinical_provider")}
    except (httpx.HTTPError, ValueError):
        return {"available": False, "interactions": [], "reason": "Clinical provider is unavailable."}
