"""Import regulator batch alerts (e.g. CDSCO monthly NSQ/spurious lists) from a reviewed CSV.

CDSCO publishes alerts as PDFs whose layout varies, so automated scraping is not trusted for a
safety feature. Workflow (docs/RUNBOOK.md): extract the table to CSV, have a second person check
it against the PDF, then import. Invalid rows are rejected and listed; nothing is silently dropped.

Columns: batch_number, product_name, category (nsq|spurious|misbranded|adulterated|recall),
alert_month (YYYY-MM), manufacturer, reason, reporting_lab, source_url,
reviewed_by, reviewed_at (YYYY-MM-DD)

`reviewed_by` and `reviewed_at` are REQUIRED: a row nobody has checked against the regulator's PDF is rejected,
so unreviewed machine-extracted drafts (scripts/cdsco_pdf_to_draft_csv.py) cannot be loaded by accident.
Usage: python -m scripts.import_regulator_alerts alerts.csv --out data/regulator_alerts.json [--append]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.batch_alerts import RegulatorAlert  # noqa: E402


def review_problem(row: dict) -> str | None:
    """Return why a row may not be imported, or None. Enforces the two-person rule in code."""
    if not (row.get("reviewed_by") or "").strip():
        return "not reviewed: reviewed_by is empty"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", (row.get("reviewed_at") or "").strip()):
        return "not reviewed: reviewed_at must be YYYY-MM-DD"
    if not (row.get("source_url") or "").strip().lower().startswith("https://"):
        return "source_url must be the https:// link of the regulator publication"
    if (row.get("review_notes") or "").strip().upper().startswith("CHECK"):
        return "unresolved reviewer note (starts with CHECK); fix it and clear the note"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--append", action="store_true")
    a = ap.parse_args()
    existing = json.loads(a.out.read_text(encoding="utf-8")) if a.append and a.out.exists() else []
    keep, rejected = [], []
    with a.csv.open(newline="", encoding="utf-8-sig") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            try:
                problem = review_problem(row)
                if problem:
                    raise ValueError(problem)
                keep.append(asdict(RegulatorAlert.from_dict({**row, "dataset": "regulator"})))
            except (ValueError, TypeError) as exc:
                rejected.append((line, str(exc)))
    seen = {(r["batch_number"], r["product_name"], r["alert_month"]) for r in existing}
    added = [r for r in keep if (r["batch_number"], r["product_name"], r["alert_month"]) not in seen]
    a.out.write_text(json.dumps(existing + added, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"accepted {len(keep)}, added {len(added)} new, rejected {len(rejected)}")
    for line, err in rejected:
        print(f"  line {line}: {err}", file=sys.stderr)
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
