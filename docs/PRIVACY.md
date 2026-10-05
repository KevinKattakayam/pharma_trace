# Privacy and compliance notes (DPDP Act 2023 / GDPR)

*Engineering notes, not legal advice. A qualified privacy lawyer must review before launch.*

| Data | Where | Purpose | Minimisation in code |
|---|---|---|---|
| Client IP | Never stored | Rate limiting | Converted to a daily-rotating keyed pseudonym, then removed from the request (ADR-0002) |
| Account ID, role, clinic | JWT, audit chain | Access control, accountability | Opaque IDs; no names in audit records |
| Scan history | `verifications` | User history, clinic stats | Scoped to owner/clinic; location only if the user sends it |
| Anonymous reports | `adverse_reports` | Safety signals | Random report token (no IP link); location coarsened with CSPRNG jitter |
| Health data (cabinet, conditions) | Supabase | User features | Owner-only access; consider it sensitive personal data |
| Error reports | Sentry (optional) | Debugging | Bodies, cookies, auth headers, IPs scrubbed; `send_default_pii=False` |

**Open items requiring human action:** a privacy notice and consent flow (DPDP s.5–6), data-principal rights endpoints (access/erasure: audit-chain records are append-only, so erase linked personal data elsewhere and keep only pseudonymous audit entries; document this lawful basis), a retention schedule, a DPA with Supabase/Sentry, and a cross-border transfer assessment for non-India hosting.
