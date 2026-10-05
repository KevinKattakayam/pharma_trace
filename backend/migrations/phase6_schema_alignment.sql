-- Phase 6: align the database with what the API actually reads and writes.
-- Idempotent. Safe to run on fresh databases (after the base script and phases 2-5) and on existing ones.
-- Found by tests/test_zz_schema_contract.py, which compares every table/column the code touches with the
-- migrated schema. Until now these gaps were hidden because failed writes silently fell back to a local file.

-- ── Tables the code uses that no earlier migration created ──
CREATE TABLE IF NOT EXISTS ai_cache (
    id            TEXT PRIMARY KEY,
    drug_name     TEXT NOT NULL,
    analysis_data JSONB NOT NULL,
    created_ts    BIGINT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_ai_cache_drug ON ai_cache(drug_name, created_ts DESC);

CREATE TABLE IF NOT EXISTS caregiver_recipients (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code         TEXT NOT NULL,
    caregiver_id TEXT NOT NULL,
    name         TEXT,
    created_at   TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (code, caregiver_id)
);
CREATE INDEX IF NOT EXISTS idx_cg_recipients_caregiver ON caregiver_recipients(caregiver_id);

CREATE TABLE IF NOT EXISTS caregiver_medications (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_code TEXT NOT NULL,
    name           TEXT NOT NULL,
    ndc            TEXT,
    rxcui          TEXT,
    status         TEXT,
    confidence     REAL,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cg_meds_recipient ON caregiver_medications(recipient_code);

CREATE TABLE IF NOT EXISTS caregiver_alerts (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    recipient_code TEXT NOT NULL,
    type           TEXT,
    message        TEXT NOT NULL,
    severity       TEXT,
    read           BOOLEAN DEFAULT FALSE,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_cg_alerts_recipient ON caregiver_alerts(recipient_code, created_at DESC);

-- ── Columns the code writes that the schema lacked ──
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS clinic_id UUID REFERENCES clinics(id);
CREATE INDEX IF NOT EXISTS idx_verifications_user ON verifications(user_id, created_at DESC);

ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS listing_status TEXT DEFAULT 'community_unverified';
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS claim_status TEXT;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS claimed_by TEXT;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS claim_verified_by TEXT;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS created_by TEXT;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS license_number TEXT;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS suspicious_reports INTEGER DEFAULT 0;
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS source TEXT;        -- e.g. 'OpenStreetMap contributors (ODbL)'
ALTER TABLE pharmacies ADD COLUMN IF NOT EXISTS source_id TEXT;     -- e.g. 'node/123456'
CREATE UNIQUE INDEX IF NOT EXISTS uq_pharmacies_source ON pharmacies(source, source_id) WHERE source_id IS NOT NULL;

ALTER TABLE pharmacy_reviews ADD COLUMN IF NOT EXISTS reviewer_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_review_once_per_user ON pharmacy_reviews(pharmacy_id, reviewer_id) WHERE reviewer_id IS NOT NULL;

ALTER TABLE reports ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS lng DOUBLE PRECISION;
ALTER TABLE reports ADD COLUMN IF NOT EXISTS photo_urls JSONB DEFAULT '[]';
ALTER TABLE reports ADD COLUMN IF NOT EXISTS user_id TEXT;

ALTER TABLE caregiver_links ADD COLUMN IF NOT EXISTS code TEXT;
ALTER TABLE caregiver_links ADD COLUMN IF NOT EXISTS creator_user_id TEXT;
ALTER TABLE caregiver_links ALTER COLUMN invite_code DROP NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_caregiver_links_code ON caregiver_links(code) WHERE code IS NOT NULL;

-- caregiver_id was UUID but app user IDs are opaque strings. A policy depends on the column, so recreate it.
DROP POLICY IF EXISTS caregiver_links_isolation ON caregiver_links;
ALTER TABLE caregiver_links ALTER COLUMN caregiver_id TYPE TEXT USING caregiver_id::text;
CREATE POLICY caregiver_links_isolation ON caregiver_links
    FOR ALL
    USING (
        caregiver_id = current_setting('request.header.x-user-id', true)
        OR creator_user_id = current_setting('request.header.x-user-id', true)
        OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin')
    );

-- ── The API writes plain lat/lng; the PostGIS RPCs (nearby_pharmacies, nearby_reports) read `location`. ──
-- Keep them in sync so map and heat-map queries actually find rows. Requires PostGIS (enabled on Supabase).
CREATE OR REPLACE FUNCTION set_location_from_latlng() RETURNS trigger
LANGUAGE plpgsql
SET search_path = public, extensions
AS $$
BEGIN
    IF NEW.lat IS NOT NULL AND NEW.lng IS NOT NULL THEN
        NEW.location := ST_SetSRID(ST_MakePoint(NEW.lng, NEW.lat), 4326)::geography;
    END IF;
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_pharmacies_location ON pharmacies;
CREATE TRIGGER trg_pharmacies_location BEFORE INSERT OR UPDATE OF lat, lng ON pharmacies
    FOR EACH ROW EXECUTE FUNCTION set_location_from_latlng();
DROP TRIGGER IF EXISTS trg_reports_location ON reports;
CREATE TRIGGER trg_reports_location BEFORE INSERT OR UPDATE OF lat, lng ON reports
    FOR EACH ROW EXECUTE FUNCTION set_location_from_latlng();

-- Backfill for rows created before this migration.
UPDATE pharmacies SET location = ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
    WHERE location IS NULL AND lat IS NOT NULL AND lng IS NOT NULL;
