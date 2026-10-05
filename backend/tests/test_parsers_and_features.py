"""GS1 / India QR parsers, batch alerts, Pack Check, LASA, openFDA escaping."""
from __future__ import annotations

from datetime import date

import pytest

from models.schemas import BarcodeVerifyRequest, ImageVerifyRequest
from services import gs1, india_qr, lasa
from services.batch_alerts import fold_batch, load_index, normalise_batch
from services.gtin import parse_cdsco_barcode, parse_gs1_datamatrix, validate_gtin
from services.pack_check import check_pack, parse_label_date

VALID_GTIN = "04006381333931"  # check digit verified against EAN-13 4006381333931


@pytest.mark.parametrize("code", ["4006381333931", "036000291452", "00012345600012", "96385074"])
def test_gtin_check_digit_reference_values(code):
    assert gs1.gtin_check_digit_ok(code) and validate_gtin(code)["check_digit_valid"]


def test_invalid_gtin_is_rejected():
    assert not validate_gtin("12345678901234")["valid"]


@pytest.mark.parametrize("data", [
    f"(01){VALID_GTIN}(17)270100(10)AB1234(21)SN998877",
    f"]d201{VALID_GTIN}17270100" "10AB1234\x1d21SN998877",
    f"https://id.gs1.org/01/{VALID_GTIN}/10/AB1234/21/SN998877?17=270100",
])
def test_gs1_all_encodings_parse_identically(data):
    r = gs1.parse(data)
    assert (r["gtin"], r["lot"], r["serial_number"], r["expiry_date"]) == (VALID_GTIN, "AB1234", "SN998877", "2027-01-31")
    assert r["valid"] and r["gtin_check_digit_valid"]


def test_legacy_gs1_wrapper_regression():
    """The old parser returned ')0890103086547' and let the batch swallow the serial."""
    r = parse_gs1_datamatrix(f"(01){VALID_GTIN}(10)AB1234(21)SN9")
    assert r["gtin"] == VALID_GTIN and r["lot"] == "AB1234" and r["serial_number"] == "SN9"


def test_gs1_flags_bad_check_digit_and_bad_date():
    r = gs1.parse("(01)08901030865478(17)271399")
    assert not r["valid"] and len(r["errors"]) == 2


def test_india_qr_eight_particulars_and_no_mrp_requirement():
    r = india_qr.parse("UPIC123|Paracetamol IP|Crocin|GSK, Mumbai|AB12|01/2025|12/2027|MB/07/123")
    assert r["complete"] and r["mfg_license"] == "MB/07/123" and r["mrp"] is None
    legacy = parse_cdsco_barcode('{"UPI":"1","API":"Paracetamol","Brand":"Crocin","Mfg":"GSK","Batch":"AB12","MfgDate":"01/2025","ExpDate":"12/2027","Lic":"L1"}')
    assert legacy["valid"] and legacy["complete"]


def test_india_qr_reports_missing_particulars():
    r = india_qr.parse('{"Brand":"Crocin","API":"Paracetamol","Batch":"AB12"}')
    assert r["recognised"] and not r["complete"] and "mfg_license" in r["particulars_missing"]


def test_garbage_is_not_recognised():
    assert not india_qr.parse("hello world")["recognised"]


# ── batch alerts ──
@pytest.mark.parametrize("raw,expected", [("B12345", "B12345"), ("Batch No: AB-12/34", "AB1234"), ("LOTUS7", "LOTUS7"), (" ab 12 ", "AB12"), (None, "")])
def test_normalise_batch_keeps_letter_prefixed_batches(raw, expected):
    assert normalise_batch(raw) == expected


def test_exact_match_requires_batch_and_product(sample_alerts):
    hit = sample_alerts.match("smpl t2401", "Paracetamol 500mg tablets")
    assert hit["status"] == "match" and hit["integrity_flags"] == ["batch_alert"]
    assert hit["coverage"]["is_sample_data"] is True


def test_batch_only_match_never_escalates(sample_alerts):
    r = sample_alerts.match("SMPL-T2401", "Atorvastatin")
    assert r["status"] == "review" and r["integrity_flags"] == [] and r["matches"][0]["match_type"] == "batch_only"


def test_ocr_confusable_batch_is_possible_variant_only(sample_alerts):
    assert fold_batch("SMPL-M0O12") == fold_batch("SMPL-MOO12")
    r = sample_alerts.match("SMPL-MOO12", "Metformin")
    assert r["matches"][0]["match_type"] in ("exact", "possible_variant")
    assert r["integrity_flags"] in ([], ["batch_alert"])


def test_no_data_is_unavailable_not_clear():
    idx = load_index(records=[])
    assert idx.match("X1", "Y")["status"] == "unavailable"


def test_invalid_alert_rows_are_rejected():
    idx = load_index(records=[{"batch_number": "A", "product_name": "B", "category": "bogus", "alert_month": "2026-01"},
                              {"batch_number": "A", "product_name": "B", "category": "nsq", "alert_month": "Jan 2026"},
                              {"batch_number": "A", "product_name": "B", "category": "nsq", "alert_month": "2026-01"}])
    assert len(idx.alerts) == 1


# ── pack check ──
@pytest.mark.parametrize("value,eom,expected", [
    ("12/2027", True, date(2027, 12, 31)), ("12/2027", False, date(2027, 12, 1)), ("Dec-2027", True, date(2027, 12, 31)),
    ("EXP 03/28", True, date(2028, 3, 31)), ("2027-06-15", True, date(2027, 6, 15)), ("15/06/2027", True, date(2027, 6, 15)),
    ("13/2027", True, None), ("garbage", True, None),
])
def test_label_dates(value, eom, expected):
    assert parse_label_date(value, end_of_month=eom) == expected


QR = "UPIC1|Paracetamol IP|Crocin|GSK Mumbai|AB12|01/2025|12/2027|MB/07/123"


def test_consistent_pack():
    r = check_pack(qr_payload=QR, printed={"batch_no": "AB12", "expiry_date": "12/2027"}, today=date(2026, 1, 1))
    assert r["status"] == "consistent" and r["integrity_flags"] == [] and r["requires_human_review"]


def test_cloned_qr_detected_by_batch_mismatch():
    r = check_pack(qr_payload=QR, printed={"batch_no": "ZZ99"}, today=date(2026, 1, 1))
    assert r["status"] == "inconsistent" and "label_inconsistent" in r["integrity_flags"]
    assert any(f["code"] == "batch_mismatch" for f in r["findings"])


def test_expiry_mismatch_and_expired_and_date_logic():
    r = check_pack(qr_payload=QR, printed={"expiry_date": "06/2027"}, today=date(2026, 1, 1))
    assert any(f["code"] == "expiry_date_mismatch" for f in r["findings"])
    r = check_pack(qr_payload=QR, today=date(2028, 2, 1))
    assert "expired" in r["integrity_flags"]
    r = check_pack(printed={"mfg_date": "05/2027", "expiry_date": "01/2027"}, today=date(2026, 1, 1))
    codes = {f["code"] for f in r["findings"]}
    assert {"mfg_after_expiry", "mfg_in_future"} <= codes


def test_pack_check_never_says_authentic():
    r = check_pack(qr_payload=QR, printed={"batch_no": "AB12"}, today=date(2026, 1, 1))
    assert "authentic" not in str(r["status"]) and "not authenticity" in r["disclaimer"].lower()


def test_pack_check_regulator_alert(sample_alerts):
    qr = "U|Paracetamol Tablets IP 500 mg|Generic|Example|SMPL-T2401|01/2025|12/2027|L"
    r = check_pack(qr_payload=qr, today=date(2026, 1, 1))
    assert "batch_alert" in r["integrity_flags"] and r["status"] == "inconsistent"


def test_empty_pack_check_is_insufficient():
    assert check_pack()["status"] == "insufficient_data"


# ── LASA ──
@pytest.fixture
def lasa_corpus(monkeypatch):
    entries = (lasa.Entry("Medzol", "Midazolam", "test"), lasa.Entry("Metzol", "Metronidazole", "test"),
               lasa.Entry("Crocin", "Paracetamol", "test"), lasa.Entry("Krocin", "Paracetamol", "test"),
               lasa.Entry("Fenzol", "Albendazole", "test"))
    monkeypatch.setattr(lasa, "corpus", lambda: entries)
    lasa._index.cache_clear()


def test_lasa_warns_on_different_molecule(lasa_corpus):
    r = lasa.check_name("Medzol")
    assert r["assumed_active_ingredients"] == ["midazolam"]
    assert any(w["similar_name"] == "Metzol" for w in r["warnings"])


def test_lasa_ignores_same_molecule(lasa_corpus):
    assert lasa.check_name("Crocin")["warnings"] == []


def test_lasa_phonetic_and_strength_stripping(lasa_corpus):
    assert lasa.phonetic_key("Krocin 500 mg tablet") == lasa.phonetic_key("Crocin")
    assert lasa.check_name("Fenzol")["status"] in ("warnings", "no_similar_names_found")


def test_lasa_real_corpus_loads():
    # ~2,000 registry rows are long product descriptions, not names, and are excluded (see plausible_name)
    assert 100 < len(lasa.corpus()) < 1000


# ── request validation & openFDA escaping ──
def test_malformed_image_is_rejected_before_processing():
    with pytest.raises(ValueError):
        ImageVerifyRequest(image="not valid base64!!!")


def test_location_is_validated():
    with pytest.raises(ValueError):
        BarcodeVerifyRequest(barcode="1", location={"lat": 91, "lng": 0})


def test_openfda_phrase_escaping():
    from services.openfda import _esc
    assert _esc('X" OR status:"Terminated') == 'X\\" OR status:\\"Terminated'
    assert len(_esc("a" * 1000)) == 200 and "\n" not in _esc("a\nb")
