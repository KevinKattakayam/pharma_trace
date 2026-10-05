"""Flows for features that previously had no tests: caregiver links, anonymous reports, cabinet.

Besides checking behaviour, they feed real traffic to the schema-contract recorder so the columns
these routers write are verified against the migrated PostgreSQL (tests/test_zz_schema_contract.py).
"""
from __future__ import annotations

import re

import pytest

from models.exceptions import DatabaseWriteError
from tests.conftest import auth

V = "/api/v1"


# ── anonymous reports ──
def test_anonymous_report_gets_random_token_and_is_stored(client):
    r = client.post(f"{V}/reports", json={"drug_name": "Telma AM", "description": "Pack looked different", "anonymous": True, "city": "Coimbatore"})
    assert r.status_code == 200 and r.json()["status"] == "pending"
    token = r.json()["anonymous_id"]
    assert re.fullmatch(r"[0-9a-f]{16}", token)
    # two reports from the same client never share a token (token is not derived from IP)
    r2 = client.post(f"{V}/reports", json={"drug_name": "Telma AM", "description": "Another", "anonymous": True})
    assert r2.json()["anonymous_id"] != token


def test_failed_report_save_is_an_error_not_fake_success(client, monkeypatch):
    import services.anonymous as anon

    async def boom(_report):
        raise DatabaseWriteError("db down")
    monkeypatch.setattr(anon.repo, "create", boom)
    r = client.post(f"{V}/reports", json={"drug_name": "X", "description": "y", "anonymous": True})
    assert r.status_code == 503, "a reporter must never be told 'submitted' when nothing was stored"


def test_report_does_not_read_client_forwarding_headers(client):
    r = client.post(f"{V}/reports", json={"drug_name": "X", "description": "y", "anonymous": True},
                    headers={"X-Forwarded-For": "6.6.6.6", "CF-Connecting-IP": "7.7.7.7"})
    assert r.status_code == 200


# ── caregiver ──
@pytest.fixture
def caregiver_stubs(monkeypatch):
    import routers.caregiver as cg

    async def resolve_all_drugs(names):
        return [{"generic_name": n.lower(), "rxcui": "161"} for n in names]

    async def check_all_interactions(*_a, **_k):
        return {"interactions": [], "overall_risk": {"value": "low"}}
    monkeypatch.setattr(cg, "resolve_all_drugs", resolve_all_drugs, raising=False)
    monkeypatch.setattr(cg, "check_all_interactions", check_all_interactions, raising=False)


def test_caregiver_link_lifecycle(client, caregiver_stubs):
    code = client.post(f"{V}/caregiver/link", headers=auth("patient-1")).json()["code"]
    assert len(code) >= 16
    assert client.post(f"{V}/caregiver/accept", json={"code": code}, headers=auth("patient-1")).status_code == 400  # cannot self-link
    assert client.post(f"{V}/caregiver/accept", json={"code": "nope"}, headers=auth("cg-1")).status_code == 404
    assert client.post(f"{V}/caregiver/accept", json={"code": code}, headers=auth("cg-1")).status_code == 200
    dash = client.get(f"{V}/caregiver/dashboard", headers=auth("cg-1")).json()
    assert dash["total_linked"] == 1
    added = client.post(f"{V}/caregiver/recipient/{code}/medication", params={"drug_name": "Paracetamol", "confidence": 90}, headers=auth("cg-1"))
    assert added.status_code == 200 and added.json()["status"] == "added"
    # a different caregiver cannot manage this recipient
    assert client.post(f"{V}/caregiver/recipient/{code}/medication", params={"drug_name": "X"}, headers=auth("cg-2")).status_code == 403
    assert client.get(f"{V}/caregiver/alerts", headers=auth("cg-1")).status_code == 200


def test_caregiver_endpoints_need_auth(client):
    assert client.post(f"{V}/caregiver/link").status_code == 401
    assert client.get(f"{V}/caregiver/dashboard").status_code == 401


def test_low_confidence_medication_raises_alert(client, caregiver_stubs):
    code = client.post(f"{V}/caregiver/link", headers=auth("p")).json()["code"]
    client.post(f"{V}/caregiver/accept", json={"code": code}, headers=auth("c"))
    r = client.post(f"{V}/caregiver/recipient/{code}/medication", params={"drug_name": "Mystery", "confidence": 20}, headers=auth("c")).json()
    assert any(a["type"] == "verification" and a["severity"] == "high" for a in r["new_alerts"])


# ── cabinet ──
def test_cabinet_members_and_medicines(client, monkeypatch):
    import routers.cabinet as cab

    async def resolve_all_drugs(names):
        return [{"generic_name": n.lower(), "rxcui": "161"} for n in names]
    monkeypatch.setattr(cab, "resolve_all_drugs", resolve_all_drugs, raising=False)
    h = auth("alice")
    m = client.post(f"{V}/cabinet/members", json={"user_id": "alice", "name": "Mum", "age": 61, "conditions": "hypertension"}, headers=h)
    assert m.status_code == 200, m.text
    assert client.post(f"{V}/cabinet/members", json={"user_id": "bob", "name": "X", "age": 5, "conditions": ""}, headers=h).status_code in (401, 403)
    med = client.post(f"{V}/cabinet/add", json={"user_id": "alice", "medicine_name": "Dolo 650", "expiry_date": "12/2027"}, headers=h)
    assert med.status_code == 200, med.text
    listed = client.get(f"{V}/cabinet/list/alice", headers=h)
    assert listed.status_code == 200
    assert client.get(f"{V}/cabinet/list/alice", headers=auth("mallory")).status_code in (401, 403)
