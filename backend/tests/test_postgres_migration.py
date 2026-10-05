"""Runs migrations/phase5_audit_chain.sql against a REAL PostgreSQL (bundled via `pgserver`).

Skipped automatically if pgserver/psycopg are not installed (they are in requirements-dev.txt).
Proves: idempotent apply, DB-computed hashes equal Python's, forks and edits are impossible,
concurrent appends from separate connections stay a single valid chain, legacy table upgrade.
"""
from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

from services.audit import GENESIS_HASH, compute_hash  # noqa: E402

MIGRATION = (Path(__file__).resolve().parents[1] / "migrations" / "phase5_audit_chain.sql").read_text()
LEGACY_TABLE = """
CREATE TABLE audit_chain (
    id SERIAL PRIMARY KEY, verification_id TEXT NOT NULL, record_hash TEXT NOT NULL UNIQUE,
    previous_hash TEXT NOT NULL, data JSONB NOT NULL, created_at TIMESTAMPTZ DEFAULT NOW());
"""


@pytest.fixture(scope="module")
def pg():
    srv = pgserver.get_server(tempfile.mkdtemp())
    yield srv.get_uri()
    srv.cleanup()


@pytest.fixture
def db(pg):
    with psycopg.connect(pg, autocommit=True) as c:
        c.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    return pg


def apply(uri: str) -> None:
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(MIGRATION)


def append(uri: str, vid: str, canonical: str) -> dict:
    with psycopg.connect(uri, autocommit=True) as c:
        row = c.execute("SELECT * FROM append_audit_record(%s, 'verification', %s)", (vid, canonical)).fetchone()
        cols = [d.name for d in c.execute("SELECT * FROM audit_chain LIMIT 0").description]
        return dict(zip(cols, row, strict=True))


def chain(uri: str) -> list[dict]:
    with psycopg.connect(uri, autocommit=True) as c:
        cur = c.execute("SELECT id, previous_hash, record_hash, canonical FROM audit_chain ORDER BY id")
        return [dict(zip(("id", "previous_hash", "record_hash", "canonical"), r, strict=True)) for r in cur.fetchall()]


def python_verifies(rows: list[dict]) -> bool:
    prev = GENESIS_HASH
    for r in rows:
        if r["previous_hash"] != prev or compute_hash(prev, r["canonical"]) != r["record_hash"]:
            return False
        prev = r["record_hash"]
    return True


def test_migration_is_idempotent(db):
    apply(db)
    apply(db)  # second run must not error


def test_database_hashes_match_python_including_unicode(db):
    apply(db)
    first = append(db, "v1", '{"drug":"Crocin"}')
    assert first["previous_hash"] == GENESIS_HASH
    append(db, "v2", '{"drug":"पैरासिटामोल","note":"ünïcode ✓"}')
    rows = chain(db)
    assert len(rows) == 2 and python_verifies(rows)


def test_append_only_triggers_block_edit_delete_truncate(db):
    apply(db)
    append(db, "v1", '{"a":1}')
    for sql in ("UPDATE audit_chain SET canonical='{}'", "DELETE FROM audit_chain", "TRUNCATE audit_chain"):
        with psycopg.connect(db, autocommit=True) as c, pytest.raises(psycopg.errors.RaiseException, match="append-only"):
            c.execute(sql)
    assert python_verifies(chain(db))


def test_fork_is_impossible(db):
    apply(db)
    append(db, "v1", '{"a":1}')
    head = chain(db)[0]
    with psycopg.connect(db, autocommit=True) as c, pytest.raises(psycopg.errors.UniqueViolation):
        c.execute("INSERT INTO audit_chain(verification_id, previous_hash, record_hash, canonical) VALUES ('x', %s, 'other', '{}')", (GENESIS_HASH,))
    assert head["previous_hash"] == GENESIS_HASH


def test_concurrent_connections_produce_one_valid_chain(db):
    apply(db)
    errors: list[Exception] = []

    def worker(i: int) -> None:
        try:
            for j in range(5):
                append(db, f"v{i}-{j}", f'{{"w":{i},"j":{j}}}')
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    rows = chain(db)
    assert not errors and len(rows) == 40 and python_verifies(rows)


def test_empty_canonical_rejected(db):
    apply(db)
    with psycopg.connect(db, autocommit=True) as c, pytest.raises(psycopg.errors.RaiseException):
        c.execute("SELECT * FROM append_audit_record('v', 'verification', '')")


def test_upgrade_from_legacy_audit_chain_table(db):
    with psycopg.connect(db, autocommit=True) as c:
        c.execute(LEGACY_TABLE)
    apply(db)
    append(db, "v1", '{"a":1}')
    assert python_verifies(chain(db))
