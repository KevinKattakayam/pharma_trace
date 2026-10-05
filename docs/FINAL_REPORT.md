# Final report: `upgrade/enterprise`

Every number below was produced by running the tool in this environment (Python 3.12, Node 22, **1 CPU core**). Anything not measured is marked as such. Nothing was estimated.

## 1. Before / after

| Metric | Before (`3a9e485`) | After |
|---|---|---|
| Fresh `pip install -r requirements.txt` → app starts | **No** (missing slowapi, groq, rapidfuzz) | Yes; a test enforces declared deps |
| `/api/v1/health` | `200 null` (function had no return) | `200 {"status":"ok",…}` + `/ready` |
| Audit records persisted in production | **No** (wrong table; silently diverted; fake hash returned) | Yes, `audit_chain` + DB-side serialised append; failures reported |
| Batch verification | **100 % of items failed**, false ">15 % failure" alarm | Works; errors not counted as failures |
| Unauthenticated "verified pharmacy" creation | **Possible** | Blocked (regulator approval, no self-approval) |
| Unauthenticated audit-chain writes | **Possible** | Blocked; client verdicts stored as claims |
| Scans labelled "suspicious" without negative evidence | **All of them** | None; every `suspicious` carries reason codes |
| GS1 bracketed codes parsed correctly | **No** (GTIN off by one) | Yes (HRI, element string, Digital Link) |
| Backend tests | 6 | **122** passing |
| Coverage | not measured | 38 % overall · **78 %** rewritten modules · **92 %** safety-critical (CI gate ≥ 80 %) |
| Ruff | not configured | **0** on rewritten modules; legacy 187 (ratchet: may only fall) |
| Bandit (medium+) | not run | **0** (3 fixed: XML parsing, 2 hash usages) |
| pip-audit (runtime) | not run | **0** known vulnerabilities |
| Frontend tests / ESLint errors | 0 / not configured | 5 passing / **0** errors (72 legacy warnings) |
| `npm audit` (production deps) | **4** (2 high: react-router; dompurify, fflate) | **0** |
| Browser runtime bugs found by lint | — | `process.env` ReferenceError (voice), duplicate method, swallowed errors |

## 2. Load test

`scripts/loadtest.py`, 1 uvicorn worker on **1 CPU core**, 1,000 requests per endpoint, 25 concurrent clients, rate limiter disabled for the run. Endpoints that call openFDA/CDSCO were **not** load-tested because the sandbox blocks external APIs; their latency in production is dominated by upstream response times and must be measured in staging.

| Endpoint | Errors | Req/s | p50 ms | **p95 ms** | p99 ms |
|---|---|---|---|---|---|
| GET /health | 0 | 405.6 | 42.9 | **153.9** | 244.2 |
| POST /safety/pack-check | 0 | 350.9 | 53.9 | **173.6** | 248.4 |
| GET /safety/batch-alerts | 0 | 399.6 | 44.1 | **165.8** | 247.2 |
| POST /barcode/parse-gs1 | 0 | 369.5 | 46.0 | **176.7** | 263.3 |
| POST /safety/lasa-check (before fix) | 0 | 46.5 | 532.9 | 571.5 | 602.4 |
| POST /safety/lasa-check (after fix) | 0 | **294.2** | 61.1 | **202.5** | 280.3 |

Server-side handling is ~2.5 ms per request; the rest is queueing on one core. The test found a real defect (O(n) regex per LASA call, blocking the event loop), now fixed: 6.4× throughput.

## 3. Not measured here (and why)

| Item | Status |
|---|---|
| Lighthouse score | **Not measured**: no browser available in the sandbox. Run `npx lighthouse http://localhost:8080 --view` after `docker compose up`. |
| Container build, Trivy scan, gitleaks | **Not run**: no container runtime. Configured in `.github/workflows/ci.yml` and will run on first push. |
| `phase5_audit_chain.sql` against PostgreSQL | **Now tested** on a real PostgreSQL 16 (see Update below). PostGIS-dependent SQL (location trigger, `nearby_*` RPCs) remains untested offline: verify on Supabase. |
| Load test of registry-backed verification | Not possible offline; see §2. |

## 4. What was built

* **Phase 0:** `docs/AUDIT.md`, 50+ findings, nine critical/high reproduced live.
* **Phase 1:** all critical/high findings fixed (CHANGELOG lists each with its audit ID); ADRs 0001–0004.
* **Phase 2:** frontend token storage, clinic sign-in, results panel, CSP (report-only), lint/test tooling; eval harness scaffold (`backend/eval/`, 4 synthetic smoke cases, **no benchmark results claimed**).
* **Phase 3:** `docs/FEATURE_PROPOSALS.md` (22 ideas, 3 rejected on safety grounds); built **Pack Check**, **batch-level regulator alerts** and the **LASA guard** (backend, API, UI, tests, flags), ADR-0005.
* **Phase 4:** multi-stage images, read-only compose stack with Redis, CI (lint, ratchet, tests, coverage gate, eval smoke, pip-audit, Bandit, prod-config check, ESLint, Vitest, build, npm audit, gitleaks, Trivy, container smoke test), Makefile, consolidated docs.

## 5. Requires human action

| # | Action | Why | What's ready |
|---|---|---|---|
| 1 | **Clinical safety officer sign-off on ADR-0004** | Verdict semantics changed (clean record match → `unknown`) | ADR, tests for every reason code |
| 2 | **Real CDSCO alert data** with second-person review each month | Batch alerts ship with SAMPLE data only | Importer with row validation, coverage endpoint, UI sample warning, RUNBOOK |
| 3 | **Licensed or curated brand-name corpus** | LASA reach is limited: bundled registry has 87 brands; plain Amoxicillin/Ampicillin are absent | `data/lasa_curated.json` loader; thresholds configurable |
| 4 | **Manufacturer/distributor serial-verification partner** | Only source of `authentic`/`counterfeit` | `MANUFACTURER_VERIFICATION_URL` adapter; tests mock it |
| 5 | **Schedule H2 (top-300) brand list** | To say *whether* GSR 823(E) particulars are mandatory for a pack | Pack Check reports missing particulars conditionally |
| 6 | **Labelled, consented evaluation dataset** (pharmacist-reviewed) | No accuracy figure may be claimed without it | Harness + schema; refuses synthetic data without a flag |
| 7 | **Privacy review** (DPDP/GDPR): notice, consent, rights, retention, DPAs | Legal requirement | `docs/PRIVACY.md` data map and open items |
| 8 | **Run phase-5 migration on staging Postgres** | Not executable here | Idempotent SQL |
| 9 | **Rotate any secrets** that were ever in `.env` files or git history | Previous defaults were public | Strict config refuses public values |
| 10 | Set a real security contact in `SECURITY.md` | Disclosure channel | Policy text |

## 6. Remaining risks and deferred work

* **Legacy modules** (interactions, symptom graph, vision, vernacular resolver, caregiver, cabinet, reports) were fixed only where they touched auth, safety or data integrity. They hold most of the 187 legacy lint issues (96 blind `except Exception`) and drive the 38 % overall coverage. Next step: pay these down module by module (the ratchet enforces direction).
* **Symptom → OTC suggestions** remain enabled with strong labelling; consider disabling (`/verify/symptom-safety`) pending clinical review.
* **Supabase service-role key bypasses RLS**; tenant isolation is enforced in application code (tested). Moving to per-user Supabase JWTs is recommended.
* **Dev-only npm advisories** (Vite dev server) need a breaking major upgrade; production bundle unaffected.
* **CSP is report-only** until reports confirm Tesseract/Leaflet sources.
* **72 ESLint warnings** (unused variables) in legacy pages.

## 7. How to run everything

```bash
# Backend
cd backend && python3.12 -m venv venv && ./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest --cov=.                       # 122 tests
./venv/bin/ruff check $(cat ../.strict-lint-paths) && ../scripts/lint_ratchet.sh
./venv/bin/bandit -q -r . -x ./tests,./venv -ll && ./venv/bin/pip-audit -r requirements.txt
./venv/bin/python -m eval.run_eval eval/cases.synthetic.json --allow-synthetic   # smoke, not a benchmark
cp .env.example .env && ./venv/bin/uvicorn main:app --reload                      # http://127.0.0.1:8000/api/docs
./venv/bin/python -m scripts.loadtest --base http://127.0.0.1:8000                # needs RATE_LIMIT_ENABLED=false

# Frontend
cd frontend && npm ci && npm test && npx eslint src --quiet && npm run build && npm run dev

# Everything in containers
cp backend/.env.example backend/.env && docker compose up --build                  # http://localhost:8080
```


## 9. Update: free data sources, price check, copy and UI

Measured after this update: **188 backend tests**, **19 frontend tests**, coverage 45 % overall / **92 %** safety-critical, Ruff 0 strict (legacy 185), Bandit 0, pip-audit 0, ESLint 0 errors, `npm audit` (production) 0.

* **New free-data feature**: NPPA ceiling-price check (`/safety/price-check`, Pack Check integration, `/price-check` page). 21 tests cover the arithmetic (ceiling × units × GST), the 2 % tolerance, refusal to match a different strength or form, "needs confirmation" instead of accusation on near matches, and that an overcharge never changes the authenticity verdict.
* **`docs/DATA_SOURCES.md`** lists every free source and key, with licence rules (ODbL attribution, Overpass/Nominatim rate limits, NPPA prices being per-unit and ex-GST) and a suggested order of work.
* **Copy and UI**: plain-language copy centralised in `utils/copy.js` and enforced by a test that fails on jargon; typography scale and spacing tokens; shared `PageHeader`/`ScopeNotice`; form fields with visible labels, 16px inputs, 44px targets, focus rings, reduced-motion support.
* **Not verified**: real NPPA/CDSCO documents (sample data only), and no browser has rendered the new pages.

## 8. Update: replacing dummy things with real ones

Measured after this update (same environment): **167 backend tests** (was 122), **12 frontend tests** (was 5), coverage 43 % overall / **92 %** on safety-critical modules, Ruff 0 on strict modules (legacy 185, ratchet lowered from 187), Bandit 0 medium+, pip-audit 0, `npm audit` (production) 0, ESLint 0 errors.

**Real PostgreSQL testing** (`pgserver`, PostgreSQL 16): the audit-chain migration is idempotent, DB-computed hashes equal Python's (including Hindi/Unicode), edits/deletes/truncate/forks are blocked, 8 concurrent connections produce one valid 40-record chain, and the legacy table upgrades. A **schema-contract test** then found ten real defects that the old silent local fallback had been hiding (docs/AUDIT.md §5), including a **stored XSS** in the map, a base migration that fails on a fresh database, five missing tables, missing columns on `verifications`/`pharmacies`, a map that could not find any pharmacy, and a pharmacy "Trust Index" that ignored star ratings and defaulted to 100/100. All fixed and tested.

**Corrections to earlier statements:** the look-alike corpus has **257** usable names, not ~2,300 (about 2,000 bundled "names" were product descriptions); the pharmacy "trust index" never measured trust.

| Dummy item | Now | Still needs |
|---|---|---|
| Regulator alerts (3 fake records) | PDF→draft extractor, importer that **rejects unreviewed rows**, API refuses sample data in staging/prod | A person to review each month's rows against CDSCO's PDF |
| Pharmacies (empty map) | Real OpenStreetMap importer (unverified, ODbL attribution), honest rating, XSS fixed | Running the importer for your area; real "verified" status needs pharmacist claims + regulator approval |
| Brand names (87) | `import_brands.py` (source required) | A product list you are licensed to use |
| "Is it ready?" | `scripts/doctor.py` lists what is dummy/unsafe, exit 1 on blockers | Fixing what it reports |
| Database | Migrations tested; phase 6 aligns schema | Running them on Supabase; verifying the PostGIS trigger there |
| `authentic`/`counterfeit` | unchanged | A manufacturer serial-verification partner |
| AI | unchanged | A (free) Groq API key |

**Not verified by me:** PostGIS behaviour (trigger, `nearby_*`), the OSM importer against the live Overpass service (tested with a synthetic response in the Overpass format), the PDF extractor against real CDSCO PDFs (tested with synthetic PDFs in the two layouts seen in public extracts; real months will differ), any browser rendering of the changed pages.
