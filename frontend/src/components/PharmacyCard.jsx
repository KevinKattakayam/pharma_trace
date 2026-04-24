import React from 'react';

export default function PharmacyCard({ pharmacy }) {
  const score = pharmacy?.trust_score || 50;
  const status = score >= 70 ? 'safe' : score >= 40 ? 'warn' : 'danger';
  const color = `var(--${status})`;

  return (
    <div className="card anim-up" style={{ cursor: 'pointer', padding: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1.25rem' }}>
        <div style={{
          width: 48, height: 48, borderRadius: '12px',
          background: 'var(--bg-tertiary)', border: '1px solid var(--border-1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.25rem', flexShrink: 0, boxShadow: 'inset 0 0 12px rgba(255,255,255,0.02)'
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"><path d="M3 21h18M3 7v1a3 3 0 006 0V4m0 4V4m0 4a3 3 0 006 0V4m0 4V4m0 4a3 3 0 006 0V4m-6 17h1m-7 0h1"/></svg>
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '0.25rem', letterSpacing: '-0.02em', color: 'var(--text-1)' }}>
            {pharmacy?.name || 'Authorized Pharmacy'}
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.4 }}>
            {pharmacy?.address || 'Geolocation data pending decryption...'}
          </p>
        </div>
      </div>

      <div className="trust-meter" style={{ marginBottom: '1.25rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
          <span style={{ fontSize: '0.625rem', fontWeight: 800, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Trust Integrity
          </span>
          <span style={{ fontSize: '0.875rem', fontWeight: 900, color: color, fontFamily: 'var(--mono)' }}>
            {Math.round(score)}%
          </span>
        </div>
        <div className="trust-meter__bar" style={{ height: '6px', background: 'var(--bg-tertiary)', borderRadius: '10px', overflow: 'hidden' }}>
          <div
            className="trust-meter__fill"
            style={{ 
              width: `${score}%`, 
              height: '100%',
              background: `linear-gradient(90deg, var(--accent), ${color})`,
              boxShadow: `0 0 8px ${color}44`
            }}
          />
        </div>
      </div>

      <div style={{
        display: 'flex', gap: '0.75rem', alignItems: 'center',
        fontSize: '0.6875rem', color: 'var(--text-3)', fontWeight: 600
      }}>
        <span style={{ color: 'var(--text-2)' }}>{pharmacy?.total_verifications || 0} verifications</span>
        <span style={{ opacity: 0.3 }}>•</span>
        <span>Pass rate: <span style={{ color: 'var(--safe)' }}>{pharmacy?.verification_pass_rate ? `${Math.round(pharmacy.verification_pass_rate)}%` : '—'}</span></span>
      </div>

      {pharmacy?.flagged_reviews > 0 && (
        <div style={{
          marginTop: '1rem', padding: '0.6rem 0.75rem',
          background: 'var(--warn-bg)', borderRadius: '8px',
          border: '1px solid rgba(251, 191, 36, 0.15)',
          fontSize: '0.6875rem', color: 'var(--warn)', fontWeight: 600,
          display: 'flex', alignItems: 'center', gap: '0.5rem'
        }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          ML Flag: {pharmacy.flagged_reviews} suspicious signals
        </div>
      )}
    </div>
  );
}

