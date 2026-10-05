"""Import NPPA ceiling prices from a reviewed CSV (India, DPCO 2013).

NPPA publishes ceiling prices as notification PDFs/Excel on nppaindia.nic.in. As with regulator
alerts, rows must be checked by a person before they can be used: an incorrect ceiling price would
make the app accuse a pharmacy of overcharging.

CSV columns: formulation, dosage_form, strength, unit, ceiling_price, notification, effective_from,
             source_url, reviewed_by, reviewed_at
  formulation    "Paracetamol"            (molecule; strength/form go in their own columns)
  dosage_form    "Tablet"                 unit "1 tablet"
  strength       "500 mg"                 ceiling_price  rupees per unit, EXCLUDING GST
  notification   "S.O. 1234(E)"           effective_from YYYY-MM-DD

    python -m scripts.import_nppa_ceiling_prices prices.csv --out data/ceiling_prices.json [--append]
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
from services.price_check import CeilingPrice  # noqa: E402


def review_problem(row: dict) -> str | None:
    if not (row.get("reviewed_by") or "").strip():
        return "not reviewed: reviewed_by is empty"
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", (row.get("reviewed_at") or "").strip()):
        return "not reviewed: reviewed_at must be YYYY-MM-DD"
    if not (row.get("source_url") or "").strip().lower().startswith("https://"):
        return "source_url must be the https:// link of the NPPA notification"
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
                keep.append(asdict(CeilingPrice.from_dict({**row, "dataset": "nppa"})))
            except (ValueError, TypeError) as exc:
                rejected.append((line, str(exc)))
    seen = {(r["formulation"], r["dosage_form"], r["strength"]) for r in existing}
    added = [r for r in keep if (r["formulation"], r["dosage_form"], r["strength"]) not in seen]
    a.out.write_text(json.dumps(existing + added, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"accepted {len(keep)}, added {len(added)} new, rejected {len(rejected)}")
    for line, why in rejected:
        print(f"  line {line}: {why}", file=sys.stderr)
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
