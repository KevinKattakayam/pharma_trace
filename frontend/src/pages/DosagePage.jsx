import React, { useState, useCallback } from 'react';
import api from '../utils/api';

export default function DosagePage() {
  const [ndc, setNdc] = useState('');
  const [age, setAge] = useState('');
  const [weight, setWeight] = useState('');
  const [kidney, setKidney] = useState('normal');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleCheck = useCallback(async (e) => {
    e.preventDefault();
    if (!ndc.trim() || !age || !weight) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await api.request(`/drugs/${encodeURIComponent(ndc.trim())}/dosage`, {
        method: 'POST',
        body: JSON.stringify({
          age: parseInt(age),
          weight_kg: parseFloat(weight),
          kidney_function: kidney
        })
      });
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [ndc, age, weight, kidney]);

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 700 }}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> Patient Safety
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>
            Dosage Personalizer
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', maxWidth: 520, margin: '0 auto' }}>
            Enter patient data to check if the standard dose is appropriate. Flags dangerous dosing for the elderly, children, and patients with kidney disease.
          </p>
        </div>

        <div className="card anim anim-d1" style={{ marginBottom: '1.5rem' }}>
          <form onSubmit={handleCheck}>
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label className="form-label" htmlFor="dosage-ndc">Drug NDC Code</label>
              <input id="dosage-ndc" type="text" value={ndc} onChange={e => setNdc(e.target.value)}
                placeholder="e.g., 59726-065-30" />
            </div>

            <div className="form-grid" style={{ marginBottom: '0.85rem' }}>
              <div className="form-group">
                <label className="form-label" htmlFor="dosage-age">Patient Age</label>
                <input id="dosage-age" type="number" min="0" max="120" value={age}
                  onChange={e => setAge(e.target.value)} placeholder="Years" />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="dosage-weight">Weight (kg)</label>
                <input id="dosage-weight" type="number" min="1" max="300" value={weight}
                  onChange={e => setWeight(e.target.value)} placeholder="Kilograms" />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '1.25rem' }}>
              <label className="form-label" htmlFor="dosage-kidney">Kidney Function</label>
              <select id="dosage-kidney" value={kidney} onChange={e => setKidney(e.target.value)}>
                <option value="normal">Normal</option>
                <option value="mild">Mild Impairment (eGFR 60-89)</option>
                <option value="moderate">Moderate Impairment (eGFR 30-59)</option>
                <option value="severe">Severe Impairment (eGFR &lt; 30)</option>
              </select>
            </div>

            <button type="submit" className="btn btn--primary btn--lg" style={{ width: '100%' }} disabled={!ndc.trim() || !age || !weight || loading}>
              {loading ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Analyzing…</> : 'Check Dosage Safety'}
            </button>
          </form>
        </div>

        {error && (
          <div className="card card--danger anim" style={{ textAlign: 'center' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.8125rem' }}>{error}</p>
          </div>
        )}

        {result && (
          <div className="anim">
            {/* Risk Level */}
            <div className={`card card--${result.risk_level === 'high' ? 'danger' : result.risk_level === 'moderate' ? 'warning' : 'safe'}`}
              style={{ marginBottom: '1rem', textAlign: 'center', padding: '1.75rem' }}>
              <div style={{
                width: 48, height: 48, borderRadius: '50%', margin: '0 auto 0.75rem',
                display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.25rem',
                background: result.risk_level === 'high' ? 'var(--danger-bg)' : result.risk_level === 'moderate' ? 'var(--warn-bg)' : 'var(--safe-bg)',
                border: `1px solid ${result.risk_level === 'high' ? 'rgba(239,68,68,0.2)' : result.risk_level === 'moderate' ? 'rgba(245,158,11,0.2)' : 'rgba(0,229,191,0.2)'}`
              }}>
                {result.risk_level === 'high' ? '⚠' : result.risk_level === 'moderate' ? '◉' : '✓'}
              </div>
              <h3 style={{ fontSize: '1.125rem', fontWeight: 800, marginBottom: '0.25rem' }}>
                {result.risk_level === 'high' ? 'High Risk — Dosage Adjustment Required'
                  : result.risk_level === 'moderate' ? 'Moderate Risk — Monitor Closely'
                    : 'Low Risk — Standard Dosage Appropriate'}
              </h3>
            </div>

            {/* Adjustments */}
            {result.adjustments && result.adjustments.length > 0 && (
              <div className="card" style={{ marginBottom: '1rem' }}>
                <div className="drug-result__section-title">Dosage Adjustments</div>
                {result.adjustments.map((adj, i) => (
                  <div key={i} style={{
                    padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)',
                    borderRadius: '8px', marginBottom: '0.4rem', fontSize: '0.8125rem',
                    color: 'var(--text-2)', borderLeft: '2px solid var(--accent)',
                    border: '1px solid var(--border-1)'
                  }}>
                    {adj}
                  </div>
                ))}
              </div>
            )}

            {/* Warnings */}
            {result.warnings && result.warnings.length > 0 && (
              <div className="card card--danger">
                <div className="drug-result__section-title" style={{ color: 'var(--danger)' }}>Clinical Warnings</div>
                {result.warnings.map((w, i) => (
                  <div key={i} style={{
                    padding: '0.65rem 0.85rem', background: 'var(--danger-bg)',
                    borderRadius: '8px', marginBottom: '0.4rem', fontSize: '0.8125rem',
                    color: 'var(--danger)', borderLeft: '2px solid var(--danger)'
                  }}>
                    {w}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
