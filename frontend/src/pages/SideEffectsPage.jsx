import React, { useState, useCallback, useEffect } from 'react';
import api from '../utils/api';

const LANGUAGES = {
  en: 'English', hi: 'हिन्दी', es: 'Español', fr: 'Français', pt: 'Português',
  ar: 'العربية', bn: 'বাংলা', zh: '中文', sw: 'Kiswahili', ta: 'தமிழ்',
  te: 'తెలుగు', ur: 'اردو', de: 'Deutsch', ja: '日本語', ko: '한국어',
  ru: 'Русский', tr: 'Türkçe', vi: 'Tiếng Việt', id: 'Bahasa Indonesia', th: 'ไทย',
};

export default function SideEffectsPage() {
  const [ndc, setNdc] = useState('');
  const [lang, setLang] = useState('en');
  const [loading, setLoading] = useState(false);
  const [effects, setEffects] = useState(null);
  const [error, setError] = useState(null);
  const [translating, setTranslating] = useState(false);

  const handleSearch = useCallback(async (e) => {
    e?.preventDefault();
    if (!ndc.trim()) return;
    setLoading(true); setError(null); setEffects(null);
    try {
      const res = await api.getSideEffects(ndc.trim(), lang);
      setEffects(res.side_effects || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [ndc, lang]);

  // Re-fetch when language changes (if we already have results)
  const handleLangChange = useCallback(async (newLang) => {
    setLang(newLang);
    if (!ndc.trim() || !effects) return;
    setTranslating(true);
    try {
      const res = await api.getSideEffects(ndc.trim(), newLang);
      setEffects(res.side_effects || []);
    } catch (err) {
      // Keep existing effects if translation fails
      console.error('Translation failed:', err);
    } finally {
      setTranslating(false);
    }
  }, [ndc, effects]);

  const severityOrder = { severe: 0, moderate: 1, mild: 2 };
  const sorted = effects ? [...effects].sort((a, b) => (severityOrder[a.severity] ?? 3) - (severityOrder[b.severity] ?? 3)) : [];
  const severe = sorted.filter(e => e.severity === 'severe');
  const moderate = sorted.filter(e => e.severity === 'moderate');
  const mild = sorted.filter(e => e.severity === 'mild');

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 700 }}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> Patient Education
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>
            Side Effect Explainer
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', maxWidth: 540, margin: '0 auto' }}>
            Drug leaflets rewritten in plain language at a 6th-grade reading level. Translated to 20+ languages via LibreTranslate (free, no API key).
          </p>
        </div>

        <div className="card anim anim-d1" style={{ maxWidth: 500, margin: '0 auto 1.5rem' }}>
          <form onSubmit={handleSearch}>
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <label className="form-label" htmlFor="se-ndc">Drug NDC Code</label>
              <input id="se-ndc" type="text" value={ndc} onChange={e => setNdc(e.target.value)}
                placeholder="e.g., 59726-065-30" autoComplete="off" />
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label" htmlFor="se-lang">
                Language
                <span style={{ fontWeight: 400, color: 'var(--text-3)', marginLeft: '0.4rem' }}>
                  (LibreTranslate — free)
                </span>
              </label>
              <select id="se-lang" value={lang} onChange={e => handleLangChange(e.target.value)}>
                {Object.entries(LANGUAGES).map(([code, name]) => (
                  <option key={code} value={code}>{name}</option>
                ))}
              </select>
            </div>

            <button type="submit" className="btn btn--primary btn--lg" style={{ width: '100%' }} disabled={!ndc.trim() || loading}>
              {loading ? <><div className="spinner" style={{ width: 14, height: 14, borderWidth: 2 }} /> Analyzing Label…</> : 'Get Plain Language Side Effects'}
            </button>
          </form>
        </div>

        {translating && (
          <div style={{ textAlign: 'center', padding: '1rem', color: 'var(--accent)', fontSize: '0.8125rem' }}>
            <div className="spinner" style={{ width: 16, height: 16, borderWidth: 2, margin: '0 auto 0.5rem' }} />
            Translating to {LANGUAGES[lang]}…
          </div>
        )}

        {error && (
          <div className="card card--danger anim" style={{ maxWidth: 500, margin: '0 auto', textAlign: 'center' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.8125rem' }}>{error}</p>
          </div>
        )}

        {effects && !translating && (
          <div className="anim">
            {lang !== 'en' && (
              <div style={{
                textAlign: 'center', marginBottom: '1rem', padding: '0.5rem',
                fontSize: '0.6875rem', color: 'var(--accent)',
                background: 'var(--accent-dim)', borderRadius: '8px',
                border: '1px solid rgba(0,229,191,0.1)'
              }}>
                Translated to {LANGUAGES[lang]} via LibreTranslate
              </div>
            )}

            {severe.length > 0 && (
              <div className="card card--danger" style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Stop Immediately — Seek Medical Help
                  </span>
                </div>
                {severe.map((e, i) => (
                  <div key={i} className="side-effect side-effect--severe">
                    <div>
                      <span>{e.description}</span>
                      {e.original_description && e.original_description !== e.description && (
                        <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', marginTop: '0.2rem', fontStyle: 'italic' }}>
                          {e.original_description}
                        </div>
                      )}
                    </div>
                    {e.frequency && <span style={{ fontSize: '0.625rem', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{e.frequency}</span>}
                  </div>
                ))}
              </div>
            )}

            {moderate.length > 0 && (
              <div className="card card--warning" style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--warn)" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--warn)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Watch Carefully — Tell Your Doctor
                  </span>
                </div>
                {moderate.map((e, i) => (
                  <div key={i} className="side-effect side-effect--moderate">
                    <div>
                      <span>{e.description}</span>
                      {e.original_description && e.original_description !== e.description && (
                        <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', marginTop: '0.2rem', fontStyle: 'italic' }}>
                          {e.original_description}
                        </div>
                      )}
                    </div>
                    {e.frequency && <span style={{ fontSize: '0.625rem', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{e.frequency}</span>}
                  </div>
                ))}
              </div>
            )}

            {mild.length > 0 && (
              <div className="card" style={{ marginBottom: '1rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="var(--info)" strokeWidth="2" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>
                  <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--info)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Common & Usually Mild
                  </span>
                </div>
                {mild.map((e, i) => (
                  <div key={i} className="side-effect side-effect--mild">
                    <div>
                      <span>{e.description}</span>
                      {e.original_description && e.original_description !== e.description && (
                        <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', marginTop: '0.2rem', fontStyle: 'italic' }}>
                          {e.original_description}
                        </div>
                      )}
                    </div>
                    {e.frequency && <span style={{ fontSize: '0.625rem', color: 'var(--text-3)', whiteSpace: 'nowrap' }}>{e.frequency}</span>}
                  </div>
                ))}
              </div>
            )}

            {sorted.length === 0 && (
              <div className="card" style={{ textAlign: 'center', padding: '2rem' }}>
                <p style={{ color: 'var(--text-3)' }}>No side effects could be parsed from this drug's FDA label.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
