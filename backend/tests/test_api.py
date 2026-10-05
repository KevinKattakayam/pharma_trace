"""API integration tests: each audited exploit/bug has a regression test here."""
from __future__ import annotations

import asyncio
import json

import pytest

from routers.verify import merge_recall_status
from services import audit
from tests.conftest import auth

V = "/api/v1"
ERR = [{"error": "SERVICE_UNAVAILABLE"}]
CD_OK = {"available": True, "has_cdsco_recall": False}
CD_DOWN = {"available": False, "has_cdsco_recall": False}
CD_HIT = {"available": True, "has_cdsco_recall": True, "recall_reason": "NSQ"}


# ── recall merge (audit P1) ──
@pytest.mark.parametrize("fda,cdsco,expected", [
    ([], CD_OK, "none_found"),
    ([{"status": "Ongoing"}], CD_DOWN, "active"),      # was "inconclusive": recall hidden
    (ERR, CD_HIT, "active"),                             # was dropped entirely
    (ERR, CD_OK, "inconclusive"),
    ([], CD_DOWN, "inconclusive"),
    (RuntimeError("x"), CD_OK, "inconclusive"),
    ([], RuntimeError("x"), "inconclusive"),
])
def test_merge_recall_status(fda, cdsco, expected):
    assert merge_recall_status(fda, cdsco)[0] == expected


# ── system endpoints (R5, S5) ──
def test_health_returns_a_body(client):
    r = client.get(f"{V}/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_ready_and_security_headers(client):
    r = client.get(f"{V}/ready")
    assert r.status_code == 200 and r.json()["checks"]["batch_alerts"]["is_sample_data"] is True
    assert r.headers["X-Content-Type-Options"] == "nosniff" and r.headers["X-Frame-Options"] == "DENY"
    assert len(r.headers["X-Request-ID"]) >= 8


def test_capabilities_lists_features(client):
    assert client.get(f"{V}/capabilities").json()["features"] == {"pack_check": True, "batch_alerts": True, "lasa_guard": True}


def test_per_client_rate_limit_buckets(client, no_rate_limits):
    """Previously every anonymous client shared the 127.0.0.1 bucket."""
    from starlette.requests import Request

    from services.limiter import rate_limit_key
    keys = set()
    for ip in ("198.51.100.1", "198.51.100.2"):
        scope = {"type": "http", "headers": [], "client": (ip, 1), "state": {}}
        from main import PrivacyMiddleware

        async def app(scope, receive, send):
            keys.add(rate_limit_key(Request(scope)))
            assert scope["client"] is None  # IP removed downstream
        asyncio.run(PrivacyMiddleware(app)(scope, None, None))
    assert len(keys) == 2


def test_rate_limit_enforced(client, no_rate_limits):
    no_rate_limits.enabled = True
    codes = [client.post(f"{V}/safety/lasa-check", json={"name": "Dolo"}).status_code for _ in range(62)]
    assert codes.count(429) >= 1


# ── verification pipeline ──
def test_barcode_clean_record_is_unknown_with_review(client, offline_externals):
    offline_externals["cdsco_drug"] = {"brand_name": "Dolo 650", "generic_name": "Paracetamol"}
    r = client.post(f"{V}/verify/barcode", json={"barcode": "Dolo 650"}).json()
    assert r["verdict"] == "unknown" and r["requires_human_review"] and r["recall_status"] == "none_found"
    assert r["has_recall"] is False and r["audit_status"] == "recorded" and len(r["audit_hash"]) == 64


def test_active_recall_survives_other_source_outage(client, offline_externals):
    offline_externals.update(cdsco_drug={"brand_name": "X", "generic_name": "Y"}, fda=[{"status": "Ongoing"}], cdsco=CD_DOWN)
    r = client.post(f"{V}/verify/barcode", json={"barcode": "X"}).json()
    assert r["verdict"] == "suspicious" and r["recall_status"] == "active" and "active_recall" in r["verdict_reasons"]


def test_inconclusive_recall_never_reported_clear(client, offline_externals):
    offline_externals.update(cdsco_drug={"brand_name": "X"}, fda=ERR)
    r = client.post(f"{V}/verify/barcode", json={"barcode": "X"}).json()
    assert r["recall_status"] == "inconclusive" and r["has_recall"] is True


def test_serial_rejection_is_counterfeit(client, offline_externals):
    offline_externals["serial"] = {"verified": False, "available": True}
    assert client.post(f"{V}/verify/barcode", json={"barcode": "(01)04006381333931(21)S1"}).json()["verdict"] == "counterfeit"


def test_invalid_check_digit_is_suspicious(client, offline_externals):
    r = client.post(f"{V}/verify/barcode", json={"barcode": "4006381333932"}).json()
    assert r["verdict"] == "suspicious" and "invalid_check_digit" in r["verdict_reasons"]


def test_indian_gtin_registry_gap_is_not_suspicious(client, offline_externals):
    r = client.post(f"{V}/verify/barcode", json={"barcode": "4006381333931"}).json()
    assert r["verdict"] == "unknown" and any(e["check"] == "registry_coverage" for e in r["evidence"])


def test_cloned_qr_flagged_via_printed_label(client, offline_externals):
    qr = "U1|Paracetamol IP|Crocin|GSK|AB12|01/2025|12/2027|MB/07/123"
    r = client.post(f"{V}/verify/barcode", json={"barcode": qr, "printed": {"batch_no": "ZZ99"}}).json()
    assert r["verdict"] == "suspicious" and "label_inconsistent" in r["verdict_reasons"]
    assert r["pack_check"]["status"] == "inconsistent"


def test_batch_alert_from_qr(client, offline_externals):
    qr = "U1|Paracetamol Tablets IP 500 mg|Generic|Example|SMPL-T2401|01/2025|12/2027|L"
    r = client.post(f"{V}/verify/barcode", json={"barcode": qr}).json()
    assert "batch_alert" in r["verdict_reasons"] and r["batch_alerts"]["coverage"]["is_sample_data"]


def test_audit_failure_is_reported_not_faked(client, offline_externals, monkeypatch):
    async def fail(*a, **k):
        raise audit.AuditWriteError("db down")
    monkeypatch.setattr(audit, "add_audit_record", fail)
    r = client.post(f"{V}/verify/barcode", json={"barcode": "X"}).json()
    assert r["audit_status"] == "failed" and r["audit_hash"] is None


def test_client_time_is_not_the_audit_time(client, offline_externals):
    client.post(f"{V}/verify/barcode", json={"barcode": "X", "verified_at": "2001-01-01T00:00:00Z"})
    rec = asyncio.run(audit.list_records(1))[0]
    assert rec["client_reported_at"].startswith("2001") and rec["recorded_at"].startswith("20") and not rec["recorded_at"].startswith("2001")


def test_wkt_injection_rejected(client, offline_externals):
    assert client.post(f"{V}/verify/barcode", json={"barcode": "X", "location": {"lat": "1) x", "lng": 2}}).status_code == 422


def test_batch_works_and_errors_are_not_failures(client, offline_externals):
    r = client.post(f"{V}/verify/batch", json={"barcodes": ["Dolo", "4006381333931", "4006381333932"]})
    lines = [json.loads(x) for x in r.text.strip().splitlines()]
    items, summary = lines[:-1], lines[-1]["data"]
    assert len(items) == 3 and not any(i["data"].get("processing_error") for i in items)
    assert summary["processed"] == 3 and summary["flagged_count"] == 1 and summary["error_count"] == 0


def test_anonymous_batch_is_capped(client, offline_externals):
    assert client.post(f"{V}/verify/batch", json={"barcodes": [str(i) for i in range(11)]}).status_code == 413


# ── authorisation regressions (S2, S6, S10) ──
@pytest.mark.parametrize("method,path,body", [
    ("post", "/verify/offline-sync", {"brand_name": "F", "verdict": "authentic", "confidence": 100}),
    ("post", "/verify/batch-audit", {"items": [{"a": 1}]}),
    ("get", "/verify/history", None),
    ("get", "/refill/schedule", None),
])
def test_endpoints_require_auth(client, method, path, body):
    r = getattr(client, method)(V + path, **({"json": body} if body else {}))
    assert r.status_code == 401


def test_offline_sync_records_claim_not_verdict(client):
    r = client.post(f"{V}/verify/offline-sync", json={"brand_name": "F", "verdict": "authentic", "confidence": 100}, headers=auth())
    assert r.status_code == 200 and r.json()["recorded_as"] == "unverified_client_claim"
    rec = asyncio.run(audit.list_records(1))[0]
    assert rec["verdict"] == "unverified_client_claim" and rec["actor"] == "user-1"


def test_history_is_scoped_to_caller(client, offline_externals):
    client.post(f"{V}/verify/barcode", json={"barcode": "A"}, headers=auth("alice"))
    client.post(f"{V}/verify/barcode", json={"barcode": "B"}, headers=auth("bob"))
    rows = client.get(f"{V}/verify/history", headers=auth("alice")).json()["verifications"]
    assert [r["barcode"] for r in rows] == ["A"]
    vid = rows[0]["id"]
    assert client.get(f"{V}/verify/{vid}", headers=auth("bob")).status_code == 404
    assert client.get(f"{V}/verify/{vid}", headers=auth("alice")).status_code == 200


def test_audit_endpoints_need_auditor_role_and_chain_verifies(client, offline_externals):
    for _ in range(3):
        client.post(f"{V}/verify/barcode", json={"barcode": "X"})
    assert client.get(f"{V}/audit/verify").status_code == 401
    assert client.get(f"{V}/audit/verify", headers=auth()).status_code == 403
    r = client.get(f"{V}/audit/verify", headers=auth("a", "auditor")).json()
    assert r["chain_valid"] and r["total_records"] == 3
    assert client.get(f"{V}/audit/log", headers=auth("a", "auditor")).json()["total"] == 3


def test_forged_token_rejected(client):
    from tests.conftest import make_token
    bad = make_token("x", "admin", secret="attacker" * 8)
    assert client.get(f"{V}/verify/history", headers={"Authorization": f"Bearer {bad}"}).status_code == 401


# ── audit chain integrity ──
def test_chain_detects_tampering(isolated_db):
    async def scenario():
        for i in range(5):
            await audit.add_audit_record(f"v{i}", {"verdict": "unknown", "drug": f"d{i}", "evidence": [{"x": i}]})
        assert (await audit.verify_chain())["chain_valid"]
        await isolated_db.local.update("audit_chain", {"canonical": '{"tampered":true}'}, {"verification_id": "v2"})
        return await audit.verify_chain()
    res = asyncio.run(scenario())
    assert not res["chain_valid"] and "canonical" in res["reason"]


def test_concurrent_appends_do_not_fork():
    async def scenario():
        await asyncio.gather(*(audit.add_audit_record(f"v{i}", {"verdict": "unknown"}) for i in range(40)))
        return await audit.verify_chain()
    res = asyncio.run(scenario())
    assert res["chain_valid"] and res["total_records"] == 40


def test_cloud_failure_fails_closed(monkeypatch, tmp_path):
    import httpx

    from models.exceptions import DatabaseWriteError
    from services.supabase import SupabaseClient

    db = SupabaseClient(local_path=tmp_path / "x.db")
    db.cloud_available, db.allow_fallback, db.url, db.key = True, False, "https://db.invalid", "k"
    db._http = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(400, text="violates not-null")))
    with pytest.raises(DatabaseWriteError):
        asyncio.run(db.insert("t", {"a": 1}))
    assert asyncio.run(db.local.query("t", None, 10, None, False)) == []  # nothing silently diverted


def test_local_store_concurrent_writes_not_lost(isolated_db):
    async def scenario():
        await asyncio.gather(*(isolated_db.insert("t", {"n": i}) for i in range(100)))
        return await isolated_db.query("t", limit=1000)
    assert len(asyncio.run(scenario())) == 100


# ── pharmacies (S1: fake "verified" pharmacy) ──
def test_pharmacy_cannot_be_self_verified(client):
    reg = client.post(f"{V}/pharmacies/register", params={"name": "Fake Meds", "address": "x", "lat": 12.9, "lng": 77.6})
    assert reg.status_code == 401
    pid = client.post(f"{V}/pharmacies/register", params={"name": "Real Meds", "address": "x", "lat": 12.9, "lng": 77.6}, headers=auth("u1")).json()["pharmacy"]["id"]
    q = {"contact_number": "9999999999", "license_number": "KA-123"}
    assert client.post(f"{V}/pharmacies/{pid}/claim", params=q, headers=auth("u1")).status_code == 403
    assert client.post(f"{V}/pharmacies/{pid}/claim", params=q, headers=auth("ph1", "pharmacist")).status_code == 200
    assert client.post(f"{V}/pharmacies/{pid}/verify-claim").status_code == 401
    assert client.post(f"{V}/pharmacies/{pid}/verify-claim", headers=auth("ph1", "pharmacist")).status_code == 403
    assert client.post(f"{V}/pharmacies/{pid}/verify-claim", headers=auth("reg1", "regulator")).status_code == 200
    inv = [{"name": "Dolo 650"}]
    assert client.put(f"{V}/pharmacies/{pid}/inventory", json=inv, headers=auth("ph2", "pharmacist")).status_code == 403
    assert client.put(f"{V}/pharmacies/{pid}/inventory", json=inv, headers=auth("ph1", "pharmacist")).status_code == 200


def test_reviews_need_auth_and_are_one_per_user(client):
    pid = client.post(f"{V}/pharmacies/register", params={"name": "PharmaOne", "address": "x", "lat": 1, "lng": 1}, headers=auth()).json()["pharmacy"]["id"]
    body = {"rating": 4, "comment": "Helpful staff and fair prices"}
    assert client.post(f"{V}/pharmacies/{pid}/review", json=body).status_code == 401
    assert client.post(f"{V}/pharmacies/{pid}/review", json=body, headers=auth("r1")).status_code == 200
    assert client.post(f"{V}/pharmacies/{pid}/review", json=body, headers=auth("r1")).status_code == 409


# ── clinic (S7, S8, R8) ──
def test_clinic_lifecycle(client):
    body = {"name": "PHC Coimbatore", "contact_email": "admin@phc.example", "admin_password": "correct horse battery"}
    assert client.post(f"{V}/clinic/create", json=body).status_code == 401
    assert client.post(f"{V}/clinic/create", json=body, headers=auth()).status_code == 403
    cid = client.post(f"{V}/clinic/create", json=body, headers=auth("root", "admin")).json()["clinic_id"]
    assert client.post(f"{V}/clinic/login", json={"email": body["contact_email"], "password": "wrong"}).status_code == 401
    assert client.post(f"{V}/clinic/login", json={"email": "nobody@x.example", "password": "x"}).status_code == 401
    tok = client.post(f"{V}/clinic/login", json={"email": body["contact_email"], "password": body["admin_password"]}).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    assert client.get(f"{V}/clinic/{cid}/dashboard", headers=h).status_code == 200
    assert client.get(f"{V}/clinic/other-clinic/dashboard", headers=h).status_code == 403


# ── cron & feature flags ──
def test_cron_requires_header_secret(client):
    assert client.post(f"{V}/push/notify-refill", params={"cron_secret": "default_secret_rotate_me"}).status_code == 401


def test_feature_flag_disables_endpoint(client, monkeypatch):
    from config import get_settings
    monkeypatch.setattr(get_settings(), "feature_pack_check", False)
    assert client.post(f"{V}/safety/pack-check", json={"qr_payload": "a|b|c|d|e|f|g|h"}).status_code == 404


def test_safety_intel_endpoints(client):
    assert client.get(f"{V}/safety/batch-alerts", params={"batch": "SMPL-T2401", "product": "Paracetamol"}).json()["status"] == "match"
    assert client.get(f"{V}/safety/batch-alerts/coverage").json()["is_sample_data"] is True
    assert client.post(f"{V}/safety/pack-check", json={}).status_code == 422
