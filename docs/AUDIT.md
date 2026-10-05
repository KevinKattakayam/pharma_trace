# PharmaTrace Security, Safety & Reliability Audit

| | |
|---|---|
| Audited revision | `3a9e485` (main, "changes made") |
| Branch for fixes | `upgrade/enterprise` |
| Method | Full read of backend services/routers/config, targeted read of frontend auth/storage, **live probing of the running app** with FastAPI `TestClient`, AST-based import and route analysis, SQL schema review |
| Severity scale | **Critical**: patient harm, audit loss, or unauthenticated privilege/data compromise reachable today. **High**: broken core feature or exploitable with modest effort. **Medium**: correctness/reliability risk under realistic conditions. **Low**: hygiene, maintainability. |

Every finding marked **[confirmed]** was reproduced by executing code; the rest are from code reading. Line numbers refer to the audited revision.

---

## 1. Headline findings

1. **The audit log never persists in production.** [confirmed] `repositories/entities.py:20` points `AuditRepository` at `safety_check_log`, a *medicine-cabinet* table (`supabase_migration.sql:201`) with `NOT NULL user_id, member_id`, `verdict BOOLEAN`, a random UUID key, and no hash columns. A correct `audit_chain` table exists (`supabase_migration.sql:140`) but is unused. Every insert is rejected by Postgres; `services/supabase.py:162` then silently writes to the container's ephemeral SQLite file; `services/audit.py:71` swallows any remaining error and returns a hash for a record that was never stored. Clients receive "proof" of an audit record that does not exist.
2. **All local-fallback database access crashes.** [confirmed] `services/supabase.py:71` calls `asyncio.to_thread` but `asyncio` is never imported → `NameError` on every query when Supabase is not configured (the default for local dev and the documented demo mode).
3. **Fresh installs cannot start.** [confirmed] `slowapi`, `groq`, `rapidfuzz` are imported unconditionally but absent from `requirements.txt`. `pdfplumber` (scripts) also missing; `redis`, `asyncpg`, `langfuse` are optional imports with no declared extra. `scikit-learn` is declared but never imported (~100 MB dead weight).
4. **A counterfeit seller can publish itself as a "verified pharmacy".** `routers/pharmacies.py:183` (register), `:222` (claim), `:257` (`verify-claim`, commented "admin-only" but unguarded) and `:284` (inventory) require no authentication. Any anonymous caller can create, claim, self-approve and publish "verified inventory" that the map shows to patients.
5. **Anyone can write arbitrary verdicts into the audit chain.** [confirmed] `POST /verify/offline-sync` (`routers/verify.py:648`) is unauthenticated and records client-supplied `verdict="authentic", confidence=100`. Its conflict check `verification_id != f"offline-{verification_id}"` (`:661`) is a tautology. `POST /verify/batch-audit` (`:630`) likewise accepts arbitrary payloads.
6. **Batch verification is 100 % broken and raises a false shipment alarm.** [confirmed] `routers/verify.py:571` calls `verify_barcode(req_model, user)` but the function signature is `(request, body, user)` and is wrapped by a rate-limit decorator that requires a real `Request`. Every item fails; the summary then reports *"High batch failure rate (>15%)"*, telling a health worker a shipment is bad because of a bug.
7. **Recall logic can drop an active recall.** `routers/verify.py:150-161`: (a) if the FDA source is down, CDSCO recalls are never appended; (b) if FDA *finds* a recall but CDSCO is unavailable, `no_recalls` becomes `None` ("inconclusive") instead of `False`, so the verdict is not `suspicious`. (c) `has_recall=not no_recalls` (`:308`) reports `True` when status is merely *unknown*. (d) CDSCO matching ignores the batch number already parsed from the QR (`:144` passes `batch_no=None`), contradicting CDSCO's own guidance that NSQ findings are batch-specific.
8. **Image verification crashes on its main path.** `routers/verify.py:360,369` use `lookup_indian_drug` and `resolve_drug_name`, which are only imported *inside* `verify_barcode` → `NameError` whenever OCR text is not an FDA hit.
9. **Every non-serialised scan is labelled "suspicious".** `compute_confidence` always returns `0.0` (correctly: there is no validated model), but `determine_verdict` still says `confidence < 50 → "suspicious"` (`services/confidence.py:27`). The documented `unknown/review` path is unreachable in production; the existing test only passes because it feeds `confidence=99`, a value the real pipeline never produces. Alarm fatigue is itself a safety risk, and home-page "counterfeits flagged" counts every scan.

## 2. Full findings register

### 2.1 Security & authorisation

| # | Sev | Location | Finding |
|---|---|---|---|
| S1 | Critical | `routers/pharmacies.py:183,222,257,284,302` | Unauthenticated register/claim/**approve**/inventory/review. See headline 4. |
| S2 | Critical | `routers/verify.py:630,648` | Unauthenticated writes of arbitrary verdicts into audit chain. [confirmed] |
| S3 | Critical | `config.py:65`, `services/anonymous.py:24`, `routers/push.py:48` | `hmac_daily_secret="default_secret_rotate_me"` is public. It keys the "anonymous" reporter ID = HMAC(IP), so IDs are reversible by enumerating IPv4 space; it also gates the cron push endpoint. |
| S4 | High | `services/limiter.py:12` | Rate-limit key read from JWT with `verify_signature=False`: attacker rotates forged `sub` values to get unlimited fresh buckets. |
| S5 | High | `main.py:160` | `IPStrippingMiddleware` is the outermost middleware, so the limiter sees every anonymous client as `127.0.0.1`: one abusive client exhausts the shared bucket for everyone (DoS). Limiter storage is in-process memory, so limits multiply by worker count and reset on deploy. |
| S6 | High | `routers/verify.py:642,703` | `/verify/history` and `/verify/{id}` unauthenticated: return all users' verifications incl. PostGIS location and clinic id. |
| S7 | High | `routers/clinic.py:90` | Unauthenticated clinic creation (no password set → account can never log in). |
| S8 | High | `routers/clinic.py:69` | On `ImportError`, password is compared to the stored *hash* in plaintext. passlib is unmaintained and incompatible with `bcrypt>=4.1`. |
| S9 | High | `routers/push.py:48` | Cron secret in query string (lands in access logs), non-constant-time compare. |
| S10 | High | `main.py:327-345` | `/audit/verify` and `/audit/log` unauthenticated (plus broken, see R3/R4). |
| S11 | Medium | `config.py:18,62` | `debug=True` by default; empty `JWT_SECRET` accepted when debug. PyJWT 2.15 rejects empty HMAC keys [confirmed], but `requirements.txt` allows `PyJWT>=2.8`; safety should not depend on library version. |
| S12 | Medium | `services/openfda.py:79,104,128,150` | User input interpolated unescaped into openFDA Lucene queries; a `"` lets callers rewrite the query and get wrong drug/recall data. |
| S13 | Medium | `routers/verify.py:259` | Unvalidated `location` dict interpolated into a WKT string. |
| S14 | Medium | `routers/verify.py:238` | Client-supplied `verified_at` stored as the audit timestamp → back-dating. |
| S15 | Medium | `routers/verify.py:428` | Anonymous image scans auto-saved to a shared `"anonymous"` cabinet. Cross-user privacy leak. |
| S16 | Medium | `routers/verify.py:494,532`; `routers/prescription.py:34`; `routers/voice.py:15` | Paid AI endpoints without rate limits → cost-exhaustion. |
| S17 | Medium | `services/supabase.py:88`, `repositories/base.py` | Backend uses the Supabase key as bearer; with the service-role key, RLS is bypassed, so the "zero-trust RLS" docstring claims are not true. `x-user-id` headers are advisory only. |
| S18 | Medium | `main.py:58` | Sentry `traces_sample_rate=1.0` and no PII scrubbing; health data can reach a third party. |
| S19 | Medium | `frontend/src/utils/api.js:393`, `hooks/useAuth.js:22` | JWT stored in plaintext `localStorage` *alongside* the "encrypted" IndexedDB copy, defeating it. `cryptoStorage.js:18` falls back to a constant entropy string; the derived key's salt lives next to the ciphertext. |
| S20 | Low | `frontend/vercel.json` | No Content-Security-Policy; `X-XSS-Protection` is deprecated. |

### 2.2 Patient safety & correctness

| # | Sev | Location | Finding |
|---|---|---|---|
| P1 | Critical | `routers/verify.py:150-161,308` | Recall merge bugs; see headline 7. |
| P2 | High | `services/confidence.py:27` | Unreachable `unknown` verdict; see headline 9. |
| P3 | High | `routers/verify.py:571` | Batch broken, false alarm; headline 6. [confirmed] |
| P4 | High | `routers/verify.py:360,369` | Image path `NameError`; headline 8. |
| P5 | High | `services/cdsco.py:197` | Recall check pulls 1,000 rows per scan and matches by name only; batch number ignored. |
| P6 | High | `services/supabase.py:268` + `services/drug_resolver.py` | Fuzzy name resolution (score ≥ 70) silently maps a typed name to a *different* similarly-named drug: a look-alike/sound-alike (LASA) error generator with no disambiguation step. |
| P7 | Medium | `routers/verify.py:288`, `services/vernacular_resolver.py:53` | Passive alias "learning" from unauthenticated traffic → alias-table poisoning; fire-and-forget tasks can be GC'd mid-flight. |
| P8 | Medium | `routers/verify.py:532` (`symptom_graph.py`) | Symptom → OTC suggestion borders on recommending treatment; must be labelled, cited, and never shown as advice. |
| P9 | Medium | `services/gtin.py:88` | Any JSON blob with a `Brand` key is a "valid CDSCO QR". GSR 823(E) QR codes are copyable; presence ≠ authenticity. |
| P10 | Low | README | "CDSCO registry match": the bundled DB is 2,255 molecule *approval* rows plus 87 hand-written brand mappings, not a brand/manufacturer licence register. |

### 2.3 Reliability, data integrity & observability

| # | Sev | Location | Finding |
|---|---|---|---|
| R1 | Critical | `repositories/entities.py:20` | Audit writes to wrong table; headline 1. |
| R2 | Critical | `services/supabase.py:71` | Missing `import asyncio`; headline 2. [confirmed] |
| R3 | High | `main.py:338` | `verify_chain()` not awaited → 500. [confirmed] |
| R4 | High | `main.py:343`, `routers/audit_export.py:33` | Import of non-existent `_audit_chain` → 500. [confirmed] |
| R5 | High | `main.py:198-245` | `health_check` has no `return` (its body was pasted after `capabilities()`'s return) → `/health` returns `null`. [confirmed] Docker `HEALTHCHECK` (`Dockerfile:28`) uses `httpx.get` without `raise_for_status`, so it passes even on 500. |
| R6 | High | `services/audit.py:22-69` | Read-latest-then-insert race forks the chain under concurrency; hash covers *all* `record_data` keys but `verify_chain` (`:97`) rebuilds only six, so any record with extra keys (`evidence`, `items`, …) can never verify. Ordering by UUID `id` is random. |
| R7 | High | `services/supabase.py:132,162,190,214` | When cloud is configured, any 4xx/5xx (constraint, RLS, outage) silently diverts writes to local SQLite → split-brain, silent loss on redeploy. |
| R8 | High | `routers/clinic.py:119,240`; `routers/audit_export.py:31` | `user.get(...)` on a Pydantic `CurrentUser` (or `None`) → `AttributeError` 500 for every caller. Clinic login token (`clinic.py:82`) lacks `sub`, so `get_current_user` rejects it: the clinic feature cannot authenticate at all. |
| R9 | Medium | `services/supabase.py:57-80` | Local store keeps each table as one JSON blob: read-modify-write races lose concurrent writes; O(n) per write. |
| R10 | Medium | `services/openfda.py:14-16` | Unbounded module-level dict caches (memory growth; no TTL on NDC/label caches, so stale recall-adjacent data). New `httpx.AsyncClient` per call (no pooling). |
| R11 | Medium | 5 × `asyncio.create_task` (verify.py:288, pharmacies.py:103, vernacular_resolver.py:53, …) | Un-referenced tasks may be garbage-collected; exceptions vanish. |
| R12 | Medium | 138 × `except Exception`, 2 × bare `except:` (`langgraph_pipeline.py:259`, `scrape_cdsco_recalls.py:193`) | Failures hidden in a safety-critical path. Bare excepts also swallow `CancelledError`/`KeyboardInterrupt`. |
| R13 | Low | `routers/verify.py:275` | `'cold_result' in locals()` control flow. |
| R14 | Low | `main.py:296` | Home stats fetch 15,000 rows to count them. |

### 2.4 Repository hygiene, tooling, docs

| # | Sev | Finding |
|---|---|---|
| H1 | High | Only one test file (6 tests); no lint, type-check, coverage, SAST, dependency or secret scanning; no frontend tests. CI never installs the real dependency set, so it cannot catch H-3. |
| H2 | Medium | `backend/.env.example` referenced in docs but missing. |
| H3 | Medium | Committed binaries: `backend/data/*.db`, `backend/data/pdfs/cdsco_approvals_0.pdf` (runtime state + source PDF in git). |
| H4 | Low | Five overlapping deploy docs (`DEPLOYMENT_*`, `LOCAL_DEPLOY_GUIDE`, `MANUAL_DEPLOY`, `QUICKSTART`) and four shell scripts; two `railway.toml`s with conflicting settings. |
| H5 | Low | Stray root `test_cold_chain.py` (network-dependent manual script, not a test). |
| H6 | Medium | README overclaims: "zero-knowledge" reporting (it is pseudonymous; see S3), "anti-gaming ML" (a 2-line rule), "immutable audit log" (broken; see R1/R6), "Zero-Trust RLS" (S17). |

## 3. What is already good (keep)

- `services/confidence.py` refuses to manufacture an authenticity probability; `authentic`/`counterfeit` reserved for an authoritative serial response. This is the right design and is preserved.
- `requires_human_review` defaults to `True`; `/capabilities` exposes honest feature flags.
- Cabinet routes correctly enforce ownership (`user_id == current_user.user_id`); this pattern is reused for the fixes.
- Strict request models (`extra="forbid"`), image size/base64 validation, production config validators for CORS and JWT strength.
- Non-root Docker user.

## 4. Fix plan

Critical and High items are fixed in Phase 1; Medium items are fixed in Phases 1–2 where they touch safety, auth or data integrity. Items deferred are listed explicitly in `docs/FINAL_REPORT.md` with reasons.
