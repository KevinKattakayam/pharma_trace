"""Safety-case workflow: triage, quarantine and resolution of medicine incidents."""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException

from dependencies import require_current_user
from models.schemas import CurrentUser, SafetyCaseCreateRequest, SafetyCaseResponse, SafetyCaseUpdateRequest
from repositories.entities import SafetyCaseRepository

router = APIRouter(prefix="/safety-cases", tags=["safety cases"])
repo = SafetyCaseRepository()


def _context(user: CurrentUser) -> dict:
    return {"user_id": user.user_id, "clinic_id": user.clinic_id, "role": user.role}


@router.post("", response_model=SafetyCaseResponse, status_code=201)
async def create_safety_case(payload: SafetyCaseCreateRequest, user: CurrentUser = Depends(require_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    row = {
        "id": str(uuid.uuid4()),
        "user_id": user.user_id,
        "clinic_id": user.clinic_id,
        "verification_id": payload.verification_id,
        "medicine_name": payload.medicine_name.strip(),
        "batch_number": payload.batch_number.strip() if payload.batch_number else None,
        "issue_type": payload.issue_type,
        "notes": payload.notes.strip(),
        "quarantined": payload.quarantined,
        "status": "open",
        "created_at": now,
        "updated_at": now,
    }
    await repo.create(row, user_context=_context(user))
    return SafetyCaseResponse(**row)


@router.get("", response_model=list[SafetyCaseResponse])
async def list_safety_cases(user: CurrentUser = Depends(require_current_user)):
    filters = None if user.role in ("admin", "clinic_admin") else {"user_id": user.user_id}
    rows = await repo.list_all(filters=filters, limit=100, order_by="created_at", order_desc=True, user_context=_context(user))
    return [SafetyCaseResponse(**row) for row in rows]


@router.patch("/{case_id}", response_model=SafetyCaseResponse)
async def update_safety_case(case_id: str, payload: SafetyCaseUpdateRequest, user: CurrentUser = Depends(require_current_user)):
    row = await repo.find_by_id(case_id, user_context=_context(user))
    if not row:
        raise HTTPException(status_code=404, detail="Safety case not found")
    if row.get("user_id") != user.user_id and user.role not in ("admin", "clinic_admin"):
        raise HTTPException(status_code=403, detail="Only the owner or a clinic administrator can update this safety case")
    updated = await repo.update(case_id, {
        "status": payload.status,
        "resolution_note": payload.resolution_note,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }, user_context=_context(user))
    return SafetyCaseResponse(**updated)
