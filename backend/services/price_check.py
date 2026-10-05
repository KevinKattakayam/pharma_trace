"""MRP check against NPPA ceiling prices (India, DPCO 2013).

Why this is useful and free: for *scheduled* formulations (those in Schedule-I of the Drugs
(Prices Control) Order, drawn from the National List of Essential Medicines), NPPA notifies a
**ceiling price per unit**, exclusive of GST. A manufacturer may not sell above that price plus
applicable GST, and retailers may not charge above the printed MRP. Overcharging on essential
medicines is common and, unlike authenticity, is something a patient can check from the pack.

How the comparison works (ADR-0008):

    allowed_mrp  =  ceiling_price_per_unit  ×  units_in_pack  ×  (1 + gst_rate)

Deliberate conservatism, because a false accusation is a real harm:
* Only an exact formulation+strength+form match is used; fuzzy matches are reported as
  ``needs_confirmation`` and never as an overcharge.
* A tolerance (default 2 %) absorbs rounding and paise differences.
* Non-scheduled formulations have no ceiling price: the result is ``not_scheduled``, not "fine".
* The output is informational ("this looks higher than the notified maximum; you can report it"),
  never a safety verdict and never a claim that a medicine is fake.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from rapidfuzz import fuzz

from config import get_settings

logger = structlog.get_logger()

NPPA_URL = "https://www.nppaindia.nic.in/en/ceiling-price/"
DEFAULT_GST_RATE = 0.12  # most formulations; 0.05 for some (e.g. several NLEM lifesaving drugs)
DEFAULT_TOLERANCE = 0.02
_STRENGTH = re.compile(r"(\d+(?:\.\d+)?)\s*(mg|mcg|g|ml|iu|%)", re.I)
_FORMS = {
    "tablet": ("tablet", "tablets", "tab", "tabs", "film coated tablet"),
    "capsule": ("capsule", "capsules", "cap", "caps"),
    "injection": ("injection", "inj", "vial", "ampoule"),
    "syrup": ("syrup", "suspension", "oral liquid", "solution"),
    "cream": ("cream", "ointment", "gel"),
    "drops": ("drops", "eye drops", "ear drops"),
}


def normalise_form(text: str) -> str | None:
    low = (text or "").lower()
    for form, words in _FORMS.items():
        if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words):
            return form
    return None


def normalise_strength(text: str) -> str | None:
    m = _STRENGTH.search(text or "")
    if not m:
        return None
    value = float(m.group(1))
    unit = m.group(2).lower()
    if unit == "g":
        value, unit = value * 1000, "mg"
    elif unit == "mcg":
        value, unit = value / 1000, "mg"
    return f"{value:g}{unit}"


def _norm_name(text: str) -> str:
    text = re.sub(r"\b(ip|bp|usp)\b", " ", (text or "").lower())
    text = _STRENGTH.sub(" ", text)
    for words in _FORMS.values():
        for w in words:
            text = re.sub(rf"\b{re.escape(w)}\b", " ", text)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+ ]", " ", text)).strip()


@dataclass(frozen=True)
class CeilingPrice:
    formulation: str            # e.g. "Paracetamol"
    dosage_form: str            # tablet | capsule | injection | syrup | cream | drops
    strength: str               # normalised, e.g. "500mg"
    unit: str                   # what one unit is, e.g. "1 tablet", "1 ml"
    ceiling_price: float        # rupees per unit, exclusive of GST
    notification: str           # S.O. number / order reference
    effective_from: str         # YYYY-MM-DD
    source_url: str = NPPA_URL
    dataset: str = "nppa"

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CeilingPrice:
        price = float(str(d.get("ceiling_price", "")).replace(",", "").strip() or 0)
        if price <= 0:
            raise ValueError("ceiling_price must be a positive number")
        eff = str(d.get("effective_from", "")).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", eff):
            raise ValueError("effective_from must be YYYY-MM-DD")
        form = normalise_form(str(d.get("dosage_form", ""))) or ""
        if not form:
            raise ValueError("dosage_form not recognised (tablet/capsule/injection/syrup/cream/drops)")
        strength = normalise_strength(str(d.get("strength", "")) or str(d.get("formulation", "")))
        if not strength:
            raise ValueError("strength missing or unparseable (e.g. '500 mg')")
        name = _norm_name(str(d.get("formulation", "")))
        if not name:
            raise ValueError("formulation is required")
        if not str(d.get("notification", "")).strip():
            raise ValueError("notification (S.O. number) is required so a price can be traced")
        return cls(
            formulation=name, dosage_form=form, strength=strength,
            unit=str(d.get("unit", "1 unit")).strip() or "1 unit", ceiling_price=round(price, 4),
            notification=str(d["notification"]).strip(), effective_from=eff,
            source_url=str(d.get("source_url", NPPA_URL) or NPPA_URL),
            dataset=str(d.get("dataset", "nppa") or "nppa"),
        )


@dataclass
class PriceIndex:
    prices: list[CeilingPrice] = field(default_factory=list)
    loaded_from: str | None = None
    loaded_at: str | None = None
    _by_key: dict[tuple[str, str, str], CeilingPrice] = field(default_factory=dict, repr=False)

    def build(self) -> PriceIndex:
        self._by_key = {(p.formulation, p.dosage_form, p.strength): p for p in self.prices}
        return self

    def coverage(self) -> dict[str, Any]:
        datasets = sorted({p.dataset for p in self.prices})
        return {
            "status": "available" if self.prices else "unavailable",
            "records": len(self.prices),
            "datasets": datasets,
            "is_sample_data": "SAMPLE" in datasets,
            "latest_effective_from": max((p.effective_from for p in self.prices), default=None),
            "loaded_from": self.loaded_from,
            "loaded_at": self.loaded_at,
            "source_url": NPPA_URL,
        }

    def find(self, name: str, form: str | None, strength: str | None) -> tuple[CeilingPrice | None, str]:
        """Return (price, match_kind) where match_kind is exact | fuzzy | none."""
        key_name, key_form = _norm_name(name), (form or normalise_form(name))
        key_strength = strength or normalise_strength(name)
        if not (key_name and key_form and key_strength):
            return None, "none"
        exact = self._by_key.get((key_name, key_form, key_strength))
        if exact:
            return exact, "exact"
        best, score = None, 0
        for p in self.prices:
            if p.dosage_form != key_form or p.strength != key_strength:
                continue
            s = fuzz.token_sort_ratio(key_name, p.formulation)
            if s > score:
                best, score = p, s
        return (best, "fuzzy") if best and score >= 85 else (None, "none")


_index: PriceIndex | None = None


def load_index(path: str | Path | None = None, records: list[dict[str, Any]] | None = None) -> PriceIndex:
    global _index
    raw: list[dict[str, Any]] = []
    source = None
    if records is not None:
        raw, source = records, "inline"
    else:
        path = path or get_settings().ceiling_prices_data_path
        if path:
            p = Path(path)
            try:
                raw, source = json.loads(p.read_text(encoding="utf-8")), str(p)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("ceiling_prices_load_failed", path=str(p), error=str(exc))
    prices: list[CeilingPrice] = []
    for i, row in enumerate(raw):
        try:
            prices.append(CeilingPrice.from_dict(row))
        except (ValueError, TypeError) as exc:
            logger.warning("ceiling_price_row_rejected", row=i, error=str(exc))
    _index = PriceIndex(prices=prices, loaded_from=source, loaded_at=datetime.now(timezone.utc).isoformat()).build()
    return _index


def get_index() -> PriceIndex:
    return _index if _index is not None else load_index()


def check_price(
    *,
    drug_name: str,
    printed_mrp: float | None,
    units_in_pack: int | None = None,
    dosage_form: str | None = None,
    strength: str | None = None,
    gst_rate: float | None = None,
    tolerance: float = DEFAULT_TOLERANCE,
) -> dict[str, Any]:
    index = get_index()
    cov = index.coverage()
    gst_rate = DEFAULT_GST_RATE if gst_rate is None else gst_rate
    base = {"status": "unknown", "coverage": cov, "drug_name": drug_name, "printed_mrp": printed_mrp,
            "disclaimer": "Price rules apply to scheduled (essential) medicines only. This is a price check, "
                          "not a check of whether the medicine is genuine."}
    if not index.prices:
        return {**base, "status": "unavailable",
                "message": "No NPPA ceiling-price data is loaded, so the price was not checked."}

    price, kind = index.find(drug_name, dosage_form, strength)
    if not price:
        return {**base, "status": "not_scheduled",
                "message": "This formulation is not in the loaded ceiling-price list. Many medicines are not price-controlled, "
                           "so this does not mean the price is wrong."}

    details = {
        "formulation": price.formulation, "dosage_form": price.dosage_form, "strength": price.strength,
        "ceiling_price_per_unit": price.ceiling_price, "unit": price.unit, "notification": price.notification,
        "effective_from": price.effective_from, "source_url": price.source_url, "match": kind,
        "gst_rate_assumed": gst_rate,
    }
    if kind == "fuzzy":
        return {**base, "status": "needs_confirmation", **details,
                "message": f"Closest listed formulation is '{price.formulation}'. Confirm the exact name and strength on the pack "
                           "before drawing any conclusion."}
    if not units_in_pack or units_in_pack <= 0:
        return {**base, "status": "need_pack_size", **details,
                "message": f"Notified ceiling price is ₹{price.ceiling_price:.2f} per {price.unit}, excluding GST. "
                           "Enter how many units the pack contains to compare it with the printed MRP."}
    allowed = round(price.ceiling_price * units_in_pack * (1 + gst_rate), 2)
    details |= {"units_in_pack": units_in_pack, "allowed_mrp": allowed}
    if printed_mrp is None:
        return {**base, "status": "need_mrp", **details,
                "message": f"Maximum allowed MRP for {units_in_pack} units is about ₹{allowed:.2f} (including {gst_rate:.0%} GST)."}
    over = round(printed_mrp - allowed, 2)
    details |= {"difference": over}
    if printed_mrp > allowed * (1 + tolerance):
        return {**base, "status": "above_ceiling", **details,
                "message": f"Printed MRP ₹{printed_mrp:.2f} is about ₹{over:.2f} above the maximum allowed ₹{allowed:.2f} "
                           f"(₹{price.ceiling_price:.2f} per {price.unit} × {units_in_pack} + {gst_rate:.0%} GST). "
                           "Check the pack size and strength first; if they match, you can report overcharging to NPPA.",
                "report_url": "https://www.nppaindia.nic.in/en/consumer-corner/"}
    return {**base, "status": "within_ceiling", **details,
            "message": f"Printed MRP ₹{printed_mrp:.2f} is within the maximum allowed ₹{allowed:.2f}."}
