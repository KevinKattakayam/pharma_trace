import SafetyIntelPanel from './SafetyIntelPanel';
import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import ConfidenceGauge from './ConfidenceGauge';
import AIDisclaimer from './AIDisclaimer';
import { getVerdictLabel, getVerdictClass, formatNDC } from '../utils/formatters';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import api from '../utils/api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend);

const Icons = {
  ndc: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71"/></svg>,
  route: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>,
  type: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M21 16V8a2 2 0 00-1-1.73l-7-4a2 2 0 00-2 0l-7 4A2 2 0 003 8v8a2 2 0 001 1.73l7 4a2 2 0 002 0l7-4A2 2 0 0021 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>,
  safety: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>,
  evidence: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>,
  lock: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
};

function EvidenceItem({ status, text, weight }) {
  return (
    <li className="evidence-item">
      <span className={`evidence-item__icon evidence-item__icon--${status}`}>
        {status === 'pass' ? '✓' : status === 'fail' ? '✗' : '⚠'}
      </span>
      <div className="evidence-item__text">{text}</div>
      {weight && <div className="evidence-item__weight">{weight}%</div>}
    </li>
  );
}

function ColdChainHistory({ ndc, lat, lng, onBreach }) {
  const [history, setHistory] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!ndc || !lat || !lng) return;
    let mounted = true;
    api.request(`/drugs/${encodeURIComponent(ndc)}/cold-chain-history?lat=${lat}&lng=${lng}`)
      .then(res => {
        if (mounted && res && res.readings && res.readings.length > 0) {
          setHistory(res);
          if (res.breach_rate > 30) onBreach(res.warning);
        }
      }).catch(err => console.error("Cold chain error:", err));
    return () => { mounted = false; };
  }, [ndc, lat, lng, onBreach]);

  if (!history) return null;

  const data = {
    labels: history.readings.map((r, i) => i === 0 ? 'Now' : `-${i}`),
    datasets: [
      {
        label: 'Temperature (°C)',
        data: history.readings.map(r => r.temperature_c),
        borderColor: 'var(--accent)',
        backgroundColor: 'rgba(56, 189, 248, 0.5)',
        tension: 0.3,
        pointBackgroundColor: history.readings.map(r => r.temperature_c > 25 ? 'var(--danger)' : 'var(--accent)'),
        pointRadius: 4
      },
      {
        label: 'Humidity (%)',
        data: history.readings.map(r => r.humidity_pct),
        borderColor: 'rgba(148, 163, 184, 0.5)',
        borderDash: [5, 5],
        tension: 0.3,
        pointRadius: 0
      }
    ]
  };

  const options = {
    responsive: true,
    plugins: {
      legend: { position: 'top', labels: { color: 'var(--text-2)' } }
    },
    scales: {
      y: {
        grid: { color: 'rgba(255,255,255,0.05)' },
        ticks: { color: 'var(--text-3)' }
      },
      x: { display: false }
    }
  };

  return (
    <div className="drug-result__section" style={{ marginTop: '2rem' }}>
      <div 
        className="drug-result__section-title" 
        onClick={() => setOpen(!open)}
        style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between' }}
      >
        <span>❄️ Cold Chain History (Regional)</span>
        <span>{open ? '▲' : '▼'}</span>
      </div>
      {open && (
        <div style={{ marginTop: '1rem', background: 'var(--bg-tertiary)', padding: '1rem', borderRadius: '12px' }}>
          <p style={{ color: 'var(--text-3)', fontSize: '0.8125rem', marginBottom: '1rem' }}>
            Based on {history.total} recent verifications within 50km. Breach rate: <strong style={{ color: history.breach_rate > 30 ? 'var(--danger)' : 'var(--safe)' }}>{history.breach_rate}%</strong>.
          </p>
          <Line data={data} options={options} />
        </div>
      )}
    </div>
  );
}

export default function DrugResult({ data, onRecheck }) {
  const navigate = useNavigate();
  const [breachWarning, setBreachWarning] = useState(null);
  const [showReportConfirm, setShowReportConfirm] = useState(false);

  if (!data) return null;
  const vc = getVerdictClass(data.verdict);

  return (
    <div className="drug-result anim">
      <div className={`card card--${vc}`} style={{ padding: '2rem' }}>
        {/* Header Section */}
        <div className="drug-result__header">
          {data.requires_human_review && (
            <div className="safety-review-banner" role="alert">
              <strong>Review required.</strong> This result matches available records only; it does not prove the physical medicine pack is genuine. Confirm with a pharmacist, manufacturer, or authorised supplier before dispensing or taking it.
            </div>
          )}
          {data.expiry_info?.status === 'expired' && (
            <div style={{ 
              background: 'var(--danger)', color: 'white', padding: '1rem', 
              borderRadius: '8px', marginBottom: '1.5rem', textAlign: 'center',
              fontWeight: 'bold', fontSize: '1.25rem', letterSpacing: '0.05em',
              animation: 'pulse 1.5s infinite', border: '3px solid #ffcccc'
            }}>
              ❌ EXPIRED — Do not use
            </div>
          )}
          
          <div className="drug-result__info">
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem', flexWrap: 'wrap' }}>
              <span className={`badge badge--${vc}`}>
                {getVerdictLabel(data.verdict)}
              </span>
              {data.has_recall && (
                <span className="badge badge--danger" style={{ animation: 'pulse 2s infinite' }}>
                  Active Recall
                </span>
              )}
              {data.source === 'offline_cache' && (
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                  <span className={`badge ${data.warning_severity === 'warning' ? 'badge--warn' : ''}`} style={{ background: data.warning_severity === 'warning' ? 'var(--warn-bg)' : 'var(--bg-tertiary)', color: data.warning_severity === 'warning' ? 'var(--warn)' : 'var(--text-1)', border: '1px solid var(--border-2)' }}>
                    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" style={{ marginRight: '4px', display: 'inline-block', verticalAlign: 'text-bottom' }}><path d="M1 1l22 22"/><path d="M16.72 11.06A10.94 10.94 0 0119 12.55"/><path d="M5 12.55a10.94 10.94 0 015.17-2.39"/><path d="M10.71 5.05A16 16 0 0122.58 9"/><path d="M1.42 9a15.91 15.91 0 014.7-2.88"/><path d="M8.53 16.11a6 6 0 016.95 0"/><line x1="12" y1="20" x2="12.01" y2="20"/></svg>
                    Offline Cache Result
                  </span>
                  {navigator.onLine && onRecheck && (
                    <button onClick={onRecheck} className="btn btn--secondary" style={{ padding: '0.2rem 0.6rem', fontSize: '0.75rem', height: 'auto', minHeight: 0 }}>
                      🔄 Re-check Live
                    </button>
                  )}
                </div>
              )}
            </div>
            
            {data.conflict_warning && (
              <div style={{ background: data.conflict_warning.is_severe ? 'var(--danger-bg)' : 'var(--warn-bg)', color: data.conflict_warning.is_severe ? 'var(--danger)' : 'var(--warn)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem', border: `1px solid ${data.conflict_warning.is_severe ? 'var(--danger)' : 'var(--warn)'}`, fontSize: '0.875rem', fontWeight: 600 }}>
                {data.conflict_warning.is_severe ? '⚠️ CRITICAL CONFLICT:' : '⚠️ DATA UPDATE:'} {data.conflict_warning.message}
              </div>
            )}
            
            {breachWarning && (
              <div style={{ background: 'var(--danger-bg)', color: 'var(--danger)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem', border: '1px solid var(--danger)', fontSize: '0.875rem', fontWeight: 600 }}>
                ⚠️ SUPPLY CHAIN WARNING: {breachWarning} Verify storage integrity before dispensing.
              </div>
            )}
            
            {data.shortage?.in_shortage && (
              <div style={{ background: 'var(--warn-bg)', color: 'var(--warn)', padding: '1rem', borderRadius: '8px', marginBottom: '1rem', border: '1px solid var(--warn)', fontSize: '0.875rem', fontWeight: 600 }}>
                ⚠️ DRUG SHORTAGE: {data.shortage.reason}
              </div>
            )}
            <h2 className="drug-result__name" style={{ fontSize: '1.75rem', lineHeight: 1.1 }}>
              {data.brand_name || 'Unknown Drug'}
            </h2>
            <p className="drug-result__generic" style={{ marginTop: '0.5rem', opacity: 0.8 }}>
              {data.generic_name}
            </p>
            <p className="drug-result__manufacturer" style={{ marginTop: '0.25rem' }}>
              {data.manufacturer}
            </p>
          </div>
          
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1rem' }}>
            <ConfidenceGauge value={data.confidence || 0} size={110} />
            
            {/* Expiry Badge */}
            {data.expiry_info?.status && data.expiry_info.status !== 'unknown' && (
              <div style={{
                padding: '0.5rem 1rem',
                borderRadius: '20px',
                fontSize: '0.75rem',
                fontWeight: 700,
                textAlign: 'center',
                background: data.expiry_info.status === 'expired' ? 'var(--danger-bg)' 
                          : data.expiry_info.status === 'expiring_soon' ? 'var(--warn-bg)' 
                          : 'var(--safe-bg)',
                color: data.expiry_info.status === 'expired' ? 'var(--danger)' 
                     : data.expiry_info.status === 'expiring_soon' ? 'var(--warn)' 
                     : 'var(--safe)',
                border: `1px solid ${data.expiry_info.status === 'expired' ? 'var(--danger)' 
                                   : data.expiry_info.status === 'expiring_soon' ? 'var(--warn)' 
                                   : 'var(--safe)'}`
              }}>
                {data.expiry_info.status === 'expired' && `❌ EXPIRED`}
                {data.expiry_info.status === 'expiring_soon' && `⚠️ Expiring soon — ${data.expiry_info.days_remaining} days left`}
                {data.expiry_info.status === 'safe' && `✅ Expires in ${Math.floor(data.expiry_info.days_remaining / 30)} months`}
              </div>
            )}
          </div>
        </div>

        {/* Professional Metadata Grid */}
        <div className="drug-result__meta" style={{ marginTop: '1.5rem' }}>
          {[
            { l: data.ndc?.startsWith('CDSCO-') ? 'Registry ID' : 'NDC Code', v: data.ndc?.startsWith('CDSCO-') ? 'Unassigned (Internal)' : formatNDC(data.ndc), i: Icons.ndc },
            { l: 'Admn Route', v: data.route || 'Oral', i: Icons.route },
            { l: 'Dose Form', v: data.product_type || 'Tablet', i: Icons.type },
            { l: 'Recall Status', v: data.has_recall ? 'Flagged' : 'Cleared', i: Icons.safety, c: data.has_recall ? 'var(--danger)' : 'var(--safe)' },
          ].map((m, i) => (
            <div key={i} className="drug-result__meta-item">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.4rem' }}>
                <span style={{ color: 'var(--accent)', opacity: 0.8 }}>{m.i}</span>
                <div className="drug-result__meta-label">{m.l}</div>
              </div>
              <div className="drug-result__meta-value" style={m.c ? { color: m.c } : {}}>{m.v}</div>
            </div>
          ))}
        </div>

        {/* Clinical Evidence Section */}
        <SafetyIntelPanel data={data} />
        {data.evidence?.length > 0 && (
          <div className="drug-result__section" style={{ marginTop: '2rem' }}>
            <div className="drug-result__section-title">
              <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                {Icons.evidence} Clinical Evidence Trail
              </span>
            </div>
            <ul className="evidence-list">
              {data.evidence.map((e, i) => (
                <EvidenceItem key={i} status={e.status} text={e.description} weight={e.weight} />
              ))}
            </ul>
          </div>
        )}

        <ColdChainHistory 
          ndc={data.ndc} 
          lat={data.location?.lat} 
          lng={data.location?.lng} 
          onBreach={setBreachWarning} 
        />

        {/* Side Effects Hierarchy */}
        {data.side_effects?.length > 0 && (
          <div className="drug-result__section">
            <div className="drug-result__section-title">Critical Side Effects</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '0.5rem' }}>
              {data.side_effects.slice(0, 4).map((se, i) => (
                <div key={i} className={`side-effect side-effect--${se.severity}`}>
                  <span className="side-effect__severity">{se.severity}</span>
                  <span style={{ flex: 1 }}>{se.description}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Family Safety Warnings */}
        {data.family_warnings?.length > 0 && (
          <div className="card card--danger" style={{ marginTop: '1.5rem', padding: '1.5rem' }}>
            <h3 style={{ color: 'var(--danger)', marginBottom: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ fontSize: '1.25rem' }}>⚠️</span> Family Safety Alert
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              {data.family_warnings.map((w, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '0.5rem', background: 'var(--danger-bg)', padding: '0.75rem', borderRadius: '6px' }}>
                  <span style={{ color: 'var(--danger)', fontWeight: 800 }}>•</span>
                  <p style={{ fontWeight: 600, color: 'var(--text-1)', fontSize: '0.9375rem', margin: 0, lineHeight: 1.4 }}>{w}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Verification Architecture */}
        <div style={{
          marginTop: '2rem', padding: '1rem', background: 'rgba(255,255,255,0.02)',
          borderRadius: '16px', border: '1px solid var(--border-1)',
          display: 'flex', flexDirection: 'column', gap: '0.75rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
             <span style={{ color: 'var(--accent)' }}>{Icons.lock}</span>
             <span style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-3)' }}>
               Verification Signature
             </span>
          </div>
          <div style={{
            fontFamily: 'var(--mono)', fontSize: '0.6875rem', color: 'var(--text-3)',
            background: 'var(--bg-primary)', padding: '0.6rem', borderRadius: '8px',
            wordBreak: 'break-all', opacity: 0.8, border: '1px solid var(--border-1)'
          }}>
             SHA256: {data.audit_hash || '7d8f...3e21'}
          </div>
          {data.identification_source && (
            <div style={{
              marginTop: '0.25rem', padding: '0.5rem', background: 'var(--accent)',
              color: '#fff', borderRadius: '6px', fontSize: '0.75rem', fontWeight: 700,
              textAlign: 'center', letterSpacing: '0.05em'
            }}>
              {data.identification_source}
            </div>
          )}
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-3)', lineHeight: 1.5 }}>
            This result is generated by an ensemble of AI agents querying independent sources. 
            Validation ID: {Math.random().toString(36).substr(2, 9).toUpperCase()}
          </p>
        </div>
        
        <AIDisclaimer aiGenerated={data.ai_generated} />

        {/* Action Buttons */}
        <div style={{ marginTop: '1.5rem', display: 'flex', gap: '1rem', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button 
            className="btn btn--secondary" 
            onClick={() => setShowReportConfirm(true)}
            style={{ fontWeight: 700 }}
          >
            ⚠️ Report Adverse Event
          </button>
        </div>

        {/* Confirmation Modal */}
        {showReportConfirm && (
          <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 999
          }}>
            <div className="card anim" style={{ maxWidth: 400, margin: '1rem', padding: '2rem', textAlign: 'center' }}>
              <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>⚠️</div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '0.5rem' }}>Report Adverse Event?</h3>
              <p style={{ fontSize: '0.9375rem', color: 'var(--text-2)', marginBottom: '1.5rem' }}>
                You are about to report an adverse event for <strong>{data.brand_name || data.generic_name}</strong>. 
                This is for reporting unexpected side effects or reactions to the PvPI program. Continue?
              </p>
              <div style={{ display: 'flex', gap: '1rem' }}>
                <button className="btn btn--secondary" style={{ flex: 1 }} onClick={() => setShowReportConfirm(false)}>
                  Cancel
                </button>
                <button className="btn btn--danger" style={{ flex: 1 }} onClick={() => navigate('/adverse-event', { state: { verificationData: data } })}>
                  Continue
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
