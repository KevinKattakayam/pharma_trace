-- ═══════════════════════════════════════════════════════════════
-- PharmaTrace — Supabase Database Schema (PostgreSQL + PostGIS)
-- Run this in the Supabase SQL Editor to set up the database.
-- ═══════════════════════════════════════════════════════════════

-- Enable PostGIS for geospatial queries
CREATE EXTENSION IF NOT EXISTS postgis;

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
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_pharmacies_trust ON pharmacies(trust_score DESC);
CREATE INDEX idx_pharmacies_location ON pharmacies USING GIST(location);

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
    invite_code TEXT UNIQUE NOT NULL,
    caregiver_id UUID,
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
        ST_Y(p.location::geometry) AS lat_out,
        ST_X(p.location::geometry) AS lng_out,
        ST_Distance(p.location, ST_MakePoint(lng, lat)::geography) AS distance_m
    FROM pharmacies p
    WHERE ST_DWithin(p.location, ST_MakePoint(lng, lat)::geography, radius_m)
    ORDER BY distance_m ASC
    LIMIT 50;
END;
$$ LANGUAGE plpgsql;

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
