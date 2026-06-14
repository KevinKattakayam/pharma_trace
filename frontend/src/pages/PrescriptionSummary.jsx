import React, { useState, useEffect } from 'react';
import api from '../utils/api';
import { useVoice } from '../hooks/useVoice';
import AudioPlayback from '../components/AudioPlayback';
import AIDisclaimer from '../components/AIDisclaimer';

const StepIndicator = ({ current }) => (
  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '.5rem', marginBottom: '2rem' }}>
    {[1, 2, 3, 4].map(s => (
      <React.Fragment key={s}>
        <div style={{
          width: 32, height: 32, borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '.75rem', fontWeight: 800, fontFamily: 'var(--mono)',
          background: s < current ? 'var(--safe)' : s === current ? 'var(--accent)' : 'var(--bg-tertiary)',
          color: s <= current ? '#fff' : 'var(--text-3)',
          border: `1px solid ${s === current ? 'var(--accent)' : 'var(--border-1)'}`,
          boxShadow: s === current ? '0 0 16px var(--accent-glow)' : 'none',
          transition: 'all .4s var(--ease)'
        }}>
          {s < current ? '✓' : s}
        </div>
        {s < 4 && <div style={{ width: 40, height: 2, borderRadius: 2, background: s < current ? 'var(--safe)' : 'var(--border-1)', transition: 'background .4s' }} />}
      </React.Fragment>
    ))}
  </div>
);

export default function PrescriptionSummary() {
  const [step, setStep] = useState(1);
  const [medicinesText, setMedicinesText] = useState('');
  const [extractedMedicines, setExtractedMedicines] = useState([]);
  const [age, setAge] = useState('');
  const [conditions, setConditions] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const { isListening, supported, startListening, stopListening } = useVoice();

  // Load persisted session on mount
  useEffect(() => {
    try {
      const saved = localStorage.getItem('pharmaTrace_prescription_session');
      if (saved) {
        const parsed = JSON.parse(saved);
        const isValid = parsed.timestamp && (Date.now() - parsed.timestamp < 24 * 60 * 60 * 1000); // 24 hours
        
        if (parsed.result && isValid) {
          if (window.confirm("You have a previous prescription summary. Would you like to continue where you left off?")) {
            setResult(parsed.result);
            setMedicinesText(parsed.medicinesText || '');
            setStep(4);
          } else {
            localStorage.removeItem('pharmaTrace_prescription_session');
          }
        } else if (!isValid) {
          localStorage.removeItem('pharmaTrace_prescription_session');
        }
      }
    } catch (e) {
      console.error("Failed to load session", e);
    }
  }, []);

  const handleVoiceToggle = async () => {
    if (isListening) {
      const audioBlob = await stopListening();
      if (!audioBlob) return;
      const formData = new FormData();
      formData.append('file', audioBlob, 'recording.webm');
      try {
        setMedicinesText('Transcribing...');
        const response = await fetch('/api/v1/voice/transcribe', { method: 'POST', body: formData });
        const data = await response.json();
        setMedicinesText(prev => prev === 'Transcribing...' ? data.english_text : prev + ', ' + data.english_text);
      } catch { setMedicinesText(''); }
    } else { startListening(); }
  };

  const handleSummarize = async () => {
    if (!medicinesText.trim()) return;
    setLoading(true); setStep(3);
    try {
      const res = await api.summarizePrescription({
        medicines: medicinesText.split(',').map(m => m.trim()).filter(Boolean),
        age: age ? parseInt(age) : null,
        conditions: conditions.split(',').map(c => c.trim()).filter(Boolean),
        language: navigator.language?.split('-')[0] || 'en'
      });
      setResult(res); 
      setStep(4);
      localStorage.setItem('pharmaTrace_prescription_session', JSON.stringify({ 
        result: res, 
        medicinesText,
        timestamp: Date.now() 
      }));
    } catch { alert('Failed to summarize.'); setStep(2); }
    finally { setLoading(false); }
  };

  const shareOnWhatsApp = () => {
    if (!result?.whatsapp_text) return;
    window.open(`https://wa.me/?text=${encodeURIComponent(result.whatsapp_text)}`, '_blank');
  };

  const handlePhotoUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setMedicinesText('Extracting medicines from photo...');
    setExtractedMedicines([]);
    try {
      const reader = new FileReader();
      reader.onloadend = async () => {
        const base64 = reader.result;
        const res = await api.extractPrescriptionImage(base64);
        if (res && res.medicines && res.medicines.length > 0) {
          setExtractedMedicines(res.medicines);
          setMedicinesText(res.medicines.map(m => m.original_name).join(', '));
        } else {
          setMedicinesText('');
          alert('Could not read medicines clearly. Please type them manually.');
        }
      };
      reader.readAsDataURL(file);
    } catch (err) {
      setMedicinesText('');
      alert('Failed to process photo.');
    }
  };

  return (
    <div className="page anim">
      <div className="container" style={{ maxWidth: 620, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '1rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '.75rem' }}>
            <span className="hero__tag-dot" /> Doctor Visit Summarizer
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '.5rem' }}>Prescription Summary</h1>
          <p style={{ color: 'var(--text-2)', fontSize: '.9375rem' }}>Understand your doctor's visit. Speak, type, or scan your prescription.</p>
        </div>

        <StepIndicator current={step} />

        {step === 1 && (
          <div className="card anim" style={{ padding: '2rem' }}>
            <div style={{ fontSize: '.65rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.12em', color: 'var(--accent)', marginBottom: '1rem' }}>Step 1 of 3</div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '.5rem' }}>What medicines were prescribed?</h2>
            <p style={{ color: 'var(--text-3)', fontSize: '.875rem', marginBottom: '1.25rem' }}>Scan your prescription photo, or enter medicines manually.</p>
            
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1rem' }}>
               <label className="btn btn--secondary" style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem', cursor: 'pointer' }}>
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>
                  Scan Photo
                  <input type="file" accept="image/*" capture="environment" onChange={handlePhotoUpload} style={{ display: 'none' }} />
               </label>
            </div>
            
            {extractedMedicines.length > 0 && (
              <div className="anim" style={{ marginBottom: '1.5rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                <div style={{ fontSize: '0.75rem', fontWeight: 800, textTransform: 'uppercase', color: 'var(--text-3)' }}>Extracted Medicines</div>
                {extractedMedicines.map((med, i) => (
                  <div key={i} style={{ padding: '0.75rem', borderRadius: '8px', border: `1px solid ${med.is_verified ? 'var(--safe)' : 'var(--danger)'}`, background: med.is_verified ? 'rgba(16,185,129,0.05)' : 'rgba(239,68,68,0.05)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                       <strong style={{ color: 'var(--text-1)' }}>{med.original_name}</strong>
                       {med.is_verified ? <span style={{ color: 'var(--safe)', fontSize: '0.8rem' }}>✓ Verified ({med.resolved_name})</span> : <span style={{ color: 'var(--danger)', fontSize: '0.8rem', fontWeight: 600 }}>Unrecognized — please verify</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
            
            <div style={{ display: 'flex', gap: '.75rem', marginBottom: '1.5rem' }}>
              <textarea rows="4" placeholder="e.g. Paracetamol, Amoxicillin, Omeprazole" value={medicinesText} onChange={e => { setMedicinesText(e.target.value); setExtractedMedicines([]); }} style={{ flex: 1 }} />
              {supported && (
                <button onClick={handleVoiceToggle} style={{
                  width: 56, height: 56, borderRadius: '50%', flexShrink: 0, border: 'none', cursor: 'pointer',
                  background: isListening ? 'var(--danger)' : 'linear-gradient(135deg, var(--accent), var(--accent-2))',
                  color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: isListening ? '0 0 20px var(--danger-bg)' : '0 4px 16px var(--accent-glow)',
                  animation: isListening ? 'voicePulse 1.5s ease-in-out infinite' : 'none',
                  transition: 'all .3s var(--ease)'
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                    <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                    <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                    <line x1="12" y1="19" x2="12" y2="23" /><line x1="8" y1="23" x2="16" y2="23" />
                  </svg>
                </button>
              )}
            </div>
            <button className="btn btn--primary btn--lg" style={{ width: '100%' }} onClick={() => setStep(2)} disabled={!medicinesText.trim() || medicinesText === 'Extracting medicines from photo...'}>Confirm & Continue</button>
          </div>
        )}

        {step === 2 && (
          <div className="card anim" style={{ padding: '2rem' }}>
            <div style={{ fontSize: '.65rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.12em', color: 'var(--accent)', marginBottom: '1rem' }}>Step 2 of 3 (optional)</div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1.25rem' }}>Personalize Your Summary</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              <div>
                <label className="form-label">Patient Age</label>
                <input type="number" placeholder="e.g. 65" value={age} onChange={e => setAge(e.target.value)} />
              </div>
              <div>
                <label className="form-label">Existing Conditions</label>
                <input type="text" placeholder="e.g. Hypertension, Diabetes" value={conditions} onChange={e => setConditions(e.target.value)} />
              </div>
              <div style={{ display: 'flex', gap: '1rem', marginTop: '.5rem' }}>
                <button className="btn btn--secondary" onClick={() => setStep(1)}>Back</button>
                <button className="btn btn--primary" style={{ flex: 1 }} onClick={handleSummarize}>Generate Summary</button>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="card anim" style={{ textAlign: 'center', padding: '4rem 2rem' }}>
            <div className="spinner" style={{ width: 40, height: 40, margin: '0 auto 1.5rem' }} />
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '.5rem' }}>Analyzing your medicines...</h2>
            <p style={{ color: 'var(--text-3)', fontSize: '.875rem' }}>Cross-referencing CDSCO and checking for interactions.</p>
          </div>
        )}

        {step === 4 && result && (
          <div className="anim">
            {/* Safety Status */}
            {result.interactions?.some(i => i.is_dangerous) ? (
              <div className="card card--danger" style={{ marginBottom: '1.25rem', padding: '1.25rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '.65rem', marginBottom: '.5rem' }}>
                  <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--danger)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: '.75rem', fontWeight: 800 }}>!</div>
                  <h3 style={{ color: 'var(--danger)', fontWeight: 800, fontSize: '1rem' }}>Interaction Warning</h3>
                </div>
                {result.interactions.filter(i => i.is_dangerous).map((inter, i) => (
                  <p key={i} style={{ color: 'var(--text-1)', fontSize: '.875rem', lineHeight: 1.6 }}>{inter.description}</p>
                ))}
              </div>
            ) : (
              <div className="card card--safe" style={{ marginBottom: '1.25rem', padding: '1.25rem', display: 'flex', alignItems: 'center', gap: '.75rem' }}>
                <div style={{ width: 28, height: 28, borderRadius: '50%', background: 'var(--safe)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-inv)', fontSize: '.75rem', fontWeight: 800 }}>✓</div>
                <h3 style={{ color: 'var(--safe)', fontWeight: 800, fontSize: '1rem', margin: 0 }}>Medicines are safe to take together</h3>
              </div>
            )}

            {/* Unresolved Drugs Warning */}
            {result.unresolved_drugs?.length > 0 && (
              <div className="card card--danger" style={{ marginBottom: '1.25rem', padding: '1.25rem', borderLeft: '4px solid var(--danger)' }}>
                <h3 style={{ color: 'var(--danger)', fontWeight: 800, fontSize: '1rem', marginBottom: '.5rem' }}>Could Not Identify Some Medicines</h3>
                <p style={{ color: 'var(--text-1)', fontSize: '.875rem', lineHeight: 1.6 }}>
                  The following names were not found in our medical databases and have been excluded from the summary: 
                  <strong style={{ marginLeft: '4px' }}>{result.unresolved_drugs.join(', ')}</strong>
                </p>
                <p style={{ color: 'var(--text-3)', fontSize: '.75rem', marginTop: '.5rem' }}>Please double-check the spelling or consult your pharmacist for these specific items.</p>
              </div>
            )}

            {/* Medicine Cards */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.25rem' }}>
              {result.summary?.medicines?.map((med, i) => (
                <div key={i} className="card" style={{ padding: '1.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '.75rem', marginBottom: '1rem' }}>
                    <div style={{ width: 36, height: 36, borderRadius: 10, background: 'var(--accent-dim)', border: '1px solid var(--border-accent)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--accent)', fontWeight: 800, fontSize: '.875rem', fontFamily: 'var(--mono)' }}>{i + 1}</div>
                    <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-1)', letterSpacing: '-0.02em' }}>{med.name}</h3>
                  </div>
                  <div style={{ display: 'grid', gap: '.65rem', fontSize: '.9rem' }}>
                    <div style={{ display: 'flex', gap: '.5rem' }}><span style={{ color: 'var(--accent)', fontWeight: 700, minWidth: 60 }}>Treats</span><span style={{ color: 'var(--text-2)' }}>{med.treats}</span></div>
                    <div style={{ display: 'flex', gap: '.5rem' }}><span style={{ color: 'var(--accent)', fontWeight: 700, minWidth: 60 }}>When</span><span style={{ color: 'var(--text-2)' }}>{med.when_to_take}</span></div>
                    <div style={{ display: 'flex', gap: '.5rem' }}><span style={{ color: 'var(--accent)', fontWeight: 700, minWidth: 60 }}>Duration</span><span style={{ color: 'var(--text-2)' }}>{med.duration}</span></div>
                    <div style={{ padding: '.65rem .85rem', background: 'var(--warn-bg)', borderLeft: '3px solid var(--warn)', borderRadius: '0 8px 8px 0', marginTop: '.25rem' }}>
                      <span style={{ fontSize: '.65rem', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--warn)', display: 'block', marginBottom: '.2rem' }}>Warning</span>
                      <span style={{ fontSize: '.875rem', color: 'var(--text-1)' }}>{med.warning}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>

            {/* Refill */}
            <div className="card" style={{ marginBottom: '1.25rem', textAlign: 'center', padding: '1.25rem' }}>
              <div style={{ fontSize: '.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.1em', color: 'var(--text-3)', marginBottom: '.35rem' }}>Refill Reminder</div>
              <div style={{ fontSize: '1.25rem', fontWeight: 800, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{result.refill_date || "28 days from now"}</div>
            </div>

            {/* Audio Playback */}
            {result.audio_script && (
              <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '1.25rem' }}>
                <AudioPlayback audioScript={result.audio_script} language={result.language} />
              </div>
            )}

            <div style={{ marginBottom: '1.25rem' }}>
              <AIDisclaimer aiGenerated={true} />
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: '1rem' }}>
              <button className="btn btn--secondary" onClick={() => { setStep(1); setMedicinesText(''); setResult(null); localStorage.removeItem('pharmaTrace_prescription_session'); }}>Start Over</button>
              <button className="btn btn--primary" style={{ flex: 1, background: '#25D366', borderColor: 'rgba(37,211,102,0.3)', boxShadow: '0 8px 20px rgba(37,211,102,0.3)' }} onClick={shareOnWhatsApp}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51a12.8 12.8 0 0 0-.57-.01c-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 0 1-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 0 1-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 0 1 2.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0 0 12.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 0 0 5.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 0 0-3.48-8.413z"/></svg>
                Share on WhatsApp
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
