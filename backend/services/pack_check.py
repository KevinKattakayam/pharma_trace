"""Pack label consistency check ("Pack Check").

Compares what the pack's QR/DataMatrix *encodes* with what is *printed* on the pack and with
basic date logic. Counterfeiters frequently copy one genuine QR onto many packs; the copied
code then disagrees with the printed batch or expiry. That disagreement is observable without
any manufacturer partnership.

What this does NOT do: prove a pack is genuine. A perfectly consistent pack can still be
falsified (the whole label can be copied). Results are "consistent / inconsistent /
incomplete", never "authentic".

Assumptions (documented in ADR-0005):
* A month-only expiry ("12/2027") is read as valid through the last day of that month.
* A month-only manufacturing date is read as the first day of that month.
* Shelf life > 5 years is unusual for finished formulations and is flagged as a *warning*,
  not as an inconsistency, because some products legitimately exceed it.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any

from rapidfuzz import fuzz

from services import gs1, india_qr
from services.batch_alerts import get_index, normalise_batch

_MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}
_MONTHS.update({m.lower(): i for i, m in enumerate(calendar.month_name) if m})
_MONTHS["sept"] = 9

CITATION_GSR = india_qr.SOURCE_URL


def parse_label_date(value: str | None, *, end_of_month: bool) -> date | None:
    """Parse common Indian label date formats. Returns None when ambiguous/unparseable."""
    if not value:
        return None
    s = str(value).strip().lower().replace(".", "/").replace(" ", "/").replace("-", "/")
    s = re.sub(r"^(exp|expiry|mfd|mfg|use/before)[:/]*", "", s).strip("/")

    def mk(y: int, m: int, d: int | None) -> date | None:
        if y < 100:
            y += 2000
        if not (1 <= m <= 12 and 1990 <= y <= 2100):
            return None
        last = calendar.monthrange(y, m)[1]
        if d is None:
            d = last if end_of_month else 1
        return date(y, m, d) if 1 <= d <= last else None

    if m := re.fullmatch(r"(\d{4})/(\d{1,2})/(\d{1,2})", s):  # ISO
        return mk(int(m[1]), int(m[2]), int(m[3]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})", s):  # DD/MM/YYYY (Indian order)
        return mk(int(m[3]), int(m[2]), int(m[1]))
    if m := re.fullmatch(r"(\d{1,2})/(\d{4}|\d{2})", s):  # MM/YYYY
        return mk(int(m[2]), int(m[1]), None)
    if m := re.fullmatch(r"([a-z]{3,9})/*(\d{4}|\d{2})", s):  # MMM/YYYY, MMMYYYY
        mon = _MONTHS.get(m[1])
        return mk(int(m[2]), mon, None) if mon else None
    if re.fullmatch(r"\d{6}", s):  # GS1 YYMMDD
        return gs1.parse_gs1_date(s)
    return None


def _finding(code: str, severity: str, message: str, field: str | None = None, citation: str | None = None) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, "field": field, "citation": citation}


def _names_agree(a: str | None, b: str | None) -> bool | None:
    if not a or not b:
        return None
    return fuzz.token_set_ratio(a.lower(), b.lower()) >= 80


def check_pack(
    *,
    qr_payload: str | None = None,
    printed: dict[str, str | None] | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    today = today or date.today()
    printed = {k: (v.strip() if isinstance(v, str) and v.strip() else None) for k, v in (printed or {}).items()}
    findings: list[dict[str, Any]] = []
    flags: list[str] = []

    qr: dict[str, Any] = {}
    if qr_payload:
        qr = india_qr.parse(qr_payload)
        if not qr["recognised"]:
            g = gs1.parse(qr_payload)
            if g["gtin"]:
                qr.update(upic=g["gtin"], batch_no=g["lot"], expiry_date=g["expiry_date"], mfg_date=g["production_date"])
                qr["particulars_present"] = [k for k in india_qr.PARTICULARS if qr.get(k)]
                qr["particulars_missing"] = [k for k in india_qr.PARTICULARS if not qr.get(k)]
                if g["gtin_check_digit_valid"] is False:
                    flags.append("invalid_check_digit")
                    findings.append(_finding("gtin_check_digit", "critical", "GTIN check digit is invalid.", "upic"))
            else:
                findings.append(_finding("qr_unrecognised", "warn", "The scanned code is not a recognised medicine pack format."))
        missing = qr.get("particulars_missing", [])
        if qr.get("particulars_present") and missing:
            findings.append(_finding(
                "gsr823e_particulars_missing", "warn",
                "Code is missing particulars required by GSR 823(E) for Schedule H2 (top-300) brands: "
                + ", ".join(india_qr.PARTICULARS[m] for m in missing)
                + ". This matters only if the brand is on the Schedule H2 list.",
                citation=CITATION_GSR,
            ))

    merged = {k: printed.get(k) or qr.get(k) for k in ("batch_no", "expiry_date", "mfg_date", "brand_name", "generic_name", "manufacturer")}

    # 1. QR vs printed label (strongest cloned-code signal)
    pb, qb = normalise_batch(printed.get("batch_no")), normalise_batch(qr.get("batch_no"))
    if pb and qb and pb != qb:
        flags.append("label_inconsistent")
        findings.append(_finding("batch_mismatch", "critical",
            f"Batch in code ({qr.get('batch_no')}) differs from printed batch ({printed.get('batch_no')}). "
            "Copied codes on falsified packs commonly show this.", "batch_no"))
    for fld, label, eom in (("expiry_date", "Expiry", True), ("mfg_date", "Manufacturing date", False)):
        pd_, qd = parse_label_date(printed.get(fld), end_of_month=eom), parse_label_date(qr.get(fld), end_of_month=eom)
        if pd_ and qd and (pd_.year, pd_.month) != (qd.year, qd.month):
            flags.append("label_inconsistent")
            findings.append(_finding(f"{fld}_mismatch", "critical", f"{label} in code ({qd:%m/%Y}) differs from printed ({pd_:%m/%Y}).", fld))
    for fld, label in (("brand_name", "Brand"), ("generic_name", "Generic name")):
        if _names_agree(printed.get(fld), qr.get(fld)) is False:
            flags.append("label_inconsistent")
            findings.append(_finding(f"{fld}_mismatch", "critical", f"{label} in code ('{qr.get(fld)}') differs from printed ('{printed.get(fld)}').", fld))

    # 2. Date logic
    exp = parse_label_date(merged["expiry_date"], end_of_month=True)
    mfg = parse_label_date(merged["mfg_date"], end_of_month=False)
    if merged["expiry_date"] and not exp:
        findings.append(_finding("expiry_unparseable", "warn", f"Could not read expiry date '{merged['expiry_date']}'. Check it by eye.", "expiry_date"))
    if exp:
        days = (exp - today).days
        if days < 0:
            flags.append("expired")
            findings.append(_finding("expired", "critical", f"Expired {-days} day(s) ago ({exp:%d %b %Y}). Do not use; return to a pharmacist.", "expiry_date"))
        elif days <= 90:
            findings.append(_finding("expiring_soon", "info", f"Expires in {days} day(s) ({exp:%d %b %Y}).", "expiry_date"))
    if mfg and mfg > today:
        flags.append("label_inconsistent")
        findings.append(_finding("mfg_in_future", "critical", f"Manufacturing date {mfg:%m/%Y} is in the future.", "mfg_date"))
    if mfg and exp:
        if mfg >= exp:
            flags.append("label_inconsistent")
            findings.append(_finding("mfg_after_expiry", "critical", "Manufacturing date is on or after the expiry date.", "mfg_date"))
        elif (exp - mfg).days > 5 * 366:
            findings.append(_finding("long_shelf_life", "warn", "Shelf life over 5 years is unusual for most formulations; confirm with a pharmacist.", "expiry_date"))

    # 3. Regulator batch alerts
    batch_result = get_index().match(merged["batch_no"], merged["brand_name"], merged["generic_name"])
    if batch_result["status"] == "match":
        flags.extend(batch_result["integrity_flags"])
        for m in batch_result["matches"]:
            if m["match_type"] == "exact":
                findings.append(_finding("regulator_batch_alert", "critical",
                    f"Batch listed as {m['category'].upper()} in {m['source']} alert {m['alert_month']}: {m['reason'] or 'see source'}.",
                    "batch_no", m["source_url"]))
    elif batch_result["status"] == "review":
        findings.append(_finding("regulator_batch_review", "warn",
            "A regulator alert lists the same (or a similar-looking) batch number for a different or unconfirmed product. Re-check the printed batch and product name.",
            "batch_no"))

    flags = list(dict.fromkeys(flags))
    critical = any(f["severity"] == "critical" for f in findings)
    has_data = bool(qr_payload) or any(printed.values())
    status = "inconsistent" if critical else ("insufficient_data" if not has_data else ("incomplete" if any(f["severity"] == "warn" for f in findings) else "consistent"))
    return {
        "status": status,
        "integrity_flags": flags,
        "findings": findings,
        "qr_fields": {k: qr.get(k) for k in (*india_qr.PARTICULARS, "mrp")} if qr else None,
        "batch_alerts": batch_result,
        "requires_human_review": True,
        "disclaimer": "Consistency is not authenticity. A genuine code can be copied onto a falsified pack. "
                      "If anything looks wrong, do not use the medicine and ask a pharmacist; you can report it to CDSCO.",
    }
