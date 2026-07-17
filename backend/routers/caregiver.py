"""
Caregiver router — linking caregivers to care recipients, real-time medication monitoring.
All data from real user interactions stored in Postgres. Zero volatile in-memory fallbacks.
"""
import uuid
import secrets
from fastapi import APIRouter, HTTPException, Depends
from models.schemas import CaregiverLinkRequest, CurrentUser
from dependencies import require_current_user
from services.supabase import get_supabase
from services.drug_resolver import resolve_all_drugs
from services.interactions import check_interactions_enterprise

router = APIRouter(prefix="/caregiver", tags=["caregiver"])


@router.post("/link")
async def generate_caregiver_link(current_user: CurrentUser = Depends(require_current_user)):
    """Generate a cryptographically secure invite code to link a caregiver."""
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="503 Service Unavailable: Database storage layer disconnected.")

    code = secrets.token_urlsafe(16)
    data = {"code": code, "status": "pending", "caregiver_id": None, "creator_user_id": current_user.user_id}
    
    try:
        res = await db.insert("caregiver_links", data)
        if not res:
            raise HTTPException(status_code=500, detail="Failed to persist invite code")
        return {"code": code, "status": "pending"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database write failure: {str(e)}")


@router.post("/accept")
async def accept_caregiver_link(request: CaregiverLinkRequest, current_user: CurrentUser = Depends(require_current_user)):
    """Accept a caregiver invite code and establish care recipient monitoring relationship."""
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="503 Service Unavailable: Database storage layer disconnected.")

    caregiver_id = current_user.user_id
    
    try:
        links = await db.query("caregiver_links", filters={"code": request.code})
        if not links:
            raise HTTPException(status_code=404, detail="404 Not Found: Invalid or expired invite code.")
            
        link = links[0]
        if link.get("creator_user_id") == current_user.user_id:
            raise HTTPException(status_code=400, detail="400 Bad Request: Cannot link yourself as your own caregiver.")
        if link.get("status") == "active":
            return {"status": "already_active", "message": "This link is already active"}
        
        # Update link status
        await db.update("caregiver_links", {"status": "active", "caregiver_id": caregiver_id}, filters={"code": request.code})
        
        # Create recipient tracking entry
        await db.insert("caregiver_recipients", {
            "id": str(uuid.uuid4()),
            "code": request.code,
            "caregiver_id": caregiver_id,
            "name": "Recipient-" + request.code[:4]
        })
        return {"status": "active", "message": "Caregiver link established", "caregiver_id": caregiver_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failure: {str(e)}")


@router.get("/dashboard")
async def get_caregiver_dashboard(current_user: CurrentUser = Depends(require_current_user)):
    """Get caregiver dashboard strictly scoped to current user's linked recipients."""
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="503 Service Unavailable: Database storage layer disconnected.")

    recipients_out = []
    
    try:
        recs = await db.query("caregiver_recipients", filters={"caregiver_id": current_user.user_id}, limit=100)
        pending = await db.query("caregiver_links", filters={"creator_user_id": current_user.user_id, "status": "pending"}, limit=100)
        pending_invites = len(pending) if pending else 0
        
        for r in (recs or []):
            meds = await db.query("caregiver_medications", filters={"recipient_code": r["code"]}, limit=50)
            alerts = await db.query("caregiver_alerts", filters={"recipient_code": r["code"]}, limit=20)
            recipients_out.append({
                "code": r["code"],
                "name": r.get("name", r["code"]),
                "medications": meds or [],
                "alerts": alerts or []
            })
        return {"recipients": recipients_out, "total_linked": len(recipients_out), "pending_invites": pending_invites}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve dashboard state: {str(e)}")


@router.post("/recipient/{code}/medication")
async def add_recipient_medication(code: str, drug_name: str, ndc: str = "", confidence: float = 0, current_user: CurrentUser = Depends(require_current_user)):
    """Add a verified medication to recipient profile and run real enterprise interaction scans."""
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="503 Service Unavailable: Database storage layer disconnected.")

    # Verify authorization (ensure caregiver is linked to this recipient)
    recs = await db.query("caregiver_recipients", filters={"code": code, "caregiver_id": current_user.user_id})
    if not recs:
        raise HTTPException(status_code=403, detail="403 Forbidden: Not authorized to manage this care recipient.")

    resolved = await resolve_all_drugs([drug_name])
    new_rxcui = resolved[0].get("rxcui") if resolved else None
    resolved_name = resolved[0].get("generic_name", drug_name) if resolved else drug_name

    med = {
        "id": str(uuid.uuid4()),
        "recipient_code": code,
        "name": resolved_name,
        "ndc": ndc,
        "rxcui": new_rxcui,
        "status": "verified" if confidence >= 70 else "unverified",
        "confidence": confidence
    }
    
    existing_rxcuis = []
    
    try:
        await db.insert("caregiver_medications", med)
        existing_meds = await db.query("caregiver_medications", filters={"recipient_code": code}, limit=100)
        if existing_meds:
            existing_rxcuis = [m.get("rxcui") for m in existing_meds if m.get("rxcui")]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to persist recipient medication: {str(e)}")

    # Real enterprise severity interactions check
    new_alerts = []
    if new_rxcui and existing_rxcuis:
        rxcuis_to_check = list(set([new_rxcui] + existing_rxcuis))
        if len(rxcuis_to_check) > 1:
            ixns = await check_interactions_enterprise(rxcuis_to_check)
            for ixn in ixns:
                if ixn.severity in ["major", "contraindicated"] and new_rxcui in [getattr(ixn, "drug_a_rxcui", ""), getattr(ixn, "drug_b_rxcui", ""), new_rxcui]:
                    alert = {
                        "id": str(uuid.uuid4()),
                        "type": "interaction",
                        "message": f"DANGEROUS INTERACTION: {ixn.drug_a} and {ixn.drug_b}. Severity: {ixn.severity}. {ixn.mechanism}",
                        "recipient_code": code,
                        "severity": "high"
                    }
                    new_alerts.append(alert)
                    
    if confidence < 70:
        new_alerts.append({
            "id": str(uuid.uuid4()),
            "type": "verification",
            "message": f"Low confidence verification for {drug_name} ({confidence}%)",
            "recipient_code": code,
            "severity": "high" if confidence < 40 else "moderate"
        })

    for alert in new_alerts:
        try:
            await db.insert("caregiver_alerts", alert)
        except Exception:
            pass

    return {"status": "added", "medication": med, "new_alerts": new_alerts}


@router.get("/alerts")
async def get_caregiver_alerts(current_user: CurrentUser = Depends(require_current_user)):
    """Get all unread clinical monitoring alerts strictly scoped to current caregiver."""
    db = get_supabase()
    if not db.available:
        raise HTTPException(status_code=503, detail="503 Service Unavailable: Database storage layer disconnected.")

    try:
        # Get all recipient codes linked to this caregiver
        recs = await db.query("caregiver_recipients", filters={"caregiver_id": current_user.user_id}, limit=100)
        rec_codes = [r["code"] for r in (recs or [])]
        
        all_alerts = []
        for code in rec_codes:
            alerts = await db.query("caregiver_alerts", filters={"recipient_code": code}, limit=50)
            all_alerts.extend(alerts or [])
            
        return {"alerts": all_alerts, "total": len(all_alerts)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve alerts: {str(e)}")
