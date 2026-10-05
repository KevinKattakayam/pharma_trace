"""Turn a downloaded CDSCO monthly alert PDF into a DRAFT csv for human review.

CDSCO changes the table layout month to month, and PDF text extraction can merge or misplace cells.
This tool therefore NEVER produces loadable data: the draft has empty `reviewed_by`/`reviewed_at`
and per-row `review_notes` flagging anything uncertain. A person must compare every row with the
PDF, fill in the reviewer columns, set the correct category, and clear the CHECK notes. Only then will
scripts/import_regulator_alerts.py accept it.

    pip install pdfplumber
    python -m scripts.cdsco_pdf_to_draft_csv alert.pdf --month 2026-08 \\
        --source-url https://cdsco.gov.in/.../alert.pdf --out draft_2026_08.csv
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

FIELDS = ["batch_number", "product_name", "category", "alert_month", "manufacturer", "reason", "reporting_lab",
          "source_url", "reviewed_by", "reviewed_at", "review_notes"]
HEADER_HINTS = {
    "product_name": ("name of drug", "drug name", "product", "name of the drug"),
    "batch_number": ("batch",),
    "manufacturer": ("manufactured by", "mfd by", "manufacturer", "mfg by"),
    "reason": ("reason",),
    "reporting_lab": ("drawn by", "laboratory", "lab"),
}
_BATCH_IN_CELL = re.compile(r"B\.?\s*No\.?\s*[:\-]?\s*([A-Za-z0-9/\-]+)", re.I)
_MFR_IN_CELL = re.compile(r"Mfd\.?\s*by\s*[:\-]?\s*(.+)", re.I | re.S)


def clean(cell: object) -> str:
    return re.sub(r"\s+", " ", str(cell or "")).strip()


def map_header(row: list[object]) -> dict[str, int]:
    mapping: dict[str, int] = {}
    for i, cell in enumerate(row):
        text = clean(cell).lower()
        for field, hints in HEADER_HINTS.items():  # one field per header cell; earlier fields take priority
            if field not in mapping and any(h in text for h in hints):
                mapping[field] = i
                break
    return mapping


def cell_for(cells: list[str], mapping: dict[str, int], field: str) -> str:
    i = mapping.get(field)
    return cells[i] if i is not None and i < len(cells) else ""


def guess_category(text: str) -> str:
    t = text.lower()
    if "spurious" in t:
        return "spurious"
    if "misbrand" in t:
        return "misbranded"
    if "adulterat" in t:
        return "adulterated"
    return "nsq"


def extract_rows(pdf_path: Path, month: str, source_url: str) -> tuple[list[dict[str, str]], dict[str, int]]:
    import pdfplumber

    rows: list[dict[str, str]] = []
    stats = {"pages": 0, "tables": 0, "skipped": 0}
    mapping: dict[str, int] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            stats["pages"] += 1
            for table in page.extract_tables():
                stats["tables"] += 1
                for raw in table:
                    if not raw or not any(clean(c) for c in raw):
                        continue
                    header = map_header(raw)
                    if "product_name" in header and ("batch_number" in header or "reason" in header):
                        mapping = header  # a header row (repeated on each page)
                        continue
                    if not mapping:
                        stats["skipped"] += 1
                        continue
                    cells = [clean(c) for c in raw]
                    product, batch, mfr = (cell_for(cells, mapping, f) for f in ("product_name", "batch_number", "manufacturer"))
                    notes: list[str] = []
                    if not batch:  # older layout: batch/mfg/exp/manufacturer share the product cell
                        m = _BATCH_IN_CELL.search(str(raw[mapping["product_name"]] or ""))
                        if m:
                            batch = m.group(1)
                            notes.append("batch taken from a combined cell")
                    if not mfr:
                        m2 = _MFR_IN_CELL.search(str(raw[mapping["product_name"]] or ""))
                        if m2:
                            mfr = clean(m2.group(1))
                    if not product or not batch:
                        stats["skipped"] += 1
                        continue
                    if re.fullmatch(r"\d+\.?", product):
                        notes.append("product looks like a serial number: columns may be shifted")
                    reason = cell_for(cells, mapping, "reason")
                    rows.append({
                        "batch_number": batch, "product_name": product, "category": guess_category(" ".join(cells)),
                        "alert_month": month, "manufacturer": mfr, "reason": reason, "reporting_lab": cell_for(cells, mapping, "reporting_lab"),
                        "source_url": source_url, "reviewed_by": "", "reviewed_at": "",
                        "review_notes": "CHECK: " + "; ".join(["verify every field against the PDF", *notes]),
                    })
    return rows, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--month", required=True, help="alert month, YYYY-MM")
    ap.add_argument("--source-url", required=True, help="https link of the CDSCO publication")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    if not re.fullmatch(r"\d{4}-\d{2}", a.month):
        print("--month must be YYYY-MM", file=sys.stderr)
        return 2
    rows, stats = extract_rows(a.pdf, a.month, a.source_url)
    with a.out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{stats['pages']} pages, {stats['tables']} tables -> {len(rows)} draft rows ({stats['skipped']} table rows skipped).")
    print("DRAFT ONLY. Compare EVERY row with the PDF, set the category, fill reviewed_by/reviewed_at, clear the CHECK notes.")
    if not rows:
        print("No rows recognised: this month's layout is probably different. Enter the rows by hand from the PDF.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
