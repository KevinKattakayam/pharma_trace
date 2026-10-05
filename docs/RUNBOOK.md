# Runbook

| Symptom | Check | Action |
|---|---|---|
| `/ready` 503, `database: error` | Supabase status, key rotation | Writes fail closed by design; restore DB. Do **not** enable `ALLOW_LOCAL_FALLBACK_WRITES` in prod. |
| Responses show `audit_status: "failed"` | Logs `audit_write_failed` | Fix DB; affected results were *not* recorded. Note the window in the incident log. |
| `/audit/verify` returns `chain_valid: false` | `broken_at_row`, `reason` | Treat as a security incident: freeze writes, snapshot DB, compare with last exported anchor hash. |
| 429s for many users | Redis reachable? `TRUSTED_PROXY_HOPS` correct? | Wrong hop count collapses users onto the proxy's IP. |
| Batch-alert coverage stale | `GET /safety/batch-alerts/coverage` → `latest_month` | Import the new month. |

**Monthly regulator alert import:** download the CDSCO NSQ/spurious PDF → extract the table to CSV
(`batch_number, product_name, category, alert_month, manufacturer, reason, reporting_lab, source_url`) →
**second person checks it against the PDF** → `python -m scripts.import_regulator_alerts file.csv --out data/regulator_alerts.json --append` →
fix any rejected lines it prints → redeploy or restart. Never point `BATCH_ALERTS_DATA_PATH` at `*.SAMPLE.json` in production.

**Secret rotation:** rotating `JWT_SECRET` signs everyone out; rotating `HMAC_DAILY_SECRET` resets rate-limit buckets. Both are safe at any time.
