"""Parser for India's GSR 823(E) pack QR / barcode (Schedule H2 "top 300" brands).

The Drugs (Eighth Amendment) Rules 2022, GSR 823(E) dated 17 Nov 2022, in force from
1 Aug 2023, require these particulars in the code (CDSCO FAQ, 21 Jul 2023):

  1. unique product identification code   5. batch number
  2. proper and generic name               6. date of manufacturing
  3. brand name                            7. date of expiry
  4. name and address of the manufacturer  8. manufacturing licence number

MRP is **not** one of the eight (the previous parser required MRP and ignored the licence
number). CDSCO also states the unique product identification code is decided by the
manufacturer's own SOP, so it is not necessarily a GTIN.

There is no single mandated encoding; manufacturers use JSON, delimited text, GS1 element
strings, or URLs. A well-formed code is NOT evidence of authenticity: it can be copied.
"""
from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from services import gs1

SOURCE_URL = "https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadPublic_NoticesFiles/Final%20FAQs%20on%20QR%20code%2021.07.2023.pdf"

PARTICULARS: dict[str, str] = {
    "upic": "Unique product identification code",
    "generic_name": "Proper and generic name",
    "brand_name": "Brand name",
    "manufacturer": "Name and address of the manufacturer",
    "batch_no": "Batch number",
    "mfg_date": "Date of manufacturing",
    "expiry_date": "Date of expiry",
    "mfg_license": "Manufacturing licence number",
}

# Lower-cased key aliases observed in manufacturer encodings.
_KEYS: dict[str, tuple[str, ...]] = {
    "upic": ("upic", "upi", "gtin", "uid", "product_code", "productcode"),
    "generic_name": ("api", "generic", "generic_name", "genericname", "proper_name", "composition"),
    "brand_name": ("brand", "brand_name", "brandname", "product", "product_name"),
    "manufacturer": ("mfg", "manufacturer", "mfr", "mfg_name", "manufactured_by", "marketed_by"),
    "batch_no": ("batch", "batch_no", "batchno", "lot", "b.no", "bno"),
    "mfg_date": ("mfd", "mfgdate", "mfg_date", "manufacturing_date", "mfd_date", "dom"),
    "expiry_date": ("exp", "expdate", "exp_date", "expiry", "expiry_date", "use_before"),
    "mfg_license": ("lic", "license", "licence", "mfg_lic", "mfg_license", "mfg_licence", "ml_no", "lic_no"),
    "mrp": ("mrp", "price"),
}
# Positional order for delimited payloads follows the order of the particulars in the rule.
_POSITIONAL = ("upic", "generic_name", "brand_name", "manufacturer", "batch_no", "mfg_date", "expiry_date", "mfg_license")


def _empty(raw: str) -> dict[str, Any]:
    return {"format": "INDIA_GSR823E", "raw": raw, **{k: None for k in (*PARTICULARS, "mrp")}}


def _from_mapping(obj: dict[str, Any], out: dict[str, Any]) -> None:
    lowered = {str(k).strip().lower(): v for k, v in obj.items()}
    for field, aliases in _KEYS.items():
        for alias in aliases:
            val = lowered.get(alias)
            if val not in (None, ""):
                out[field] = str(val).strip()
                break


def parse(data: str) -> dict[str, Any]:
    raw = (data or "").strip()
    out = _empty(raw)
    payload = raw
    if raw.lower().startswith(("http://", "https://")):
        url = urlparse(raw)
        qs = {k.lower(): v[0] for k, v in parse_qs(url.query).items() if v}
        if "/01/" in url.path:  # GS1 Digital Link
            g = gs1.parse(raw)
            out.update(upic=g["gtin"], batch_no=g["lot"], expiry_date=g["expiry_date"], mfg_date=g["production_date"])
        payload = unquote(qs.pop("data", qs.pop("d", "")))
        if not payload:
            _from_mapping(qs, out)
    if payload:
        try:
            obj = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            obj = None
        if isinstance(obj, dict):
            _from_mapping(obj, out)
        elif payload.startswith("(") or payload[:2] in ("01", "]d"):
            g = gs1.parse(payload)
            if g["gtin"]:
                out.update(upic=g["gtin"], batch_no=g["lot"], expiry_date=g["expiry_date"], mfg_date=g["production_date"])
        else:
            for sep in ("|", ";", "\n", "~"):
                parts = [p.strip() for p in payload.split(sep)]
                if len(parts) >= 6:
                    if all(":" in p for p in parts if p):
                        _from_mapping(dict(p.split(":", 1) for p in parts if p), out)
                    else:
                        for field, value in zip(_POSITIONAL, parts, strict=False):  # payloads may carry extra/fewer trailing fields
                            out[field] = value or None
                    break
    present = [k for k in PARTICULARS if out.get(k)]
    out["particulars_present"] = present
    out["particulars_missing"] = [k for k in PARTICULARS if k not in present]
    out["recognised"] = len(present) >= 3
    out["complete"] = not out["particulars_missing"]
    return out
