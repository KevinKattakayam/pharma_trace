# ADR-0005: Pack Check, batch-level alerts and LASA guard

**Status:** accepted · See `docs/FEATURE_PROPOSALS.md` for selection rationale.

* **Batch alerts.** Normalised batch matching (prefix stripping only before a separator; O/0-style folding only yields `possible_variant`). Only batch **and** product agreement flags a pack, because batch numbers are not unique across manufacturers. No data → `unavailable`, never "clear". Coverage (months, source, sample flag) is always returned.
* **Pack Check.** Compares QR-encoded fields with the printed label and date logic. Month-only expiry = end of month; month-only mfg date = first of month; shelf life > 5 years is a warning only. Output is consistent/inconsistent/incomplete, never "authentic".
* **LASA guard.** Compares against names actually in loaded registries; warns only for a different ingredient set; ratio ≥ 84 or length-aware edit distance (1 edit ≤ 6 letters). Thresholds are not clinically validated and are configurable.

All three are feature-flagged and covered by tests with synthetic, clearly labelled data.
