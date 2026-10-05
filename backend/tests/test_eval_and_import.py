import json
import subprocess
import sys
from pathlib import Path

import pytest

from eval.run_eval import evaluate

BACKEND = Path(__file__).resolve().parents[1]
CASES = BACKEND / "eval" / "cases.synthetic.json"


def test_eval_refuses_synthetic_without_flag():
    with pytest.raises(SystemExit):
        evaluate(CASES, allow_synthetic=False)


def test_eval_smoke_cases_pass_and_are_labelled_synthetic():
    r = evaluate(CASES, allow_synthetic=True)
    assert r["label"].startswith("SYNTHETIC") and r["fail"] == 0 and r["pass"] == 4, r["failures"]


def test_importer_rejects_bad_rows_and_reports_them(tmp_path):
    src = tmp_path / "a.csv"
    src.write_text("batch_number,product_name,category,alert_month,manufacturer,reason,reporting_lab,source_url,reviewed_by,reviewed_at\n"
                   "B1,Paracetamol,nsq,2026-08,M,assay,CDL,https://cdsco.gov.in/x,Asha,2026-09-01\n"
                   "B2,Ibuprofen,unknown,2026-08,M,x,CDL,https://cdsco.gov.in/y,Asha,2026-09-01\n")
    out = tmp_path / "out.json"
    p = subprocess.run([sys.executable, "-m", "scripts.import_regulator_alerts", str(src), "--out", str(out)],
                       cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert p.returncode == 1 and "accepted 1" in p.stdout and "line 3" in p.stderr
    assert json.loads(out.read_text())[0]["dataset"] == "regulator"
