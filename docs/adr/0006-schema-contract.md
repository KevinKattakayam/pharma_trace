# ADR-0006: Schema contract test against a real PostgreSQL

**Status:** accepted · **Context:** the application and its SQL had drifted apart (docs/AUDIT.md §5). The old silent local fallback hid every mismatch; with fail-closed writes (ADR-0003) they would surface as production errors.

**Decision.** `tests/conftest.py` records every table and column touched through `SupabaseClient` (writes, filters, selects) while the whole suite runs. `tests/test_zz_schema_contract.py` (runs last) applies `supabase_migration.sql` + `migrations/*.sql` in order to a real PostgreSQL (bundled via `pgserver`) and fails if any statement errors, any table the code names is missing, or any recorded column is absent. Only PostGIS and `pg_trgm` are unavailable in the bundled build: `GEOGRAPHY` is shimmed to `TEXT` and statements failing *because of those extensions* are tolerated; everything else must succeed.

**Limits.** Column existence, not types or constraints of every payload; routes not exercised by a test are covered only for table existence. PostGIS behaviour (the `set_location_from_latlng` trigger, `nearby_*` RPCs) is **not** tested here: verify on Supabase.
