"""NPPA ceiling-price checks. A false overcharge accusation is a real harm, so the rules are conservative."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from services.price_check import check_price, load_index, normalise_form, normalise_strength

BACKEND = Path(__file__).resolve().parents[1]
ROW = {"formulation": "Paracetamol", "dosage_form": "Tablet", "strength": "500 mg", "unit": "1 tablet",
       "ceiling_price": 1.37, "notification": "S.O. 1(E)", "effective_from": "2026-04-01", "dataset": "nppa"}


@pytest.fixture(autouse=True)
def prices():
    return load_index(records=[ROW])


@pytest.mark.parametrize("text,expected", [("500 mg", "500mg"), ("1 g", "1000mg"), ("250mcg", "0.25mg"), ("5 ml", "5ml"), ("none", None)])
def test_strength_normalisation(text, expected):
    assert normalise_strength(text) == expected


@pytest.mark.parametrize("text,expected", [("Film coated Tablet", "tablet"), ("Caps", "capsule"), ("Dry Syrup", "syrup"), ("widget", None)])
def test_form_normalisation(text, expected):
    assert normalise_form(text) == expected


def test_mrp_above_ceiling_is_flagged_with_the_arithmetic_shown():
    r = check_price(drug_name="Paracetamol Tablets IP 500 mg", printed_mrp=30.0, units_in_pack=15)
    assert r["status"] == "above_ceiling" and r["allowed_mrp"] == pytest.approx(23.02, abs=0.01)
    assert "1.37" in r["message"] and "15" in r["message"] and r["report_url"].startswith("https://")


def test_mrp_within_ceiling_and_tolerance_absorbs_rounding():
    assert check_price(drug_name="Paracetamol Tablet 500mg", printed_mrp=22.0, units_in_pack=15)["status"] == "within_ceiling"
    assert check_price(drug_name="Paracetamol Tablet 500mg", printed_mrp=23.3, units_in_pack=15)["status"] == "within_ceiling"


def test_unlisted_formulation_is_not_scheduled_not_a_pass():
    r = check_price(drug_name="Atorvastatin Tablets 10 mg", printed_mrp=500.0, units_in_pack=10)
    assert r["status"] == "not_scheduled" and "does not mean the price is wrong" in r["message"]


def test_wrong_strength_or_form_never_matches():
    assert check_price(drug_name="Paracetamol Tablets 650 mg", printed_mrp=99.0, units_in_pack=15)["status"] == "not_scheduled"
    assert check_price(drug_name="Paracetamol Syrup 500 mg", printed_mrp=99.0, units_in_pack=15)["status"] == "not_scheduled"


def test_near_match_asks_for_confirmation_instead_of_accusing():
    r = check_price(drug_name="Paracetamoll Tablet 500 mg", printed_mrp=999.0, units_in_pack=15)
    assert r["status"] == "needs_confirmation" and "Confirm the exact name" in r["message"]


def test_missing_inputs_ask_for_them():
    assert check_price(drug_name="Paracetamol Tablet 500mg", printed_mrp=30.0)["status"] == "need_pack_size"
    assert check_price(drug_name="Paracetamol Tablet 500mg", printed_mrp=None, units_in_pack=15)["status"] == "need_mrp"


def test_no_data_is_unavailable_not_fine():
    load_index(records=[])
    assert check_price(drug_name="Paracetamol Tablet 500mg", printed_mrp=30.0, units_in_pack=15)["status"] == "unavailable"


def test_invalid_rows_rejected():
    idx = load_index(records=[{**ROW, "ceiling_price": 0}, {**ROW, "effective_from": "April 2026"},
                              {**ROW, "notification": ""}, {**ROW, "dosage_form": "widget"}, ROW])
    assert len(idx.prices) == 1


def test_price_check_never_affects_the_authenticity_verdict(client, offline_externals):
    """An overcharge is a pricing offence; it must not make a pack look falsified."""
    from services import price_check as pc
    pc.load_index(records=[ROW])
    qr = "U1|Paracetamol Tablets IP 500 mg|Dolo 500|GSK|AB12|01/2025|12/2030|L"
    r = client.post("/api/v1/verify/barcode", json={"barcode": qr, "printed": {"batch_no": "AB12", "mrp": 999.0}, "units_in_pack": 15}).json()
    assert r["price_check"]["status"] == "above_ceiling"
    assert "label_inconsistent" not in r["verdict_reasons"] and "mrp_above_ceiling" not in r["verdict_reasons"]
    assert any(f["code"] == "mrp_above_ceiling" and f["severity"] == "warn" for f in r["pack_check"]["findings"])


def test_price_check_needs_strength_on_the_label(client, offline_externals):
    """If the label's generic name carries no strength, no price claim is made (documented limit)."""
    from services import price_check as pc
    pc.load_index(records=[ROW])
    qr = "U1|Paracetamol|Dolo|GSK|AB12|01/2025|12/2030|L"
    r = client.post("/api/v1/verify/barcode", json={"barcode": qr, "printed": {"mrp": 999.0}}).json()
    assert r["price_check"]["status"] == "not_scheduled"
    assert not any(f["code"] == "mrp_above_ceiling" for f in r["pack_check"]["findings"])


def test_api_endpoints(client):
    from services import price_check as pc
    pc.load_index(records=[ROW])
    r = client.post("/api/v1/safety/price-check", json={"drug_name": "Paracetamol Tablet 500mg", "printed_mrp": 30.0, "units_in_pack": 15})
    assert r.status_code == 200 and r.json()["status"] == "above_ceiling"
    assert client.get("/api/v1/safety/price-check/coverage").json()["records"] == 1
    assert client.get("/api/v1/capabilities").json()["features"]["price_check"] is True


def test_importer_requires_review(tmp_path):
    head = "formulation,dosage_form,strength,unit,ceiling_price,notification,effective_from,source_url,reviewed_by,reviewed_at\n"
    src, out = tmp_path / "p.csv", tmp_path / "p.json"
    src.write_text(head
                   + "Paracetamol,Tablet,500 mg,1 tablet,1.37,S.O. 1(E),2026-04-01,https://nppaindia.nic.in/x,Asha,2026-09-01\n"
                   + "Metformin,Tablet,500 mg,1 tablet,2.11,S.O. 2(E),2026-04-01,https://nppaindia.nic.in/y,,\n")
    p = subprocess.run([sys.executable, "-m", "scripts.import_nppa_ceiling_prices", str(src), "--out", str(out)],
                       cwd=BACKEND, capture_output=True, text=True, timeout=60)
    assert p.returncode == 1 and "reviewed_by is empty" in p.stderr
    data = json.loads(out.read_text())
    assert [d["formulation"] for d in data] == ["paracetamol"] and data[0]["strength"] == "500mg"
