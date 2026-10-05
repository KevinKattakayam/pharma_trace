"""Shared fixtures: isolated storage, fixed secrets, no network, token factory."""
from __future__ import annotations

import os
import sys
import warnings
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.update({
    "ENVIRONMENT": "test",
    "JWT_SECRET": "test-jwt-secret-Aa1!-" + "x" * 48,
    "HMAC_DAILY_SECRET": "test-hmac-secret-" + "y" * 32,
    "CRON_SECRET": "test-cron-secret-" + "z" * 32,
    "SUPABASE_URL": "",
    "SUPABASE_KEY": "",
    "SENTRY_DSN": "",
    "GROQ_API_KEY": "",
    "OPENROUTER_API_KEY": "",
    "MANUFACTURER_VERIFICATION_URL": "",
    "BATCH_ALERTS_DATA_PATH": str(BACKEND / "data" / "samples" / "regulator_alerts.SAMPLE.json"),
})
warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*ephemeral.*")

import jwt  # noqa: E402

from config import get_settings  # noqa: E402

SAMPLE_ALERTS = BACKEND / "data" / "samples" / "regulator_alerts.SAMPLE.json"


def make_token(sub: str = "user-1", role: str = "user", clinic_id: str | None = None, *, expired: bool = False, secret: str | None = None) -> str:
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {"sub": sub, "role": role, "exp": now + (timedelta(hours=-1) if expired else timedelta(hours=1)), "iat": now}
    if clinic_id:
        payload["clinic_id"] = clinic_id
    return jwt.encode(payload, secret or s.jwt_secret, algorithm=s.jwt_algorithm)


def auth(sub: str = "user-1", role: str = "user", clinic_id: str | None = None) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(sub, role, clinic_id)}"}


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    from services import audit
    from services.supabase import reset_supabase_for_tests
    client = reset_supabase_for_tests(tmp_path / "local.db")
    audit._lock = __import__("asyncio").Lock()
    yield client


@pytest.fixture(autouse=True)
def no_rate_limits():
    from services.limiter import limiter
    limiter.reset()
    limiter.enabled = False
    yield limiter
    limiter.enabled = True


@pytest.fixture(autouse=True)
def sample_alerts():
    from services.batch_alerts import load_index
    return load_index(path=SAMPLE_ALERTS)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    import main
    with TestClient(main.app) as c:
        yield c


@pytest.fixture
def offline_externals(monkeypatch):
    """Deterministic stand-ins for every network dependency of the verification pipeline."""
    import routers.verify as v
    state = {"fda": [], "cdsco": {"available": True, "has_cdsco_recall": False}, "ndc": None, "cdsco_drug": None, "resolved": None, "serial": {"verified": None, "available": False}}

    async def lookup_by_ndc(*a, **k): return state["ndc"]
    async def lookup_indian_drug(*a, **k): return state["cdsco_drug"]
    async def resolve_drug_name(*a, **k): return state["resolved"] or {"source": "unresolved"}
    async def check_recalls(*a, **k): return state["fda"]
    async def check_cdsco_recall(*a, **k): return state["cdsco"]
    async def check_drug_shortage(*a, **k): return {"in_shortage": False}
    async def get_drug_label(*a, **k): return None
    async def verify_serialized_package(**k): return state["serial"]
    async def check_cold_chain(*a, **k): return {"available": False}

    for name, fn in list(locals().items()):
        if callable(fn) and hasattr(v, name):
            monkeypatch.setattr(v, name, fn)
    return state


# ── Schema-contract recorder ─────────────────────────────────────────────────
# Every table/column the application touches while the whole suite runs is recorded, and
# tests/test_zz_schema_contract.py checks them against a real, fully migrated PostgreSQL.
SCHEMA_TOUCH: dict[str, dict[str, set[str]]] = {}


def _touch(table: str, kind: str, cols) -> None:
    entry = SCHEMA_TOUCH.setdefault(table, {"write": set(), "filter": set(), "select": set()})
    entry[kind].update(c for c in cols if isinstance(c, str))


def _install_recorder() -> None:
    from services.supabase import SupabaseClient

    def wrap(name: str, record):
        original = getattr(SupabaseClient, name)

        async def recorded(self, *args, **kwargs):
            record(args, kwargs)
            return await original(self, *args, **kwargs)
        setattr(SupabaseClient, name, recorded)

    def arg(args, kwargs, i, key, default=None):
        return args[i] if len(args) > i else kwargs.get(key, default)

    wrap("insert", lambda a, k: _touch(arg(a, k, 0, "table"), "write", (arg(a, k, 1, "data") or {}).keys()))
    wrap("insert_many", lambda a, k: [_touch(arg(a, k, 0, "table"), "write", r.keys()) for r in (arg(a, k, 1, "rows") or [])])
    wrap("update", lambda a, k: (_touch(arg(a, k, 0, "table"), "write", (arg(a, k, 1, "data") or {}).keys()),
                                 _touch(arg(a, k, 0, "table"), "filter", (arg(a, k, 2, "filters") or {}).keys())))
    wrap("delete", lambda a, k: _touch(arg(a, k, 0, "table"), "filter", (arg(a, k, 1, "filters") or {}).keys()))

    def rec_query(a, k):
        table = arg(a, k, 0, "table")
        _touch(table, "filter", (k.get("filters") or {}).keys())
        if k.get("order_by"):
            _touch(table, "select", [k["order_by"]])
        sel = k.get("select", "*")
        if isinstance(sel, str) and sel != "*":
            _touch(table, "select", [c.strip() for c in sel.split(",") if c.strip().isidentifier()])
    wrap("query", rec_query)


_install_recorder()
