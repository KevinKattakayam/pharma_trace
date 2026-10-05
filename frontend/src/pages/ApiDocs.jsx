import React, { useState, useEffect } from 'react';
import api from '../utils/api';

const endpoints = [
  { method: 'POST', path: '/verify/barcode', desc: 'Verify drug by barcode/NDC (OpenFDA + WHO GTIN + Cold Chain)', tag: 'verification' },
  { method: 'POST', path: '/verify/image', desc: 'Verify drug by photo (GPT-4o Vision)', tag: 'verification' },
  { method: 'POST', path: '/verify/batch', desc: 'Batch verify multiple barcodes', tag: 'verification' },
  { method: 'GET', path: '/verify/history', desc: 'Get verification history', tag: 'verification' },
  { method: 'POST', path: '/interactions/check', desc: 'Multi-drug interaction scanner (pairwise + triple)', tag: 'interactions' },
  { method: 'GET', path: '/drugs/{ndc}', desc: 'Get drug details from OpenFDA', tag: 'drugs' },
  { method: 'GET', path: '/drugs/{ndc}/side-effects?lang=en', desc: 'Plain-language side effects (LibreTranslate)', tag: 'drugs' },
  { method: 'POST', path: '/drugs/{ndc}/dosage', desc: 'Dosage personalizer (age, weight, kidney)', tag: 'drugs' },
  { method: 'GET', path: '/drugs/{ndc}/generics', desc: 'Find generic alternatives (same active ingredient)', tag: 'drugs' },
  { method: 'GET', path: '/adverse-events/{drug}', desc: 'FDA FAERS adverse event reports', tag: 'drugs' },
  { method: 'POST', path: '/reports', desc: 'Submit suspicious drug report (anonymous)', tag: 'reports' },
  { method: 'GET', path: '/reports/heatmap', desc: 'Counterfeit drug heatmap data', tag: 'reports' },
  { method: 'GET', path: '/pharmacies/nearby', desc: 'Nearby pharmacies with trust scores (PostGIS)', tag: 'pharmacies' },
  { method: 'POST', path: '/caregiver/link', desc: 'Generate caregiver invite code', tag: 'caregiver' },
  { method: 'GET', path: '/caregiver/dashboard', desc: 'Caregiver monitoring dashboard', tag: 'caregiver' },
  { method: 'GET', path: '/translate/languages', desc: 'Supported languages (LibreTranslate)', tag: 'translation' },
  { method: 'POST', path: '/translate', desc: 'Translate text to any language', tag: 'translation' },
  { method: 'POST', path: '/barcode/validate', desc: 'WHO GTIN/GS1 barcode validation', tag: 'barcode' },
  { method: 'POST', path: '/barcode/parse-gs1', desc: 'GS1 DataMatrix parser (lot, expiry, serial)', tag: 'barcode' },
  { method: 'POST', path: '/vision/analyze', desc: 'GPT-4o Vision pill analysis', tag: 'vision' },
  { method: 'POST', path: '/vision/identify', desc: 'Identify pill from text description', tag: 'vision' },
  { method: 'GET', path: '/cold-chain', desc: 'Cold chain analysis (Open-Meteo)', tag: 'system' },
  { method: 'GET', path: '/audit/verify', desc: 'Verify SHA-256 audit chain integrity', tag: 'system' },
  { method: 'GET', path: '/audit/log', desc: 'Get audit log entries', tag: 'system' },
  { method: 'GET', path: '/refill/schedule', desc: 'Refill reminders with nearest pharmacy', tag: 'system' },
  { method: 'GET', path: '/health', desc: 'Service health & status', tag: 'system' },
];

const services = [
  { name: 'OpenFDA', status: 'active', desc: 'Drug database, labels, recalls, FAERS adverse events, generics', free: true },
  { name: 'Open-Meteo', status: 'active', desc: 'Cold chain weather monitoring (no API key)', free: true },
  { name: 'LibreTranslate', status: 'active', desc: 'Translation to 20+ languages (free public instances)', free: true },
  { name: 'WHO GTIN/GS1', status: 'active', desc: 'International barcode validation & country detection', free: true },
  { name: 'GPT-4o Vision', status: 'optional', desc: 'Pill/packaging image analysis (needs OPENAI_API_KEY)', free: false },
  { name: 'Supabase', status: 'optional', desc: 'PostgreSQL + PostGIS persistent storage (needs credentials)', free: true },
  { name: 'Web Speech API', status: 'active', desc: 'Voice interface (built into Chrome/Edge)', free: true },
  { name: 'Leaflet + CARTO', status: 'active', desc: 'Maps, heatmaps, tile layers', free: true },
  { name: 'SHA-256 Chain', status: 'active', desc: 'Tamper-evident hash-chained audit log', free: true },
];

const pythonSDK = `# pip install httpx

import httpx

BASE = "http://localhost:8000/api/v1"

# Verify a drug by NDC
resp = httpx.post(f"{BASE}/verify/barcode", json={
    "barcode": "59726-065-30",
    "location": {"lat": 19.076, "lng": 72.877}
})
result = resp.json()
print(f"{result['verdict']} — {result['confidence']}% — {result['brand_name']}")

# Check drug interactions
resp = httpx.post(f"{BASE}/interactions/check", json={
    "drugs": ["Warfarin", "Aspirin", "Ibuprofen"]
})
for ix in resp.json()["interactions"]:
    print(f"⚠ {ix['drug_a']} + {ix['drug_b']}: {ix['severity']} — {ix['clinical_effect']}")

# Get side effects in Hindi
resp = httpx.get(f"{BASE}/drugs/59726-065-30/side-effects?lang=hi")
for se in resp.json()["side_effects"]:
    print(f"[{se['severity']}] {se['description']}")

# Validate international barcode (WHO GTIN)
resp = httpx.post(f"{BASE}/barcode/validate?barcode=8901234567890")
print(resp.json())  # → format, country, check_digit_valid

# Check cold chain conditions
resp = httpx.get(f"{BASE}/cold-chain?lat=19.076&lng=72.877")
print(resp.json())  # → temp, humidity, ok/not-ok
`;

const jsSDK = `// npm install node-fetch
const BASE = 'http://localhost:8000/api/v1';

// Verify a drug
const verify = await fetch(\`\${BASE}/verify/barcode\`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    barcode: '59726-065-30',
    location: { lat: 19.076, lng: 72.877 }
  })
}).then(r => r.json());

console.log(\`\${verify.verdict} — \${verify.confidence}% — \${verify.brand_name}\`);

// Check interactions
const ix = await fetch(\`\${BASE}/interactions/check\`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ drugs: ['Warfarin', 'Aspirin', 'Ibuprofen'] })
}).then(r => r.json());

ix.interactions.forEach(i =>
  console.log(\`⚠ \${i.drug_a} + \${i.drug_b}: \${i.severity}\`)
);

// Get side effects in Spanish
const se = await fetch(\`\${BASE}/drugs/59726-065-30/side-effects?lang=es\`)
  .then(r => r.json());

// Find generic alternatives
const generics = await fetch(\`\${BASE}/drugs/59726-065-30/generics\`)
  .then(r => r.json());
`;

export default function ApiDocs() {
  const [health, setHealth] = useState(null);
  const [tab, setTab] = useState('endpoints');

  useEffect(() => {
    api.getHealth().then(setHealth).catch(() => {});
  }, []);

  const tags = [...new Set(endpoints.map(e => e.tag))];

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 900 }}>
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> Platform Integration
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>
            Open API & SDK
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', maxWidth: 560, margin: '0 auto' }}>
            Documented REST API with Python and JavaScript SDKs. Integrate drug verification into hospitals, NGO systems, and other applications.
          </p>
        </div>

        {/* Service Status */}
        {health && (
          <div className="card anim anim-d1" style={{ marginBottom: '1.5rem' }}>
            <div className="drug-result__section-title">Integrated Services</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(250px, 1fr))', gap: '0.5rem' }}>
              {services.map((s, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.5rem 0.65rem', borderRadius: '8px',
                  background: 'rgba(255,255,255,0.02)', border: '1px solid var(--border-1)'
                }}>
                  <span style={{
                    width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                    background: s.status === 'active' ? 'var(--safe)' : 'var(--warn)'
                  }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700 }}>{s.name}</div>
                    <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {s.desc}
                    </div>
                  </div>
                  {s.free && (
                    <span style={{
                      fontSize: '0.5rem', fontWeight: 700, color: 'var(--safe)',
                      background: 'var(--safe-bg)', padding: '0.15rem 0.4rem',
                      borderRadius: '4px', textTransform: 'uppercase', letterSpacing: '0.05em', flexShrink: 0
                    }}>FREE</span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '0.4rem', marginBottom: '1.25rem', justifyContent: 'center' }}>
          {['endpoints', 'python', 'javascript'].map(t => (
            <button key={t} className={`btn ${tab === t ? 'btn--primary' : 'btn--secondary'}`}
              onClick={() => setTab(t)} style={{ textTransform: 'capitalize', fontSize: '0.75rem' }}>
              {t === 'python' ? 'Python SDK' : t === 'javascript' ? 'JavaScript SDK' : 'API Endpoints'}
            </button>
          ))}
        </div>

        {/* Endpoints */}
        {tab === 'endpoints' && (
          <div className="anim">
            {tags.map(tag => (
              <div key={tag} style={{ marginBottom: '1.5rem' }}>
                <div style={{
                  fontSize: '0.625rem', fontWeight: 700, color: 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: '0.5rem'
                }}>{tag}</div>
                {endpoints.filter(e => e.tag === tag).map((ep, i) => (
                  <div key={i} style={{
                    display: 'flex', alignItems: 'center', gap: '0.65rem',
                    padding: '0.5rem 0.75rem', marginBottom: '0.3rem',
                    borderRadius: '8px', background: 'rgba(255,255,255,0.02)',
                    border: '1px solid var(--border-1)', fontSize: '0.8125rem'
                  }}>
                    <span style={{
                      fontFamily: 'var(--mono)', fontSize: '0.5625rem', fontWeight: 700,
                      padding: '0.15rem 0.45rem', borderRadius: '4px',
                      background: ep.method === 'GET' ? 'rgba(0,229,191,0.1)' : 'rgba(99,102,241,0.1)',
                      color: ep.method === 'GET' ? 'var(--safe)' : 'var(--info)',
                      flexShrink: 0
                    }}>{ep.method}</span>
                    <span style={{ fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-1)', flexShrink: 0 }}>
                      {ep.path}
                    </span>
                    <span style={{ color: 'var(--text-3)', fontSize: '0.6875rem', marginLeft: 'auto' }}>
                      {ep.desc}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        )}

        {/* Python SDK */}
        {tab === 'python' && (
          <div className="card anim">
            <div className="drug-result__section-title">Python SDK</div>
            <pre style={{
              background: 'var(--bg-secondary)', borderRadius: '10px', padding: '1.25rem',
              fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-1)',
              overflow: 'auto', lineHeight: 1.6, border: '1px solid var(--border-1)'
            }}>{pythonSDK}</pre>
          </div>
        )}

        {/* JavaScript SDK */}
        {tab === 'javascript' && (
          <div className="card anim">
            <div className="drug-result__section-title">JavaScript SDK</div>
            <pre style={{
              background: 'var(--bg-secondary)', borderRadius: '10px', padding: '1.25rem',
              fontFamily: 'var(--mono)', fontSize: '0.75rem', color: 'var(--text-1)',
              overflow: 'auto', lineHeight: 1.6, border: '1px solid var(--border-1)'
            }}>{jsSDK}</pre>
          </div>
        )}

        {/* Interactive Docs Link */}
        <div className="card anim" style={{ textAlign: 'center', marginTop: '1.5rem', padding: '1.5rem' }}>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-2)', marginBottom: '0.75rem' }}>
            Full interactive API documentation with try-it-out forms:
          </p>
          <div style={{ display: 'flex', gap: '0.65rem', justifyContent: 'center' }}>
            <a href="/api/docs" target="_blank" rel="noopener" className="btn btn--primary" id="btn-swagger">
              Swagger UI
            </a>
            <a href="/api/redoc" target="_blank" rel="noopener" className="btn btn--secondary" id="btn-redoc">
              ReDoc
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
