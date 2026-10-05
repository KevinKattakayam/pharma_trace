"""Batch-level matching against regulator drug alerts (CDSCO monthly NSQ / spurious lists).

Why batch-level: CDSCO states each NSQ finding is specific to the batch tested and does not
warrant concern about other products on the market. The previous implementation matched
recalls by brand name only, which both over-alarms (every batch of a brand) and misses
(brand spelled differently).

Matching rules (ADR-0005):

* ``exact``: normalised batch AND product name agree → integrity flag ``batch_alert``.
* ``batch_only``: batch agrees but product differs/unknown → informational only. Batch
  numbers are not unique across manufacturers, so this must not escalate a verdict.
* ``possible_variant``: batch agrees only after O/0, I/1, S/5 folding (OCR confusions) →
  ask the user to re-check the printed batch; never escalates.

Coverage is always reported. With no alert data loaded the status is ``unavailable``,
never "clear".
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from rapidfuzz import fuzz

from config import get_settings

logger = structlog.get_logger()

CDSCO_ALERTS_URL = "https://cdsco.gov.in/opencms/opencms/en/Notifications/Alerts/"
SEVERITY = {"spurious": "critical", "adulterated": "critical", "nsq": "high", "misbranded": "medium", "recall": "high"}
# Label prefixes are stripped only when followed by a separator/space, so real batch
# numbers that start with letters (e.g. "B12345", "LOTUS7") are left intact.
_PREFIX = re.compile(r"^(?:BATCH\s*NO|BATCH|B\.?\s*NO|LOT\s*NO|LOT)\.?\s*(?:[:#\-]\s*|\s+)", re.IGNORECASE)
_FOLD = str.maketrans({"O": "0", "I": "1", "L": "1", "S": "5", "B": "8", "Z": "2"})


def normalise_batch(value: str | None) -> str:
    if not value:
        return ""
    text = _PREFIX.sub("", str(value).strip().upper())
    return re.sub(r"[^A-Z0-9]", "", text)


def fold_batch(value: str) -> str:
    return normalise_batch(value).translate(_FOLD)


def _norm_name(value: str | None) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+ ]", " ", (value or "").lower())).strip()


@dataclass(frozen=True)
class RegulatorAlert:
    batch_number: str
    product_name: str
    category: str  # nsq | spurious | misbranded | adulterated | recall
    alert_month: str  # YYYY-MM
    manufacturer: str = ""
    reason: str = ""
    reporting_lab: str = ""
    source: str = "CDSCO"
    source_url: str = CDSCO_ALERTS_URL
    dataset: str = "regulator"  # "SAMPLE" for synthetic fixtures

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RegulatorAlert:
        category = str(d.get("category", "nsq")).strip().lower()
        if category not in SEVERITY:
            raise ValueError(f"unknown alert category: {category!r}")
        month = str(d.get("alert_month", "")).strip()
        if not re.fullmatch(r"\d{4}-\d{2}", month):
            raise ValueError(f"alert_month must be YYYY-MM, got {month!r}")
        batch = str(d.get("batch_number", "")).strip()
        product = str(d.get("product_name", "")).strip()
        if not batch or not product:
            raise ValueError("batch_number and product_name are required")
        return cls(
            batch_number=batch,
            product_name=product,
            category=category,
            alert_month=month,
            manufacturer=str(d.get("manufacturer", "") or ""),
            reason=str(d.get("reason", "") or ""),
            reporting_lab=str(d.get("reporting_lab", "") or ""),
            source=str(d.get("source", "CDSCO") or "CDSCO"),
            source_url=str(d.get("source_url", CDSCO_ALERTS_URL) or CDSCO_ALERTS_URL),
            dataset=str(d.get("dataset", "regulator") or "regulator"),
        )


@dataclass
class AlertIndex:
    alerts: list[RegulatorAlert] = field(default_factory=list)
    loaded_from: str | None = None
    loaded_at: str | None = None
    _by_batch: dict[str, list[RegulatorAlert]] = field(default_factory=dict, repr=False)
    _by_folded: dict[str, list[RegulatorAlert]] = field(default_factory=dict, repr=False)

    def build(self) -> AlertIndex:
        self._by_batch.clear()
        self._by_folded.clear()
        for a in self.alerts:
            self._by_batch.setdefault(normalise_batch(a.batch_number), []).append(a)
            self._by_folded.setdefault(fold_batch(a.batch_number), []).append(a)
        return self

    def coverage(self) -> dict[str, Any]:
        months = sorted({a.alert_month for a in self.alerts})
        datasets = sorted({a.dataset for a in self.alerts})
        return {
            "status": "available" if self.alerts else "unavailable",
            "records": len(self.alerts),
            "months_covered": months,
            "earliest_month": months[0] if months else None,
            "latest_month": months[-1] if months else None,
            "datasets": datasets,
            "is_sample_data": "SAMPLE" in datasets,
            "loaded_from": self.loaded_from,
            "loaded_at": self.loaded_at,
            "source_url": CDSCO_ALERTS_URL,
        }

    def match(self, batch_number: str | None, product_name: str | None = None, generic_name: str | None = None) -> dict[str, Any]:
        cov = self.coverage()
        key = normalise_batch(batch_number)
        if not key:
            return {"status": "no_batch", "matches": [], "integrity_flags": [], "coverage": cov}
        if not self.alerts:
            return {"status": "unavailable", "matches": [], "integrity_flags": [], "coverage": cov}

        names = [n for n in (_norm_name(product_name), _norm_name(generic_name)) if n]
        matches: list[dict[str, Any]] = []
        seen: set[int] = set()

        def product_agrees(alert: RegulatorAlert) -> tuple[bool, int]:
            target = _norm_name(alert.product_name)
            best = max((fuzz.token_set_ratio(n, target) for n in names), default=0)
            return best >= 80, int(best)

        for alert in self._by_batch.get(key, []):
            seen.add(id(alert))
            agrees, score = product_agrees(alert)
            matches.append(self._as_match(alert, "exact" if agrees else "batch_only", score))
        for alert in self._by_folded.get(fold_batch(key), []):
            if id(alert) not in seen:
                matches.append(self._as_match(alert, "possible_variant", product_agrees(alert)[1]))

        exact = [m for m in matches if m["match_type"] == "exact"]
        status = "match" if exact else ("review" if matches else "no_match")
        return {
            "status": status,
            "matches": matches,
            "integrity_flags": ["batch_alert"] if exact else [],
            "coverage": cov,
            "note": (
                "No alert found for this batch in the loaded period. This does not mean the batch was tested."
                if status == "no_match"
                else "Batch numbers are not unique across manufacturers; only a batch + product match is treated as a hit."
            ),
        }

    @staticmethod
    def _as_match(alert: RegulatorAlert, match_type: str, product_score: int) -> dict[str, Any]:
        return {
            **asdict(alert),
            "match_type": match_type,
            "severity": SEVERITY[alert.category],
            "product_similarity": product_score,
        }


class SampleDataInProductionError(RuntimeError):
    """Synthetic alert data must never be served as if it were regulator data."""


def assert_no_sample_data(index: AlertIndex, *, strict: bool) -> None:
    if strict and index.coverage()["is_sample_data"]:
        raise SampleDataInProductionError(
            "Refusing to start: SAMPLE regulator alert data is loaded in staging/prod. "
            "Point BATCH_ALERTS_DATA_PATH at reviewed real data or leave it empty."
        )


_index: AlertIndex | None = None


def load_index(path: str | Path | None = None, records: list[dict[str, Any]] | None = None) -> AlertIndex:
    """Load alerts from ``records`` or a JSON file (list of dicts). Invalid rows are skipped and logged."""
    global _index
    raw: list[dict[str, Any]] = []
    source = None
    if records is not None:
        raw, source = records, "inline"
    else:
        path = path or get_settings().batch_alerts_data_path
        if path:
            p = Path(path)
            try:
                raw = json.loads(p.read_text(encoding="utf-8"))
                source = str(p)
            except (OSError, json.JSONDecodeError) as exc:
                logger.error("batch_alerts_load_failed", path=str(p), error=str(exc))
    alerts: list[RegulatorAlert] = []
    for i, row in enumerate(raw):
        try:
            alerts.append(RegulatorAlert.from_dict(row))
        except (ValueError, TypeError) as exc:
            logger.warning("batch_alert_row_rejected", row=i, error=str(exc))
    _index = AlertIndex(alerts=alerts, loaded_from=source, loaded_at=datetime.now(timezone.utc).isoformat()).build()
    return _index


def get_index() -> AlertIndex:
    return _index if _index is not None else load_index()
