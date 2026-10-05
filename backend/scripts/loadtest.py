"""Minimal async load generator. Reports latency percentiles per endpoint; no external deps beyond httpx.

Usage: python -m scripts.loadtest --base http://127.0.0.1:8000 --requests 2000 --concurrency 50
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx

SCENARIOS = {
    "GET /health": ("GET", "/api/v1/health", None),
    "POST /safety/pack-check": ("POST", "/api/v1/safety/pack-check",
        {"qr_payload": "U1|Paracetamol IP|Crocin|GSK|AB12|01/2025|12/2027|MB/07/123", "printed": {"batch_no": "AB12", "expiry_date": "12/2027"}}),
    "POST /safety/lasa-check": ("POST", "/api/v1/safety/lasa-check", {"name": "Combiflam"}),
    "GET /safety/batch-alerts": ("GET", "/api/v1/safety/batch-alerts?batch=SMPL-T2401&product=Paracetamol", None),
    "POST /barcode/parse-gs1": ("POST", "/api/v1/barcode/parse-gs1?data=(01)04006381333931(17)270100(10)AB1234(21)S1", None),
}


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(round(p / 100 * (len(s) - 1))))]


async def run(base: str, name: str, n: int, conc: int) -> dict:
    method, path, body = SCENARIOS[name]
    lat: list[float] = []
    errors = 0
    sem = asyncio.Semaphore(conc)
    async with httpx.AsyncClient(base_url=base, timeout=30, limits=httpx.Limits(max_connections=conc)) as c:
        async def one() -> None:
            nonlocal errors
            async with sem:
                t = time.perf_counter()
                r = await c.request(method, path, json=body)
                lat.append((time.perf_counter() - t) * 1000)
                errors += r.status_code >= 400
        t0 = time.perf_counter()
        await asyncio.gather(*(one() for _ in range(n)))
        wall = time.perf_counter() - t0
    return {"endpoint": name, "requests": n, "concurrency": conc, "errors": errors, "rps": round(n / wall, 1),
            "p50_ms": round(statistics.median(lat), 1), "p95_ms": round(pct(lat, 95), 1), "p99_ms": round(pct(lat, 99), 1)}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--requests", type=int, default=1000)
    ap.add_argument("--concurrency", type=int, default=50)
    a = ap.parse_args()
    for name in SCENARIOS:
        print(json.dumps(await run(a.base, name, a.requests, a.concurrency)))


if __name__ == "__main__":
    asyncio.run(main())
