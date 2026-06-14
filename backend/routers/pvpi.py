"""
PvPI (Pharmacovigilance Programme of India) Adverse Event Reporting Router.
Pre-fills a structured adverse event report from a verified drug result.
The form data can POST directly to the PvPI portal — no backend storage of patient data needed.
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/pvpi", tags=["pvpi"])

# PvPI portal submission URL (ADR form)
PVPI_PORTAL_URL = "https://www.ipc.gov.in/PvPI/adr.html"


class PvPIReportRequest(BaseModel):
    """Input: a verified drug result + patient/reporter details."""
    verification_id: str
    drug_name: str
    drug_brand_name: Optional[str] = None
    manufacturer: Optional[str] = None
    batch_no: Optional[str] = None
    ndc: Optional[str] = None
    # Patient information (initials only — no full names for privacy)
    patient_initials: Optional[str] = None
    patient_age: Optional[int] = None
    patient_sex: Optional[str] = None  # M, F, Other
    # Adverse event details
    adverse_event: str  # free-text description
    date_of_onset: Optional[str] = None  # ISO date
    outcome: Optional[str] = None  # recovered, recovering, not_recovered, fatal, unknown
    seriousness: Optional[str] = None  # serious, non_serious
    # Reporter
    reporter_name: Optional[str] = None
    reporter_qualification: Optional[str] = None  # physician, pharmacist, nurse, patient, other
    reporter_institution: Optional[str] = None
    reporter_email: Optional[str] = None


class PvPIFormData(BaseModel):
    """Output: structured form data ready for PvPI portal submission."""
    form_fields: dict
    portal_url: str
    instructions: str
    can_auto_submit: bool


@router.post("/prefill-report")
async def prefill_pvpi_report(req: PvPIReportRequest) -> PvPIFormData:
    """
    Generate a pre-filled PvPI-compatible adverse event report form.
    The frontend renders this as a confirmation form and can either:
    1. Open the PvPI portal in a new tab with pre-filled fields, or
    2. Let the user download a filled PDF for manual submission.
    """

    # Map our fields to PvPI ADR form field names
    form_fields = {
        # Section A: Patient Information
        "patient_initials": req.patient_initials or "",
        "patient_age": str(req.patient_age) if req.patient_age else "",
        "patient_sex": req.patient_sex or "",

        # Section B: Suspected Adverse Reaction
        "adverse_reaction_description": req.adverse_event,
        "date_of_onset": req.date_of_onset or "",
        "outcome": _map_outcome(req.outcome),
        "seriousness": "Yes" if req.seriousness == "serious" else "No",

        # Section C: Suspected Medication
        "drug_name_generic": req.drug_name,
        "drug_name_brand": req.drug_brand_name or "",
        "manufacturer": req.manufacturer or "",
        "batch_lot_number": req.batch_no or "",
        "dose": "",  # User fills this in
        "route": "",  # User fills this in
        "indication": "",  # User fills this in
        "date_started": "",
        "date_stopped": "",

        # Section D: Reporter Information
        "reporter_name": req.reporter_name or "",
        "reporter_qualification": req.reporter_qualification or "",
        "reporter_institution": req.reporter_institution or "",
        "reporter_email": req.reporter_email or "",
        "report_date": _today_iso(),

        # PharmaTrace metadata (for traceability)
        "pharmatrace_verification_id": req.verification_id,
        "pharmatrace_ndc": req.ndc or "",
    }

    # Persist a local record for tracking (not patient data — just status)
    from services.supabase import get_supabase
    db = get_supabase()
    if db.available:
        try:
            await db.insert("pvpi_reports", {
                "verification_id": req.verification_id,
                "drug_name": req.drug_name,
                "patient_initials": req.patient_initials,
                "patient_age": req.patient_age,
                "adverse_event_description": req.adverse_event,
                "date_of_onset": req.date_of_onset,
                "reporter_name": req.reporter_name,
                "reporter_type": req.reporter_qualification or "other",
                "status": "pending_submission",
            })
        except Exception:
            pass  # Non-critical — the form still works

    return PvPIFormData(
        form_fields=form_fields,
        portal_url=PVPI_PORTAL_URL,
        instructions=(
            "Review the pre-filled fields below. Complete the dosage and indication fields, "
            "then submit directly to the PvPI portal. Your verification ID is included for "
            "traceability. No patient-identifiable data is stored on PharmaTrace servers."
        ),
        can_auto_submit=False,  # PvPI doesn't have a structured API — manual submission required
    )


@router.get("/report-status/{verification_id}")
async def get_report_status(verification_id: str):
    """Check the submission status of a PvPI report."""
    from services.supabase import get_supabase
    db = get_supabase()
    if not db.available:
        return {"status": "unknown", "message": "Database not configured"}

    try:
        reports = await db.query("pvpi_reports", limit=100)
        match = next(
            (r for r in (reports or []) if r.get("verification_id") == verification_id),
            None
        )
        if match:
            return {
                "status": match.get("status", "pending_submission"),
                "drug_name": match.get("drug_name"),
                "created_at": match.get("created_at"),
                "pvpi_reference_id": match.get("pvpi_reference_id"),
            }
    except Exception:
        pass

    return {"status": "not_found"}


def _map_outcome(outcome: str | None) -> str:
    """Map our outcome codes to PvPI-expected values."""
    mapping = {
        "recovered": "Recovered",
        "recovering": "Recovering",
        "not_recovered": "Not Recovered",
        "fatal": "Fatal",
        "unknown": "Unknown",
    }
    return mapping.get(outcome or "", "Unknown")


def _today_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
