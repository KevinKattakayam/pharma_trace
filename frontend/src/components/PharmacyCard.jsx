import React from 'react';
import { listingLabel, ratingText, ratingTone } from '../utils/pharmacyView';

/** One pharmacy listing. Shows where the listing came from and a community rating only when one exists. */
export default function PharmacyCard({ pharmacy }) {
  const rated = pharmacy?.trust_score != null;
  const tone = ratingTone(pharmacy);
  const color = `var(--${tone})`;

  return (
    <div className="card anim-up" style={{ padding: '1.5rem' }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem', marginBottom: '1rem' }}>
        <div style={{
          width: 48, height: 48, borderRadius: '12px', background: 'var(--bg-tertiary)', border: '1px solid var(--border-1)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M3 21h18M3 7v1a3 3 0 006 0V4m0 4V4m0 4a3 3 0 006 0V4m0 4V4m0 4a3 3 0 006 0V4m-6 17h1m-7 0h1" /></svg>
        </div>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '0.25rem', color: 'var(--text-1)' }}>
            {pharmacy?.name || 'Unnamed pharmacy'}
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.4, margin: 0 }}>
            {pharmacy?.address || 'No address listed'}
          </p>
        </div>
      </div>

      <p style={{ fontSize: '0.75rem', fontWeight: 700, color: pharmacy?.listing_status === 'claim_verified' ? 'var(--safe)' : 'var(--text-2)', margin: '0 0 0.75rem' }}>
        {listingLabel(pharmacy)}
      </p>

      <div style={{ marginBottom: '0.75rem' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: rated ? '0.5rem' : 0 }}>
          <span style={{ fontSize: '0.8125rem', color: 'var(--text-2)' }}>{ratingText(pharmacy)}</span>
        </div>
        {rated && (
          <div role="img" aria-label={`Community rating ${pharmacy.average_rating} out of 5`} style={{ height: '6px', background: 'var(--bg-tertiary)', borderRadius: '10px', overflow: 'hidden' }}>
            <div style={{ width: `${pharmacy.trust_score}%`, height: '100%', background: color }} />
          </div>
        )}
      </div>

      <p style={{ fontSize: '0.6875rem', color: 'var(--text-3)', margin: 0 }}>
        A rating reflects customer reviews only. It says nothing about whether the medicines sold are genuine.
      </p>

      {pharmacy?.flagged_reviews > 0 && (
        <p style={{ fontSize: '0.6875rem', color: 'var(--danger-amber-dark)', margin: '0.5rem 0 0' }}>
          Some reviews for this listing were excluded as suspicious.
        </p>
      )}
    </div>
  );
}
