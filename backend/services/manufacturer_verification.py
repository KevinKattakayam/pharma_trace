"""Authoritative package-serial verification adapter.

The endpoint is intentionally provider-neutral: deployments connect it to a
manufacturer or authorised distributor service. Without that contract, the
application must report a record match only—not physical authenticity.
"""
from typing import Optional
import httpx

from config import get_settings


async def verify_serialized_package(
    *, gtin: Optional[str], serial_number: Optional[str], lot: Optional[str] = None
) -> dict:
    settings = get_settings()
    if not gtin or not serial_number:
        return {"available": False, "verified": None, "reason": "Serialized GTIN and serial number are required."}
    if not settings.manufacturer_verification_url:
        return {"available": False, "verified": None, "reason": "No authorised manufacturer verification service is configured."}

    headers = {"Accept": "application/json"}
    if settings.manufacturer_verification_token:
        headers["Authorization"] = f"Bearer {settings.manufacturer_verification_token}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                settings.manufacturer_verification_url,
                headers=headers,
                json={"gtin": gtin, "serial_number": serial_number, "lot": lot},
            )
        if response.status_code != 200:
            return {"available": False, "verified": None, "reason": f"Authorised verification service returned {response.status_code}."}
        data = response.json()
        verified = data.get("verified")
        if not isinstance(verified, bool):
            return {"available": False, "verified": None, "reason": "Authorised verification response was incomplete."}
        return {
            "available": True,
            "verified": verified,
            "provider": data.get("provider", "authorised_serial_service"),
            "reference": data.get("reference"),
        }
    except (httpx.HTTPError, ValueError):
        return {"available": False, "verified": None, "reason": "Authorised verification service is unavailable."}
