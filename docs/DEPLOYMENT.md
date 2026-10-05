# Deployment

1. **Database:** in the Supabase SQL editor (PostGIS and pg_trgm enabled), run in order: `backend/supabase_migration.sql`, then `backend/migrations/phase2_security.sql`, `phase3_data_governance.sql`, `phase4_safety_cases.sql`, `phase5_audit_chain.sql`, `phase6_schema_alignment.sql`. All are idempotent. Phase 5 (append-only audit chain) is tested on PostgreSQL 16; the PostGIS location trigger in phase 6 is **not** testable offline: after running it, add a pharmacy and check `/api/v1/pharmacies/nearby` finds it.
   Then run `python -m scripts.doctor --ping-db` and fix every BLOCKER.
2. **Secrets:** set `ENVIRONMENT=prod`, `JWT_SECRET` (≥64 chars, mixed classes), `HMAC_DAILY_SECRET` (≥32), `CRON_SECRET` (≥32), `CORS_ORIGINS`, `SUPABASE_URL`/`SUPABASE_KEY` in your platform's secret store. The app refuses to start otherwise.
3. **Redis:** set `RATE_LIMIT_STORAGE_URI=redis://…` when running more than one worker or instance.
4. **Proxy:** set `TRUSTED_PROXY_HOPS` to the number of reverse proxies you control (Railway/Render/nginx: usually 1).
5. **API image:** `docker build backend` (Railway uses `backend/railway.toml`). Health: `/api/v1/health` (liveness), `/api/v1/ready` (readiness).
6. **Web:** Vercel (`frontend/vercel.json`) or `docker build frontend` (nginx). Watch CSP reports, then switch `Content-Security-Policy-Report-Only` to `Content-Security-Policy`.
7. **Scheduled jobs:** `POST /api/v1/push/notify-refill` with header `X-Cron-Secret`.
8. **Regulator alerts:** import monthly (see RUNBOOK) and set `BATCH_ALERTS_DATA_PATH`.
