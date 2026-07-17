-- Enterprise incident workflow for suspected falsified, recalled, or damaged medicines.
CREATE TABLE IF NOT EXISTS safety_cases (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    clinic_id TEXT,
    verification_id UUID,
    medicine_name TEXT NOT NULL,
    batch_number TEXT,
    issue_type TEXT NOT NULL CHECK (issue_type IN ('suspected_falsified', 'recall', 'quality_defect', 'storage_concern', 'adverse_event', 'other')),
    notes TEXT NOT NULL,
    quarantined BOOLEAN NOT NULL DEFAULT false,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'triaged', 'escalated', 'resolved', 'dismissed')),
    resolution_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_safety_cases_user_created ON safety_cases (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_safety_cases_clinic_status ON safety_cases (clinic_id, status);
ALTER TABLE safety_cases ENABLE ROW LEVEL SECURITY;
CREATE POLICY safety_cases_owner_or_admin ON safety_cases FOR ALL
    USING (user_id = current_setting('request.header.x-user-id', true) OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin'))
    WITH CHECK (user_id = current_setting('request.header.x-user-id', true) OR current_setting('request.header.x-user-role', true) IN ('admin', 'clinic_admin'));
