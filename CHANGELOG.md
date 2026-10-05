# Changelog

All notable changes to this project are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); the project uses semantic versioning.

## [Unreleased] — `upgrade/enterprise`

### Phase 0 — Audit
- Added `docs/AUDIT.md`: 50+ findings with file:line and severity, nine critical/high
  defects reproduced by running the application.

### Phase 1: Fix and harden (security, safety, reliability)
#### Security
- Pharmacies: register/claim/approve/inventory/review now require auth and roles; claimants cannot self-approve; one review per user (S1).
- Offline sync and batch-audit require auth; client verdicts are stored as `unverified_client_claim` (S2).
- Reporter IDs are random tokens, not HMAC(IP) under a public key (S3).
- Rate limiting keyed by verified JWT subject or a keyed client pseudonym; Redis storage supported (S4, S5).
- History, verification lookup and refill schedule scoped to the caller (S6); audit endpoints require auditor/regulator (S10).
- Clinic: admin-only creation with bcrypt, constant-cost login, rate limited, tokens with `sub`/`role` (S7, S8, R8).
- Cron secret moved to `X-Cron-Secret` header, constant-time compare (S9).
- Secure-by-default config: no default secrets, `debug` off, strict validation in staging/prod (S11, ADR-0001).
- openFDA query escaping (S12); validated `GeoPoint` (S13); server-authoritative audit time (S14); no shared anonymous cabinet (S15); rate limits on AI endpoints (S16); Sentry PII scrubbing (S18).
- Security headers and pure-ASGI middleware; client IP removed from the request scope.
#### Patient safety
- Recall merge: an active recall from any source is never hidden; unknown is `inconclusive` (P1). New `recall_status` field.
- Verdicts require concrete negative evidence and include `verdict_reasons` (P2, ADR-0004).
- Batch verification fixed; processing errors no longer counted as failures (P3).
- Image verification `NameError` fixed (P4).
- GS1 parser rewritten (HRI, element string, Digital Link; DD=00; check digits). India QR parser corrected to the eight GSR 823(E) particulars (licence, not MRP).
#### Reliability & data integrity
- Audit chain on `audit_chain` with canonical hashing, advisory-locked DB append, fork-proof constraint, append-only triggers (R1, R6, ADR-0003).
- Missing `asyncio` import fixed; cloud DB failures fail closed instead of silently writing locally; row-level local store with write lock (R2, R7, R9).
- `/health` returns a body; new `/ready`; Docker healthcheck checks status (R5).
- Bounded TTL caches; supervised background tasks drained on shutdown; bare excepts removed (R10–R12).
#### Tooling
- Declared all runtime deps (slowapi, groq, rapidfuzz, limits, bcrypt); removed unused scikit-learn and unmaintained passlib; optional/scripts/dev requirement files.
- 119 tests (was 6). Ruff (zero issues in rewritten modules, ratchet baseline 187 for legacy), Bandit (0 medium+), pip-audit (0 known vulns).
- `.env.example` added.

### Phase 2: Module upgrades (frontend & integration)
- Token storage: non-extractable AES-GCM key in IndexedDB; plaintext `localStorage` token removed and migrated (S19).
- Clinic dashboard: credential sign-in replaces "enter a clinic ID" access (anyone with an ID could open a dashboard).
- Fixed browser `ReferenceError` (`process.env` in `useVoice.js`), duplicate `identifyPill`, swallowed errors, invalid regex escapes.
- New `SafetyIntelPanel` on verification results: plain-language verdict reasons, recall status, label findings, alert coverage, LASA warnings.
- CSP shipped as `Report-Only` (safe rollout), HSTS, Permissions-Policy; removed deprecated `X-XSS-Protection`.
- Vitest + ESLint (0 errors); `npm audit` production: 0 vulnerabilities (was 4: dompurify, fflate, react-router).

### Phase 3: Safety intelligence features
- `POST /safety/pack-check`, `GET /safety/batch-alerts`, `GET /safety/batch-alerts/coverage`, `POST /safety/lasa-check`.
- Integrated into `/verify/barcode` (`pack_check`, `batch_alerts`, `lasa` fields) and a new `/pack-check` page.

### Phase 4: Quality, DevOps, docs
- Multi-stage API image (non-root, working healthcheck), nginx web image, read-only compose stack with Redis; `LOCAL_STORE_PATH` for writable volumes.
- CI: strict lint, ratchet, tests, ≥80 % coverage gate on safety-critical modules, eval smoke, pip-audit, Bandit, prod-config check, ESLint, Vitest, build, npm audit, gitleaks, Trivy, container smoke test.
- Load test script; fixed LASA hot path found by it (46 → 294 req/s).
- Eval harness scaffold and reviewed-CSV regulator alert importer.
- Consolidated docs: README (claims match code), SAFETY, ARCHITECTURE, DEPLOYMENT, RUNBOOK, PRIVACY, API_CHANGES, SECURITY, CONTRIBUTING, FINAL_REPORT. Removed 5 overlapping guides, 7 deploy scripts, duplicate `railway.toml`, committed PDFs and runtime DB.
- `RATE_LIMIT_ENABLED` ops switch.
