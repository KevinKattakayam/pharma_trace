import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';

const I = ({ d, size = 20 }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none"
    stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
    <path d={d} />
  </svg>
);

const SCAN_D = "M3 7V5a2 2 0 0 1 2-2h2M17 3h2a2 2 0 0 1 2 2v2M21 17v2a2 2 0 0 1-2 2h-2M7 21H5a2 2 0 0 1-2-2v-2M12 8v8M8 12h8";
const PULSE_D = "M22 12h-4l-3 9L9 3l-3 9H2";
const SHIELD_D = "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z";
const LOCK_D = "M19 11H5a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7a2 2 0 0 0-2-2zM7 11V7a5 5 0 0 1 10 0v4";
const LINK_D = "M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71";

/* ── Animated counter ── */
function Counter({ end, suffix = '', duration = 1800 }) {
  const [val, setVal] = useState(0);
  const ref = useRef();
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (!e.isIntersecting) return;
      if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
        setVal(end);
      } else {
        let start = 0; const step = end / (duration / 16);
        const id = setInterval(() => { start += step; if (start >= end) { setVal(end); clearInterval(id); } else setVal(Math.floor(start)); }, 16);
      }
      obs.disconnect();
    }, { threshold: 0.3 });
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, [end, duration]);
  return <span ref={ref}>{val}{suffix}</span>;
}

import api from '../utils/api';

/* ── Live demo ── */
function LiveDemo() {
  const [ndc, setNdc] = useState('');
  const [state, setState] = useState('idle');
  const [result, setResult] = useState(null);
  const t = useRef(null);

  function lookup(v) {
    clearTimeout(t.current); setNdc(v);
    if (v.length < 4) { setState('idle'); setResult(null); return; }
    setState('loading');
    t.current = setTimeout(async () => {
      try {
        const res = await api.verifyBarcode(v.trim());
        setResult(res);
        setState('result');
      } catch (err) {
        setState('offline');
      }
    }, 600);
  }

  const conf = result?.confidence || 0;
  const cc = result ? (conf >= 85 ? 'var(--safe)' : conf >= 65 ? 'var(--warn)' : 'var(--danger)') : 'var(--accent)';
  const circ = 2 * Math.PI * 36, off = result ? circ * (1 - conf / 100) : circ;

  return (
    <div className="demo-shell">
      <div className="demo-bar">
        <span className="demo-bar__dot" />
        <span style={{ fontSize: '.7rem', color: 'var(--text-3)', fontWeight: 600 }}>
          Live Verification &middot; <code style={{ color: 'var(--accent)' }}>Powered by OpenFDA</code>
        </span>
      </div>
      <div className="demo-body">
        <div className="demo-input-wrap">
          <div className="demo-scan-icon"><I d={SCAN_D} /></div>
          <input className="demo-input" value={ndc} onChange={e => lookup(e.target.value)} placeholder="Try 59726-065-30 or 0781..." maxLength={20} />
          {state === 'loading' && <div className="spinner" style={{ marginRight: '.75rem' }} />}
          {state === 'result' && <span className="demo-verdict-pill" data-v={result.verdict}>{result.verdict === 'authentic' ? 'Genuine' : result.verdict === 'suspicious' ? 'Flagged' : result.verdict === 'counterfeit' ? 'Counterfeit' : 'Unknown'}</span>}
        </div>
        
        {state === 'offline' && (
           <div className="demo-result anim" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem 1rem', textAlign: 'center' }}>
             <I d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" size={32} style={{ color: 'var(--danger)', opacity: 0.5, marginBottom: '1rem' }} />
             <div style={{ color: 'var(--text-1)', fontWeight: 700, marginBottom: '0.25rem' }}>Backend Offline</div>
             <div style={{ color: 'var(--text-3)', fontSize: '0.8125rem', marginBottom: '1rem' }}>Deploy the API to enable live verification.</div>
             <button className="btn btn--secondary" style={{ padding: '0.4rem 1rem', fontSize: '0.8125rem' }} onClick={() => lookup(ndc)}>Retry Connection</button>
           </div>
        )}

        {state === 'result' && result && (
          <div className="demo-result anim">
            <div className="demo-result__left">
              <div className="demo-result__name">{result.brand_name || result.generic_name || ndc}</div>
              <div className="demo-result__generic">{result.generic_name || 'Active ingredient unknown'}</div>
              <div className="demo-result__mfr">{result.manufacturer || 'Unknown Manufacturer'}</div>
              <ul className="evidence-list" style={{ marginTop: '1rem' }}>
                {[{ l: 'FDA Match', v: result.evidence?.some(e => e.check === 'openfda_match' && e.status === 'pass') ? 'Exact' : 'Not Found', p: result.evidence?.some(e => e.check === 'openfda_match' && e.status === 'pass') }, 
                  { l: 'Recall', v: result.has_recall ? 'Alert Active' : 'None', p: !result.has_recall }, 
                  { l: 'Authenticity', v: result.verdict, p: result.verdict === 'authentic' }].map(e => (
                  <li key={e.l} className="evidence-item">
                    <span className={`evidence-item__icon evidence-item__icon--${e.p ? 'pass' : 'warn'}`}>{e.p ? '✓' : '!'}</span>
                    <span className="evidence-item__text">{e.l}</span>
                    <span className="evidence-item__weight" style={{ textTransform: 'capitalize' }}>{e.v}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="demo-result__right">
              <div className="confidence-gauge">
                <svg className="confidence-gauge__svg" width="96" height="96" viewBox="0 0 96 96">
                  <circle className="confidence-gauge__track" cx="48" cy="48" r="36" />
                  <circle className="confidence-gauge__fill" cx="48" cy="48" r="36" stroke={cc} strokeDasharray={circ} strokeDashoffset={off} />
                </svg>
                <div className="confidence-gauge__label">
                  <span className="confidence-gauge__value" style={{ color: cc, fontSize: '1.4rem' }}>{conf}%</span>
                  <span className="confidence-gauge__unit">conf.</span>
                </div>
              </div>
              <div style={{ textAlign: 'center', marginTop: '.75rem', fontSize: '.7rem', color: 'var(--text-3)' }}>Real-time verification<br />via LangGraph</div>
            </div>
          </div>
        )}
        {state === 'idle' && !ndc && (
          <div className="demo-placeholder"><I d={SCAN_D} /><span>Type an NDC above to verify against live FDA data</span></div>
        )}
      </div>
    </div>
  );
}

const AGENTS = [
  { n: '01', k: 'barcode', d: SCAN_D, l: 'Barcode', s: 'GS1 check-digit, GTIN prefix, country' },
  { n: '02', k: 'openfda', d: 'M4 7h16M4 12h16M4 17h7', l: 'FDA lookup', s: 'NDC, brand, manufacturer, ingredients' },
  { n: '03', k: 'recalls', d: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z', l: 'Recall check', s: 'Live FDA enforcement alerts' },
  { n: '04', k: 'interactions', d: PULSE_D, l: 'Interactions', s: 'Cross-check drug pairs in regimen' },
  { n: '05', k: 'supabase', d: SHIELD_D, l: 'Safety score', s: 'Weighted confidence from all data' },
  { n: '06', k: 'groq_ai', d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6', l: 'AI report', s: 'Llama 3.3 plain-language summary' },
];

const FEATURES = [
  { d: SCAN_D, l: 'Scan and Verify', s: 'Barcode, NDC, or camera photo. Verify against the FDA database in seconds.', c: 'var(--action)', bg: 'var(--action-dim)', big: true },
  { d: 'M1 6l7-3 8 3 7-3v15l-7 3-8-3-7 3V6zM8 3v15M16 6v15', l: 'Outbreak Map', s: 'Heatmap of counterfeit reports with pharmacy trust scores.', c: 'var(--danger)', bg: 'var(--danger-bg)', big: true },
  { d: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', l: 'Family Cabinet', s: 'Digital medicine inventory with auto safety cross-referencing.', c: 'var(--safe)', bg: 'var(--safe-bg)' },
  { d: 'M1 6s4-4 11-4 11 4 11 4M5 10s2.5-2 7-2 7 2 7 2M8.5 14s1.5-1 3.5-1 3.5 1 3.5 1M2 2l20 20', l: 'Works Offline', s: 'IndexedDB caches top medicines. Verify with zero connectivity.', c: 'var(--safe)', bg: 'var(--safe-bg)' },
  { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', l: 'Batch Verification', s: 'Streamlined multi-scan workflow for clinics and pharmacies.', c: 'var(--warn)', bg: 'var(--warn-bg)' },
  { d: PULSE_D, l: 'Drug Interactions', s: 'Cross-checks every drug pair using live FDA labels and Groq AI.', c: 'var(--accent)', bg: 'var(--accent-dim)' },
];

const TRUST = [
  { d: LOCK_D, t: 'Zero-knowledge reports', s: 'No IP logged. Location rounded to city level.' },
  { d: LINK_D, t: 'SHA-256 audit chain', s: 'Every verification hash-chained. Tamper-evident.' },
  { d: SHIELD_D, t: 'Live FDA data only', s: 'No mock data. No placeholders. Real drug records.' },
  { d: 'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z', t: 'Open source MIT', s: 'Python + React. Fully auditable on GitHub.' },
];

/* ── Live Stats Bar ── */
function LiveStats() {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch('/api/v1/home/stats').then(r => r.json()).then(setStats).catch(() => {});
  }, []);

  if (!stats) return <div className="home-stats anim" style={{ minHeight: 80 }}></div>;
  if (stats.verifications_performed === 0) {
    return <div className="home-stats anim" style={{ justifyContent: 'center', padding: '2rem', color: 'var(--text-2)' }}>Be the first to verify a medicine in your region.</div>;
  }

  return (
    <div className="home-stats anim">
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.verifications_performed} /></div>
        <div className="home-stat__lbl">Verifications performed</div>
      </div>
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.counterfeits_flagged} /></div>
        <div className="home-stat__lbl">Counterfeits detected</div>
      </div>
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.active_recalls} /></div>
        <div className="home-stat__lbl">Active regional recalls</div>
      </div>
    </div>
  );
}

let globalHealthCache = { data: null, timestamp: 0 };

export default function Home() {
  const nav = useNavigate();
  const [api, setApi] = useState(globalHealthCache.data ? (globalHealthCache.data.status === 'healthy' ? 'live' : 'degraded') : null);
  const [health, setHealth] = useState(globalHealthCache.data);

  useEffect(() => {
    if (Date.now() - globalHealthCache.timestamp < 30000 && globalHealthCache.data) {
      return; // Use cached state
    }
    fetch('/api/v1/health').then(r => r.json()).then(d => {
      globalHealthCache = { data: d, timestamp: Date.now() };
      setApi(d.status === 'healthy' ? 'live' : 'degraded');
      setHealth(d);
    }).catch(() => setApi('offline'));
  }, []);

  return (
    <div className="page home-page">
      <section className="home-hero">
        <div className="container">
          <div className="home-hero__tag anim">
            <span className="hero__tag-dot" />
            Pharmaceutical Intelligence Platform
            {api && <span className={`home-api-dot home-api-dot--${api}`} title={`API ${api}`} />}
          </div>

          <h1 className="home-hero__h1 anim anim-d1">
            Verify any medicine<br />
            <em className="home-hero__em">before it reaches your family.</em>
          </h1>

          <p className="home-hero__sub anim anim-d2">
            Scan a barcode, photograph a pill, or speak your prescription in any language.
            Six AI agents query live FDA databases, detect counterfeits, and return a
            transparent confidence score with full evidence trail.
          </p>

          <div className="home-hero__actions anim anim-d3">
            <button className="btn btn--primary btn--lg" onClick={() => nav('/scan')}><I d={SCAN_D} /> Scan Medicine</button>
            <button className="btn btn--secondary btn--lg" onClick={() => nav('/prescription')}><I d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 15h6M9 12h6M9 18h6" /> Doctor Visit Summary</button>
          </div>

          <div className="anim anim-d4"><LiveDemo /></div>

          <div className="anim anim-d5"><LiveStats /></div>
        </div>
      </section>

      <section className="home-section">
        <div className="container">
          <div className="home-section__eyebrow">How it works</div>
          <div className="home-section__title">Six agents. One verdict.</div>
          <p className="home-section__sub">A LangGraph pipeline orchestrates every verification. No black boxes. Full evidence trail on every scan.</p>
          <div className="agent-pipeline">
            {AGENTS.map((a, i) => {
              const status = health ? health.services?.[a.k] : null;
              const color = status === 'connected' ? 'var(--safe)' : status === 'offline' ? 'var(--danger)' : status ? 'var(--warn)' : 'var(--text-3)';
              
              return (
                <div key={a.n} className="agent-step card anim" style={{ animationDelay: `${i * 0.08}s`, borderTop: `3px solid ${color}` }}>
                  <div className="agent-step__num" style={{ color }}>{a.n}</div>
                  <div className="agent-step__icon" style={{ color }}><I d={a.d} size={20} /></div>
                  <div className="agent-step__label">{a.l}</div>
                  <div className="agent-step__desc">{a.s}</div>
                  {i < AGENTS.length - 1 && <div className="agent-step__arrow"><I d="M5 12h14M12 5l7 7-7 7" /></div>}
                </div>
              );
            })}
          </div>
        </div>
      </section>

      <section className="home-section home-section--alt">
        <div className="container">
          <div className="home-section__eyebrow">Core features</div>
          <div className="home-section__title">Built for real clinical use</div>
          <p className="home-section__sub">Every feature powered by live FDA data. Every result backed by a transparent evidence chain.</p>
          <div className="bento-grid">
            {FEATURES.map((f, i) => (
              <div key={f.l} className={`bento-card card anim ${f.big ? 'bento-card--big' : ''}`} style={{ animationDelay: `${i * 0.06}s` }}>
                <div className="bento-card__icon" style={{ background: f.bg, color: f.c }}><I d={f.d} size={22} /></div>
                <div className="bento-card__label">{f.l}</div>
                <div className="bento-card__desc">{f.s}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="home-section">
        <div className="container">
          <div className="trust-strip">
            {TRUST.map(t => (
              <div key={t.t} className="trust-item">
                <div className="trust-item__icon"><I d={t.d} /></div>
                <div>
                  <div className="trust-item__title">{t.t}</div>
                  <div className="trust-item__sub">{t.s}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="home-section">
        <div className="container">
          <div className="home-cta card">
            <div className="home-cta__left">
              <div className="home-cta__title">Start verifying in 30 seconds.</div>
              <div className="home-cta__sub">No signup required. No API keys needed for core verification.</div>
            </div>
            <div className="home-cta__actions">
              <button className="btn btn--primary" onClick={() => nav('/scan')}><I d={SCAN_D} /> Scan now</button>
              <button className="btn btn--ghost" onClick={() => nav('/api-docs')}>API docs <I d="M5 12h14M12 5l7 7-7 7" /></button>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
