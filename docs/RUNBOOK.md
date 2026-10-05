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

## Making the data real

**Regulator alerts (monthly).** 1) Download the CDSCO alert PDF. 2) `python -m scripts.cdsco_pdf_to_draft_csv alert.pdf --month YYYY-MM --source-url https://… --out draft.csv`: *draft only*, layouts change monthly. 3) A person checks **every row** against the PDF, sets `category`, fills `reviewed_by`/`reviewed_at`, clears the `CHECK` notes. 4) `python -m scripts.import_regulator_alerts draft.csv --out data/regulator_alerts.json --append` rejects anything unreviewed. 5) Set `BATCH_ALERTS_DATA_PATH`, restart. Revised lists replace earlier ones: re-import the month.

**Pharmacies.** `python -m scripts.import_osm_pharmacies --bbox S,W,N,E --dry-run`, then without `--dry-run`. One district at a time (Overpass is shared). Listings stay `osm_unverified`. Keep the OpenStreetMap attribution visible (ODbL).

**Brand names.** Obtain a product list you are licensed to use; `python -m scripts.import_brands brands.csv` (each row needs a `source`); restart.

**Check progress.** `python -m scripts.doctor` lists what is still dummy.
