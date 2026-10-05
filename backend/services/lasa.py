"""Look-alike / sound-alike (LASA) medicine-name guard.

Problem: in India many brand names differ by a letter or sound alike yet contain different
molecules; prescriptions usually carry brand names only. This app's own fuzzy resolver can
silently map a typed or OCR'd name to a similar-but-different drug (audit P6).

This module never invents confusable pairs. It compares the queried name against the names
that are actually in the loaded registries (bundled CDSCO brand mappings and approved
molecules, plus an optional operator-curated JSON list) and warns only when a close name maps
to a *different* active-ingredient set. Output is a warning to confirm the exact name; it
never changes a verdict or a dose.

Similarity = orthographic (ratio ≥ 84 OR length-aware edit distance) OR phonetic (a simple English/Indian-English
consonant skeleton). Thresholds were chosen conservatively and are NOT clinically validated;
they are configurable and covered by tests.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import structlog
from rapidfuzz import fuzz, process
from rapidfuzz.distance import Levenshtein

logger = structlog.get_logger()

DATA_DIR = Path(__file__).parent.parent / "data"
REGISTRY_DB = DATA_DIR / "cdsco_registry.db"
CURATED_FILE = DATA_DIR / "lasa_curated.json"  # optional, operator-maintained, see docs
ORTHO_THRESHOLD = 84
PREFILTER_THRESHOLD = 60


def max_edits(name: str) -> int:
    """Length-aware tolerance: one letter matters most in short names (e.g. Medzol/Metzol = 83%)."""
    n = len(name.replace(" ", ""))
    return 1 if n <= 6 else 2 if n <= 12 else 3
PHONETIC_MIN_LEN = 4

_PHONETIC_RULES = [
    (r"ph", "f"), (r"ck", "k"), (r"q", "k"), (r"c(?=[eiy])", "s"), (r"c", "k"), (r"x", "ks"),
    (r"z", "s"), (r"gh", "g"), (r"th", "t"), (r"w", "v"), (r"y", "i"), (r"([a-z])\1+", r"\1"),
]


def _clean(name: str) -> str:
    name = re.sub(r"\b\d+(\.\d+)?\s*(mg|mcg|g|ml|iu|%)?\b", " ", name.lower())
    name = re.sub(r"\b(tab|tabs|tablet|tablets|cap|caps|capsule|syrup|inj|injection|forte|plus|ds|sr|er|xr|cr|od|mr)\b", " ", name)
    return re.sub(r"[^a-z ]", "", re.sub(r"\s+", " ", name)).strip()


def plausible_name(name: str) -> bool:
    """Registry rows sometimes hold whole product descriptions ("... 375mg eq. Sulbactam 147.0 mg ... tablets").
    Those are not names a person reads off a pack, and they distort similarity matching."""
    return len(name) <= 60 and "(" not in name and sum(ch.isdigit() for ch in name) <= 3


def phonetic_key(name: str) -> str:
    s = _clean(name).replace(" ", "")
    for pattern, repl in _PHONETIC_RULES:
        s = re.sub(pattern, repl, s)
    return (s[:1] + re.sub(r"[aeiou]", "", s[1:])) if s else ""


def ingredient_set(generic: str | None) -> frozenset[str]:
    if not generic:
        return frozenset()
    parts = re.split(r"\s*(?:\+|,|;|/| and )\s*", generic.lower())
    return frozenset(p for p in (_clean(x) for x in parts) if p)


@dataclass(frozen=True)
class Entry:
    name: str
    generic: str
    source: str


@lru_cache(maxsize=1)
def corpus() -> tuple[Entry, ...]:
    entries: list[Entry] = []
    if REGISTRY_DB.exists():
        try:
            with sqlite3.connect(REGISTRY_DB) as conn:
                entries += [Entry(b, g, "cdsco_brand_mapping") for b, g in conn.execute("SELECT brand_name, generic_name FROM brand_mappings") if b and g]
                entries += [Entry(g, g, "cdsco_approved_molecule") for (g,) in conn.execute("SELECT generic_name FROM indian_drugs") if g and plausible_name(g)]
        except sqlite3.Error as exc:
            logger.warning("lasa_registry_unavailable", error=str(exc))
    if CURATED_FILE.exists():
        try:
            for row in json.loads(CURATED_FILE.read_text(encoding="utf-8")):
                entries.append(Entry(row["name"], row["generic"], row.get("source", "curated")))
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.error("lasa_curated_load_failed", error=str(exc))
    return tuple(entries)


@lru_cache(maxsize=1)
def _index() -> tuple[list[str], dict[str, list[int]]]:
    """Cleaned names and a phonetic-key → indices map, computed once per corpus."""
    entries = corpus()
    names = [_clean(e.name) for e in entries]
    by_key: dict[str, list[int]] = {}
    for i, e in enumerate(entries):
        by_key.setdefault(phonetic_key(e.name), []).append(i)
    return names, by_key


def check_name(name: str, generic_name: str | None = None, *, limit: int = 5) -> dict[str, Any]:
    entries = corpus()
    query = _clean(name)
    if len(query) < 3 or not entries:
        return {"query": name, "warnings": [], "corpus_size": len(entries), "status": "not_checked" if not entries else "too_short"}

    names, by_key = _index() if len(entries) == len(_index()[0]) else ([_clean(e.name) for e in entries], {})
    own = ingredient_set(generic_name)
    if not own:  # infer from an exact registry hit (uses precomputed names; was O(n) regex per call)
        hit = next((i for i, n in enumerate(names) if n == query), None)
        own = ingredient_set(entries[hit].generic) if hit is not None else frozenset()
    q_ph = phonetic_key(name)
    hits: dict[int, tuple[str, int]] = {}
    tolerance = max_edits(query)
    for _, score, idx in process.extract(query, names, scorer=fuzz.ratio, limit=40, score_cutoff=PREFILTER_THRESHOLD):
        if names[idx] != query and (score >= ORTHO_THRESHOLD or Levenshtein.distance(query, names[idx]) <= tolerance):
            hits[idx] = ("look-alike", int(score))
    if len(q_ph) >= PHONETIC_MIN_LEN:
        candidates = by_key.get(q_ph) if by_key else [i for i, e in enumerate(entries) if phonetic_key(e.name) == q_ph]
        for idx in candidates or []:
            if names[idx] != query and idx not in hits:
                hits[idx] = ("sound-alike", int(fuzz.ratio(query, names[idx])))

    warnings = []
    seen: set[tuple[str, frozenset[str]]] = set()
    for idx, (kind, score) in sorted(hits.items(), key=lambda kv: -kv[1][1]):
        e = entries[idx]
        theirs = ingredient_set(e.generic)
        if own and (not theirs or theirs == own):
            continue  # same molecule(s): not a LASA hazard
        key = (_clean(e.name), theirs)
        if key in seen:
            continue
        seen.add(key)
        warnings.append({
            "similar_name": e.name,
            "its_active_ingredients": e.generic,
            "kind": kind,
            "similarity": score,
            "source": e.source,
            "message": f"'{name}' {('looks' if kind == 'look-alike' else 'sounds')} like '{e.name}' ({e.generic}). "
                       "Confirm the exact name and strength on the prescription and pack.",
        })
        if len(warnings) >= limit:
            break
    return {
        "query": name,
        "assumed_active_ingredients": sorted(own) or None,
        "warnings": warnings,
        "status": "warnings" if warnings else "no_similar_names_found",
        "corpus_size": len(entries),
        "note": "Checked only against names in the loaded registries; absence of a warning is not a guarantee.",
    }
