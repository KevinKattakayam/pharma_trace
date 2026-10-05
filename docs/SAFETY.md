# Safety principles and verdict semantics

1. **No authenticity without authority.** `authentic`/`counterfeit` come only from an authoritative serial service (`MANUFACTURER_VERIFICATION_URL`). Registry, barcode, QR, OCR and AI results are never proof.
2. **Fail safe, never silent.** Missing data is `inconclusive` / `unavailable` / `incomplete`, never "clear". A failed audit write is reported (`audit_status: "failed"`).
3. **Suspicion needs evidence.** `suspicious` always carries reason codes (ADR-0004): `serial_rejected`, `active_recall`, `batch_alert`, `invalid_check_digit`, `registry_miss` (US NDC/UPC only), `expired`, `label_inconsistent`, `vision_high_suspicion`.
4. **Human review by default.** `requires_human_review` is `true` unless serial-verified.
5. **No clinical decisions.** No dose changes (`automated_dose_recommendations: false`), no diagnosis. AI outputs carry `ai_generated: true` and a safety notice.
6. **Cited content.** Regulatory findings link to their source (CDSCO FAQ / alert URL). Sample data is labelled `SAMPLE` in data, API (`is_sample_data`) and UI.

**Changes needing clinical safety officer sign-off:** ADR-0004 (clean record match → `unknown` instead of `suspicious`).
