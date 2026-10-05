"""Import real pharmacy locations from OpenStreetMap (Overpass API) as UNVERIFIED listings.

Data © OpenStreetMap contributors, licensed under the ODbL (https://www.openstreetmap.org/copyright).
Attribution is stored on every record (`source`) and shown in the map UI. OSM is edited by the public,
so every imported listing is marked `osm_unverified`: it is a place that exists on a map, NOT a pharmacy
anyone has checked for a valid licence or genuine stock. Pharmacies become `claim_verified` only through the
claim + regulator approval flow in routers/pharmacies.py.

    python -m scripts.import_osm_pharmacies --bbox 10.90,76.85,11.15,77.10 --dry-run
    python -m scripts.import_osm_pharmacies --bbox 10.90,76.85,11.15,77.10          # writes to the configured DB
    (bbox = south,west,north,east in decimal degrees; keep it to one city/district: Overpass is a shared service)
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
SOURCE = "OpenStreetMap contributors (ODbL)"
MAX_AREA_DEG2 = 1.0  # refuse accidentally huge boxes (≈ 12,000 km² at the equator)
USER_AGENT = "PharmaTrace-importer/2.0 (+https://github.com/Kevinbastin/pharma_trace)"


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    try:
        s, w, n, e = (float(x) for x in text.split(","))
    except ValueError as exc:
        raise ValueError("bbox must be four numbers: south,west,north,east") from exc
    if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
        raise ValueError("bbox out of range or south>=north / west>=east")
    if (n - s) * (e - w) > MAX_AREA_DEG2:
        raise ValueError(f"bbox too large (> {MAX_AREA_DEG2} square degrees); import one city or district at a time")
    return s, w, n, e


def build_query(bbox: tuple[float, float, float, float]) -> str:
    b = ",".join(str(x) for x in bbox)
    return f'[out:json][timeout:60];(node["amenity"="pharmacy"]({b});way["amenity"="pharmacy"]({b}););out center tags;'


def _address(tags: dict[str, str]) -> str:
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"), tags.get("addr:suburb"), tags.get("addr:city"), tags.get("addr:postcode")]
    return ", ".join(p for p in parts if p) or tags.get("addr:full", "")


def parse_elements(elements: list[dict[str, Any]], bbox: tuple[float, float, float, float]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    s, w, n, e = bbox
    out: list[dict[str, Any]] = []
    stats = {"seen": len(elements), "no_name": 0, "no_coords": 0, "outside_bbox": 0}
    seen_ids: set[str] = set()
    for el in elements:
        tags = el.get("tags") or {}
        name = (tags.get("name") or tags.get("name:en") or "").strip()
        lat = el.get("lat", (el.get("center") or {}).get("lat"))
        lng = el.get("lon", (el.get("center") or {}).get("lon"))
        if not name:
            stats["no_name"] += 1
            continue
        if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
            stats["no_coords"] += 1
            continue
        if not (s <= lat <= n and w <= lng <= e):
            stats["outside_bbox"] += 1
            continue
        source_id = f"{el.get('type', 'node')}/{el.get('id')}"
        if source_id in seen_ids:
            continue
        seen_ids.add(source_id)
        out.append({
            "name": name[:160], "address": _address(tags)[:300], "city": tags.get("addr:city", "")[:80],
            "country": "India" if tags.get("addr:country") == "IN" else tags.get("addr:country", "")[:80],
            "lat": float(lat), "lng": float(lng), "contact_number": (tags.get("phone") or tags.get("contact:phone") or None),
            "listing_status": "osm_unverified", "is_claimed": False, "verified_inventory": [],
            "source": SOURCE, "source_id": source_id,
        })
    return out, stats


async def fetch(bbox: tuple[float, float, float, float], *, client: httpx.AsyncClient | None = None, url: str = OVERPASS_URL) -> list[dict[str, Any]]:
    own = client is None
    client = client or httpx.AsyncClient(timeout=90, headers={"User-Agent": USER_AGENT})
    try:
        resp = await client.post(url, data={"data": build_query(bbox)})
        resp.raise_for_status()
        return resp.json().get("elements", [])
    finally:
        if own:
            await client.aclose()


async def store(records: list[dict[str, Any]]) -> tuple[int, int]:
    """Insert records whose (source, source_id) is new. Returns (inserted, already_present)."""
    from services.supabase import get_supabase
    db = get_supabase()
    existing = {r.get("source_id") for r in await db.query("pharmacies", filters={"source": SOURCE}, limit=100_000)}
    fresh = [r for r in records if r["source_id"] not in existing]
    for i in range(0, len(fresh), 200):
        await db.insert_many("pharmacies", fresh[i:i + 200])
    return len(fresh), len(records) - len(fresh)


async def run(bbox_text: str, *, dry_run: bool, out: Path | None) -> int:
    bbox = parse_bbox(bbox_text)
    records, stats = parse_elements(await fetch(bbox), bbox)
    print(f"OSM returned {stats['seen']} elements -> {len(records)} usable "
          f"({stats['no_name']} unnamed, {stats['no_coords']} without coordinates, {stats['outside_bbox']} outside box).")
    if out:
        await asyncio.to_thread(out.write_text, json.dumps(records, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"wrote {out}")
    if dry_run:
        print("dry run: nothing stored.")
        return 0
    inserted, present = await store(records)
    print(f"stored {inserted} new listings ({present} already present). All are marked osm_unverified.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bbox", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    try:
        return asyncio.run(run(a.bbox, dry_run=a.dry_run, out=a.out))
    except (ValueError, httpx.HTTPError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
