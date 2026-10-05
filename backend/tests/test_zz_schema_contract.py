"""Schema contract: everything the application reads/writes must exist in the migrated database.

Runs LAST (zz) so it sees the traffic recorded by the whole suite. Migrations are applied to a real
PostgreSQL. Only PostGIS/pg_trgm are unavailable in the bundled build, so those exact features are
shimmed (GEOGRAPHY→TEXT; statements that need them are tolerated); every other statement must succeed.
"""
from __future__ import annotations

import pathlib
import re
import tempfile

import pytest

pgserver = pytest.importorskip("pgserver")
psycopg = pytest.importorskip("psycopg")

from tests.conftest import SCHEMA_TOUCH  # noqa: E402

BACKEND = pathlib.Path(__file__).resolve().parents[1]
TOLERATED = re.compile(r"postgis|pg_trgm|geography|gin_trgm|similarity|gist|\bst_|vector", re.I)
# Tables every full run must have exercised; otherwise the test was run in isolation.
EXPECTED_TOUCHED = {"verifications", "pharmacies", "audit_chain", "clinics"}


def split_statements(sql: str) -> list[str]:
    out, buf, in_dollar = [], [], False
    for line in sql.splitlines(keepends=True):
        buf.append(line)
        if line.count("$$") % 2:
            in_dollar = not in_dollar
        if not in_dollar and line.rstrip().endswith(";"):
            stmt = "".join(buf)
            if re.sub(r"--.*", "", stmt).strip():
                out.append(stmt)
            buf = []
    return out


@pytest.fixture(scope="module")
def migrated():
    srv = pgserver.get_server(tempfile.mkdtemp())
    uri = srv.get_uri()
    with psycopg.connect(uri, autocommit=True) as c:
        for role in ("anon", "authenticated", "service_role"):
            c.execute(f"DO $$ BEGIN CREATE ROLE {role}; EXCEPTION WHEN duplicate_object THEN NULL; END $$")
        c.execute("CREATE SCHEMA IF NOT EXISTS auth")
        c.execute("CREATE OR REPLACE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql AS $$ SELECT NULL::uuid $$")
        files = [BACKEND / "supabase_migration.sql", *sorted((BACKEND / "migrations").glob("*.sql"))]
        unexpected = []
        for f in files:
            sql = re.sub(r"GEOGRAPHY\s*\(\s*Point\s*,\s*4326\s*\)", "TEXT", f.read_text(), flags=re.I)
            for stmt in split_statements(sql):
                try:
                    c.execute(stmt)
                except psycopg.Error as exc:
                    if not TOLERATED.search(str(exc) + stmt[:200]):
                        unexpected.append(f"{f.name}: {str(exc).splitlines()[0]}  <- {stmt.strip()[:90]!r}")
        cols: dict[str, set[str]] = {}
        for t, col in c.execute("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'").fetchall():
            cols.setdefault(t, set()).add(col)
    yield cols, unexpected
    srv.cleanup()


def test_migrations_apply_cleanly_in_order(migrated):
    _, unexpected = migrated
    assert not unexpected, "migration statements failed:\n" + "\n".join(unexpected)


def test_every_table_the_code_uses_exists(migrated):
    cols, _ = migrated
    code_tables = set()
    pat = re.compile(r"(?:\.query|\.insert|\.insert_many|\.update|\.delete|\.geo_query)\(\s*[\"']([a-z_]+)[\"']")
    table_attr = re.compile(r"table_name\s*=\s*[\"']([a-z_]+)[\"']")
    for f in BACKEND.rglob("*.py"):
        if any(x in f.parts for x in ("venv", "tests", "scripts", "eval")):
            continue
        s = f.read_text()
        code_tables |= set(pat.findall(s)) | set(table_attr.findall(s))
    missing = sorted(t for t in code_tables if t not in cols)
    assert not missing, f"tables used by code but missing from migrations: {missing}"


def test_every_column_touched_by_the_suite_exists(migrated):
    cols, _ = migrated
    if not EXPECTED_TOUCHED <= set(SCHEMA_TOUCH):
        pytest.skip("run the full suite so the recorder sees real traffic")
    problems = []
    for table, kinds in sorted(SCHEMA_TOUCH.items()):
        if table == "t":  # scratch table used by the local-store unit test
            continue
        if table not in cols:
            problems.append(f"{table}: TABLE MISSING")
            continue
        for kind, names in kinds.items():
            for col in sorted(names - cols[table]):
                problems.append(f"{table}.{col} ({kind})")
    assert not problems, "columns used by the application but absent from the schema:\n  " + "\n  ".join(problems)
