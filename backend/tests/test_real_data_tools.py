"""Guards and tools that stand between the app and fake/unreviewed data."""
from __future__ import annotations

import csv
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from config import Settings
from scripts.doctor import BLOCKER, INFO, OK, WARN, run_checks
from services.batch_alerts import SampleDataInProductionError, assert_no_sample_data, load_index

BACKEND = Path(__file__).resolve().parents[1]
STRONG = {"jwt_secret": "Aa1!" + "k" * 70, "hmac_daily_secret": "h" * 40, "cors_origins": ["https://app.example"]}


def levels(checks, area):
    return {c.level for c in checks if c.area == area}


# ── sample data can never be served in production ──
def test_sample_data_refused_in_strict_but_allowed_in_dev(sample_alerts):
    with pytest.raises(SampleDataInProductionError):
        assert_no_sample_data(sample_alerts, strict=True)
    assert_no_sample_data(sample_alerts, strict=False)
    assert_no_sample_data(load_index(records=[]), strict=True)  # empty is allowed; doctor warns instead


def test_real_data_passes_strict_guard():
    idx = load_index(records=[{"batch_number": "A1", "product_name": "P", "category": "nsq", "alert_month": "2026-08", "dataset": "regulator"}])
    assert_no_sample_data(idx, strict=True)


# ── doctor tells the truth about what is dummy ──
def doctor(settings_kwargs, index, lasa=87, today=date(2026, 10, 5)):
    return run_checks(Settings(_env_file=None, **settings_kwargs), index, lasa, today=today)


def test_doctor_flags_every_dummy_item_in_dev(sample_alerts):
    c = doctor({"environment": "dev"}, sample_alerts)
    assert WARN in levels(c, "database") and WARN in levels(c, "batch alerts")
    assert WARN in levels(c, "name warnings") and INFO in levels(c, "serial verification") and INFO in levels(c, "ai")


def test_doctor_blocks_prod_with_sample_data_and_no_database(sample_alerts):
    c = doctor({"environment": "prod", **STRONG}, sample_alerts)
    assert BLOCKER in levels(c, "database") and BLOCKER in levels(c, "batch alerts")


def test_doctor_ok_with_real_fresh_data_and_database():
    idx = load_index(records=[{"batch_number": "A1", "product_name": "P", "category": "nsq", "alert_month": "2026-09", "dataset": "regulator"}])
    c = doctor({"environment": "prod", "supabase_url": "https://x.supabase.co", "supabase_key": "k", "rate_limit_storage_uri": "redis://r",
                "sentry_dsn": "https://s", "groq_api_key": "g", **STRONG}, idx, lasa=900)
    assert not [x for x in c if x.level in (BLOCKER, WARN)], [x for x in c if x.level in (BLOCKER, WARN)]
    assert OK in levels(c, "batch alerts") and OK in levels(c, "name warnings")


def test_doctor_warns_when_alerts_are_stale():
    idx = load_index(records=[{"batch_number": "A1", "product_name": "P", "category": "nsq", "alert_month": "2026-01", "dataset": "regulator"}])
    assert WARN in levels(doctor({"environment": "dev"}, idx), "batch alerts")


def test_doctor_cli_exit_codes(tmp_path):
    env = {"PATH": "/usr/bin:/bin", "ENVIRONMENT": "prod", "JWT_SECRET": "", "HMAC_DAILY_SECRET": ""}
    p = subprocess.run([sys.executable, "-m", "scripts.doctor"], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 1 and "BLOCKER" in p.stdout and "Refusing to start" in p.stdout


# ── importer enforces review ──
HEAD = "batch_number,product_name,category,alert_month,manufacturer,reason,reporting_lab,source_url,reviewed_by,reviewed_at,review_notes\n"


def run_import(tmp_path, body):
    src, out = tmp_path / "a.csv", tmp_path / "out.json"
    src.write_text(HEAD + body)
    p = subprocess.run([sys.executable, "-m", "scripts.import_regulator_alerts", str(src), "--out", str(out)], cwd=BACKEND, capture_output=True, text=True, timeout=60)
    return p, (json.loads(out.read_text()) if out.exists() else [])


def test_unreviewed_rows_are_rejected(tmp_path):
    p, data = run_import(tmp_path, "B1,Paracetamol,nsq,2026-08,M,assay,CDL,https://cdsco.gov.in/x,,,\n")
    assert p.returncode == 1 and "reviewed_by is empty" in p.stderr and data == []


def test_draft_with_check_note_is_rejected_even_if_signed(tmp_path):
    p, data = run_import(tmp_path, "B1,Paracetamol,nsq,2026-08,M,assay,CDL,https://cdsco.gov.in/x,Asha,2026-09-01,CHECK: verify\n")
    assert p.returncode == 1 and "unresolved reviewer note" in p.stderr and data == []


def test_reviewed_rows_import_and_non_https_source_rejected(tmp_path):
    good = "B1,Paracetamol,nsq,2026-08,M,assay,CDL,https://cdsco.gov.in/x,Asha,2026-09-01,\n"
    bad = "B2,Ibuprofen,nsq,2026-08,M,assay,CDL,http://example.com,Asha,2026-09-01,\n"
    p, data = run_import(tmp_path, good + bad)
    assert [d["batch_number"] for d in data] == ["B1"] and data[0]["dataset"] == "regulator" and "https://" in p.stderr


# ── PDF → draft ──
reportlab = pytest.importorskip("reportlab")
pdfplumber = pytest.importorskip("pdfplumber")


def make_pdf(path: Path, rows: list[list[str]]) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    t = Table(rows)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.black), ("FONTSIZE", (0, 0), (-1, -1), 7)]))
    SimpleDocTemplate(str(path), pagesize=landscape(A4)).build([t])


def draft(tmp_path, rows):
    from scripts.cdsco_pdf_to_draft_csv import extract_rows
    pdf = tmp_path / "alert.pdf"
    make_pdf(pdf, rows)
    return extract_rows(pdf, "2026-08", "https://cdsco.gov.in/alert.pdf")[0]


def test_pdf_column_layout_extracts_fields_and_is_unreviewed(tmp_path):
    rows = draft(tmp_path, [["S.No", "Name of Drug", "Batch No.", "Manufactured by", "Reason for failure", "Drawn by"],
                            ["1", "Examplecillin 500 Tablets", "ZX9001", "Fictional Labs Ltd", "Dissolution", "SDTL Test"],
                            ["2", "Sampleprazole Caps", "ZX9002", "Imaginary Pharma", "Identification failed - spurious", "SDTL Test"]])
    assert [r["batch_number"] for r in rows] == ["ZX9001", "ZX9002"]
    assert rows[0]["manufacturer"] == "Fictional Labs Ltd" and rows[0]["reporting_lab"] == "SDTL Test"
    assert rows[1]["category"] == "spurious" and rows[0]["category"] == "nsq"
    assert all(r["reviewed_by"] == "" and r["review_notes"].startswith("CHECK") for r in rows)


def test_pdf_combined_cell_layout(tmp_path):
    rows = draft(tmp_path, [["S.No", "Name of Drug / Batch", "Reason for failure"],
                            ["1", "Examplecillin 0.5 Tablets\nB. No.: MT201577\nMfd by: M/s. Fictional Labs", "Related Substances"]])
    assert rows and rows[0]["batch_number"] == "MT201577" and "Fictional Labs" in rows[0]["manufacturer"]
    assert "combined cell" in rows[0]["review_notes"]


def test_pdf_draft_cannot_be_imported_until_reviewed(tmp_path):
    from scripts.cdsco_pdf_to_draft_csv import FIELDS, extract_rows
    pdf = tmp_path / "a.pdf"
    make_pdf(pdf, [["S.No", "Name of Drug", "Batch No.", "Reason for failure"], ["1", "Examplecillin", "ZX9001", "Assay"]])
    rows, _ = extract_rows(pdf, "2026-08", "https://cdsco.gov.in/a.pdf")
    csv_path, out = tmp_path / "draft.csv", tmp_path / "out.json"
    with csv_path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    p = subprocess.run([sys.executable, "-m", "scripts.import_regulator_alerts", str(csv_path), "--out", str(out)], cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert p.returncode == 1 and json.loads(out.read_text()) == []


def test_pdf_with_unrecognised_layout_yields_nothing_rather_than_guessing(tmp_path):
    assert draft(tmp_path, [["Foo", "Bar"], ["x", "y"]]) == []
