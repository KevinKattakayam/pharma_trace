# API changes (v1, additive unless noted)

**Additive response fields on `/verify/barcode` and `/verify/image`:** `recall_status` (`active|none_found|inconclusive`), `verdict_reasons`, `audit_status`, `pack_check`, `batch_alerts`, `lasa`, `name_match_approximate`, `safety_notice`. `has_recall` remains boolean and is `true` when recall status is not `none_found` (unchanged semantics for inconclusive).

**Additive request field:** `printed` on `/verify/barcode` (printed batch/expiry for Pack Check).

**New endpoints:** `/ready`, `/safety/pack-check`, `/safety/batch-alerts`, `/safety/batch-alerts/coverage`, `/safety/lasa-check`.

**Behaviour changes (security fixes, intentionally breaking for unauthorised callers):**
* Auth now required: `/verify/offline-sync`, `/verify/batch-audit`, `/verify/history` (scoped), `/refill/schedule` (scoped), pharmacy register/claim/review; roles required for `/pharmacies/{id}/verify-claim` (regulator), inventory (verified claimant), `/clinic/create` (admin), `/audit/verify` and `/audit/log` (auditor/regulator).
* `/clinic/login` expects `{email, password}`; its token includes `sub`, `role`, `clinic_id`.
* `/push/notify-refill` reads `X-Cron-Secret` header (query parameter removed).
* `/verify/batch`: anonymous ≤10 items; summary adds `processed`, `flagged_count`, `error_count`.
* Verdict semantics: see ADR-0004.
