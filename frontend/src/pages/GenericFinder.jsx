import React, { useState, useCallback } from 'react';
import api from '../utils/api';

export default function GenericFinder() {
  const [ndc, setNdc] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleSearch = useCallback(async (e) => {
    e.preventDefault();
    if (!ndc.trim()) return;
    setLoading(true); setError(null); setResult(null);
    try {
      const res = await api.request(`/drugs/${encodeURIComponent(ndc.trim())}/generics`);
      setResult(res);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [ndc]);

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 800 }}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> Affordability Tools
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>
            Generic Drug Finder
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', maxWidth: 520, margin: '0 auto' }}>
            Enter a branded drug's NDC to find verified generic alternatives with the same active compound. Prevent counterfeiting by making authenticity affordable.
          </p>
        </div>

        <div className="card anim anim-d1" style={{ maxWidth: 460, margin: '0 auto 1.5rem' }}>
          <form onSubmit={handleSearch}>
            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" htmlFor="generic-ndc">NDC of Branded Drug</label>
              <input id="generic-ndc" type="text" value={ndc} onChange={e => setNdc(e.target.value)}
                placeholder="e.g., 59726-065-30" autoComplete="off" />
            </div>
            <button type="submit" className="btn btn--primary btn--lg" style={{ width: '100%' }} disabled={!ndc.trim() || loading}>
              {loading ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Searching FDA…</> : 'Find Generics'}
            </button>
          </form>
        </div>

        {error && (
          <div className="card card--danger anim" style={{ maxWidth: 460, margin: '0 auto', textAlign: 'center' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.8125rem' }}>{error}</p>
          </div>
        )}

        {result && (
          <div className="anim">
            {/* Source Drug */}
            <div className="card" style={{ marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
                <div style={{ width: 40, height: 40, borderRadius: '10px', background: 'var(--accent-dim)', border: '1px solid rgba(0,229,191,0.12)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--accent)" strokeWidth="2" strokeLinecap="round"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>
                </div>
                <div>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>Original Drug</div>
                  <div style={{ fontSize: '1rem', fontWeight: 700 }}>{result.original_drug || ndc}</div>
                </div>
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-2)' }}>
                Active Ingredient: <span style={{ fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{result.active_ingredient || 'Unknown'}</span>
              </div>
            </div>

            {/* Generics List */}
            {result.generics && result.generics.length > 0 ? (
              <div>
                <div className="drug-result__section-title" style={{ marginBottom: '0.65rem' }}>
                  {result.generics.length} Verified Generic{result.generics.length !== 1 ? 's' : ''} Found
                </div>
                {result.generics.map((g, i) => (
                  <div key={i} className="card" style={{ marginBottom: '0.65rem', padding: '1.15rem' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: '1rem' }}>
                      <div style={{ flex: 1 }}>
                        <div style={{ fontSize: '0.9375rem', fontWeight: 700, marginBottom: '0.2rem' }}>
                          {g.brand_name || g.generic_name || 'Unknown'}
                        </div>
                        {g.generic_name && g.brand_name && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--text-2)', marginBottom: '0.35rem' }}>{g.generic_name}</div>
                        )}
                        <div style={{ fontSize: '0.75rem', color: 'var(--text-3)' }}>{g.manufacturer}</div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-2)' }}>{g.ndc}</div>
                        {g.strength && <div style={{ fontSize: '0.6875rem', color: 'var(--text-3)', marginTop: '0.15rem' }}>{g.strength}</div>}
                      </div>
                    </div>
                    {(g.route || g.dosage_form) && (
                      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
                        {g.route && <span className="badge badge--info">{g.route}</span>}
                        {g.dosage_form && <span className="badge badge--info">{g.dosage_form}</span>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="card" style={{ textAlign: 'center', padding: '2rem' }}>
                <p style={{ color: 'var(--text-3)' }}>No generic alternatives found in the FDA database for this active ingredient.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
