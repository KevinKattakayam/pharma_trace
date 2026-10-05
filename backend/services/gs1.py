"""GS1 Application Identifier parsing for pharmaceutical codes (DataMatrix / GS1-128 / Digital Link).

Supports:
* Human-readable form:   ``(01)08901030865478(17)270131(10)AB1234(21)SN998877``
* Raw element string:    ``0108901030865478172701311OAB1234<GS>21SN998877`` (FNC1 = ASCII 29)
  with an optional symbology identifier prefix (``]d2``, ``]C1``, ``]Q3``).
* GS1 Digital Link URI:  ``https://id.example.com/01/08901030865478/10/AB1234?17=270131``

Reference: GS1 General Specifications, section 3 (Application Identifiers). Only AIs
relevant to medicine packs are named; unknown AIs are preserved verbatim.

Replaces the previous parser, which shifted every bracketed value by one character
(GTIN ")0890103086547") and let the batch swallow the serial number.
"""
from __future__ import annotations

import calendar
import re
from datetime import date
from typing import Any
from urllib.parse import parse_qs, urlparse

GS = "\x1d"

# AI -> (name, fixed_length or None for variable, max_length)
AI_TABLE: dict[str, tuple[str, int | None, int]] = {
    "00": ("SSCC", 18, 18),
    "01": ("GTIN", 14, 14),
    "02": ("CONTENT_GTIN", 14, 14),
    "10": ("BATCH_LOT", None, 20),
    "11": ("PROD_DATE", 6, 6),
    "15": ("BEST_BEFORE", 6, 6),
    "17": ("EXPIRY", 6, 6),
    "21": ("SERIAL", None, 20),
    "30": ("VAR_COUNT", None, 8),
    "240": ("ADDITIONAL_ID", None, 30),
    "710": ("NHRN_DE", None, 20),
    "711": ("NHRN_FR", None, 20),
    "712": ("NHRN_ES", None, 20),
    "713": ("NHRN_BR", None, 20),
    "714": ("NHRN_PT", None, 20),
}
_HRI = re.compile(r"\((\d{2,4})\)([^()]*)")
_SYMBOLOGY_PREFIX = re.compile(r"^\][A-Za-z]\d")


def gtin_check_digit_ok(gtin: str) -> bool:
    if not gtin.isdigit() or len(gtin) not in (8, 12, 13, 14):
        return False
    digits = [int(c) for c in gtin]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def parse_gs1_date(yymmdd: str) -> date | None:
    """YYMMDD with GS1 century rule and DD=00 meaning last day of the month."""
    if not re.fullmatch(r"\d{6}", yymmdd or ""):
        return None
    yy, mm, dd = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:])
    if not 1 <= mm <= 12:
        return None
    # GS1 GenSpecs 7.12: years within -49..+50 of the current year.
    current = date.today().year
    century = current - current % 100
    year = century + yy
    if year - current > 50:
        year -= 100
    elif current - year > 49:
        year += 100
    last = calendar.monthrange(year, mm)[1]
    if dd == 0:
        dd = last
    if not 1 <= dd <= last:
        return None
    return date(year, mm, dd)


def _match_ai(s: str) -> str | None:
    for length in (2, 3, 4):
        if s[:length] in AI_TABLE:
            return s[:length]
    return None


def _parse_raw(data: str) -> tuple[dict[str, str], list[str]]:
    fields: dict[str, str] = {}
    errors: list[str] = []
    i = 0
    while i < len(data):
        if data[i] == GS:
            i += 1
            continue
        ai = _match_ai(data[i:])
        if ai is None:
            errors.append(f"unknown AI at position {i}")
            break
        _, fixed, max_len = AI_TABLE[ai]
        start = i + len(ai)
        if fixed:
            value = data[start:start + fixed]
            i = start + fixed
        else:
            end = data.find(GS, start)
            end = len(data) if end == -1 else end
            value = data[start:end]
            i = end
            if len(value) > max_len:
                errors.append(f"AI {ai} longer than {max_len} characters")
        fields[ai] = value
    return fields, errors


def _parse_digital_link(data: str) -> dict[str, str]:
    url = urlparse(data)
    parts = [p for p in url.path.split("/") if p]
    fields: dict[str, str] = {}
    for idx in range(len(parts) - 1):
        if parts[idx] in AI_TABLE:
            fields[parts[idx]] = parts[idx + 1]
    for key, values in parse_qs(url.query).items():
        if key in AI_TABLE and values:
            fields[key] = values[0]
    return fields


def parse(data: str) -> dict[str, Any]:
    raw = (data or "").strip()
    errors: list[str] = []
    if raw.lower().startswith(("http://", "https://")):
        fields = _parse_digital_link(raw)
        form = "digital_link"
    elif raw.startswith("("):
        fields = {ai: val.strip().rstrip(GS) for ai, val in _HRI.findall(raw)}
        form = "hri"
    else:
        fields, errors = _parse_raw(_SYMBOLOGY_PREFIX.sub("", raw))
        form = "element_string"

    gtin = fields.get("01")
    expiry = parse_gs1_date(fields.get("17", ""))
    prod = parse_gs1_date(fields.get("11", ""))
    if gtin and not gtin_check_digit_ok(gtin):
        errors.append("GTIN check digit invalid")
    if "17" in fields and expiry is None:
        errors.append("expiry (AI 17) is not a valid YYMMDD date")
    return {
        "raw": raw,
        "form": form,
        "gtin": gtin,
        "gtin_check_digit_valid": gtin_check_digit_ok(gtin) if gtin else None,
        "lot": fields.get("10"),
        "serial_number": fields.get("21"),
        "expiry_date": expiry.isoformat() if expiry else None,
        "production_date": prod.isoformat() if prod else None,
        "national_codes": {AI_TABLE[k][0]: v for k, v in fields.items() if k.startswith("71")},
        "parsed_fields": [{"ai": k, "name": AI_TABLE.get(k, ("UNKNOWN",))[0], "value": v} for k, v in fields.items()],
        "errors": errors,
        "valid": bool(gtin) and not errors,
    }
