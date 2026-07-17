# PharmaTrace production readiness

## Safety boundary

PharmaTrace is a decision-support and reporting system. A registry match, OCR
result, barcode check digit, image result, or AI-generated explanation is not
proof that a physical medicine package is genuine and is not a diagnosis or a
prescription. The API now returns `requires_human_review: true` unless an
authorised serial-verification provider confirms the specific package.

Do not enable autonomous dispensing, dosage changes, interaction clearance, or
counterfeit accusations from a record-match result.

## Required production integrations

1. Contract an authorised manufacturer or distributor verification provider.
   Configure `MANUFACTURER_VERIFICATION_URL` and
   `MANUFACTURER_VERIFICATION_TOKEN`; the endpoint must return a boolean
   `verified` response for GTIN + serial (+ lot when available).
   The adapter sends `{"gtin", "serial_number", "lot"}` and expects
   `{"verified": true|false, "provider", "reference"}`.
2. Contract a licensed clinical interaction provider before allowing a `low`
   interaction risk to guide care. Configure
   `CLINICAL_INTERACTION_PROVIDER_URL` and
   `CLINICAL_INTERACTION_PROVIDER_TOKEN`. Its adapter sends
   `{"drug_concepts": [...]}` and expects `{"interactions": [...]}`; every
   item must include the two drugs, severity, clinical effect, recommendation,
   and source.
3. Apply `backend/migrations/phase2_security.sql` and
   `backend/migrations/phase3_data_governance.sql` through the managed database
   migration process.
4. Schedule source ingestion with retained run metadata:
   - CDSCO NSQ, spurious-drug, theft, and recall notices: at least daily.
   - FDA label, recall, and shortage sources: at least daily, with outage alerts.
   - A licensed, clinically maintained interaction knowledge provider before
     presenting an interaction result as clinically actionable.
5. Set `ENVIRONMENT=prod`, `DEBUG=false`, a 64+ character `JWT_SECRET`, named
   `CORS_ORIGINS`, and provider credentials. Startup rejects unsafe production
   defaults and wildcard CORS.

## Automated checks

Copy `backend/.env.example` to a local `backend/.env` and supply values through
your deployment platform in production. Before deploying, run from `backend/`:

```bash
python -m scripts.preflight
```

The command checks configuration without exposing secrets. CI runs its safe
development variant automatically. Database migration execution remains a
separate controlled deployment action because it changes shared production data.

## Validation before patient-facing rollout

Build a versioned, consented golden dataset before publishing accuracy claims.
It must contain genuine packs, regulator-confirmed falsified/NSQ packs,
recalled lots, valid and invalid GS1 payloads, damaged/blurred labels, and each
supported script/language. Report false negatives separately for each country,
manufacturer, product type, and input mode.

Release gates:

- 100% pass rate for recall and serial-verification regression cases.
- No “authentic” response without an authoritative serial response.
- Human pharmacist review of all high-risk/unknown cohorts.
- Source freshness and ingestion failure alarms tested in staging.
- Load, backup-restore, audit-chain, access-control, and incident-response tests
  signed off by the deployment owner.

## Operational controls

- Keep raw package serials out of general logs; store only a salted hash where
  retention is necessary.
- Rotate provider and JWT secrets through the deployment platform, never source
  control.
- Treat new model or prompt changes as clinical-safety changes: version them,
  evaluate against the golden dataset, obtain review, then deploy gradually.
- Keep LLM use constrained to extraction and plain-language summaries. It must
  not be the authority for product identity, interactions, dose, or recalls.
