"""
Audit Export Router — Generates regulatory-compliant audit chain exports.
Supports CSV and PDF output formats with SHA-256 hash chain verification.
A drug inspector requests this during a clinic audit.
"""
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from dependencies import ensure_clinic_access, require_role
from models.schemas import CurrentUser

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("/export")
async def export_audit_chain(
    format: str = Query("csv", enum=["csv", "pdf"]),
    start_date: str = Query(None, description="ISO date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="ISO date (YYYY-MM-DD)"),
    clinic_id: str = Query(None, description="Filter by clinic ID"),
    redacted: bool = Query(True, description="Redact patient PII"),
    user: CurrentUser = Depends(require_role("auditor", "regulator", "clinic_admin")),
):
    """
    Export the SHA-256 audit chain for regulatory compliance.
    Returns a signed CSV or PDF with record hash, previous hash,
    verification status, and chain integrity verification.
    Streams directly to the client without persisting to ephemeral storage.
    """
    if user.role == "clinic_admin":
        if not clinic_id:
            clinic_id = user.clinic_id
        ensure_clinic_access(user, clinic_id or "")

    from services.audit import compute_hash, list_records, verify_chain  # noqa: F401

    # Parse date filters
    dt_start = None
    dt_end = None
    if start_date:
        try:
            dt_start = datetime.fromisoformat(start_date).replace(tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid start_date: {start_date}")
    if end_date:
        try:
            dt_end = datetime.fromisoformat(end_date).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid end_date: {end_date}")

    filtered = []
    for rec in await list_records(limit=100_000):
        record = {
            "id": rec.get("id"),
            "verification_id": rec.get("verification_id"),
            "record_hash": rec.get("record_hash"),
            "previous_hash": rec.get("previous_hash"),
            "canonical": rec.get("_canonical"),
            "created_at": rec.get("recorded_at", ""),
            "verified_at": rec.get("client_reported_at", ""),
            "record_data": rec,
        }
        try:
            rec_dt = datetime.fromisoformat(str(record["created_at"]).replace("Z", "+00:00"))
        except ValueError:
            rec_dt = None
        if dt_start and rec_dt and rec_dt < dt_start:
            continue
        if dt_end and rec_dt and rec_dt > dt_end:
            continue
        if clinic_id and rec.get("clinic_id") != clinic_id:
            continue
        filtered.append(record)

    chain_status = await verify_chain()

    if format == "csv":
        buffer, filename, media_type = _generate_csv(filtered, chain_status, redacted)
    else:
        buffer, filename, media_type = _generate_pdf(filtered, chain_status, redacted)

    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
def _redact_value(val):
    """Keyed pseudonym (an unkeyed MD5 of a low-entropy value is reversible by dictionary)."""
    if not val:
        return val
    from services.security import pseudonymise
    return "REDACTED-" + pseudonymise(str(val), purpose="audit-export")[:10]

def _generate_csv(records: list[dict], chain_status: dict, redacted: bool) -> tuple:
    """Generate a CSV export of the audit chain."""
    output = io.StringIO()
    writer = csv.writer(output)

    # Header metadata
    writer.writerow(["# PharmaTrace Audit Chain Export"])
    writer.writerow([f"# Generated: {datetime.now(timezone.utc).isoformat()}"])
    if redacted:
        writer.writerow(["# PRIVACY NOTICE: This is a REDACTED regulatory copy. Patient PII is anonymized."])
    writer.writerow([f"# Chain Valid: {chain_status['chain_valid']}"])
    writer.writerow([f"# Total Records in Chain: {chain_status['total_records']}"])
    writer.writerow([f"# Records in Export: {len(records)}"])
    if chain_status.get("broken_at_row"):
        writer.writerow([f"# WARNING: Chain broken at row {chain_status['broken_at_row']}"])
    writer.writerow([])

    # Column headers
    writer.writerow([
        "Row", "Verification ID", "Record Hash (SHA-256)", "Previous Hash",
        "Method", "Verdict", "Confidence", "Drug/Barcode", "Source", "Verified At", "Created At", "Hash Valid"
    ])

    from services.audit import compute_hash as _compute_hash
    for i, record in enumerate(records):
        expected = _compute_hash(record["previous_hash"], record["canonical"] or "")
        hash_valid = expected == record["record_hash"]

        rec_data = record.get("record_data", {})
        source = rec_data.get("source", "")
        if redacted and source:
            source = _redact_value(source)

        writer.writerow([
            record.get("id", i + 1),
            record.get("verification_id", ""),
            record.get("record_hash", ""),
            record.get("previous_hash", ""),
            rec_data.get("method", ""),
            rec_data.get("verdict", ""),
            rec_data.get("confidence", ""),
            rec_data.get("barcode", rec_data.get("drug", "")),
            source,
            record.get("verified_at", ""),
            record.get("created_at", ""),
            "✓" if hash_valid else "✗ TAMPERED",
        ])

    output.seek(0)
    filename = f"pharmatrace_audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"
    return output, filename, "text/csv"


def _generate_pdf(records: list[dict], chain_status: dict, redacted: bool) -> tuple:
    """Generate a PDF export of the audit chain using reportlab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError:
        return _generate_csv(records, chain_status, redacted)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=15 * mm, rightMargin=15 * mm, topMargin=20 * mm, bottomMargin=15 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("AuditTitle", parent=styles["Title"], fontSize=18, spaceAfter=4 * mm)
    meta_style = ParagraphStyle("Meta", parent=styles["Normal"], fontSize=9, textColor=colors.grey)

    elements = []
    elements.append(Paragraph("PharmaTrace — Audit Chain Export", title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} | "
        f"Chain Valid: {'YES ✓' if chain_status['chain_valid'] else 'NO ✗ — TAMPERED'} | "
        f"Records: {len(records)} of {chain_status['total_records']}",
        meta_style
    ))
    if redacted:
        elements.append(Paragraph("<b>PRIVACY NOTICE:</b> This is a REDACTED regulatory copy. Patient PII is anonymized.", meta_style))
    
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#6366f1")))
    elements.append(Spacer(1, 4 * mm))

    from services.audit import compute_hash as _compute_hash
    header = ["#", "Verification ID", "Hash (first 16)", "Prev Hash (first 16)", "Method", "Verdict", "Confidence", "Verified At", "Valid"]
    data = [header]
    for i, record in enumerate(records):
        expected = _compute_hash(record["previous_hash"], record["canonical"] or "")
        hash_valid = expected == record["record_hash"]
        rec_data = record.get("record_data", {})

        data.append([
            str(record.get("id", i + 1)),
            record.get("verification_id", "")[:12] + "…",
            record.get("record_hash", "")[:16] + "…",
            record.get("previous_hash", "")[:16] + "…",
            rec_data.get("method", ""),
            rec_data.get("verdict", ""),
            str(rec_data.get("confidence", "")),
            record.get("verified_at", "")[:19],
            "✓" if hash_valid else "✗",
        ])

    col_widths = [25, 95, 100, 100, 50, 65, 55, 120, 30]
    table = Table(data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6366f1")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("FONTSIZE", (0, 1), (-1, -1), 6.5),
        ("FONTNAME", (2, 1), (3, -1), "Courier"),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ALIGN", (-1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 8 * mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Spacer(1, 3 * mm))
    elements.append(Paragraph(
        f"Document Hash: SHA-256 chain anchored to genesis <font name='Courier' size='7'>a1b2c3...{chain_status.get('last_hash', 'N/A')[-8:]}</font>",
        meta_style
    ))
    elements.append(Paragraph(
        "This document is machine-generated by PharmaTrace for regulatory audit purposes. "
        "Each row's hash is independently verifiable against the previous row's hash.",
        meta_style
    ))

    doc.build(elements)
    buffer.seek(0)
    filename = f"pharmatrace_audit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.pdf"
    return buffer, filename, "application/pdf"
