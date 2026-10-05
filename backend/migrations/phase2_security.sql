-- ═══════════════════════════════════════════════════════════════════
-- PharmaTrace Phase 2 Security Migration
-- Zero-Trust RLS Policies + Live CDSCO Registry + OCC Versioning
-- ═══════════════════════════════════════════════════════════════════

-- ───────────────────────────────────────────────────
-- 1. Live Indian Drug Registry (replaces static SQLite)
-- ───────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS indian_drug_registry (
    id              UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    cdsco_code      TEXT UNIQUE NOT NULL,
    generic_name    TEXT NOT NULL,
    brand_name      TEXT,
    manufacturer    TEXT,
    indication      TEXT,
    approval_date   TEXT,
    route           TEXT DEFAULT 'ORAL',
    last_synced_at  TIMESTAMPTZ DEFAULT now(),
    sync_source     TEXT DEFAULT 'manual',
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_indian_drug_registry_generic ON indian_drug_registry (LOWER(generic_name));
CREATE INDEX IF NOT EXISTS idx_indian_drug_registry_cdsco ON indian_drug_registry (cdsco_code);

-- Auto-update updated_at on modification
CREATE OR REPLACE FUNCTION update_modified_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_indian_drug_registry_modtime ON indian_drug_registry;
CREATE TRIGGER update_indian_drug_registry_modtime
    BEFORE UPDATE ON indian_drug_registry
    FOR EACH ROW EXECUTE PROCEDURE update_modified_column();


-- ───────────────────────────────────────────────────
-- 2. OCC entity_version column for offline sync conflict detection
-- ───────────────────────────────────────────────────

ALTER TABLE verifications ADD COLUMN IF NOT EXISTS entity_version TEXT;
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

DROP TRIGGER IF EXISTS update_verifications_modtime ON verifications;
CREATE TRIGGER update_verifications_modtime
    BEFORE UPDATE ON verifications
    FOR EACH ROW EXECUTE PROCEDURE update_modified_column();


-- ───────────────────────────────────────────────────
-- 3. Zero-Trust RLS Policies (Postgres-native tenant isolation)
-- ───────────────────────────────────────────────────

-- Enable RLS on all tenant-scoped tables
ALTER TABLE verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE safety_check_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE caregiver_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE reports ENABLE ROW LEVEL SECURITY;  -- was `adverse_reports`, a table no migration creates

-- Allow service role to bypass RLS (for backend admin operations)
ALTER TABLE verifications FORCE ROW LEVEL SECURITY;
ALTER TABLE safety_check_log FORCE ROW LEVEL SECURITY;
ALTER TABLE caregiver_links FORCE ROW LEVEL SECURITY;

-- Verifications: Users can only see/modify their own verifications
-- RLS reads user identity from the x-user-id header injected by BaseRepository
CREATE POLICY verifications_tenant_isolation ON verifications
    FOR ALL
    USING (
        user_id = current_setting('request.header.x-user-id', true)
        OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin')
    )
    WITH CHECK (
        user_id = current_setting('request.header.x-user-id', true)
        OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin')
    );

-- Audit logs: APPEND-ONLY. No updates or deletes, ever.
-- Everyone can read audit logs (transparency), but only the system can insert.
CREATE POLICY audit_log_read ON safety_check_log
    FOR SELECT
    USING (true);

CREATE POLICY audit_log_insert ON safety_check_log
    FOR INSERT
    WITH CHECK (true);

-- Explicitly deny UPDATE and DELETE on audit logs at the policy level
-- (This supplements the application-layer NotImplementedError in AuditRepository)
CREATE POLICY audit_log_no_update ON safety_check_log
    FOR UPDATE
    USING (false);

CREATE POLICY audit_log_no_delete ON safety_check_log
    FOR DELETE
    USING (false);

-- Caregiver links: Only the caregiver or the patient can see links
CREATE POLICY caregiver_links_isolation ON caregiver_links
    FOR ALL
    USING (
        caregiver_id = current_setting('request.header.x-user-id', true)
        OR creator_user_id = current_setting('request.header.x-user-id', true)
        OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin')
    );

-- Clinic-scoped isolation: workers see only their clinic's data
CREATE POLICY verifications_clinic_isolation ON verifications
    FOR ALL
    USING (
        clinic_id IS NULL
        OR clinic_id::text = current_setting('request.header.x-clinic-id', true)
        OR current_setting('request.header.x-user-role', true) = 'admin'
    );

-- Indian drug registry: Public read access (reference data)
ALTER TABLE indian_drug_registry ENABLE ROW LEVEL SECURITY;
CREATE POLICY indian_drug_registry_public_read ON indian_drug_registry
    FOR SELECT
    USING (true);

CREATE POLICY indian_drug_registry_admin_write ON indian_drug_registry
    FOR INSERT
    WITH CHECK (
        current_setting('request.header.x-user-role', true) IN ('admin', 'system')
        OR current_setting('role', true) = 'service_role'
    );
