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
        <span style={{ fontSize: '.75rem', color: 'var(--text-main)', fontWeight: 700, letterSpacing: '0.02em' }}>
          Verification workspace &middot; <code style={{ color: 'var(--primary)', fontWeight: 800 }}>Live registry checks</code>
        </span>
      </div>
      <div className="demo-body">
        <div className="demo-input-wrap">
          <div className="demo-scan-icon"><I d={SCAN_D} /></div>
          <input className="demo-input" value={ndc} onChange={e => lookup(e.target.value)} placeholder="Enter NDC or GTIN (e.g., 59726-065-30)..." maxLength={20} />
          {state === 'loading' && <div className="spinner" style={{ marginRight: '.85rem' }} />}
          {state === 'result' && <span className="demo-verdict-pill" data-v={result.verdict}>{result.verdict === 'authentic' ? 'Verified Authentic' : result.verdict === 'suspicious' ? 'Safety Flag' : result.verdict === 'counterfeit' ? 'Counterfeit Alert' : 'Unknown Status'}</span>}
        </div>
        
        {state === 'offline' && (
           <div className="demo-result anim" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2.5rem 1rem', textAlign: 'center' }}>
             <I d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" size={36} style={{ color: 'var(--danger)', opacity: 0.7, marginBottom: '1rem' }} />
             <div style={{ color: 'var(--text-main)', fontWeight: 800, fontSize: '18px', marginBottom: '0.35rem' }}>Verification service unavailable</div>
             <div style={{ color: 'var(--text-muted)', fontSize: '14px', marginBottom: '1.25rem', maxWidth: '380px', lineHeight: 1.6 }}>We can’t reach the verification service right now. Try again when you have a connection.</div>
             <button className="btn btn--secondary" style={{ padding: '0.6rem 1.5rem', fontSize: '14px', width: 'auto' }} onClick={() => lookup(ndc)}>Retry Connection</button>
           </div>
        )}

        {state === 'result' && result && (
          <div className="demo-result anim">
            <div className="demo-result__left">
              <div className="demo-result__name">{result.brand_name || result.generic_name || ndc}</div>
              <div className="demo-result__generic">{result.generic_name || 'Active ingredient unknown'}</div>
              <div className="demo-result__mfr">{result.manufacturer || 'Unknown Manufacturer'}</div>
              <ul className="evidence-list" style={{ marginTop: '1.25rem' }}>
                {[{ l: 'FDA Match', v: result.evidence?.some(e => e.check === 'openfda_match' && e.status === 'pass') ? 'Exact Record' : 'Not Found', p: result.evidence?.some(e => e.check === 'openfda_match' && e.status === 'pass') }, 
                  { l: 'Recall Status', v: result.has_recall ? 'Alert Active' : 'Clear & Safe', p: !result.has_recall }, 
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
                <svg className="confidence-gauge__svg" width="110" height="110" viewBox="0 0 96 96">
                  <circle className="confidence-gauge__track" cx="48" cy="48" r="36" />
                  <circle className="confidence-gauge__fill" cx="48" cy="48" r="36" stroke={cc} strokeDasharray={circ} strokeDashoffset={off} />
                </svg>
                <div className="confidence-gauge__label">
                  <span className="confidence-gauge__value" style={{ color: cc }}>{conf}%</span>
                  <span className="confidence-gauge__unit">safety</span>
                </div>
              </div>
              <div style={{ textAlign: 'center', marginTop: '0.85rem', fontSize: '11px', color: 'var(--text-muted)', fontWeight: 600 }}>Evidence-based result<br />from configured sources</div>
            </div>
          </div>
        )}
        {state === 'idle' && !ndc && (
          <div className="demo-placeholder"><I d={SCAN_D} size={24} /><span>Enter an NDC or GTIN to check available records</span></div>
        )}
      </div>
    </div>
  );
}

const AGENTS = [
  { n: '01', k: 'barcode', d: SCAN_D, l: 'Optical & GS1 Scan', s: 'Decodes GTIN, NDC, and cryptographic serial numbers' },
  { n: '02', k: 'openfda', d: 'M4 7h16M4 12h16M4 17h7', l: 'Live FDA Registry', s: 'Cross-references active ingredients and manufacturers' },
  { n: '03', k: 'recalls', d: 'M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z', l: 'Recall & Enforcement', s: 'Screens real-time FDA and regional safety alerts' },
  { n: '04', k: 'interactions', d: PULSE_D, l: 'Regimen Safety', s: 'Evaluates multi-drug interactions and contraindications' },
  { n: '05', k: 'supabase', d: SHIELD_D, l: 'Evidence scoring', s: 'Combines available source checks into a transparent result' },
  { n: '06', k: 'groq_ai', d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6', l: 'Plain-language summary', s: 'Optional explanations for patients and care teams' },
];

const FEATURES = [
  { d: SCAN_D, l: 'Medication verification', s: 'Scan barcodes, NDC packages, or blister cards and review the available regulatory evidence.', c: 'var(--action)', bg: 'var(--action-dim)', big: true },
  { d: 'M1 6l7-3 8 3 7-3v15l-7 3-8-3-7 3V6zM8 3v15M16 6v15', l: 'Real-Time Outbreak Map', s: 'Interactive geospatial heatmap tracking counterfeit clusters and pharmacy trust scores across regions.', c: 'var(--danger)', bg: 'var(--danger-bg)', big: true },
  { d: 'M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', l: 'Smart Clinical Cabinet', s: 'Digital inventory management with automatic expiration tracking and cross-drug safety monitoring.', c: 'var(--safe)', bg: 'var(--safe-bg)' },
  { d: 'M1 6s4-4 11-4 11 4 11 4M5 10s2.5-2 7-2 7 2 7 2M8.5 14s1.5-1 3.5-1 3.5 1M2 2l20 20', l: 'Zero-Latency Edge Mode', s: 'IndexedDB caching and Bloom filters enable instantaneous offline verification in remote clinical settings.', c: 'var(--safe)', bg: 'var(--safe-bg)' },
  { d: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z', l: 'High-Throughput Batch', s: 'Rapid multi-scan workflow engineered for hospital pharmacies, clinics, and supply chain distributors.', c: 'var(--warn)', bg: 'var(--warn-bg)' },
  { d: PULSE_D, l: 'Regimen review', s: 'Review potential drug interactions alongside patient context and clear safety guidance.', c: 'var(--accent)', bg: 'var(--accent-dim)' },
];

const TRUST = [
  { d: LOCK_D, t: 'Zero-Knowledge Privacy', s: 'No patient IP or personal health data is ever stored or logged.' },
  { d: LINK_D, t: 'SHA-256 Audit Trail', s: 'Every verification is cryptographically hash-chained for tamper-evidence.' },
  { d: SHIELD_D, t: 'Live Regulatory Data', s: 'Direct synchronization with FDA, CDSCO, and NIH RxNorm databases.' },
  { d: 'M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z', t: 'Open Architecture', s: 'Transparent Python & React stack audited against enterprise clinical standards.' },
];

/* ── Live Stats Bar ── */
function LiveStats() {
  const [stats, setStats] = useState(null);
  
  useEffect(() => {
    fetch('/api/v1/home/stats').then(r => r.json()).then(setStats).catch(() => {});
  }, []);

  if (!stats) return <div className="home-stats anim" style={{ minHeight: 80 }}></div>;
  if (stats.verifications_performed === 0) {
    return <div className="home-stats anim" style={{ justifyContent: 'center', padding: '2rem', color: 'var(--text-muted)', fontWeight: 600 }}>Be the first to perform a clinical verification in your region.</div>;
  }

  return (
    <div className="home-stats anim">
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.verifications_performed} /></div>
        <div className="home-stat__lbl">Verifications Performed</div>
      </div>
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.counterfeits_flagged} /></div>
        <div className="home-stat__lbl">Counterfeits Flagged</div>
      </div>
      <div className="home-stat">
        <div className="home-stat__val"><Counter end={stats.active_recalls} /></div>
        <div className="home-stat__lbl">Active Safety Alerts</div>
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
            Medication safety platform
            {api && <span className={`home-api-dot home-api-dot--${api}`} title={`API ${api}`} />}
          </div>

          <h1 className="home-hero__h1 anim anim-d1">
            Verify any medicine.<br />
            <em className="home-hero__em">Before it reaches a patient.</em>
          </h1>

          <p className="home-hero__sub anim anim-d2">
            Scan a barcode, photograph a packaging label, or speak your prescription in any language.
            Review product records, safety alerts, and supporting evidence in one workflow—designed
            to help patients, pharmacists, and care teams make a more informed next decision.
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
          <div className="home-section__title">Clear evidence, one place.</div>
          <p className="home-section__sub">Each check shows the source that informed it, so a result can be understood and reviewed.</p>
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
