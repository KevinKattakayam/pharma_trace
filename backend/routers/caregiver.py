"""
Caregiver router — linking caregivers to care recipients, real-time medication monitoring.
All data from real user interactions. No dummy/sample data.
"""
import uuid
from fastapi import APIRouter, HTTPException
from models.schemas import CaregiverLinkRequest

router = APIRouter(prefix="/caregiver", tags=["caregiver"])

# In-memory storage — in production: Supabase
_links: list[dict] = []
_recipients: dict[str, dict] = {}  # code -> recipient data
_alerts: list[dict] = []


@router.post("/link")
async def generate_caregiver_link():
    """Generate an invite code to link a caregiver."""
    code = "PT-" + uuid.uuid4().hex[:6].upper()
    _links.append({"code": code, "status": "pending", "caregiver_id": None})
    return {"code": code, "status": "pending"}


@router.post("/accept")
async def accept_caregiver_link(request: CaregiverLinkRequest):
    """Accept a caregiver invite code."""
    for link in _links:
        if link["code"] == request.code:
            if link["status"] == "active":
                return {"status": "already_active", "message": "This link is already active"}
            link["status"] = "active"
            link["caregiver_id"] = str(uuid.uuid4())
            _recipients[request.code] = {
                "name": request.code,
                "linked_at": None,
                "medications": [],
                "alerts": []
            }
            return {"status": "active", "message": "Caregiver link established", "caregiver_id": link["caregiver_id"]}
    raise HTTPException(status_code=404, detail="Invalid invite code")


@router.get("/dashboard")
async def get_caregiver_dashboard():
    """
    Get caregiver dashboard with all care recipients and their medications.
    Returns real linked recipients and their verified medications.
    """
    active_links = [l for l in _links if l["status"] == "active"]

    recipients = []
    for link in active_links:
        recipient = _recipients.get(link["code"], {})
        recipients.append({
            "code": link["code"],
            "name": recipient.get("name", link["code"]),
            "medications": recipient.get("medications", []),
            "alerts": recipient.get("alerts", [])
        })

    return {
        "recipients": recipients,
        "total_linked": len(active_links),
        "pending_invites": sum(1 for l in _links if l["status"] == "pending")
    }


@router.post("/recipient/{code}/medication")
async def add_recipient_medication(code: str, drug_name: str, ndc: str = "",
                                     confidence: float = 0):
    """Add a verified medication to a care recipient's profile."""
    if code not in _recipients:
        raise HTTPException(status_code=404, detail="Recipient not found")

    med = {
        "name": drug_name,
        "ndc": ndc,
        "status": "verified" if confidence >= 70 else "unverified",
        "confidence": confidence
    }
    _recipients[code]["medications"].append(med)

    # Generate alert if low confidence
    if confidence < 70:
        alert = {
            "type": "verification",
            "message": f"Low confidence verification for {drug_name} ({confidence}%)",
            "recipient": code,
            "severity": "high" if confidence < 40 else "moderate"
        }
        _recipients[code]["alerts"].append(alert)
        _alerts.append(alert)

    return {"status": "added", "medication": med}


@router.get("/alerts")
async def get_caregiver_alerts():
    """Get all unread alerts for caregiver."""
    return {"alerts": _alerts, "total": len(_alerts)}
