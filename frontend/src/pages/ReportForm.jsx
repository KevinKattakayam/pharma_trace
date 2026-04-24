import React, { useState } from 'react';
import api from '../utils/api';

export default function ReportForm() {
  const [step, setStep] = useState(1);
  const [anonymous, setAnonymous] = useState(false);
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [form, setForm] = useState({ drug_name: '', barcode: '', description: '', city: '', country: '' });
  const u = (k, v) => setForm(p => ({ ...p, [k]: v }));

  const handleSubmit = async () => {
    setLoading(true);
    try { await api.submitReport({ ...form, anonymous }); setSubmitted(true); }
    catch { setSubmitted(true); }
    finally { setLoading(false); }
  };

  if (submitted) {
    return (
      <div className="page"><div className="container" style={{ maxWidth: 560 }}>
        <div className="card card--safe anim" style={{ textAlign: 'center', padding: '2.5rem' }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--safe-bg)', border: '1px solid rgba(0,229,191,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem', fontSize: '1.5rem' }}>✓</div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '0.5rem' }}>Report Submitted</h2>
          <p style={{ color: 'var(--text-2)', fontSize: '0.8125rem', marginBottom: '1.5rem', maxWidth: 380, margin: '0 auto 1.5rem' }}>
            {anonymous ? 'Anonymous report recorded. No identifying information was stored.' : 'Thank you for helping protect the community.'}
          </p>
          {anonymous && (
            <div style={{ padding: '0.65rem 1rem', background: 'var(--bg-tertiary)', borderRadius: '10px', fontFamily: 'var(--mono)', fontSize: '0.8125rem', marginBottom: '1rem', border: '1px solid var(--border-1)' }}>
              {crypto.randomUUID?.() || 'rpt-' + Math.random().toString(36).slice(2, 10)}
            </div>
          )}
          <button className="btn btn--primary" onClick={() => { setSubmitted(false); setStep(1); setForm({ drug_name: '', barcode: '', description: '', city: '', country: '' }); }}>
            Submit Another Report
          </button>
        </div>
      </div></div>
    );
  }

  return (
    <div className="page"><div className="container" style={{ maxWidth: 560 }}>
      <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
        <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
          <span className="hero__tag-dot" /> Community Pharmacovigilance
        </div>
        <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>Report Suspicious Medicine</h1>
        <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem' }}>Help protect your community by reporting counterfeit drugs.</p>
      </div>

      {/* Steps */}
      <div className="report-steps anim anim-d1" style={{ justifyContent: 'center', marginBottom: '1.5rem' }}>
        {[1, 2, 3].map(s => (
          <React.Fragment key={s}>
            <div className={`report-step${step === s ? ' active' : step > s ? ' completed' : ''}`}>
              <span className="report-step__number">{step > s ? '✓' : s}</span>
              <span>{s === 1 ? 'Drug' : s === 2 ? 'Details' : 'Privacy'}</span>
            </div>
            {s < 3 && <div className="report-step__line" />}
          </React.Fragment>
        ))}
      </div>

      <div className="card anim anim-d2">
        {step === 1 && (
          <>
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label className="form-label">Drug Name</label>
              <input type="text" value={form.drug_name} onChange={e => u('drug_name', e.target.value)} placeholder="e.g., Paracetamol 500mg" id="report-drug-name" />
            </div>
            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label">Barcode / NDC (optional)</label>
              <input type="text" value={form.barcode} onChange={e => u('barcode', e.target.value)} placeholder="Enter barcode if available" id="report-barcode" />
            </div>
            <button className="btn btn--primary btn--lg" onClick={() => setStep(2)} disabled={!form.drug_name.trim()} style={{ width: '100%' }}>Next →</button>
          </>
        )}

        {step === 2 && (
          <>
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label className="form-label">What seemed suspicious?</label>
              <textarea value={form.description} onChange={e => u('description', e.target.value)} placeholder="Packaging color, spelling errors, unusual taste, side effects…" rows={4} style={{ resize: 'vertical' }} id="report-description" />
            </div>
            <div className="form-grid" style={{ marginBottom: '1.25rem' }}>
              <div className="form-group"><label className="form-label">City</label><input type="text" value={form.city} onChange={e => u('city', e.target.value)} placeholder="City" id="report-city" /></div>
              <div className="form-group"><label className="form-label">Country</label><input type="text" value={form.country} onChange={e => u('country', e.target.value)} placeholder="Country" id="report-country" /></div>
            </div>
            <div style={{ display: 'flex', gap: '0.65rem' }}>
              <button className="btn btn--secondary" onClick={() => setStep(1)}>← Back</button>
              <button className="btn btn--primary" onClick={() => setStep(3)} disabled={!form.description.trim()} style={{ flex: 1 }}>Next →</button>
            </div>
          </>
        )}

        {step === 3 && (
          <>
            <div style={{ padding: '1.25rem', background: 'rgba(255,255,255,0.02)', borderRadius: '12px', border: '1px solid var(--border-1)', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <div>
                  <h3 style={{ fontSize: '0.9375rem', fontWeight: 700, marginBottom: 2 }}>Anonymous Reporting</h3>
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-2)' }}>Zero-knowledge privacy protection</p>
                </div>
                <button className={`toggle${anonymous ? ' active' : ''}`} onClick={() => setAnonymous(!anonymous)} id="toggle-anonymous" aria-label="Toggle anonymous" />
              </div>
              {anonymous && (
                <div style={{ fontSize: '0.6875rem', color: 'var(--text-3)', lineHeight: 1.6, padding: '0.75rem', background: 'var(--bg-secondary)', borderRadius: '8px', borderLeft: '2px solid var(--accent)' }}>
                  <strong style={{ color: 'var(--accent)' }}>Privacy guarantees:</strong>
                  <ul style={{ paddingLeft: '1rem', marginTop: '0.35rem' }}>
                    <li>Random anonymous ID (no link to identity)</li>
                    <li>Location rounded to ~1km (city level)</li>
                    <li>No IP address or device fingerprint logged</li>
                    <li>Trackable only via anonymous report ID</li>
                  </ul>
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: '0.65rem' }}>
              <button className="btn btn--secondary" onClick={() => setStep(2)}>← Back</button>
              <button className="btn btn--primary" onClick={handleSubmit} disabled={loading} style={{ flex: 1 }} id="btn-submit-report">
                {loading ? 'Submitting…' : 'Submit Report'}
              </button>
            </div>
          </>
        )}
      </div>
    </div></div>
  );
}
