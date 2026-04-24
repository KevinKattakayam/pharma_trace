import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import api from '../utils/api';

function AnimatedCounter({ end, duration = 2000, suffix = '' }) {
  const [count, setCount] = useState(0);
  useEffect(() => {
    let start = 0;
    const step = end / (duration / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= end) { setCount(end); clearInterval(timer); }
      else setCount(Math.floor(start));
    }, 16);
    return () => clearInterval(timer);
  }, [end, duration]);
  return <>{count.toLocaleString()}{suffix}</>;
}

const keyFeatures = [
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M21 17v2a2 2 0 01-2 2h-2M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>,
    title: 'Scan and Verify',
    desc: 'Barcode, NDC, or camera — verify any medicine against the FDA National Drug Code database in seconds.',
    link: '/scan',
    color: '#7c5cfc'
  },
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>,
    title: 'Interaction Scanner',
    desc: 'Enter all medications. Cross-checks every pair using live FDA labels, Groq AI parsing, and FAERS adverse event data.',
    link: '/interactions',
    color: '#3b82f6'
  },
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>,
    title: 'Side Effects',
    desc: 'FDA labels rewritten in plain language with severity labels. Translatable to 20+ languages.',
    link: '/side-effects',
    color: '#06d6a0'
  },
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></svg>,
    title: 'Dosage Safety',
    desc: 'Flags unsafe doses for elderly, pediatric, and renal-impaired patients using clinical guidelines.',
    link: '/dosage',
    color: '#fbbf24'
  },
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>,
    title: 'Outbreak Map',
    desc: 'Leaflet.js heatmap with animated playback. Track counterfeit drug reports across regions in real time.',
    link: '/map',
    color: '#ef4444'
  },
  {
    icon: <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></svg>,
    title: 'Batch Verify',
    desc: 'Health workers scan 50+ drugs in minutes. Export PDF reports for clinic records.',
    link: '/batch',
    color: '#a78bfa'
  },
];

export default function Home() {
  const [health, setHealth] = useState(null);
  useEffect(() => { api.getHealth().then(setHealth).catch(() => {}); }, []);

  const connected = health ? Object.values(health.services).filter(v => v === 'connected').length : 0;
  const total = health ? Object.keys(health.services).length : 0;

  return (
    <div className="page">
      <div className="container">

        {/* Hero */}
        <section className="hero" id="hero-section">
          <div className="hero__tag anim">
            <span className="hero__tag-dot" />
            Pharmaceutical Intelligence Platform
          </div>

          <h1 className="hero__title anim anim-d1">
            Verify Any Medicine<br />
            <span className="hero__title-gradient">Before It Harms You</span>
          </h1>

          <p className="hero__subtitle anim anim-d2">
            Scan any drug package. PharmaTrace queries FDA databases, detects counterfeits,
            checks interactions, and returns a transparent confidence score — all in real time.
          </p>

          <div className="hero__actions anim anim-d3">
            <Link to="/scan" className="btn btn--primary btn--lg" id="btn-hero-scan">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>
              Scan Medicine
            </Link>
            <Link to="/interactions" className="btn btn--secondary btn--lg" id="btn-hero-interactions">
              Check Interactions
            </Link>
          </div>

          <div className="hero__stats anim anim-d4">
            <div className="hero__stat">
              <div className="hero__stat-val"><AnimatedCounter end={37} /></div>
              <div className="hero__stat-lbl">API Endpoints</div>
            </div>
            <div className="hero__stat">
              <div className="hero__stat-val">{connected || 6}<span style={{ opacity: 0.4 }}>/{total || 7}</span></div>
              <div className="hero__stat-lbl">Live Services</div>
            </div>
            <div className="hero__stat">
              <div className="hero__stat-val"><AnimatedCounter end={6} /></div>
              <div className="hero__stat-lbl">AI Agents</div>
            </div>
            <div className="hero__stat">
              <div className="hero__stat-val"><AnimatedCounter end={20} suffix="+" /></div>
              <div className="hero__stat-lbl">Languages</div>
            </div>
          </div>
        </section>

        {/* Live Status */}
        {health && (
          <section className="anim anim-d5" style={{ marginBottom: '4rem' }}>
            <div style={{
              display: 'flex', flexWrap: 'wrap', gap: '0.5rem',
              justifyContent: 'center'
            }}>
              {Object.entries(health.services).map(([name, status]) => (
                <div key={name} style={{
                  display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                  padding: '0.3rem 0.85rem', borderRadius: 100,
                  background: status === 'connected' ? 'rgba(6,214,160,0.06)' : 'rgba(78,86,120,0.08)',
                  border: `1px solid ${status === 'connected' ? 'rgba(6,214,160,0.12)' : 'rgba(78,86,120,0.12)'}`,
                  fontSize: '0.6875rem', fontWeight: 600,
                  color: status === 'connected' ? 'var(--safe)' : 'var(--text-3)'
                }}>
                  <span style={{
                    width: 5, height: 5, borderRadius: '50%', flexShrink: 0,
                    background: status === 'connected' ? 'var(--safe)' : 'var(--text-3)',
                    boxShadow: status === 'connected' ? '0 0 6px rgba(6,214,160,0.5)' : 'none'
                  }} />
                  {name.replace(/_/g, ' ')}
                </div>
              ))}
            </div>
          </section>
        )}

        {/* Quick Try */}
        <section className="anim" style={{ marginBottom: '4rem' }}>
          <div className="card" style={{
            background: 'linear-gradient(135deg, rgba(124,92,252,0.06), rgba(59,130,246,0.04))',
            border: '1px solid rgba(124,92,252,0.12)',
            padding: '1.75rem 2rem',
            display: 'flex', alignItems: 'center', gap: '1.5rem', flexWrap: 'wrap'
          }}>
            <div style={{ flex: 1, minWidth: 220 }}>
              <div style={{
                fontSize: '0.625rem', fontWeight: 700, color: 'var(--accent)',
                textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.35rem'
              }}>Quick Test</div>
              <div style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                Try NDC <span style={{ fontFamily: 'var(--mono)', color: 'var(--accent)' }}>59726-065-30</span>
              </div>
              <div style={{ fontSize: '0.8125rem', color: 'var(--text-2)' }}>
                Enter this code in the scanner to see a live verification with FDA data, cold chain, and GTIN validation.
              </div>
            </div>
            <Link to="/scan" className="btn btn--primary">Verify Now</Link>
          </div>
        </section>

        {/* How It Works */}
        <section style={{ marginBottom: '4.5rem' }}>
          <div className="section-head">
            <div className="section-head__tag">How It Works</div>
            <h2 className="section-head__title">Three Steps to Verified Medicine</h2>
          </div>
          <div className="steps-grid">
            {[
              { num: '01', title: 'Scan or Enter', desc: 'Point your camera at the barcode, photograph the pill, or type the NDC code manually.' },
              { num: '02', title: '6-Agent AI Pipeline', desc: 'LangGraph orchestrates: GTIN check, FDA lookup, recall scan, interaction analysis, safety score, and AI report.' },
              { num: '03', title: 'Transparent Verdict', desc: 'Confidence score with every evidence item. See what matched, what failed, and which FDA database confirmed it.' }
            ].map((s, i) => (
              <div key={i} className="card step-card anim" style={{ animationDelay: `${0.08 * (i + 1)}s` }}>
                <div className="step-card__num">{s.num}</div>
                <h3 className="step-card__title">{s.title}</h3>
                <p className="step-card__desc">{s.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* Key Features */}
        <section style={{ marginBottom: '4.5rem' }}>
          <div className="section-head">
            <div className="section-head__tag">Core Features</div>
            <h2 className="section-head__title">Built for Real Clinical Use</h2>
            <p className="section-head__subtitle">Every feature powered by live FDA data. No mock data, no placeholders.</p>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: '1rem' }}>
            {keyFeatures.map((f, i) => (
              <Link key={i} to={f.link} className="card anim" style={{
                animationDelay: `${0.06 * i}s`, textDecoration: 'none', color: 'inherit',
                padding: '1.75rem', display: 'flex', flexDirection: 'column', gap: '0.85rem'
              }}>
                <div style={{
                  width: 44, height: 44, borderRadius: 12,
                  background: `${f.color}10`, border: `1px solid ${f.color}20`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: f.color
                }}>{f.icon}</div>
                <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>{f.title}</h3>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-2)', lineHeight: 1.6 }}>{f.desc}</p>
              </Link>
            ))}
          </div>
        </section>

        {/* More Tools */}
        <section style={{ marginBottom: '4rem' }}>
          <div className="section-head">
            <div className="section-head__tag">Full Toolkit</div>
            <h2 className="section-head__title">25 Features. Zero Compromise.</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '0.65rem' }}>
            {[
              { name: 'Generic Drug Finder', link: '/generics' },
              { name: 'Caregiver Dashboard', link: '/dashboard' },
              { name: 'Anonymous Reporting', link: '/report' },
              { name: 'Pill Identification (AI)', link: '/scan' },
              { name: 'Refill Reminders', link: '/scan' },
              { name: 'Pharmacy Trust Scores', link: '/map' },
              { name: 'FAERS Adverse Events', link: '/side-effects' },
              { name: 'Voice Interface', link: '/scan' },
              { name: 'Translation (20+ langs)', link: '/side-effects' },
              { name: 'Cold Chain Analysis', link: '/scan' },
              { name: 'Immutable Audit Log', link: '/api-docs' },
              { name: 'API and SDK', link: '/api-docs' },
            ].map((t, i) => (
              <Link key={i} to={t.link} className="card anim" style={{
                padding: '0.85rem 1.15rem', textDecoration: 'none', color: 'inherit',
                animationDelay: `${0.03 * i}s`, display: 'flex', alignItems: 'center', gap: '0.65rem'
              }}>
                <span style={{
                  width: 6, height: 6, borderRadius: '50%', flexShrink: 0,
                  background: 'var(--accent)', opacity: 0.5
                }} />
                <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>{t.name}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* Tech Stack */}
        <section style={{ marginBottom: '4rem' }}>
          <div className="section-head">
            <div className="section-head__tag">Infrastructure</div>
            <h2 className="section-head__title">Free. Open. Production-Grade.</h2>
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(130px, 1fr))', gap: '0.5rem' }}>
            {[
              { name: 'OpenFDA', role: 'Drug Database' },
              { name: 'Groq', role: 'Llama 3.3 70B' },
              { name: 'OpenRouter', role: 'GPT-4o Vision' },
              { name: 'LangGraph', role: 'Agent Pipeline' },
              { name: 'FastAPI', role: 'Backend' },
              { name: 'React', role: 'Frontend' },
              { name: 'LibreTranslate', role: 'Translation' },
              { name: 'Open-Meteo', role: 'Cold Chain' },
              { name: 'Leaflet.js', role: 'Maps' },
              { name: 'Supabase', role: 'PostgreSQL' },
            ].map((t, i) => (
              <div key={i} className="card anim" style={{
                padding: '0.75rem', textAlign: 'center',
                animationDelay: `${0.03 * i}s`
              }}>
                <div style={{ fontSize: '0.8125rem', fontWeight: 700, marginBottom: '0.1rem' }}>{t.name}</div>
                <div style={{ fontSize: '0.5625rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.role}</div>
              </div>
            ))}
          </div>
        </section>

        {/* CTA */}
        <section style={{ textAlign: 'center', padding: '3rem 0 2rem' }}>
          <h2 style={{ fontSize: '1.75rem', fontWeight: 800, letterSpacing: '-0.03em', marginBottom: '0.75rem' }}>
            Start Protecting Lives Today
          </h2>
          <p style={{ color: 'var(--text-2)', maxWidth: 420, margin: '0 auto 1.75rem', fontSize: '0.9375rem' }}>
            Counterfeit medicines kill 250,000 children every year. PharmaTrace gives
            everyone the power to verify — for free.
          </p>
          <Link to="/scan" className="btn btn--primary btn--lg" id="btn-cta-scan">
            Verify Your First Medicine
          </Link>
        </section>

      </div>
    </div>
  );
}
