"""Go-live readiness check: tells you, in plain words, what is still dummy or unsafe.

    python -m scripts.doctor            # human-readable
    python -m scripts.doctor --json     # for CI
    python -m scripts.doctor --ping-db  # also test the Supabase connection (needs network)

Exit code 1 if any BLOCKER is found. Makes no network calls unless --ping-db is given.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BLOCKER, WARN, INFO, OK = "BLOCKER", "WARN", "INFO", "OK"
STALE_AFTER_DAYS = 70  # CDSCO publishes monthly; allow for publication delay


@dataclass
class Check:
    level: str
    area: str
    message: str
    fix: str = ""


def run_checks(settings: Any, index: Any, lasa_entries: int, *, today: date | None = None) -> list[Check]:
    today = today or date.today()
    strict = settings.is_strict
    out: list[Check] = []

    def add(level: str, area: str, message: str, fix: str = "") -> None:
        out.append(Check(level, area, message, fix))

    # Data stores
    if settings.supabase_url and settings.supabase_key:
        add(OK, "database", "Supabase is configured.")
    else:
        add(BLOCKER if strict else WARN, "database",
            "No Supabase configured: data goes to a local file that is not shared or durable.",
            "Set SUPABASE_URL and SUPABASE_KEY, then run the migrations in docs/DEPLOYMENT.md (including phase 6).")
    if settings.allow_local_fallback_writes and strict:
        add(BLOCKER, "database", "ALLOW_LOCAL_FALLBACK_WRITES is on: failed writes are silently kept in a local file.", "Set it to false.")
    if settings.rate_limit_storage_uri or settings.redis_url:
        add(OK, "rate limiting", "Shared rate-limit storage is configured.")
    else:
        add(WARN if strict else INFO, "rate limiting", "Rate limits are per-process memory (not shared across workers).", "Set RATE_LIMIT_STORAGE_URI=redis://...")
    if strict and any("localhost" in o or "127.0.0.1" in o for o in settings.cors_origins):
        add(WARN, "cors", "CORS allows localhost origins in a strict environment.", "List only your real front-end origin(s).")

    # Regulator alerts: the single most important real-data item
    cov = index.coverage()
    if cov["status"] == "unavailable":
        add(WARN, "batch alerts", "No regulator alert data loaded: batches are NOT being checked.",
            "Import a reviewed month with scripts/import_regulator_alerts.py (docs/RUNBOOK.md).")
    elif cov["is_sample_data"]:
        add(BLOCKER if strict else WARN, "batch alerts", "Alert data is SAMPLE (fake) data.", "Replace it with reviewed real data.")
    else:
        latest = cov["latest_month"]
        y, m = (int(x) for x in latest.split("-"))
        age_days = (today - date(y, m, 1)).days
        if age_days > STALE_AFTER_DAYS + 31:
            add(WARN, "batch alerts", f"Newest alert month is {latest} ({age_days} days old).", "Import the latest CDSCO month.")
        else:
            add(OK, "batch alerts", f"{cov['records']} real alerts loaded, newest month {latest}.")

    from services.price_check import get_index as price_index
    pcov = price_index().coverage()
    if pcov["status"] == "unavailable":
        add(INFO, "price check", "No NPPA ceiling-price data loaded: printed MRPs are not checked.",
            "Import a reviewed notification with scripts/import_nppa_ceiling_prices.py.")
    elif pcov["is_sample_data"]:
        add(BLOCKER if strict else WARN, "price check", "Ceiling-price data is SAMPLE (fake) data.", "Replace it with reviewed NPPA data.")
    else:
        add(OK, "price check", f"{pcov['records']} ceiling prices loaded.")

    # Look-alike name coverage
    if lasa_entries < 500:
        add(WARN, "name warnings", f"Look-alike/sound-alike checks cover only {lasa_entries} names.",
            "Load a licensed or curated brand list with scripts/import_brands.py.")
    else:
        add(OK, "name warnings", f"{lasa_entries} names loaded for look-alike checks.")

    # Capabilities
    if settings.manufacturer_verification_url:
        add(OK, "serial verification", "Manufacturer serial verification is configured.")
    else:
        add(INFO, "serial verification", "No serial-verification partner: 'authentic'/'counterfeit' verdicts are unavailable by design.",
            "Needs a manufacturer/distributor API (MANUFACTURER_VERIFICATION_URL).")
    if settings.groq_api_key or settings.openrouter_api_key or settings.gemini_api_key:
        add(OK, "ai", "At least one AI provider key is set (outputs stay labelled AI-generated).")
    else:
        add(INFO, "ai", "No AI key: photo analysis and AI explanations return 'unavailable'.", "Add GROQ_API_KEY (free tier available).")
    if strict and not settings.sentry_dsn:
        add(WARN, "monitoring", "No SENTRY_DSN: errors will go unnoticed.", "Create a Sentry project and set SENTRY_DSN.")
    if not settings.cron_secret:
        add(INFO, "cron", "CRON_SECRET empty: the refill-notification endpoint is disabled.")
    if not strict:
        add(INFO, "environment", f"ENVIRONMENT={settings.environment}: secrets may be ephemeral, so tokens will not survive a restart.")
    return out


def _lasa_entries() -> int:
    from services import lasa
    return len(lasa.corpus())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ping-db", action="store_true")
    args = ap.parse_args()

    try:
        from config import get_settings
        settings = get_settings()
    except ValueError as exc:  # strict validation failed
        checks = [Check(BLOCKER, "configuration", str(exc), "Fix the listed settings (see backend/.env.example).")]
    else:
        from services.batch_alerts import get_index
        checks = run_checks(settings, get_index(), _lasa_entries())
        if args.ping_db and settings.supabase_url:
            import httpx
            try:
                r = httpx.get(f"{settings.supabase_url.rstrip('/')}/rest/v1/", headers={"apikey": settings.supabase_key}, timeout=8)
                checks.append(Check(OK if r.status_code < 400 else BLOCKER, "database", f"Supabase answered HTTP {r.status_code}."))
            except httpx.HTTPError as exc:
                checks.append(Check(BLOCKER, "database", f"Cannot reach Supabase: {exc!r}"))

    if args.json:
        print(json.dumps([asdict(c) for c in checks], indent=2))
    else:
        for level in (BLOCKER, WARN, INFO, OK):
            for c in (x for x in checks if x.level == level):
                print(f"[{c.level:7}] {c.area}: {c.message}" + (f"\n          -> {c.fix}" if c.fix else ""))
        n = sum(c.level == BLOCKER for c in checks)
        print(f"\n{n} blocker(s)." if n else "\nNo blockers.")
    return 1 if any(c.level == BLOCKER for c in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
