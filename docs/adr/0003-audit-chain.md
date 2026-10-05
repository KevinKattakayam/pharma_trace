# ADR-0003: Tamper-evident audit chain on a dedicated, append-only table

**Status:** accepted · **Context:** audit R1, R6, headline 1. Records were written to the wrong table, hashes covered fields that verification could not rebuild, appends raced, and failures returned fake hashes.

**Decision.**
* Table `audit_chain` (migration `phase5_audit_chain.sql`) with `canonical TEXT`; `record_hash = sha256(previous_hash ‖ canonical)`. Verification recomputes from the stored string.
* Variable detail (evidence, batch items) is bound via `payload_digest` inside the canonical JSON.
* Server time is authoritative; client time is kept as `client_reported_at`.
* Postgres: `append_audit_record()` takes `pg_advisory_xact_lock` and computes the hash in the database; `UNIQUE(previous_hash)` makes forks impossible; triggers block UPDATE/DELETE/TRUNCATE even for the service role (which bypasses RLS). Local mode uses an `asyncio.Lock`.
* Failures raise `AuditWriteError`; verification responses carry `audit_status: "failed"` instead of a hash.

**Limits (stated in docs).** This is tamper-*evidence*. A database superuser can rewrite the whole chain; external anchoring of `last_hash` (e.g. daily signed export) is recommended. Not a claim of 21 CFR Part 11 compliance (removed from code).
