"""Add brand-name → generic mappings to the look-alike/sound-alike checker, from a CSV YOU have the right to use.

The bundled registry has only ~87 brands. A real deployment needs a proper product list from a source you
are licensed to use (a drug-database vendor, your distributor's or pharmacy chain's product master, a
regulator publication). This tool does not ship or scrape one. Every row must carry a `source` so each
mapping can be traced; rows without one are rejected.

CSV columns: brand_name, generic_name, source        (generic_name: use "+" between ingredients)
    python -m scripts.import_brands brands.csv [--out data/lasa_curated.json]
Restart the API afterwards (the corpus is cached at start-up).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "lasa_curated.json"


def validate(row: dict[str, str]) -> str | None:
    name, generic, source = ((row.get(k) or "").strip() for k in ("brand_name", "generic_name", "source"))
    if not name or not generic:
        return "brand_name and generic_name are required"
    if not source:
        return "source is required (where did this mapping come from?)"
    if len(name) > 80 or len(generic) > 200:
        return "name too long: looks like a description, not a brand name"
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    a = ap.parse_args()
    existing = json.loads(a.out.read_text(encoding="utf-8")) if a.out.exists() else []
    seen = {(r["name"].lower(), r["generic"].lower()) for r in existing}
    added, rejected = 0, []
    with a.csv.open(newline="", encoding="utf-8-sig") as fh:
        for line, row in enumerate(csv.DictReader(fh), start=2):
            problem = validate(row)
            if problem:
                rejected.append((line, problem))
                continue
            key = (row["brand_name"].strip().lower(), row["generic_name"].strip().lower())
            if key in seen:
                continue
            seen.add(key)
            existing.append({"name": row["brand_name"].strip(), "generic": row["generic_name"].strip(), "source": row["source"].strip()})
            added += 1
    a.out.write_text(json.dumps(existing, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"added {added}, total {len(existing)}, rejected {len(rejected)}")
    for line, why in rejected:
        print(f"  line {line}: {why}", file=sys.stderr)
    return 1 if rejected else 0


if __name__ == "__main__":
    raise SystemExit(main())
