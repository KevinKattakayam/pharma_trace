-- ═══════════════════════════════════════════════════════════════
-- PharmaTrace — Supabase Database Schema (PostgreSQL + PostGIS)
-- Run this in the Supabase SQL Editor to set up the database.
-- ═══════════════════════════════════════════════════════════════

-- Enable PostGIS for geospatial queries
CREATE EXTENSION IF NOT EXISTS postgis;

-- Enable pg_trgm for fuzzy text matching
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ── Vernacular Drug Aliases (Trigram Fuzzy Matching) ──
CREATE TABLE IF NOT EXISTS vernacular_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_alias TEXT NOT NULL,
    canonical_name TEXT NOT NULL,
    active_ingredients TEXT[] NOT NULL,
    language_code TEXT NOT NULL DEFAULT 'en',
    alias_type TEXT NOT NULL CHECK (alias_type IN ('brand', 'phonetic', 'script', 'regional', 'ai_resolved')),
    source TEXT NOT NULL CHECK (source IN ('rxnorm', 'cdsco', 'openfda_traffic', 'ai_resolved', 'manual')),
    confidence FLOAT NOT NULL DEFAULT 1.0,
    verified BOOLEAN NOT NULL DEFAULT FALSE,
    usage_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_alias_unique ON vernacular_aliases(lower(drug_alias));
CREATE INDEX idx_alias_trgm ON vernacular_aliases USING GIN(drug_alias gin_trgm_ops);
CREATE INDEX idx_alias_lang ON vernacular_aliases(language_code);

-- ── Verification Records ──
CREATE TABLE IF NOT EXISTS verifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    barcode TEXT,
    method TEXT NOT NULL CHECK (method IN ('barcode', 'image', 'manual', 'batch')),
    verdict TEXT NOT NULL CHECK (verdict IN ('authentic', 'suspicious', 'counterfeit', 'unknown')),
    confidence REAL NOT NULL DEFAULT 0,
    brand_name TEXT,
    generic_name TEXT,
    manufacturer TEXT,
    ndc TEXT,
    has_recall BOOLEAN DEFAULT FALSE,
    evidence JSONB DEFAULT '[]',
    audit_hash TEXT,
    gtin_data JSONB,
    temperature_c REAL,
    humidity_pct REAL,
    location GEOGRAPHY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_verifications_ndc ON verifications(ndc);
CREATE INDEX idx_verifications_created ON verifications(created_at DESC);
CREATE INDEX idx_verifications_location ON verifications USING GIST(location);

-- ── Community Reports (Anonymous) ──
CREATE TABLE IF NOT EXISTS reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    anonymous_id TEXT UNIQUE,
    drug_name TEXT NOT NULL,
    barcode TEXT,
    description TEXT,
    city TEXT,
    country TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'investigating', 'confirmed', 'resolved')),
    location GEOGRAPHY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_status ON reports(status);
CREATE INDEX idx_reports_location ON reports USING GIST(location);
CREATE INDEX idx_reports_created ON reports(created_at DESC);

-- ── Pharmacies ──
CREATE TABLE IF NOT EXISTS pharmacies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    address TEXT,
    city TEXT,
    country TEXT,
    trust_score REAL DEFAULT 50 CHECK (trust_score >= 0 AND trust_score <= 100),
    total_verifications INTEGER DEFAULT 0,
    verification_pass_rate REAL DEFAULT 0,
    flagged_reviews INTEGER DEFAULT 0,
    location GEOGRAPHY(Point, 4326),
    is_claimed BOOLEAN DEFAULT FALSE,
    verified_inventory JSONB DEFAULT '[]',
    contact_number TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pharmacies_trust ON pharmacies(trust_score DESC);
CREATE INDEX idx_pharmacies_location ON pharmacies USING GIST(location);

-- ── Doctors / Medical Professionals ──
CREATE TABLE IF NOT EXISTS doctors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    specialty TEXT,
    address TEXT,
    city TEXT,
    country TEXT,
    contact_number TEXT,
    registration_number TEXT,
    accepts_digital_prescriptions BOOLEAN DEFAULT TRUE,
    trust_score REAL DEFAULT 100,
    location GEOGRAPHY(Point, 4326),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_doctors_location ON doctors USING GIST(location);

-- ── Pharmacy Reviews ──
CREATE TABLE IF NOT EXISTS pharmacy_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pharmacy_id UUID REFERENCES pharmacies(id) ON DELETE CASCADE,
    rating INTEGER NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    flagged BOOLEAN DEFAULT FALSE,
    flag_reason TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reviews_pharmacy ON pharmacy_reviews(pharmacy_id);

-- ── Flagged Reviews (Anti-Gaming) ──
CREATE TABLE IF NOT EXISTS flagged_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID REFERENCES pharmacy_reviews(id) ON DELETE CASCADE,
    pharmacy_id UUID REFERENCES pharmacies(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    flagged_at TIMESTAMPTZ DEFAULT NOW(),
    resolved BOOLEAN DEFAULT FALSE
);

CREATE INDEX idx_flagged_reviews_pharmacy ON flagged_reviews(pharmacy_id);
-- ── Audit Chain ──
CREATE TABLE IF NOT EXISTS audit_chain (
    id SERIAL PRIMARY KEY,
    verification_id TEXT NOT NULL,
    record_hash TEXT NOT NULL UNIQUE,
    previous_hash TEXT NOT NULL,
    data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_audit_created ON audit_chain(created_at DESC);

-- ── Caregiver Links ──
CREATE TABLE IF NOT EXISTS caregiver_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invite_code TEXT UNIQUE,            -- legacy name; the API uses `code`
    code TEXT UNIQUE,
    creator_user_id TEXT,
    caregiver_id TEXT,                  -- app user IDs are opaque strings, not necessarily UUIDs
    recipient_name TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'revoked')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_caregiver_code ON caregiver_links(invite_code);

-- ── Drug Scan History (for refill prediction) ──
CREATE TABLE IF NOT EXISTS scan_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    ndc TEXT NOT NULL,
    drug_name TEXT,
    scanned_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scan_history_user ON scan_history(user_id, scanned_at DESC);

-- ── Family Members ──
CREATE TABLE IF NOT EXISTS family_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    name TEXT NOT NULL,
    age INTEGER,
    conditions_raw TEXT,
    conditions_normalized JSONB
);

-- ── Medicine Cabinet ──
CREATE TABLE IF NOT EXISTS medicine_cabinet (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    medicine_name TEXT NOT NULL,
    expiry_date TEXT,
    scanned_at TIMESTAMPTZ DEFAULT NOW(),
    rxcui TEXT,
    quantity_remaining INTEGER,
    daily_dose_units INTEGER,
    days_supply_remaining INTEGER GENERATED ALWAYS AS 
      (CASE WHEN daily_dose_units > 0 
       THEN quantity_remaining / daily_dose_units 
       ELSE NULL END) STORED
);

-- ── Safety Check Log ──
CREATE TABLE IF NOT EXISTS safety_check_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checked_at TIMESTAMPTZ DEFAULT NOW(),
    user_id TEXT NOT NULL,
    member_id TEXT NOT NULL,
    medicine_name_raw TEXT NOT NULL,
    medicine_name_resolved TEXT,
    rxcui TEXT,
    conditions_raw TEXT,
    conditions_normalized JSONB,
    verdict BOOLEAN NOT NULL,
    verdict_source TEXT NOT NULL,
    verdict_reason TEXT,
    llm_prompt TEXT,
    llm_response TEXT
);

-- ═══════════════════════════════════════════════════════════════
-- PostGIS Functions for Geospatial Queries
-- ═══════════════════════════════════════════════════════════════

-- Find nearby pharmacies using PostGIS ST_DWithin
CREATE OR REPLACE FUNCTION nearby_pharmacies(
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    radius_m INTEGER DEFAULT 5000
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    address TEXT,
    trust_score REAL,
    total_verifications INTEGER,
    verification_pass_rate REAL,
    flagged_reviews INTEGER,
    is_claimed BOOLEAN,
    lat_out DOUBLE PRECISION,
    lng_out DOUBLE PRECISION,
    distance_m DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        p.id,
        p.name,
        p.address,
        p.trust_score,
        p.total_verifications,
        p.verification_pass_rate,
        p.flagged_reviews,
        p.is_claimed,
        ST_Y(p.location::geometry) AS lat_out,
        ST_X(p.location::geometry) AS lng_out,
        ST_Distance(p.location, ST_MakePoint(lng, lat)::geography) AS distance_m
    FROM pharmacies p
    WHERE ST_DWithin(p.location, ST_MakePoint(lng, lat)::geography, radius_m)
    ORDER BY distance_m ASC;
END;
$$ LANGUAGE plpgsql;

-- Find nearby doctors using PostGIS ST_DWithin
CREATE OR REPLACE FUNCTION nearby_doctors(
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    radius_m INTEGER DEFAULT 10000
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    specialty TEXT,
    address TEXT,
    accepts_digital_prescriptions BOOLEAN,
    trust_score REAL,
    lat_out DOUBLE PRECISION,
    lng_out DOUBLE PRECISION,
    distance_m DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.name,
        d.specialty,
        d.address,
        d.accepts_digital_prescriptions,
        d.trust_score,
        ST_Y(d.location::geometry) AS lat_out,
        ST_X(d.location::geometry) AS lng_out,
        ST_Distance(d.location, ST_MakePoint(lng, lat)::geography) AS distance_m
    FROM doctors d
    WHERE ST_DWithin(
        d.location,
        ST_MakePoint(lng, lat)::geography,
        radius_m
    )
    ORDER BY distance_m ASC;
END;
$$ LANGUAGE plpgsql;

-- Fuzzy matching for drug aliases
CREATE OR REPLACE FUNCTION fuzzy_drug_alias(query_text TEXT, similarity_threshold FLOAT)
RETURNS TABLE(canonical_name TEXT, active_ingredients TEXT[], similarity FLOAT) AS $$
    SELECT canonical_name, active_ingredients, similarity(drug_alias, query_text) AS similarity
    FROM vernacular_aliases
    WHERE similarity(drug_alias, query_text) > similarity_threshold
    ORDER BY similarity DESC
    LIMIT 1;
$$ LANGUAGE sql STABLE;

-- Find nearby reports for heatmap
CREATE OR REPLACE FUNCTION nearby_reports(
    lat DOUBLE PRECISION,
    lng DOUBLE PRECISION,
    radius_m INTEGER DEFAULT 50000
)
RETURNS TABLE (
    id UUID,
    drug_name TEXT,
    city TEXT,
    status TEXT,
    lat_out DOUBLE PRECISION,
    lng_out DOUBLE PRECISION,
    created_at TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.drug_name,
        r.city,
        r.status,
        ST_Y(r.location::geometry) AS lat_out,
        ST_X(r.location::geometry) AS lng_out,
        r.created_at
    FROM reports r
    WHERE ST_DWithin(r.location, ST_MakePoint(lng, lat)::geography, radius_m)
    ORDER BY r.created_at DESC
    LIMIT 200;
END;
$$ LANGUAGE plpgsql;

-- ═══════════════════════════════════════════════════════════════
-- Row Level Security (optional — enable for production)
-- ═══════════════════════════════════════════════════════════════

-- ALTER TABLE verifications ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE reports ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE pharmacies ENABLE ROW LEVEL SECURITY;

-- Allow anonymous reads for public data
-- CREATE POLICY "Public read verifications" ON verifications FOR SELECT USING (true);
-- CREATE POLICY "Public read reports" ON reports FOR SELECT USING (true);
-- CREATE POLICY "Public read pharmacies" ON pharmacies FOR SELECT USING (true);

-- ═══════════════════════════════════════════════════════════════
-- Cold Chain History (Feature 2)
-- ═══════════════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION cold_chain_history(
    p_ndc TEXT,
    p_lat DOUBLE PRECISION,
    p_lng DOUBLE PRECISION,
    p_radius_m INTEGER DEFAULT 50000
)
RETURNS TABLE (
    temperature_c REAL,
    humidity_pct REAL,
    created_at TIMESTAMPTZ,
    distance_m DOUBLE PRECISION
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        v.temperature_c,
        v.humidity_pct,
        v.created_at,
        ST_Distance(v.location, ST_MakePoint(p_lng, p_lat)::geography) AS distance_m
    FROM verifications v
    WHERE v.ndc = p_ndc
      AND v.temperature_c IS NOT NULL
      AND ST_DWithin(v.location, ST_MakePoint(p_lng, p_lat)::geography, p_radius_m)
    ORDER BY v.created_at DESC
    LIMIT 30;
END;
$$ LANGUAGE plpgsql;

-- ═══════════════════════════════════════════════════════════════
-- Push Subscriptions (Feature 5 — Refill Notifications)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS push_subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    endpoint TEXT NOT NULL UNIQUE,
    p256dh_key TEXT NOT NULL,
    auth_key TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_push_subs_user ON push_subscriptions(user_id);

-- ═══════════════════════════════════════════════════════════════
-- Enterprise Features
-- ═══════════════════════════════════════════════════════════════

-- ── Clinics (Multi-tenant B2B) ──
CREATE TABLE IF NOT EXISTS clinics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    address TEXT,
    contact_email TEXT UNIQUE,
    password_hash TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tenant/owner columns the API writes. These were a commented-out manual step, which made the
-- index below fail on a fresh database and left verifications without an owner column.
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS clinic_id UUID REFERENCES clinics(id);
ALTER TABLE verifications ADD COLUMN IF NOT EXISTS user_id TEXT;
ALTER TABLE scan_history ADD COLUMN IF NOT EXISTS clinic_id UUID REFERENCES clinics(id);
ALTER TABLE medicine_cabinet ADD COLUMN IF NOT EXISTS clinic_id UUID REFERENCES clinics(id);
CREATE INDEX IF NOT EXISTS idx_verifications_user ON verifications(user_id, created_at DESC);

CREATE INDEX idx_verifications_clinic_date ON verifications(clinic_id, created_at);

-- ── CDSCO Recalls (India) ──
CREATE TABLE IF NOT EXISTS cdsco_recalls (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_name TEXT NOT NULL,
    batch_no TEXT,
    manufacturer TEXT,
    reason TEXT,
    date_issued DATE,
    url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(drug_name, batch_no)
);
CREATE INDEX idx_cdsco_drug ON cdsco_recalls(drug_name);
CREATE INDEX idx_cdsco_batch ON cdsco_recalls(batch_no);

CREATE TABLE IF NOT EXISTS scrape_errors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source TEXT NOT NULL,
    raw_html TEXT,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── PvPI Adverse Event Reports (India) ──
CREATE TABLE IF NOT EXISTS pvpi_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    verification_id TEXT NOT NULL,
    drug_name TEXT NOT NULL,
    patient_initials TEXT,
    patient_age INTEGER,
    adverse_event_description TEXT NOT NULL,
    date_of_onset DATE,
    reporter_name TEXT,
    reporter_type TEXT CHECK (reporter_type IN ('physician', 'pharmacist', 'patient', 'other')),
    status TEXT DEFAULT 'pending_submission' CHECK (status IN ('pending_submission', 'submitted', 'failed')),
    pvpi_reference_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── Audit Export Jobs ──
CREATE TABLE IF NOT EXISTS export_jobs (
    id UUID PRIMARY KEY,
    status TEXT NOT NULL,
    format TEXT NOT NULL,
    file_path TEXT,
    filename TEXT,
    error TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- ── Schedule Classifications (India) ──
CREATE TABLE IF NOT EXISTS schedule_classifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    generic_name TEXT NOT NULL UNIQUE,
    schedule TEXT NOT NULL CHECK (schedule IN ('H', 'H1', 'X', 'OTC', 'GSL')),
    source TEXT DEFAULT 'cdsco',
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_schedule_generic ON schedule_classifications(generic_name);
