# ADR-0004: Verdicts require concrete negative evidence

**Status:** accepted, **pending clinical safety officer sign-off** · **Context:** audit P2. `compute_confidence` correctly returns 0 without a validated model, but `determine_verdict` still applied `confidence < 50 → suspicious`, so every scan was "suspicious" and the documented `unknown` path was unreachable. Universal alarms train users to ignore alarms.

**Decision.** `assess_verdict()` returns a verdict **and reason codes**:
* `authentic` / `counterfeit`: only from an authoritative serial-verification response (unchanged).
* `suspicious`: at least one observable problem: `serial_rejected`, `active_recall`, `batch_alert` (batch + product match), `invalid_check_digit`, `registry_miss` (only where the registry is authoritative for the code type, i.e. US NDC/UPC vs openFDA), `expired`, `label_inconsistent`, `vision_high_suspicion`.
* `unknown`: everything else. **`requires_human_review` stays `true`**, and the UI says "Not verified".

**Why this is not a weakened control.** The removed rule carried no information (it fired on 100 % of non-serialised scans). The new rules add checks that did not exist before (cloned-QR mismatch, batch alerts, expiry, check digit). Safety tests cover every code.

**Backward compatibility.** `has_recall` stays a boolean and remains `true` when recall status is inconclusive; new clients read `recall_status`.
