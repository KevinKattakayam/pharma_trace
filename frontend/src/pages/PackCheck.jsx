import React, { useState } from 'react';
import api from '../utils/api';

const STATUS = {
  consistent: { title: 'Label is consistent', tone: 'var(--primary)', text: 'The code and the printed label agree and the dates make sense. This does not prove the medicine is genuine.' },
  inconsistent: { title: 'Problems found on this pack', tone: 'var(--danger-red)', text: 'Do not use this medicine until a pharmacist has checked it.' },
  incomplete: { title: 'Some information is missing', tone: 'var(--danger-amber)', text: 'We could only check part of the label. Read the notes below.' },
  insufficient_data: { title: 'Nothing to check yet', tone: 'var(--offline-slate)', text: 'Enter the code contents or the printed details.' },
};
const SEV = { critical: 'var(--danger-red)', warn: 'var(--danger-amber)', info: 'var(--offline-slate)' };

export default function PackCheck() {
  const [qr, setQr] = useState('');
  const [printed, setPrinted] = useState({ batch_no: '', expiry_date: '', mfg_date: '' });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const field = (key, label, placeholder) => (
    <label style={{ display: 'grid', gap: '0.3rem', fontWeight: 600, fontSize: '0.875rem' }}>
      {label}
      <input value={printed[key]} placeholder={placeholder} maxLength={40}
        onChange={(e) => setPrinted({ ...printed, [key]: e.target.value })} />
    </label>
  );

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const p = Object.fromEntries(Object.entries(printed).filter(([, v]) => v.trim()));
      setResult(await api.packCheck(qr.trim() || null, Object.keys(p).length ? p : null));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const s = result && (STATUS[result.status] || STATUS.insufficient_data);
  return (
    <div className="page">
      <h1 style={{ fontSize: '1.6rem', fontWeight: 800, marginBottom: '0.4rem' }}>Check a pack’s label</h1>
      <p style={{ maxWidth: '62ch', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
        Copied QR codes are often stuck on fake packs. Compare what the code says with what is printed
        on the strip or box: batch number, expiry and manufacturing date.
      </p>

      <form className="card" onSubmit={submit} style={{ maxWidth: 560, display: 'grid', gap: '0.9rem' }}>
        <label style={{ display: 'grid', gap: '0.3rem', fontWeight: 600, fontSize: '0.875rem' }}>
          Code contents (from the Scan page or a QR reader app)
          <textarea rows={3} value={qr} maxLength={2048} onChange={(e) => setQr(e.target.value)}
            placeholder="Paste what the QR or DataMatrix code contains" />
        </label>
        <fieldset style={{ border: 0, padding: 0, margin: 0, display: 'grid', gap: '0.6rem', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))' }}>
          <legend style={{ fontWeight: 700, marginBottom: '0.4rem' }}>Printed on the pack</legend>
          {field('batch_no', 'Batch no.', 'e.g. AB1234')}
          {field('expiry_date', 'Expiry', 'e.g. 12/2027')}
          {field('mfg_date', 'Mfg. date', 'e.g. 01/2025')}
        </fieldset>
        <button type="submit" className="btn btn--primary btn--lg" disabled={loading || (!qr.trim() && !Object.values(printed).some((v) => v.trim()))}>
          {loading ? 'Checking…' : 'Check label'}
        </button>
      </form>

      {error && <div role="alert" className="card card--danger" style={{ maxWidth: 560, marginTop: '1rem' }}>{error}</div>}

      {result && (
        <section aria-live="polite" className="card" style={{ maxWidth: 560, marginTop: '1rem', borderLeft: `4px solid ${s.tone}` }}>
          <h2 style={{ fontSize: '1.15rem', fontWeight: 800, marginBottom: '0.3rem' }}>{s.title}</h2>
          <p style={{ marginTop: 0 }}>{s.text}</p>
          {result.findings.length > 0 && (
            <ul style={{ listStyle: 'none', padding: 0, margin: '0.75rem 0' }}>
              {result.findings.map((f, i) => (
                <li key={`${f.code}-${i}`} style={{ borderLeft: `3px solid ${SEV[f.severity] || SEV.info}`, padding: '0.3rem 0 0.3rem 0.65rem', marginBottom: '0.45rem' }}>
                  <span className="sr-only">{f.severity}: </span>{f.message}
                  {f.citation && <> <a href={f.citation} target="_blank" rel="noreferrer noopener">Source</a></>}
                </li>
              ))}
            </ul>
          )}
          {result.batch_alerts?.coverage?.is_sample_data && (
            <p style={{ color: 'var(--danger-amber-dark)', fontWeight: 700 }}>Demo data: regulator alerts shown here are samples, not real CDSCO records.</p>
          )}
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginBottom: 0 }}>{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
