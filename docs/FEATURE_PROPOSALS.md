# Feature proposals

## 1. Problem space (what the research established)

These facts were checked against primary or reputable sources during Phase 3:

* **India's pack-code rule.** GSR 823(E) (17 Nov 2022, in force 1 Aug 2023) requires the Schedule H2 "top 300" brands to carry a barcode/QR with eight particulars: unique product identification code, proper/generic name, brand name, manufacturer name and address, batch, manufacturing date, expiry date, manufacturing licence number. CDSCO's FAQ states the unique product code is set by the manufacturer's own SOP (not necessarily a GTIN). Sources: [CDSCO FAQ, 21 Jul 2023](https://cdsco.gov.in/opencms/resources/UploadCDSCOWeb/2018/UploadPublic_NoticesFiles/Final%20FAQs%20on%20QR%20code%2021.07.2023.pdf); [CDSCO guidance on spurious drugs](https://cdsco.gov.in/opencms/export/sites/CDSCO_WEB/Pdf-documents/Guidance-for-Identification-and-Verification-of-Spurious-Drugs.pdf).
* **Regulator quality alerts are monthly and batch-specific.** CDSCO publishes NSQ and spurious lists every month; the ministry states each NSQ finding applies to the batch tested and does not warrant concern about other products on the market. Recent months list hundreds of batches (e.g. 220 samples flagged for August 2026, including a batch the labelled manufacturer said it never made). Sources: press coverage of CDSCO statements (Daily Pioneer, The South First, Medical Dialogues, Sep 2026).
* **Copied codes are the obvious attack on QR schemes.** A QR encodes label data; nothing stops a counterfeiter copying a genuine one. The one observable symptom without a manufacturer partnership is a **mismatch between the code and the printed label**.
* **Look-alike/sound-alike (LASA) names are a documented Indian hazard.** A Lancet commentary and follow-up reporting describe identical or near-identical brand names for different drugs; DTAB recommended in January 2024 prohibiting different drugs under the same brand name. Prescriptions in India usually carry brand names only. Sources: The South First, Medical Dialogues, SpicyIP, Mondaq (2024).
* **Existing tools** (described at the level we can verify): pharmacy/e-commerce apps offer drug information and substitutes; national pharmacovigilance programmes run ADR reporting apps; SMS scratch-code verification schemes have operated in West Africa; WHO runs a global surveillance system for substandard and falsified products. What we did not find is a free, offline-capable, *batch-level, label-consistency-first* checker for Indian packs that refuses to call anything "genuine". **This was a limited desk search, not a systematic market review.**

**Underserved users:** rural patients and caregivers on low-end Android phones with poor connectivity; ASHA/ANM health workers dispensing from PHC stock; small chemists without a pharmacist on duty; district drug inspectors who receive alerts as PDFs.

## 2. Candidates

Effort: S ≤ 1 week, M 2–4 weeks, L > 1 month (one engineer). Impact and risk are judgements, not measurements.

| # | Idea | Who it helps | Novelty (honest) | Reuses | Effort | Impact | Safety / regulatory risk | Dependencies |
|---|---|---|---|---|---|---|---|---|
| 1 | **Pack Check**: QR vs printed label vs date logic | Patients, chemists, ASHAs | Copied-QR mismatch detection presented as *consistency, not authenticity*: not found in tools we checked | gs1, india_qr, expiry | S | High | Low: never claims genuine | None |
| 2 | **Batch-level regulator alert matching** | Everyone; inspectors | Alerts exist as PDFs; batch+product matching inside a scan flow appears uncommon | batch_alerts, verify | M | High | Medium: false match → batch-only matches never escalate | Monthly CDSCO lists; human-reviewed import |
| 3 | **LASA name guard** on resolution/OCR | Patients, chemists | LASA lists exist for hospitals; inline warning on a consumer scan path is uncommon | drug_resolver, rapidfuzz | S | Medium–High | Low (warning only) | Broader brand corpus (licence) |
| 4 | Cloned-serial velocity signal (same GS1 serial scanned in distant districts) | Regulators | Standard in full track-and-trace; novel for a crowd-sourced app | audit, verifications | M | Medium | Privacy: needs k-anonymity, coarse geo | Serialised packs (rare in India today) |
| 5 | District alert digest for drug inspectors (new alerts × local scans) | Regulators | Novel | batch_alerts, reports | M | Medium | Must not expose individuals | Inspector onboarding |
| 6 | Offline alert pack (signed daily delta of alert index to the PWA) | Rural users | Uncommon | service worker, batch_alerts | M | High | Stale data → show coverage date | Signing key |
| 7 | WhatsApp/SMS pack check (send photo or code, get consistency report) | Feature-phone users | Messaging bots exist; this check doesn't | pack_check | M | High | Message privacy; no verdicts by SMS | Messaging provider contract |
| 8 | Jan Aushadhi generic price comparison | Price-sensitive patients | Not novel (official app exists) | generics | S | Medium | Substitution is a pharmacist decision | PMBI product list |
| 9 | Pharmacist "second look" queue for suspicious scans | Patients, chemists | Novel as a workflow | safety_cases | M | High | Liability; pharmacist registration check | Pharmacist partners |
| 10 | Pre-filled PvPI ADR form from a scan | Patients, clinics | Partly exists (repo has prefill) | pvpi | S | Medium | Must not pre-judge causality | None |
| 11 | Expiry and recall watch for a household cabinet | Caregivers | Reminders exist; batch-alert watch is new | cabinet, batch_alerts | S | Medium | Low | Push keys |
| 12 | Multilingual spoken results (Tamil, Hindi, …) | Low-literacy users | Uncommon for verification results | voice, translation | M | High | Mistranslation: needs reviewed strings, not MT | Translator review |
| 13 | Cold-chain excursion diary for insulin/vaccines at home | Patients on biologics | Uncommon | cold_chain | M | Medium | Must not advise use/discard; refer | Weather API |
| 14 | Clinic stock reconciliation against alerts (CSV upload) | PHCs, clinics | Novel for small clinics | batch_alerts, clinic | M | High | Data handling | None |
| 15 | Antibiotic (Schedule H1) purchase education card | Patients | Not novel content; useful placement | drugs | S | Low–Medium | Must stay educational | Schedule data |
| 16 | Prescription-to-pack match (does the dispensed pack match the Rx?) | Patients, caregivers | Novel combined with LASA | prescription, lasa | M | High | OCR errors: confirmation required | None |
| 17 | Anonymous community signal map with k-anonymity thresholds | Public health | Heatmaps exist; enforced thresholds rare | reports | M | Medium | Re-identification, panic | Privacy review |
| 18 | GS1 Digital Link resolver (open product page from code) | Everyone | Not novel (GS1 standard) | gs1 | S | Low | Phishing links: allow-list domains | None |
| 19 | Regulator-format monthly export for inspectors | Regulators | Low novelty | audit_export | S | Low–Medium | Data minimisation | Regulator format |
| 20 | Pill-image "what is this tablet?" identification | Patients | Exists (US imprint databases); poor fit for Indian generics | vision | L | Low | **High**: misidentification → harm | Licensed image DB; **rejected** |
| 21 | AI dose adjustment by age/kidney function | — | — | dosage | — | — | **Rejected:** changes doses | — |
| 22 | "Genuine" badge from registry match | — | — | — | — | — | **Rejected:** declares authenticity without serial verification | — |

## 3. Ranking and selection

Scored on impact × feasibility with free/open data × safety, then novelty as a tie-breaker:

1. **#1 Pack Check**: built.
2. **#2 Batch-level alerts**: built (matcher, coverage reporting, reviewed-CSV importer; real data loading is a human action).
3. **#3 LASA guard**: built (real-world reach limited by the bundled corpus; see final report).
4. #14 Clinic stock reconciliation: next; small step on top of #2.
5. #6 Offline alert pack: next; makes #2 useful without connectivity.
6. #9 Pharmacist second-look queue: needs partners.
7. #7 WhatsApp/SMS: needs a provider contract.

**Why these three:** they target the two concrete Indian attack/error patterns the research confirmed (copied codes and batch-specific quality failures) plus a medication-error pattern this codebase was *itself* creating (the fuzzy resolver silently snapping names to different drugs). All three run on free data, work without AI, fail safe ("unavailable"/"incomplete", never "clear"/"genuine"), and reuse existing modules.

**Rejected:** #20, #21 and #22 conflict with the non-negotiable safety principles. #8 and #18 duplicate existing tools.

## 4. What was built

| Feature | Backend | API | Frontend | Tests | Flag |
|---|---|---|---|---|---|
| Pack Check | `services/pack_check.py`, `india_qr.py`, `gs1.py` | `POST /api/v1/safety/pack-check`; `printed` field on `/verify/barcode` | `/pack-check` page; `SafetyIntelPanel` | 15+ | `FEATURE_PACK_CHECK` |
| Batch alerts | `services/batch_alerts.py`, `scripts/import_regulator_alerts.py` | `GET /safety/batch-alerts`, `/coverage`; `batch_alerts` in verification | Coverage line with sample-data warning | 10+ | `FEATURE_BATCH_ALERTS` |
| LASA guard | `services/lasa.py` | `POST /safety/lasa-check`; `lasa` in verification | Warning box | 5 | `FEATURE_LASA_GUARD` |
