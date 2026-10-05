-- Phase 5: make the audit chain real (audit findings R1, R6).
-- Idempotent. Needs PostgreSQL 11+ (built-in sha256()); no extensions required.

CREATE TABLE IF NOT EXISTS audit_chain (
    id              BIGSERIAL PRIMARY KEY,
    verification_id TEXT        NOT NULL,
    record_hash     TEXT        NOT NULL UNIQUE,
    previous_hash   TEXT        NOT NULL,
    data            JSONB,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE audit_chain ADD COLUMN IF NOT EXISTS canonical  TEXT;
ALTER TABLE audit_chain ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'verification';
ALTER TABLE audit_chain ALTER COLUMN data DROP NOT NULL;

-- Each hash may be the predecessor of exactly one record: forks are impossible.
DO $$ BEGIN
    ALTER TABLE audit_chain ADD CONSTRAINT audit_chain_previous_hash_unique UNIQUE (previous_hash);
EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL; END $$;

CREATE INDEX IF NOT EXISTS idx_audit_chain_verification ON audit_chain(verification_id);

-- Append-only: triggers apply even to the service role (which bypasses RLS).
CREATE OR REPLACE FUNCTION audit_chain_block_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit_chain is append-only (% blocked)', TG_OP;
END $$;

DROP TRIGGER IF EXISTS trg_audit_chain_no_update ON audit_chain;
CREATE TRIGGER trg_audit_chain_no_update BEFORE UPDATE OR DELETE ON audit_chain
    FOR EACH ROW EXECUTE FUNCTION audit_chain_block_mutation();
DROP TRIGGER IF EXISTS trg_audit_chain_no_truncate ON audit_chain;
CREATE TRIGGER trg_audit_chain_no_truncate BEFORE TRUNCATE ON audit_chain
    FOR EACH STATEMENT EXECUTE FUNCTION audit_chain_block_mutation();

-- Serialised append. The application computes the canonical JSON string; the database
-- computes the hash so concurrent API workers cannot race on "read last hash".
CREATE OR REPLACE FUNCTION append_audit_record(
    p_verification_id TEXT,
    p_event_type      TEXT,
    p_canonical       TEXT
) RETURNS audit_chain
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
    v_prev TEXT;
    v_row  audit_chain;
BEGIN
    IF p_canonical IS NULL OR length(p_canonical) = 0 THEN
        RAISE EXCEPTION 'canonical payload required';
    END IF;
    PERFORM pg_advisory_xact_lock(hashtext('pharmatrace.audit_chain'));
    SELECT record_hash INTO v_prev FROM audit_chain ORDER BY id DESC LIMIT 1;
    IF v_prev IS NULL THEN
        v_prev := encode(sha256(convert_to('PHARMATRACE_GENESIS', 'UTF8')), 'hex');
    END IF;
    INSERT INTO audit_chain (verification_id, event_type, previous_hash, record_hash, canonical)
    VALUES (
        p_verification_id,
        p_event_type,
        v_prev,
        encode(sha256(convert_to(v_prev || p_canonical, 'UTF8')), 'hex'),
        p_canonical
    )
    RETURNING * INTO v_row;
    RETURN v_row;
END $$;

REVOKE ALL ON FUNCTION append_audit_record(TEXT, TEXT, TEXT) FROM PUBLIC;
-- Grant to the role your API uses (Supabase: service_role).
DO $$ BEGIN
    GRANT EXECUTE ON FUNCTION append_audit_record(TEXT, TEXT, TEXT) TO service_role;
EXCEPTION WHEN undefined_object THEN NULL; END $$;
