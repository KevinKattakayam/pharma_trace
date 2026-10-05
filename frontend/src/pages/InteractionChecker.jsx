import React, { useState, useCallback } from 'react';
import api from '../utils/api';
import AIDisclaimer from '../components/AIDisclaimer';
import { getSeverityLabel, getSeverityColor } from '../utils/formatters';

const Icons = {
  flask: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M6 3h12"/><path d="M19 18a2 2 0 01-2 2H7a2 2 0 01-2-2V5h14v13z"/><path d="M9 3v17"/><path d="M15 3v17"/></svg>,
  plus: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>,
  pulse: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
  info: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>,
  brain: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><path d="M9.5 2A5.5 5.5 0 004 7.5c0 1.25.4 2.4 1.1 3.3l-1.1 4.7 4.7-1.1c.9.7 2.05 1.1 3.3 1.1a5.5 5.5 0 005.5-5.5V7.5A5.5 5.5 0 0012 2h-2.5z"/><path d="M14.5 2A5.5 5.5 0 0120 7.5c0 1.25-.4 2.4-1.1 3.3l1.1 4.7-4.7-1.1c-.9.7-2.05 1.1-3.3 1.1a5.5 5.5 0 01-5.5-5.5V7.5A5.5 5.5 0 0112 2h2.5z"/></svg>
};

export default function InteractionChecker() {
  const [drugs, setDrugs] = useState(['', '']);
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState(null);
  const [aiExplanation, setAiExplanation] = useState({});
  const [error, setError] = useState(null);

  const addDrug = () => { if (drugs.length < 10) setDrugs([...drugs, '']); };
  const removeDrug = (i) => { if (drugs.length > 2) setDrugs(drugs.filter((_, idx) => idx !== i)); };
  const updateDrug = (i, v) => { const u = [...drugs]; u[i] = v; setDrugs(u); };

  const handleCheck = useCallback(async () => {
    const valid = drugs.filter(d => d.trim());
    if (valid.length < 2) { setError('Enter at least 2 medications to initialize analysis'); return; }
    setLoading(true); setError(null); setResults(null); setAiExplanation({});
    try {
      const res = await api.checkInteractions(valid);
      setResults(res);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, [drugs]);

  const handleExplain = async (ix, index) => {
    if (aiExplanation[index]) return;
    setAiExplanation(prev => ({ ...prev, [index]: { loading: true } }));
    try {
      const res = await api.explainInteraction(ix.drug_a, ix.drug_b, ix.clinical_effect);
      setAiExplanation(prev => ({ ...prev, [index]: { loading: false, data: res } }));
    } catch {
      setAiExplanation(prev => ({ ...prev, [index]: { loading: false, error: true } }));
    }
  };

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 900 }}>
        {/* Header Block */}
        <div style={{ marginBottom: '3rem' }} className="anim">
          <div className="hero__tag" style={{ marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> General information, not advice
          </div>
          <h1 style={{ fontSize: '2.5rem', fontWeight: 900, letterSpacing: '-0.04em', lineHeight: 1.1, marginBottom: '0.75rem' }}>
            Interaction Intelligence
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '1rem', maxWidth: 600 }}>
            Utilizing Llama 3.3 70B and official FDA FAERS co-occurrence signals to detect dangerous contraindications in multi-drug regimens.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: '2rem', alignItems: 'start' }}>
          <div className="anim anim-left">
            {/* Input Dashboard */}
            <div className="card" style={{ padding: '2rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1.5rem' }}>
                <span style={{ color: 'var(--accent)' }}>{Icons.flask}</span>
                <h3 style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-2)' }}>Compound Entry Registry</h3>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                {drugs.map((drug, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }} className="anim-up">
                    <div style={{
                      width: '28px', height: '28px', borderRadius: '8px', background: 'var(--bg-tertiary)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '0.625rem',
                      fontWeight: 800, color: 'var(--text-3)', border: '1px solid var(--border-1)'
                    }}>{String(i + 1).padStart(2, '0')}</div>
                    <input
                      type="text" value={drug} onChange={(e) => updateDrug(i, e.target.value)}
                      placeholder={i === 0 ? 'e.g., Warfarin' : i === 1 ? 'e.g., Aspirin' : 'Search Medication...'}
                      className="input--clinical"
                      style={{ flex: 1, height: '42px' }}
                      onKeyDown={(e) => { if (e.key === 'Enter') handleCheck(); }}
                    />
                    {drugs.length > 2 && (
                      <button className="btn--icon-tiny" onClick={() => removeDrug(i)} style={{ color: 'var(--danger)' }}>
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M18 6L6 18M6 6l12 12"/></svg>
                      </button>
                    )}
                  </div>
                ))}
              </div>
              
              <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
                <button className="btn btn--secondary" onClick={addDrug} disabled={drugs.length >= 10} style={{ padding: '0.6rem 1rem' }}>
                  {Icons.plus} Add Compound
                </button>
                <button className="btn btn--primary" onClick={handleCheck} disabled={loading} style={{ flex: 1 }}>
                  {loading ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <>{Icons.pulse} Run Analysis</>}
                </button>
              </div>
              {error && <div className="error-badge" style={{ marginTop: '1rem' }}>{error}</div>}
            </div>

            {/* Results Display Area */}
            {results && (
              <div className="anim anim-up" style={{ marginTop: '2rem' }}>
                 {/* Detail Cards */}
                 {results.interactions?.length > 0 ? (
                   <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                     {results.interactions.map((ix, i) => (
                       <InteractionCard key={i} ix={ix} index={i} ai={aiExplanation[i]} onExplain={() => handleExplain(ix, i)} />
                     ))}
                   </div>
                 ) : (
                   <div className="card" style={{ padding: '3rem', textAlign: 'center' }}>
                      <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>✅</div>
                      <h3 style={{ fontSize: '1.25rem', fontWeight: 800 }}>Clean Diagnostic</h3>
                      <p style={{ color: 'var(--text-3)', fontSize: '0.875rem', marginTop: '0.5rem' }}>
                        No known adverse interactions detected between {results.drug_count} compounds.
                      </p>
                   </div>
                 )}
              </div>
            )}
          </div>

          {/* Side Panel: Information & Global State */}
          <div className="anim anim-right">
            {results ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                 <div className="card" style={{ padding: '1.5rem', background: results.overall_risk === 'high' ? 'rgba(239, 68, 68, 0.05)' : 'var(--bg-tertiary)' }}>
                    <div style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-3)', marginBottom: '1rem' }}>Integrity Assessment</div>
                    <div style={{ fontSize: '2rem', fontWeight: 900, color: `var(--${results.overall_risk === 'high' ? 'danger' : results.overall_risk === 'moderate' ? 'warn' : 'safe'})` }}>
                      {results.overall_risk?.toUpperCase()}
                    </div>
                    <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginTop: '0.5rem', lineHeight: 1.5 }}>
                      Composite safety rating across all {results.drug_count} medications.
                    </p>
                 </div>

                 <div className="card" style={{ padding: '1.5rem' }}>
                    <div style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: 'var(--text-3)', marginBottom: '1.25rem' }}>Medicines checked together</div>
                    <div className="mini-matrix">
                        <table>
                          <tbody>
                            {results.matrix?.map((row, i) => (
                              <tr key={i}>
                                {row.map((cell, j) => (
                                  <td key={j} className={`matrix-cell--${cell}`} title={`${results.drug_names[i]} x ${results.drug_names[j]}`}>
                                    {i === j ? '•' : ''}
                                  </td>
                                ))}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', marginTop: '1rem' }}>
                       {results.drug_names?.map((n, i) => (
                         <span key={i} style={{ fontSize: '0.625rem', fontWeight: 700, color: 'var(--text-3)', background: 'var(--bg-tertiary)', padding: '2px 6px', borderRadius: '4px' }}>
                           {i+1}. {n}
                         </span>
                       ))}
                    </div>
                 </div>

                 <div className="card" style={{ padding: '1.5rem', border: '1px dashed var(--border-2)', background: 'transparent' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent)', marginBottom: '0.75rem' }}>
                      {Icons.info} <span style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Clinical Note</span>
                    </div>
                     <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', lineHeight: 1.6 }}>
                      Verification engine synthesized data from: {results.data_sources?.join(', ') || 'Global Pharma DB'}. 
                      AI explanations are generated by Llama 3.3.
                    </p>
                 </div>
                 
                 <AIDisclaimer aiGenerated={results.ai_generated} />
              </div>
            ) : (
              <div className="card" style={{ padding: '1.5rem', opacity: 0.6 }}>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', textAlign: 'center' }}>
                  Awaiting input compounds for analysis initialization.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function InteractionCard({ ix, index, ai, onExplain }) {
  const sev = ix.severity === 'major' || ix.severity === 'contraindicated' ? 'danger' : ix.severity === 'moderate' ? 'warn' : 'info';
  
  return (
    <div className="card anim-up" style={{ padding: '1.5rem', borderLeft: `4px solid var(--${sev})` }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
        <div>
          <div style={{ fontSize: '0.625rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.1em', color: `var(--${sev})`, marginBottom: '0.25rem' }}>
            {getSeverityLabel(ix.severity)} Interaction
          </div>
          <h4 style={{ fontSize: '1.125rem', fontWeight: 800 }}>{ix.drug_a} + {ix.drug_b}</h4>
        </div>
        <button className="btn btn--tiny btn--ghost" onClick={onExplain} disabled={ai?.loading || ai?.data}>
          {ai?.loading ? <span className="spinner--tiny" /> : ai?.data ? '✓ AI Explained' : <>{Icons.brain} AI Insight</>}
        </button>
      </div>

      <p style={{ fontSize: '0.875rem', color: 'var(--text-2)', lineHeight: 1.6, marginBottom: '1rem' }}>
        {ix.clinical_effect}
      </p>

      {ix.recommendation && (
        <div style={{ 
          background: 'rgba(255,255,255,0.03)', padding: '0.75rem', borderRadius: '8px', 
          fontSize: '0.75rem', color: 'var(--safe)', border: '1px solid rgba(0,229,191,0.1)' 
        }}>
          <strong>What to do:</strong> {ix.recommendation}
        </div>
      )}

      {ai?.data && (
        <div className="ai-overlay anim-scale" style={{ marginTop: '1rem', borderTop: '1px solid var(--border-1)', paddingTop: '1rem' }}>
           <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
             <span style={{ color: 'var(--accent)' }}>{Icons.brain}</span>
             <span style={{ fontSize: '0.6875rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-2)' }}>How this was worked out</span>
           </div>
           <p style={{ fontSize: '0.8125rem', color: 'var(--text-3)', lineHeight: 1.6 }}>{ai.data.explanation}</p>
           {ai.data.what_to_do && (
             <p style={{ marginTop: '0.75rem', fontSize: '0.75rem', color: 'var(--accent)', fontWeight: 700 }}>→ Clinical Action: {ai.data.what_to_do}</p>
           )}
        </div>
      )}
    </div>
  );
}

