-- PharmaTrace Phase 3: source provenance, freshness and serial-verification evidence.
-- Apply through the managed migration process before enabling production workflows.

CREATE TABLE IF NOT EXISTS data_source_runs (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    source_version TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'partial')),
    records_seen INTEGER NOT NULL DEFAULT 0 CHECK (records_seen >= 0),
    records_upserted INTEGER NOT NULL DEFAULT 0 CHECK (records_upserted >= 0),
    checksum TEXT,
    error_summary TEXT
);

CREATE TABLE IF NOT EXISTS authoritative_serial_checks (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    verification_id UUID NOT NULL,
    provider TEXT NOT NULL,
    provider_reference TEXT,
    gtin TEXT NOT NULL,
    serial_number_hash TEXT NOT NULL,
    lot_hash TEXT,
    verified BOOLEAN NOT NULL,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    response_hash TEXT NOT NULL,
    UNIQUE (provider, gtin, serial_number_hash, checked_at)
);

CREATE INDEX IF NOT EXISTS idx_data_source_runs_source_completed ON data_source_runs (source_name, completed_at DESC);
CREATE INDEX IF NOT EXISTS idx_authoritative_serial_checks_verification ON authoritative_serial_checks (verification_id);

ALTER TABLE data_source_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE authoritative_serial_checks ENABLE ROW LEVEL SECURITY;

CREATE POLICY data_source_runs_admin_read ON data_source_runs
    FOR SELECT USING (current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin'));
CREATE POLICY serial_checks_admin_read ON authoritative_serial_checks
    FOR SELECT USING (current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin'));
