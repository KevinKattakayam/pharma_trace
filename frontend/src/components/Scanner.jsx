import React, { useState, useCallback } from 'react';
import { useScanner } from '../hooks/useScanner';

export default function Scanner({ onBarcodeScan, onImageCapture, onManualEntry }) {
  const { videoRef, isScanning, error, startCamera, stopCamera, captureFrame } = useScanner();
  const [manualBarcode, setManualBarcode] = useState('');
  const [mode, setMode] = useState('manual');

  const handleCapture = useCallback(() => {
    const frame = captureFrame();
    if (frame && onImageCapture) { 
      onImageCapture(frame); 
      stopCamera(); 
    }
  }, [captureFrame, onImageCapture, stopCamera]);

  const handleManualSubmit = useCallback((e) => {
    e.preventDefault();
    if (manualBarcode.trim() && onManualEntry) { 
      onManualEntry(manualBarcode.trim()); 
      setManualBarcode(''); 
    }
  }, [manualBarcode, onManualEntry]);

  const modes = [
    { key: 'barcode', label: 'Scan Barcode', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg> },
    { key: 'photo', label: 'AI Photo ID', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg> },
    { key: 'manual', label: 'Type NDC', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg> }
  ];

  return (
    <div className="anim">
      {/* Precision Mode Selector */}
      <div style={{ 
        display: 'flex', background: 'var(--bg-tertiary)', 
        padding: '4px', borderRadius: '14px', marginBottom: '2rem',
        border: '1px solid var(--border-1)', maxWidth: '400px', margin: '0 auto 2.5rem'
      }}>
        {modes.map(m => (
          <button key={m.key}
            onClick={() => { 
              setMode(m.key); 
              if (m.key !== 'manual' && !isScanning) startCamera(); 
              if (m.key === 'manual') stopCamera(); 
            }}
            style={{
              flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
              padding: '0.75rem 0.5rem', borderRadius: '10px', fontSize: '0.75rem', fontWeight: 700,
              color: mode === m.key ? '#fff' : 'var(--text-3)',
              background: mode === m.key ? 'var(--accent)' : 'transparent',
              transition: 'all 0.3s var(--ease)',
              boxShadow: mode === m.key ? '0 4px 12px rgba(124, 92, 252, 0.3)' : 'none'
            }}>
            {m.icon}
            <span style={{ display: mode === m.key ? 'inline' : 'none' }}>{m.label}</span>
          </button>
        ))}
      </div>

      {/* Clinical Viewport */}
      {mode !== 'manual' && (
        <div style={{ position: 'relative' }}>
          <div className="scanner" id="scanner-viewport">
            <video ref={videoRef} className="scanner__video" autoPlay playsInline muted />
            <div className="scanner__overlay">
              <div className="scanner__frame">
                <span className="scanner__corner scanner__corner--tl" />
                <span className="scanner__corner scanner__corner--tr" />
                <span className="scanner__corner scanner__corner--bl" />
                <span className="scanner__corner scanner__corner--br" />
                
                {/* Visual AI Indicators */}
                <div style={{
                  position: 'absolute', top: '-40px', left: '50%', transform: 'translateX(-50%)',
                  whiteSpace: 'nowrap', fontSize: '0.625rem', fontWeight: 800, color: 'var(--accent)',
                  textTransform: 'uppercase', letterSpacing: '0.15em', display: 'flex', alignItems: 'center', gap: '0.5rem'
                }}>
                  <span className="hero__tag-dot" /> AI Recognition Active
                </div>
              </div>
            </div>
            
            <div className="scanner__status">
              {isScanning ? (
                <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} />
                  {mode === 'barcode' ? 'Align barcode with center line' : 'Capture clear packaging photo'}
                </span>
              ) : 'Adjusting optics…'}
            </div>
          </div>

          <div style={{ display: 'flex', justifyContent: 'center', gap: '1rem', marginTop: '2.5rem' }}>
            {isScanning ? (
              <>
                <button className="btn btn--primary btn--lg"
                  onClick={() => { 
                    if (mode === 'barcode') { 
                      const f = captureFrame(); 
                      if (f && onBarcodeScan) onBarcodeScan(f); 
                    } else handleCapture(); 
                  }}
                  id={mode === 'barcode' ? 'btn-scan-barcode' : 'btn-capture-photo'}>
                  {mode === 'barcode' ? 'Capture Scan' : 'Identify Package'}
                </button>
                <button className="btn btn--secondary" onClick={stopCamera} id="btn-stop-camera">Cancel</button>
              </>
            ) : (
              !error && <button className="btn btn--primary btn--lg" onClick={startCamera}>Re-enable Optical Sensor</button>
            )}
          </div>
        </div>
      )}

      {/* Manual Clinical Entry */}
      {mode === 'manual' && (
        <div className="card anim" style={{ maxWidth: 420, margin: '0 auto', padding: '2rem' }}>
          <form onSubmit={handleManualSubmit}>
            <div className="form-group" style={{ marginBottom: '1.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                <label className="form-label" htmlFor="manual-barcode">Direct NDC Entry</label>
                <span style={{ fontSize: '0.625rem', fontWeight: 700, color: 'var(--text-3)' }}>10 Digits</span>
              </div>
              <input 
                id="manual-barcode" 
                type="text" 
                value={manualBarcode} 
                onChange={(e) => setManualBarcode(e.target.value)}
                placeholder="XXXXX-XXX-XX" 
                style={{ fontSize: '1.125rem', fontWeight: 600, letterSpacing: '0.05em', textAlign: 'center' }}
                autoComplete="off" 
                autoFocus 
              />
            </div>
            <button 
              type="submit" 
              className="btn btn--primary btn--lg" 
              style={{ width: '100%' }} 
              disabled={!manualBarcode.trim()} 
              id="btn-manual-verify"
            >
              Initialize Verification
            </button>
          </form>

          <div style={{
            marginTop: '2rem', padding: '1.25rem', background: 'var(--bg-primary)',
            borderRadius: '16px', border: '1px solid var(--border-2)', position: 'relative'
          }}>
            <div style={{ 
              position: 'absolute', top: '-10px', left: '20px', background: 'var(--bg-primary)',
              padding: '0 8px', fontSize: '0.625rem', fontWeight: 800, color: 'var(--accent)',
              textTransform: 'uppercase', letterSpacing: '0.1em'
            }}>
              Sandbox Mode
            </div>
            <p style={{ fontSize: '0.8125rem', color: 'var(--text-2)', lineHeight: 1.6 }}>
              Use <span style={{ fontFamily: 'var(--mono)', color: 'var(--accent)', fontWeight: 700 }}>59726-065-30</span> for a clinical-grade verification demonstration.
            </p>
          </div>
        </div>
      )}

      {error && (
        <div className="card card--danger anim" style={{ maxWidth: 420, margin: '2rem auto 0', textAlign: 'center' }}>
          <div style={{ fontSize: '1.25rem', marginBottom: '0.5rem' }}>⚠️</div>
          <p style={{ color: 'var(--danger)', fontSize: '0.875rem', fontWeight: 600, marginBottom: '1rem' }}>{error}</p>
          <button className="btn btn--secondary" onClick={startCamera}>Retry Connection</button>
        </div>
      )}
    </div>
  );
}

