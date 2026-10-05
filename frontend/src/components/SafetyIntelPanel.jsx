import React from 'react';
import { describeVerdict, recallText } from '../utils/verdictCopy';

const TONE = { ok: 'var(--primary)', warn: 'var(--danger-amber)', danger: 'var(--danger-red)', neutral: 'var(--offline-slate)' };
const SEVERITY_TONE = { critical: TONE.danger, warn: TONE.warn, info: TONE.neutral };

/** Plain-language summary of why a pack got its verdict (v2 response fields; all optional). */
export default function SafetyIntelPanel({ data }) {
  if (!data) return null;
  const v = describeVerdict(data.verdict, data.verdict_reasons || []);
  const findings = data.pack_check?.findings || [];
  const lasa = data.lasa?.warnings || [];
  const cov = data.batch_alerts?.coverage;

  return (
    <section className="card" aria-labelledby="safety-intel-title" style={{ borderLeft: `4px solid ${TONE[v.tone]}`, marginBottom: '1rem' }}>
      <h3 id="safety-intel-title" style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '0.35rem' }}>{v.label}</h3>
      <p style={{ margin: '0 0 0.75rem' }}>{v.advice}</p>

      {v.reasons.length > 0 && (
        <ul style={{ margin: '0 0 0.75rem', paddingLeft: '1.1rem' }}>
          {v.reasons.map((r) => <li key={r}>{r}</li>)}
        </ul>
      )}

      {data.recall_status && <p style={{ margin: '0 0 0.5rem', color: 'var(--text-muted)' }}>{recallText(data.recall_status)}</p>}

      {findings.length > 0 && (
        <div style={{ marginTop: '0.75rem' }}>
          <h4 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '0.35rem' }}>Label check</h4>
          <ul style={{ margin: 0, paddingLeft: 0, listStyle: 'none' }}>
            {findings.map((f, i) => (
              <li key={`${f.code}-${i}`} style={{ borderLeft: `3px solid ${SEVERITY_TONE[f.severity] || TONE.neutral}`, padding: '0.25rem 0 0.25rem 0.6rem', marginBottom: '0.35rem' }}>
                <span className="sr-only">{f.severity}: </span>{f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {cov && (
        <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
          {cov.status === 'available'
            ? `Batch checked against regulator alerts from ${cov.earliest_month} to ${cov.latest_month}.`
            : 'Regulator batch alerts are not loaded, so the batch was not checked.'}
          {cov.is_sample_data && <strong style={{ color: TONE.warn }}> Demo data only, not real regulator alerts.</strong>}
        </p>
      )}

      {lasa.length > 0 && (
        <div role="note" style={{ marginTop: '0.75rem', padding: '0.6rem 0.75rem', background: 'var(--bg-secondary)', borderRadius: 8 }}>
          <strong>Similar medicine names exist.</strong>
          <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.1rem' }}>
            {lasa.slice(0, 3).map((w) => <li key={w.similar_name}>{w.message}</li>)}
          </ul>
        </div>
      )}
      {data.audit_status === 'failed' && <p role="alert" style={{ color: TONE.warn, marginTop: '0.5rem' }}>This check could not be saved to the audit trail.</p>}
    </section>
  );
}
