# ADR-0007: Pharmacy community rating instead of a "Trust Index"

**Status:** accepted · **Context:** the old score used `log10(review count)` (ignoring stars), a pass-rate term reading an unrelated table, and defaulted to 100/100. It would have displayed unreviewed listings as maximally trustworthy and ranked many 1-star reviews above a few 5-star ones.

**Decision.** `trust_score` (field kept for compatibility) is a Bayesian average of star ratings of non-flagged reviews, mapped 1–5★ → 0–100, with prior mean 3.0 and weight 5, and **no score below 3 reviews** (`rating_status`: `rated | not_enough_reviews | not_rated | unavailable`). The UI calls it a community rating and states it says nothing about medicine authenticity. Imported OpenStreetMap listings are `osm_unverified` and reach `claim_verified` only through the pharmacist claim + regulator approval flow.

**Honesty note.** The prior and minimum are standard small-sample practice, not validated for this domain; they are constants in `routers/pharmacies.py`.
