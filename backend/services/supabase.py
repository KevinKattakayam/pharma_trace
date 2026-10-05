"""Supabase (PostgREST) client with an explicit, honest local fallback.

Behaviour (audit R2, R7, R9):

* **No cloud configured** (local dev, tests, offline demo): every call uses a local SQLite
  store with one row per record and a process-wide write lock, so concurrent writes are
  not lost.
* **Cloud configured**: failures raise ``DatabaseReadError`` / ``DatabaseWriteError``.
  They are *not* silently diverted to a local file that disappears on redeploy. Set
  ``ALLOW_LOCAL_FALLBACK_WRITES=true`` only for demos where that trade-off is acceptable.
"""
from __future__ import annotations

import asyncio
import json
import math
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import structlog
from rapidfuzz import fuzz
from rapidfuzz import process as rfuzz_process

from config import get_settings
from models.exceptions import DatabaseReadError, DatabaseWriteError

logger = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent / "data"
DB_PATH = DATA_DIR / "local_fallback.db"
CDSCO_DB_PATH = DATA_DIR / "cdsco_registry.db"


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _matches(row: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    return not filters or all(str(row.get(k)) == str(v) for k, v in filters.items())


class LocalStore:
    """Row-per-record SQLite store used when no cloud database is configured."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = asyncio.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS records (
                       seq INTEGER PRIMARY KEY AUTOINCREMENT,
                       table_name TEXT NOT NULL,
                       data TEXT NOT NULL)"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS ix_records_table ON records(table_name, seq)")
            self._migrate_legacy_blob_table(conn)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    @staticmethod
    def _migrate_legacy_blob_table(conn: sqlite3.Connection) -> None:
        """One-time import from the old one-JSON-blob-per-table layout."""
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='local_fallback'"
        ).fetchone()
        if not exists:
            return
        for table_name, blob in conn.execute("SELECT table_name, data FROM local_fallback").fetchall():
            try:
                rows = json.loads(blob) or []
            except json.JSONDecodeError:
                logger.error("local_store_legacy_row_unreadable", table=table_name)
                continue
            conn.executemany(
                "INSERT INTO records(table_name, data) VALUES (?, ?)",
                [(table_name, json.dumps(r, default=str)) for r in rows],
            )
        conn.execute("DROP TABLE local_fallback")

    # -- sync primitives (run in a worker thread) --------------------------------
    def _all(self, table: str) -> list[tuple[int, dict[str, Any]]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT seq, data FROM records WHERE table_name=? ORDER BY seq", (table,))
            return [(seq, json.loads(data)) for seq, data in cur.fetchall()]

    def _insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        with self._connect() as conn:
            for row in rows:
                row = dict(row)
                row.setdefault("id", str(uuid.uuid4()))
                cur = conn.execute(
                    "INSERT INTO records(table_name, data) VALUES (?, ?)",
                    (table, json.dumps(row, default=str)),
                )
                row.setdefault("_seq", cur.lastrowid)
                out.append(row)
        return out

    def _update(self, table: str, data: dict[str, Any], filters: dict[str, Any]) -> list[dict[str, Any]]:
        updated = []
        with self._connect() as conn:
            for seq, row in self._all(table):
                if _matches(row, filters):
                    row.update(data)
                    conn.execute("UPDATE records SET data=? WHERE seq=?", (json.dumps(row, default=str), seq))
                    updated.append(row)
        return updated

    def _delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        deleted = []
        with self._connect() as conn:
            for seq, row in self._all(table):
                if _matches(row, filters):
                    conn.execute("DELETE FROM records WHERE seq=?", (seq,))
                    deleted.append(row)
        return deleted

    # -- async API ---------------------------------------------------------------
    async def query(
        self, table: str, filters: dict[str, Any] | None, limit: int, order_by: str | None, order_desc: bool
    ) -> list[dict[str, Any]]:
        rows = [r for _, r in await asyncio.to_thread(self._all, table) if _matches(r, filters)]
        if order_by:
            rows.sort(key=lambda x: (x.get(order_by) is None, str(x.get(order_by, ""))), reverse=order_desc)
        elif order_desc:
            rows.reverse()
        return rows[:limit]

    async def insert(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._insert, table, rows)

    async def update(self, table: str, data: dict[str, Any], filters: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._update, table, data, filters)

    async def delete(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        async with self._lock:
            return await asyncio.to_thread(self._delete, table, filters)


class SupabaseClient:
    def __init__(self, local_path: Path = DB_PATH) -> None:
        settings = get_settings()
        self.url = settings.supabase_url.rstrip("/") if settings.supabase_url else ""
        self.key = settings.supabase_key
        self.cloud_available = bool(self.url and self.key)
        self.allow_fallback = (not self.cloud_available) or settings.allow_local_fallback_writes
        self.available = True  # kept for backward compatibility with existing callers
        self.pooler_enabled = ":6543" in self.url
        self.local = LocalStore(local_path)
        self._http: httpx.AsyncClient | None = None

    # -- infrastructure ----------------------------------------------------------
    @property
    def headers(self) -> dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(5.0, connect=3.0),
                limits=httpx.Limits(max_connections=get_settings().supabase_max_connections),
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()

    @staticmethod
    def _filter_params(filters: dict[str, Any] | None) -> dict[str, str]:
        return {k: f"eq.{v}" for k, v in (filters or {}).items()}

    def _fail(self, exc_type: type[Exception], op: str, table: str, detail: str) -> None:
        logger.error("db_cloud_failure", op=op, table=table, detail=detail[:300], fallback=self.allow_fallback)
        if not self.allow_fallback:
            raise exc_type(f"{op} on '{table}' failed: {detail[:200]}")

    # -- CRUD --------------------------------------------------------------------
    async def query(
        self,
        table: str,
        select: str = "*",
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        order_by: str | None = None,
        order_desc: bool = False,
        custom_params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        if self.cloud_available:
            params: dict[str, Any] = {"select": select, "limit": str(limit), **self._filter_params(filters)}
            if order_by:
                params["order"] = f"{order_by}.{'desc' if order_desc else 'asc'}"
            if custom_params:
                params.update(custom_params)
            start = time.perf_counter()
            try:
                resp = await self._client().get(
                    f"{self.url}/rest/v1/{table}", headers={**self.headers, **(extra_headers or {})}, params=params
                )
                if resp.status_code == 200:
                    rows = resp.json()
                    logger.debug("db_query", table=table, rows=len(rows), ms=round((time.perf_counter() - start) * 1000, 1))
                    return rows
                self._fail(DatabaseReadError, "query", table, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseReadError, "query", table, repr(exc))
        return await self.local.query(table, filters, limit, order_by, order_desc)

    async def insert(
        self, table: str, data: dict[str, Any], upsert: bool = False, extra_headers: dict[str, str] | None = None
    ) -> dict[str, Any]:
        if self.cloud_available:
            headers = {**self.headers, **(extra_headers or {})}
            if upsert:
                headers["Prefer"] = "return=representation, resolution=merge-duplicates"
            try:
                resp = await self._client().post(f"{self.url}/rest/v1/{table}", headers=headers, json=data)
                if resp.status_code in (200, 201):
                    result = resp.json()
                    return (result[0] if isinstance(result, list) and result else result) or data
                self._fail(DatabaseWriteError, "insert", table, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseWriteError, "insert", table, repr(exc))
        return (await self.local.insert(table, [data]))[0]

    async def insert_many(self, table: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not rows:
            return []
        if self.cloud_available:
            try:
                resp = await self._client().post(f"{self.url}/rest/v1/{table}", headers=self.headers, json=rows)
                if resp.status_code in (200, 201):
                    return resp.json()
                self._fail(DatabaseWriteError, "insert_many", table, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseWriteError, "insert_many", table, repr(exc))
        return await self.local.insert(table, rows)

    async def update(
        self, table: str, data: dict[str, Any], filters: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        if not filters:
            raise DatabaseWriteError("refusing unfiltered UPDATE")
        if self.cloud_available:
            try:
                resp = await self._client().patch(
                    f"{self.url}/rest/v1/{table}",
                    headers={**self.headers, **(extra_headers or {})},
                    params=self._filter_params(filters),
                    json=data,
                )
                if resp.status_code == 200:
                    return resp.json()
                self._fail(DatabaseWriteError, "update", table, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseWriteError, "update", table, repr(exc))
        return await self.local.update(table, data, filters)

    async def delete(
        self, table: str, filters: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> list[dict[str, Any]]:
        if not filters:
            raise DatabaseWriteError("refusing unfiltered DELETE")
        if self.cloud_available:
            try:
                resp = await self._client().delete(
                    f"{self.url}/rest/v1/{table}",
                    headers={**self.headers, **(extra_headers or {})},
                    params=self._filter_params(filters),
                )
                if resp.status_code == 200:
                    return resp.json()
                self._fail(DatabaseWriteError, "delete", table, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseWriteError, "delete", table, repr(exc))
        return await self.local.delete(table, filters)

    async def rpc(self, function_name: str, params: dict[str, Any] | None = None) -> Any:
        params = params or {}
        if self.cloud_available:
            try:
                resp = await self._client().post(f"{self.url}/rest/v1/rpc/{function_name}", headers=self.headers, json=params)
                if resp.status_code == 200:
                    return resp.json()
                self._fail(DatabaseReadError, "rpc", function_name, f"HTTP {resp.status_code}: {resp.text}")
            except httpx.HTTPError as exc:
                self._fail(DatabaseReadError, "rpc", function_name, repr(exc))

        if function_name == "fuzzy_drug_alias":
            return await self._local_fuzzy_alias(str(params.get("query_text", "")))
        if function_name.startswith("nearby_"):
            return await self._local_nearby(function_name.removeprefix("nearby_"), params)
        logger.warning("rpc_no_local_equivalent", function=function_name)
        return []

    async def geo_query(self, table: str, lat: float, lng: float, radius_meters: int = 5000) -> list[dict[str, Any]]:
        return await self.rpc(f"nearby_{table}", {"lat": lat, "lng": lng, "radius_m": radius_meters})

    # -- local RPC equivalents -------------------------------------------------------
    async def _local_fuzzy_alias(self, query_text: str) -> list[dict[str, Any]]:
        q = query_text.lower().strip()
        if len(q) < 2:
            return []

        def _search() -> list[dict[str, Any]]:
            if not (CDSCO_DB_PATH.exists() and CDSCO_DB_PATH.stat().st_size > 0):
                return []
            try:
                with sqlite3.connect(CDSCO_DB_PATH) as conn:
                    names = [r[0] for r in conn.execute("SELECT generic_name FROM indian_drugs") if r[0]]
            except sqlite3.Error as exc:
                logger.warning("cdsco_fuzzy_sqlite_error", error=str(exc))
                return []
            return [
                {"canonical_name": m, "similarity": round(score / 100.0, 2), "active_ingredients": [m.split("+")[0].strip()]}
                for m, score, _ in rfuzz_process.extract(q, names, scorer=fuzz.token_sort_ratio, limit=5)
                if score >= 70
            ]

        results = await asyncio.to_thread(_search)
        for alias in await self.query("vernacular_aliases", limit=500):
            v_name = str(alias.get("vernacular_name", "")).lower()
            if v_name and (q in v_name or v_name in q or fuzz.ratio(q, v_name) >= 75):
                c_name = str(alias.get("canonical_name", ""))
                results.append({"canonical_name": c_name, "similarity": 0.90, "active_ingredients": alias.get("active_ingredients", [c_name])})
        results.sort(key=lambda x: x.get("similarity", 0), reverse=True)
        return results[:5]

    async def _local_nearby(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        lat = float(params.get("lat", 0))
        lng = float(params.get("lng", 0))
        radius_m = float(params.get("radius_m", 5000))
        lat_delta = radius_m / 111_000.0
        lng_delta = radius_m / (111_000.0 * max(0.01, math.cos(math.radians(lat))))
        nearby = []
        for rec in await self.query(table, limit=5000):
            try:
                r_lat, r_lng = float(rec.get("lat", 0)), float(rec.get("lng", 0))
            except (TypeError, ValueError):
                continue
            if r_lat == 0 and r_lng == 0:
                continue
            if not (lat - lat_delta <= r_lat <= lat + lat_delta and lng - lng_delta <= r_lng <= lng + lng_delta):
                continue
            dist = _haversine_meters(lat, lng, r_lat, r_lng)
            if dist <= radius_m:
                nearby.append({**rec, "distance_m": round(dist)})
        nearby.sort(key=lambda x: x["distance_m"])
        return nearby


_client: SupabaseClient | None = None


def get_supabase() -> SupabaseClient:
    global _client
    if _client is None:
        configured = get_settings().local_store_path
        _client = SupabaseClient(local_path=Path(configured) if configured else DB_PATH)
    return _client


def reset_supabase_for_tests(path: Path) -> SupabaseClient:
    """Point the singleton at an isolated store (tests only)."""
    global _client
    _client = SupabaseClient(local_path=path)
    return _client
