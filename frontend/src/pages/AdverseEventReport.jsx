import React, { useState, useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import api from '../utils/api';

const OUTCOMES = [
  { value: 'recovered', label: 'Recovered' },
  { value: 'recovering', label: 'Recovering' },
  { value: 'not_recovered', label: 'Not Recovered' },
  { value: 'fatal', label: 'Fatal' },
  { value: 'unknown', label: 'Unknown' },
];

const REPORTER_TYPES = [
  { value: 'physician', label: 'Physician' },
  { value: 'pharmacist', label: 'Pharmacist' },
  { value: 'nurse', label: 'Nurse' },
  { value: 'patient', label: 'Patient / Caregiver' },
  { value: 'other', label: 'Other' },
];

const FormField = ({ label, required, children }) => (
  <div style={{ marginBottom: '1rem' }}>
    <label style={{ display: 'block', fontSize: '0.75rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-3)', marginBottom: '0.35rem' }}>
      {label} {required && <span style={{ color: 'var(--danger)' }}>*</span>}
    </label>
    {children}
  </div>
);

export default function AdverseEventReport() {
  const location = useLocation();
  const [step, setStep] = useState(1); // 1: form, 2: preview, 3: done
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState(null);

  // Drug info (can be pre-filled from a verification result)
  const [verificationId, setVerificationId] = useState('');
  const [drugName, setDrugName] = useState('');
  const [brandName, setBrandName] = useState('');
  const [manufacturer, setManufacturer] = useState('');
  const [batchNo, setBatchNo] = useState('');

  useEffect(() => {
    if (location.state?.verificationData) {
      const data = location.state.verificationData;
      setVerificationId(data.verification_id || '');
      setDrugName(data.generic_name || data.brand_name || '');
      setBrandName(data.brand_name || '');
      setManufacturer(data.manufacturer || '');
    }
  }, [location.state]);

  // Patient
  const [initials, setInitials] = useState('');
  const [age, setAge] = useState('');
  const [sex, setSex] = useState('');

  // Event
  const [adverseEvent, setAdverseEvent] = useState('');
  const [dateOnset, setDateOnset] = useState('');
  const [outcome, setOutcome] = useState('unknown');
  const [seriousness, setSeriousness] = useState('non_serious');

  // Reporter
  const [reporterName, setReporterName] = useState('');
  const [reporterType, setReporterType] = useState('pharmacist');
  const [reporterInstitution, setReporterInstitution] = useState('');
  const [reporterEmail, setReporterEmail] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!drugName.trim() || !adverseEvent.trim()) return;

    setLoading(true);
    try {
      const res = await api.prefillPvpiReport({
        verification_id: verificationId || `manual-${Date.now()}`,
        drug_name: drugName,
        drug_brand_name: brandName,
        manufacturer,
        batch_no: batchNo,
        patient_initials: initials,
        patient_age: age ? parseInt(age) : null,
        patient_sex: sex,
        adverse_event: adverseEvent,
        date_of_onset: dateOnset || null,
        outcome,
        seriousness,
        reporter_name: reporterName,
        reporter_qualification: reporterType,
        reporter_institution: reporterInstitution,
        reporter_email: reporterEmail,
      });
      setFormData(res);
      setStep(2);
    } catch (err) {
      alert('Failed to generate report: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenPortal = () => {
    if (formData?.portal_url) {
      window.open(formData.portal_url, '_blank');
      setStep(3);
    }
  };

  return (
    <div className="page anim">
      <div className="container" style={{ maxWidth: 640, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '.75rem' }}>
            <span className="hero__tag-dot" /> Pharmacovigilance
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '.5rem' }}>
            Adverse Event Report
          </h1>
          <p style={{ color: 'var(--text-2)', fontSize: '.9375rem', maxWidth: 480, margin: '0 auto' }}>
            Report a suspected adverse drug reaction to India's PvPI programme. No patient-identifiable data is stored on PharmaTrace servers.
          </p>
        </div>

        {/* Step indicator */}
        <div style={{ display: 'flex', justifyContent: 'center', gap: '0.5rem', marginBottom: '2rem' }}>
          {['Fill Form', 'Review', 'Submit'].map((s, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem'
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: '0.7rem', fontWeight: 800,
                background: step > i + 1 ? 'var(--safe)' : step === i + 1 ? 'var(--accent)' : 'var(--bg-tertiary)',
                color: step >= i + 1 ? '#fff' : 'var(--text-3)',
                transition: 'all 0.3s var(--ease)'
              }}>
                {step > i + 1 ? '✓' : i + 1}
              </div>
              {i < 2 && <div style={{ width: 40, height: 2, background: step > i + 1 ? 'var(--safe)' : 'var(--border-1)' }} />}
            </div>
          ))}
        </div>

        {/* Step 1: Form */}
        {step === 1 && (
          <form onSubmit={handleSubmit}>
            {/* Drug Section */}
            <div className="card anim" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '0.875rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Section A — Suspected Medication
              </h3>
              <FormField label="Drug Name (Generic)" required>
                <input type="text" value={drugName} onChange={(e) => setDrugName(e.target.value)} placeholder="e.g. Paracetamol" required />
              </FormField>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <FormField label="Brand Name">
                  <input type="text" value={brandName} onChange={(e) => setBrandName(e.target.value)} placeholder="e.g. Crocin" />
                </FormField>
                <FormField label="Batch/Lot No.">
                  <input type="text" value={batchNo} onChange={(e) => setBatchNo(e.target.value)} placeholder="e.g. BN2024-A1" />
                </FormField>
              </div>
              <FormField label="Manufacturer">
                <input type="text" value={manufacturer} onChange={(e) => setManufacturer(e.target.value)} placeholder="e.g. GSK India" />
              </FormField>
              <FormField label="PharmaTrace Verification ID">
                <input type="text" value={verificationId} onChange={(e) => setVerificationId(e.target.value)} placeholder="Paste from scan result (optional)" style={{ fontFamily: 'var(--mono)', fontSize: '0.8125rem' }} />
              </FormField>
            </div>

            {/* Patient Section */}
            <div className="card anim" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '0.875rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Section B — Patient Information
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                <FormField label="Initials">
                  <input type="text" value={initials} onChange={(e) => setInitials(e.target.value)} placeholder="A.B." maxLength={5} />
                </FormField>
                <FormField label="Age">
                  <input type="number" value={age} onChange={(e) => setAge(e.target.value)} placeholder="45" min={0} max={120} />
                </FormField>
                <FormField label="Sex">
                  <select value={sex} onChange={(e) => setSex(e.target.value)}>
                    <option value="">—</option>
                    <option value="M">Male</option>
                    <option value="F">Female</option>
                    <option value="Other">Other</option>
                  </select>
                </FormField>
              </div>
            </div>

            {/* Adverse Event Section */}
            <div className="card anim" style={{ padding: '1.5rem', marginBottom: '1rem' }}>
              <h3 style={{ fontSize: '0.875rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Section C — Adverse Reaction
              </h3>
              <FormField label="Description of Adverse Event" required>
                <textarea rows={4} value={adverseEvent} onChange={(e) => setAdverseEvent(e.target.value)} placeholder="Describe the suspected adverse reaction in detail..." required />
              </FormField>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.75rem' }}>
                <FormField label="Date of Onset">
                  <input type="date" value={dateOnset} onChange={(e) => setDateOnset(e.target.value)} />
                </FormField>
                <FormField label="Outcome">
                  <select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
                    {OUTCOMES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </FormField>
                <FormField label="Seriousness">
                  <select value={seriousness} onChange={(e) => setSeriousness(e.target.value)}>
                    <option value="non_serious">Non-Serious</option>
                    <option value="serious">Serious</option>
                  </select>
                </FormField>
              </div>
            </div>

            {/* Reporter Section */}
            <div className="card anim" style={{ padding: '1.5rem', marginBottom: '1.5rem' }}>
              <h3 style={{ fontSize: '0.875rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Section D — Reporter
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                <FormField label="Reporter Name">
                  <input type="text" value={reporterName} onChange={(e) => setReporterName(e.target.value)} placeholder="Dr. Sharma" />
                </FormField>
                <FormField label="Qualification">
                  <select value={reporterType} onChange={(e) => setReporterType(e.target.value)}>
                    {REPORTER_TYPES.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
                  </select>
                </FormField>
              </div>
              <FormField label="Institution">
                <input type="text" value={reporterInstitution} onChange={(e) => setReporterInstitution(e.target.value)} placeholder="City District Hospital" />
              </FormField>
              <FormField label="Email">
                <input type="email" value={reporterEmail} onChange={(e) => setReporterEmail(e.target.value)} placeholder="reporter@hospital.org" />
              </FormField>
            </div>

            <button type="submit" className="btn btn--primary btn--lg" style={{ width: '100%' }} disabled={loading || !drugName.trim() || !adverseEvent.trim()}>
              {loading ? 'Generating Report...' : 'Preview Report →'}
            </button>
          </form>
        )}

        {/* Step 2: Preview */}
        {step === 2 && formData && (
          <div className="anim">
            <div className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem', border: '2px solid var(--accent)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem' }}>
                <span style={{ fontSize: '1.5rem' }}>📋</span>
                <div>
                  <h3 style={{ fontSize: '1.125rem', fontWeight: 800 }}>PvPI Report Preview</h3>
                  <p style={{ fontSize: '0.8125rem', color: 'var(--text-3)' }}>{formData.instructions}</p>
                </div>
              </div>

              <div style={{ background: 'var(--bg-primary)', borderRadius: '12px', padding: '1.25rem', border: '1px solid var(--border-1)' }}>
                {Object.entries(formData.form_fields).map(([key, value]) => {
                  if (!value || key.startsWith('pharmatrace_')) return null;
                  const label = key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
                  return (
                    <div key={key} style={{ display: 'flex', justifyContent: 'space-between', padding: '0.5rem 0', borderBottom: '1px solid var(--border-1)' }}>
                      <span style={{ fontSize: '0.8125rem', color: 'var(--text-3)', fontWeight: 600 }}>{label}</span>
                      <span style={{ fontSize: '0.8125rem', fontWeight: 700, textAlign: 'right', maxWidth: '60%' }}>{value}</span>
                    </div>
                  );
                })}
              </div>

              <div style={{ marginTop: '1rem', padding: '0.75rem', borderRadius: '8px', background: 'rgba(99,102,241,0.06)', border: '1px solid var(--accent)' }}>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-2)', lineHeight: 1.6 }}>
                  <strong>Privacy Notice:</strong> PharmaTrace does not store patient-identifiable data. Only the drug name, verification ID, and submission status are recorded locally for your tracking purposes.
                </p>
              </div>
            </div>

            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button className="btn btn--primary btn--lg" style={{ flex: 1 }} onClick={handleOpenPortal}>
                Open PvPI Portal to Manually Submit →
              </button>
              <button className="btn btn--secondary" onClick={() => setStep(1)}>Edit</button>
            </div>
          </div>
        )}

        {/* Step 3: Done */}
        {step === 3 && (
          <div className="card anim" style={{ padding: '2.5rem', textAlign: 'center' }}>
            <div style={{ fontSize: '4rem', marginBottom: '1rem' }}>✅</div>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 900, marginBottom: '0.5rem' }}>Form Ready for Submission</h2>
            <p style={{ color: 'var(--text-2)', fontSize: '0.9375rem', marginBottom: '1.5rem', maxWidth: 400, margin: '0 auto 1.5rem' }}>
              The PvPI portal has been opened in a new tab. Please manually enter your structured data into the official form to complete the submission.
            </p>
            <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
              <button className="btn btn--primary" onClick={() => { setStep(1); setFormData(null); }}>
                Prepare Another Report
              </button>
              <button className="btn btn--secondary" onClick={() => window.history.back()}>
                Back to Dashboard
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
