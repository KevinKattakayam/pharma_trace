from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

import httpx
import pytest

from scripts import import_osm_pharmacies as osm
from tests.conftest import auth

BACKEND = Path(__file__).resolve().parents[1]
BBOX = (10.90, 76.85, 11.15, 77.10)
# Synthetic Overpass-shaped response (made-up places; names/ids are not real businesses).
ELEMENTS = [
    {"type": "node", "id": 1, "lat": 11.0, "lon": 76.9, "tags": {"amenity": "pharmacy", "name": "Example Medicals", "addr:street": "Test Road", "addr:city": "Coimbatore", "phone": "+91 000 000 0000"}},
    {"type": "way", "id": 2, "center": {"lat": 11.01, "lon": 76.95}, "tags": {"amenity": "pharmacy", "name": "Sample Pharmacy", "addr:country": "IN"}},
    {"type": "node", "id": 3, "lat": 11.0, "lon": 76.9, "tags": {"amenity": "pharmacy"}},                        # unnamed
    {"type": "node", "id": 4, "tags": {"amenity": "pharmacy", "name": "No Coords"}},                            # no coordinates
    {"type": "node", "id": 5, "lat": 50.0, "lon": 5.0, "tags": {"amenity": "pharmacy", "name": "Elsewhere"}},   # outside box
    {"type": "node", "id": 1, "lat": 11.0, "lon": 76.9, "tags": {"amenity": "pharmacy", "name": "Example Medicals"}},  # duplicate id
]


def test_parse_marks_everything_unverified_with_attribution():
    recs, stats = osm.parse_elements(ELEMENTS, BBOX)
    assert [r["source_id"] for r in recs] == ["node/1", "way/2"]
    assert all(r["listing_status"] == "osm_unverified" and r["source"] == osm.SOURCE and r["is_claimed"] is False for r in recs)
    assert (stats["no_name"], stats["no_coords"], stats["outside_bbox"]) == (1, 1, 1)
    assert recs[1]["lat"] == 11.01 and recs[1]["country"] == "India" and "Test Road" in recs[0]["address"]


@pytest.mark.parametrize("bad", ["1,2,3", "a,b,c,d", "11,77,10,76", "0,0,50,50", "100,0,101,1"])
def test_bbox_validation(bad):
    with pytest.raises(ValueError):
        osm.parse_bbox(bad)


def test_fetch_uses_overpass_query_and_store_is_idempotent(isolated_db):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content.decode()
        return httpx.Response(200, json={"elements": ELEMENTS})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            recs, _ = osm.parse_elements(await osm.fetch(BBOX, client=c), BBOX)
        first = await osm.store(recs)
        second = await osm.store(recs)
        return first, second, await isolated_db.query("pharmacies", limit=10)
    first, second, rows = asyncio.run(scenario())
    assert "amenity" in seen["body"] and "pharmacy" in seen["body"]
    assert first == (2, 0) and second == (0, 2) and len(rows) == 2


def test_nearby_shows_not_rated_instead_of_a_default_score(client, isolated_db):
    recs, _ = osm.parse_elements(ELEMENTS, BBOX)
    asyncio.run(osm.store(recs))
    r = client.get("/api/v1/pharmacies/nearby", params={"lat": 11.0, "lng": 76.9, "radius": 5000})
    assert r.status_code == 200, r.text
    items = r.json()["pharmacies"]
    assert items and all(p["trust_score"] is None and p["rating_status"] == "not_rated" for p in items)  # no reviews: no score
    assert all(p["listing_status"] == "osm_unverified" for p in items)


def test_osm_listing_cannot_become_verified_without_the_claim_flow(client, isolated_db):
    asyncio.run(osm.store(osm.parse_elements(ELEMENTS, BBOX)[0]))
    pid = asyncio.run(isolated_db.query("pharmacies", limit=1))[0]["id"]
    assert client.put(f"/api/v1/pharmacies/{pid}/inventory", json=[{"name": "x"}], headers=auth("ph1", "pharmacist")).status_code == 403
    assert client.post(f"/api/v1/pharmacies/{pid}/verify-claim", headers=auth("reg", "regulator")).status_code == 400  # no pending claim


# ── brands ──
def run_brands(tmp_path, body):
    src, out = tmp_path / "b.csv", tmp_path / "lasa.json"
    src.write_text("brand_name,generic_name,source\n" + body)
    p = subprocess.run([sys.executable, "-m", "scripts.import_brands", str(src), "--out", str(out)], cwd=BACKEND, capture_output=True, text=True, timeout=60)
    return p, (json.loads(out.read_text()) if out.exists() else [])


def test_brand_import_requires_a_source(tmp_path):
    p, data = run_brands(tmp_path, "Examplin,Exampleamide,Vendor list 2026\nNoSource,Whatever,\n")
    assert p.returncode == 1 and "source is required" in p.stderr and [d["name"] for d in data] == ["Examplin"]


def test_brand_import_is_idempotent_and_feeds_lasa(tmp_path, monkeypatch):
    run_brands(tmp_path, "Examplin,Exampleamide,Vendor list 2026\n")
    _, data = run_brands(tmp_path, "Examplin,Exampleamide,Vendor list 2026\nExamplyn,Otherazole,Vendor list 2026\n")
    assert len(data) == 2
    from services import lasa
    entries = tuple(lasa.Entry(d["name"], d["generic"], d["source"]) for d in data)
    monkeypatch.setattr(lasa, "corpus", lambda: entries)
    lasa._index.cache_clear()
    r = lasa.check_name("Examplin")
    assert any(w["similar_name"] == "Examplyn" for w in r["warnings"])


def test_lasa_ignores_description_like_registry_rows():
    from services.lasa import plausible_name
    assert plausible_name("Metformin") and plausible_name("Dolo 650")
    assert not plausible_name("Sulta micillin(as Tosylate) 375mg eq. Sulbactam 147.0 mg + Ampicillin 220 mg Film coated tablets.")


# ── community rating (replaces the review-count "trust index") ──
def _pharmacy_with_ratings(client, ratings):
    pid = client.post("/api/v1/pharmacies/register", params={"name": "RatedMeds", "address": "x", "lat": 11.0, "lng": 76.9}, headers=auth("owner")).json()["pharmacy"]["id"]
    for i, stars in enumerate(ratings):
        r = client.post(f"/api/v1/pharmacies/{pid}/review", json={"rating": stars, "comment": f"Visit number {i} experience"}, headers=auth(f"rev{i}"))
        assert r.status_code == 200, r.text
    return pid


def _rating(client, pid):
    from services.cache_manager import get_cache
    asyncio.run(get_cache().delete(f"trust_score:{pid}")) if hasattr(get_cache(), "delete") else None
    return client.get(f"/api/v1/pharmacies/{pid}/trust-score").json()


def test_rating_uses_stars_not_review_count(client):
    many_bad = _rating(client, _pharmacy_with_ratings(client, [1] * 6))
    few_good = _rating(client, _pharmacy_with_ratings(client, [5, 5, 5]))
    assert many_bad["trust_score"] is not None and few_good["trust_score"] is not None
    assert many_bad["trust_score"] < 35 < few_good["trust_score"], (many_bad, few_good)  # old formula ranked these the other way round


def test_one_glowing_review_is_not_enough_for_a_score(client):
    r = _rating(client, _pharmacy_with_ratings(client, [5]))
    assert r["trust_score"] is None and r["rating_status"] == "not_enough_reviews" and r["review_count"] == 1
