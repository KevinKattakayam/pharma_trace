"""Unit tests: config posture, security primitives, verdict rules, caches, tasks."""
from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from config import Settings
from services import tasks
from services.confidence import assess_verdict, compute_confidence, determine_verdict
from services.security import client_ip, constant_time_equals, decode_token, pseudonymise
from services.ttl_cache import TTLCache
from tests.conftest import make_token

STRONG = "Aa1!" + "k" * 70


# ── config ──
def _strict(**kw):
    base = dict(environment="prod", jwt_secret=STRONG, hmac_daily_secret="h" * 40, cors_origins=["https://app.example"])
    return Settings(_env_file=None, **{**base, **kw})


def test_prod_accepts_strong_config():
    assert _strict().is_strict


@pytest.mark.parametrize("override", [
    {"jwt_secret": ""}, {"jwt_secret": "short"}, {"jwt_secret": "a" * 80},
    {"hmac_daily_secret": "default_secret_rotate_me"}, {"hmac_daily_secret": ""},
    {"debug": True}, {"cors_origins": ["*"]}, {"allow_unauthenticated_demo_user": True},
])
def test_prod_rejects_weak_or_public_settings(override):
    with pytest.raises(ValidationError):
        _strict(**override)


def test_dev_never_uses_guessable_secret():
    with pytest.warns(RuntimeWarning):
        s = Settings(_env_file=None, environment="dev", jwt_secret="", hmac_daily_secret="default_secret_rotate_me")
    assert len(s.jwt_secret) >= 48 and s.hmac_daily_secret != "default_secret_rotate_me"


def test_debug_defaults_off():
    assert Settings(_env_file=None, environment="dev", jwt_secret=STRONG, hmac_daily_secret="h" * 40).debug is False


# ── security ──
def test_decode_rejects_forged_and_expired_tokens():
    assert decode_token(make_token("u1"))["sub"] == "u1"
    assert decode_token(make_token("u1", secret="attacker-secret-" + "q" * 40)) is None
    assert decode_token(make_token("u1", expired=True)) is None
    assert decode_token("not.a.token") is None


def _req(headers=None, client=("203.0.113.9", 1234)):
    return Request({"type": "http", "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()], "client": client})


def test_client_ip_ignores_xff_without_trusted_proxies(monkeypatch):
    assert client_ip(_req({"X-Forwarded-For": "1.1.1.1"})) == "203.0.113.9"


def test_client_ip_uses_trusted_hop(monkeypatch):
    from config import get_settings
    monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
    assert client_ip(_req({"X-Forwarded-For": "6.6.6.6, 198.51.100.7"})) == "198.51.100.7"


def test_pseudonyms_are_keyed_and_domain_separated():
    a = pseudonymise("203.0.113.9", purpose="ratelimit")
    assert a == pseudonymise("203.0.113.9", purpose="ratelimit")
    assert a != pseudonymise("203.0.113.9", purpose="reporter")
    assert "203" not in a


def test_constant_time_equals():
    assert constant_time_equals("abc", "abc") and not constant_time_equals("abc", "abd")
    assert not constant_time_equals(None, "x") and not constant_time_equals("", "")


def test_rate_limit_key_uses_verified_subject_only():
    from services.limiter import rate_limit_key
    good = _req({"Authorization": f"Bearer {make_token('alice')}"})
    forged = _req({"Authorization": f"Bearer {make_token('mallory', secret='x' * 64)}"})
    assert rate_limit_key(good) == "user:alice"
    assert rate_limit_key(forged).startswith("anon:")


# ── verdict rules (original safety tests preserved + new) ──
def test_record_match_cannot_become_authentic_without_serial_check():
    assert determine_verdict(99, serial_verification=None, no_active_recall=True) == "unknown"


def test_authoritative_serial_check_controls_final_claim():
    assert determine_verdict(99, serial_verification=True, no_active_recall=True) == "authentic"
    assert determine_verdict(99, serial_verification=False, no_active_recall=True) == "counterfeit"


def test_active_recall_is_never_authentic():
    assert determine_verdict(99, serial_verification=True, no_active_recall=False) == "suspicious"


def test_serial_verified_but_recall_unknown_is_not_authentic():
    assert determine_verdict(99, serial_verification=True, no_active_recall=None) == "unknown"


def test_clean_record_match_is_unknown_not_suspicious():
    """Regression: confidence is always 0 without a serial check; that alone must not alarm."""
    assert assess_verdict(serial_verification=None, no_active_recall=True, registry_match=True) == ("unknown", [])


@pytest.mark.parametrize("flag", ["invalid_check_digit", "batch_alert", "expired", "label_inconsistent", "vision_high_suspicion"])
def test_each_negative_evidence_code_makes_pack_suspicious(flag):
    verdict, reasons = assess_verdict(integrity_flags=[flag])
    assert verdict == "suspicious" and flag in reasons


def test_registry_miss_is_suspicious_and_unknown_flags_ignored():
    assert assess_verdict(registry_match=False)[0] == "suspicious"
    assert assess_verdict(integrity_flags=["made_up_code"])[0] == "unknown"


def test_serial_rejection_dominates():
    assert assess_verdict(serial_verification=False, no_active_recall=True, integrity_flags=["expired"])[0] == "counterfeit"


def test_missing_recall_coverage_is_not_reported_as_clear():
    confidence, evidence = compute_confidence(False, True, None)
    assert confidence == 0.0
    assert next(e for e in evidence if e.check == "recall_check").status == "warn"


# ── caches & tasks ──
def test_ttl_cache_bounds_and_expiry():
    c: TTLCache[int] = TTLCache(maxsize=3, ttl_seconds=0.05)
    for i in range(10):
        c[str(i)] = i
    assert len(c) == 3 and c.get("0") is None and c.get("9") == 9
    time.sleep(0.07)
    assert c.get("9") is None


def test_supervised_tasks_are_tracked_and_drained():
    async def scenario():
        done = []

        async def work():
            await asyncio.sleep(0.01)
            done.append(1)

        async def boom():
            raise RuntimeError("x")

        tasks.spawn(work(), name="w")
        tasks.spawn(boom(), name="b")
        assert tasks.pending_count() == 2
        assert await tasks.drain(grace_period=1) == 0
        return done
    assert asyncio.run(scenario()) == [1]
