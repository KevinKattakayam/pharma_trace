# PharmaTrace

Medicine verification and safety tools for India and global users: scan a pack's barcode, GS1
DataMatrix or India GSR 823(E) QR code, check it against registries, recalls and regulator
quality alerts, and spot label inconsistencies that copied codes leave behind.

> **What PharmaTrace can and cannot tell you.** A barcode, registry, OCR or AI result shows that a
> *record exists* or that a *label is internally consistent*. It never proves that the physical pack
> in your hand is genuine. Only an authoritative manufacturer/distributor serial check (an optional
> integration, not configured by default) can return `authentic` or `counterfeit`. Nothing here is a
> diagnosis, prescription or dosing instruction. If in doubt, do not use the medicine and ask a
> pharmacist. See [docs/SAFETY.md](docs/SAFETY.md).

## What it does

| Capability | How it works | Limits |
|---|---|---|
| Barcode / QR verification | Parses GTIN/EAN/UPC, NDC, GS1 (bracketed, raw, Digital Link) and GSR 823(E) QR; looks up openFDA and a bundled CDSCO dataset; checks openFDA and CDSCO recalls | Bundled CDSCO data = 2,255 approved molecules + 87 brand mappings, not a full brand/licence register |
| **Pack Check** | Compares what the code encodes with the printed batch/expiry/mfg date; date logic; regulator alerts | Consistency only; a fully copied label passes |
| **Batch-level regulator alerts** | Matches batch **and** product against loaded CDSCO NSQ/spurious alerts | Needs alert data imported via a reviewed CSV; ships with **sample data only** |
| **Look-alike/sound-alike warnings** | Flags names close to registered names with different ingredients | Bundled corpus is ~257 usable names; load a licensed brand list (`scripts/import_brands.py`) for real coverage |
| Verdicts with reasons | `unknown` (record match only), `suspicious` (+ reason codes), `authentic`/`counterfeit` (serial check only) | `requires_human_review` is true unless serial-verified |
| **Pharmacy map** | Real OpenStreetMap locations (via `scripts/import_osm_pharmacies.py`) shown as *unverified*; community star rating only with 3+ reviews; "verified" only after a regulator approves a pharmacist's licence claim | A listing says a place exists, not that its stock is genuine |
| **Price check (India)** | Compares the printed MRP with NPPA's notified ceiling price for scheduled (essential) medicines | Needs reviewed NPPA data; unlisted medicines return "no limit set", not "fine" |
| Interactions, side effects, generics, cabinet, caregiver, clinic dashboards, PvPI ADR prefill, adverse events (FAERS), cold-chain context, offline PWA | See API docs | AI output is labelled and requires review |
| Tamper-evident audit trail | SHA-256 hash chain; DB-side serialised append; append-only triggers | Tamper-*evident*, not immutable (see ADR-0003) |

## Quick start

```bash
# Containers (API + web + Redis)
cp backend/.env.example backend/.env
docker compose up --build            # web: http://localhost:8080, API docs: /api/docs

# Or locally
make setup && make test
cd backend && ./venv/bin/uvicorn main:app --reload      # http://127.0.0.1:8000/api/docs
cd frontend && npm run dev                               # http://localhost:5173
```

With no `SUPABASE_URL`, the API uses a local SQLite store and generates ephemeral secrets (dev only).
Staging/prod refuse to start without strong secrets: see [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Architecture

FastAPI backend (Python 3.12) · React 19 + Vite PWA · Supabase/PostgreSQL (PostGIS) · optional Redis.
Diagrams and data flows: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Quality (measured on the `upgrade/enterprise` branch)

Backend: 122 tests; Ruff clean on all rewritten modules (legacy debt ratcheted); Bandit 0 medium+;
pip-audit 0 known vulnerabilities. Frontend: Vitest, ESLint 0 errors, `npm audit` (production) 0.
Exact figures and what was *not* measured: [docs/FINAL_REPORT.md](docs/FINAL_REPORT.md).

## Documentation

[Data sources & free keys](docs/DATA_SOURCES.md) · [Audit](docs/AUDIT.md) · [Final report](docs/FINAL_REPORT.md) · [Feature proposals](docs/FEATURE_PROPOSALS.md) ·
[Safety](docs/SAFETY.md) · [Architecture](docs/ARCHITECTURE.md) · [Deployment](docs/DEPLOYMENT.md) ·
[Runbook](docs/RUNBOOK.md) · [Privacy & compliance](docs/PRIVACY.md) · [API changes](docs/API_CHANGES.md) ·
[ADRs](docs/adr/) · [Security policy](SECURITY.md) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md)

## Licence

MIT (see `LICENSE`). Third-party data (openFDA, CDSCO publications, DrugBank) carries its own terms.
