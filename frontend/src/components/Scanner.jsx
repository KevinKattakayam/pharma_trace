import React, { useState, useCallback, useEffect, useRef } from 'react';
import { useScanner } from '../hooks/useScanner';
import Tesseract from 'tesseract.js';
import { checkOfflineCache, requestPersistentStorage, saveOfflineScan } from '../utils/cache';
import { preprocessForOCR } from '../utils/imageProcess';

export default function Scanner({ onBarcodeScan, onImageCapture, onManualEntry, onCachedResult, requireExpiry = false }) {
  const { videoRef, isScanning, error, startCamera, stopCamera, captureFrame } = useScanner();
  const [manualInput, setManualInput] = useState('');
  const [mode, setMode] = useState('manual'); // Start in manual — safest default
  const [isProcessingAI, setIsProcessingAI] = useState(false);
  const [persistenceFailed, setPersistenceFailed] = useState(false);
  const [isAwaitingExpiry, setIsAwaitingExpiry] = useState(false);
  const cameraRequested = useRef(false);

  // Camera startup — only when user explicitly requests a camera mode
  const switchToCamera = useCallback((targetMode) => {
    setMode(targetMode);
    cameraRequested.current = true;
    startCamera();
  }, [startCamera]);

  // If camera fails after user requested it, auto-fallback to manual
  useEffect(() => {
    if (error && cameraRequested.current) {
      cameraRequested.current = false;
      // Don't auto-switch — let the error screen show with a manual entry button
    }
  }, [error]);

  const formatCachedResult = async (cached) => {
    let warningSeverity = 'info';
    let ageStr = 'recently';
    if (cached.cached_at) {
       const hours = (Date.now() - cached.cached_at) / (1000 * 60 * 60);
       if (hours > 48) warningSeverity = 'warning';
       const days = Math.floor(hours / 24);
       ageStr = days > 0 ? `${days} days ago` : `${Math.floor(hours)} hours ago`;
    }
    
    let verdictStr = 'safe';
    let confidenceVal = 100;
    let labelText = `Matched ${cached.name} directly from local offline database. Cached ${ageStr} — reconnect to verify.`;
    
    if (cached.identification_uncertain) {
       verdictStr = 'suspicious';
       confidenceVal = 0;
       warningSeverity = 'warning';
       labelText = `CRITICAL: Fuzzy match on drug name (${cached.name}) but dosage/strength cannot be confirmed exactly. Do not administer.`;
    } else if (cached.fuzzy_matched) {
       verdictStr = 'suspicious';
       confidenceVal = Math.round(cached.similarity * 100);
       labelText = `Closest match found: ${cached.name} (${confidenceVal}% similar). Cached ${ageStr} — reconnect to verify.`;
    }

    const payload = {
      verification_id: `offline-${Date.now()}`,
      source: 'offline_cache',
      verdict: verdictStr,
      confidence: confidenceVal,
      brand_name: cached.name,
      generic_name: cached.generic_name,
      product_type: 'Offline Cache',
      identification_source: cached.identification_uncertain ? 'Uncertain Identification' : (cached.fuzzy_matched ? 'Fuzzy Match Offline' : 'Exact Match Offline'),
      evidence: [{ check: 'offline_cache', status: warningSeverity === 'warning' ? 'warn' : 'pass', description: labelText }],
      side_effects: [
         { severity: 'mild', description: cached.uses },
         { severity: 'moderate', description: cached.warnings },
         { severity: 'severe', description: cached.interactions }
      ],
      cached_at: cached.cached_at,
      warning_severity: warningSeverity
    };

    // Save offline scan for background sync audit trail
    try {
      await saveOfflineScan({
        verification_id: payload.verification_id,
        drug_name: cached.name,
        confidence: confidenceVal,
        fuzzy_matched: cached.fuzzy_matched
      });
    } catch (err) {
      console.warn("Failed to write to scan_history outbox", err);
    }

    return payload;
  };

  // Barcode decode loop
  useEffect(() => {
    let codeReader;
    let isDecoding = true;

    if (mode === 'barcode' && isScanning && videoRef.current && !isAwaitingExpiry) {
      import('@zxing/library').then(({ BrowserMultiFormatReader }) => {
        codeReader = new BrowserMultiFormatReader();
        const decodeLoop = async () => {
          if (!isDecoding || isAwaitingExpiry) return;
          try {
            const result = await codeReader.decodeOnceFromVideoElement(videoRef.current);
            if (result && result.text) {
              const barcode = result.text.trim();
              
              const finishScan = async (frameToPass) => {
                const cached = await checkOfflineCache(barcode);
                if (cached && onCachedResult) {
                  const formatted = await formatCachedResult(cached);
                  onCachedResult(formatted);
                } else if (onBarcodeScan) {
                  onBarcodeScan(barcode, frameToPass);
                } else if (onManualEntry) {
                  onManualEntry(barcode, frameToPass);
                }
                isDecoding = false;
                stopCamera();
              };

              if (requireExpiry) {
                 setIsAwaitingExpiry(true);
                 setTimeout(() => {
                    const frame = captureFrame();
                    setIsAwaitingExpiry(false);
                    finishScan(frame);
                 }, 1500);
                 return;
              } else {
                 const frame = captureFrame();
                 finishScan(frame);
              }
            }
          } catch (e) {
            // No barcode found in current frame, loop
            if (isDecoding && !isAwaitingExpiry) setTimeout(decodeLoop, 100);
          }
        };
        decodeLoop();
      });
    }

    return () => {
      isDecoding = false;
      if (codeReader) codeReader.reset();
    };
  }, [mode, isScanning, onManualEntry, onCachedResult, stopCamera, videoRef, requireExpiry, isAwaitingExpiry]);

  const handleCapture = useCallback(async () => {
    const frame = captureFrame();
    if (frame && onImageCapture) { 
      stopCamera(); 
      setIsProcessingAI(true);
      
      let extractedText = '';
      try {
        const processedFrame = await preprocessForOCR(frame);
        const { data: { text, confidence } } = await Tesseract.recognize(processedFrame, 'eng');
        if (confidence >= 70) {
          extractedText = text.trim();
          
          const cached = await checkOfflineCache(extractedText);
          if (cached && onCachedResult) {
            setIsProcessingAI(false);
            const formatted = await formatCachedResult(cached);
            onCachedResult(formatted);
            return;
          }
        }
      } catch (err) {
        console.error("Tesseract extraction failed:", err);
      } finally {
        setIsProcessingAI(false);
      }
      
      onImageCapture({ 
        image: frame.replace(/^data:image\/[a-z]+;base64,/, ''), 
        extracted_text: extractedText || undefined 
      }); 
    }
  }, [captureFrame, onImageCapture, stopCamera, onCachedResult]);

  const handleManualSubmit = useCallback(async (e) => {
    e.preventDefault();
    const persisted = await requestPersistentStorage();
    if (!persisted && !persistenceFailed) setPersistenceFailed(true);
    
    const query = manualInput.trim();
    if (query) { 
      const cached = await checkOfflineCache(query);
      if (cached && onCachedResult) {
        const formatted = await formatCachedResult(cached);
        onCachedResult(formatted);
      } else if (onManualEntry) {
        onManualEntry(query); 
      }
      setManualInput(''); 
    }
  }, [manualInput, onManualEntry, onCachedResult, persistenceFailed]);

  return (
    <div className="anim">
      {persistenceFailed && (
        <div style={{ background: 'var(--warn-bg)', color: 'var(--warn)', padding: '0.75rem', borderRadius: '8px', marginBottom: '1.5rem', border: '1px solid var(--warn)', fontSize: '0.8125rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
           <span>Your browser may clear offline data under storage pressure. Install the app for guaranteed offline access.</span>
           <button onClick={() => setPersistenceFailed(false)} style={{ background: 'transparent', border: 'none', color: 'var(--warn)', cursor: 'pointer', fontWeight: 'bold' }}>x</button>
        </div>
      )}

      {/* Camera Viewport — only when camera mode is active */}
      {mode !== 'manual' && (
        <div className="scanner-fullscreen">
          <video ref={videoRef} className="scanner-fullscreen__video" autoPlay playsInline muted />
          
          {error ? (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '2rem', textAlign: 'center', zIndex: 201, background: 'rgba(0,0,0,0.9)' }}>
              <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'rgba(239, 68, 68, 0.15)', color: '#ef4444', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '28px', fontWeight: 800, marginBottom: '1.25rem' }}>!</div>
              <p style={{ color: '#fff', fontSize: '16px', fontWeight: 600, marginBottom: '0.5rem' }}>Camera Unavailable</p>
              <p style={{ color: 'rgba(255,255,255,0.6)', fontSize: '13px', marginBottom: '2rem', maxWidth: 300 }}>{error}</p>
              <button className="btn btn--primary" onClick={() => { setMode('manual'); stopCamera(); }} style={{ width: '100%', maxWidth: 280 }}>
                Use Manual Entry Instead
              </button>
            </div>
          ) : (
            <>
              <div className="scanner-fullscreen__overlay">
                <div className="scanner-fullscreen__crop" />
              </div>

              <div style={{
                position: 'absolute', top: '4rem', left: '0', right: '0', textAlign: 'center',
                color: '#fff', fontSize: '15px', fontWeight: 600, zIndex: 201
              }}>
                {isScanning ? (
                  mode === 'barcode' ? 'Align barcode within the frame' : 'Hold steady — tap circle to capture'
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}>
                    <span className="spinner" style={{ width: 14, height: 14, borderColor: 'rgba(255,255,255,0.3)', borderTopColor: '#fff' }} />
                    Starting camera...
                  </span>
                )}
              </div>
              
              {/* Photo capture button */}
              {isScanning && mode === 'photo' && (
                <div style={{ position: 'absolute', bottom: '4rem', left: '0', right: '0', display: 'flex', justifyContent: 'center', zIndex: 201 }}>
                  <button 
                    onClick={handleCapture}
                    aria-label="Capture photo"
                    style={{
                      width: '72px', height: '72px', borderRadius: '50%', background: '#fff',
                      border: '4px solid rgba(255,255,255,0.4)', backgroundClip: 'padding-box',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.3)'
                    }}
                  />
                </div>
              )}

              {/* Mode switcher at bottom — barcode vs photo */}
              {isScanning && (
                <div style={{ position: 'absolute', bottom: mode === 'photo' ? '8rem' : '4rem', left: '0', right: '0', display: 'flex', justifyContent: 'center', gap: '0.75rem', zIndex: 201 }}>
                  <button 
                    onClick={() => setMode('barcode')}
                    style={{
                      padding: '0.5rem 1rem', borderRadius: '20px', fontSize: '13px', fontWeight: 600,
                      background: mode === 'barcode' ? 'var(--primary)' : 'rgba(255,255,255,0.15)',
                      color: '#fff', border: 'none', cursor: 'pointer'
                    }}
                  >
                    Barcode
                  </button>
                  <button 
                    onClick={() => setMode('photo')}
                    style={{
                      padding: '0.5rem 1rem', borderRadius: '20px', fontSize: '13px', fontWeight: 600,
                      background: mode === 'photo' ? 'var(--primary)' : 'rgba(255,255,255,0.15)',
                      color: '#fff', border: 'none', cursor: 'pointer'
                    }}
                  >
                    AI Photo
                  </button>
                </div>
              )}
            </>
          )}

          {/* Close button — always visible */}
          <button className="scanner-fullscreen__close" onClick={() => { setMode('manual'); stopCamera(); }}>
            <svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" strokeWidth="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
          
          {isAwaitingExpiry && !error && (
             <div className="anim" style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#fff', zIndex: 202, padding: '2rem', textAlign: 'center' }}>
                <svg viewBox="0 0 24 24" width="48" height="48" stroke="var(--primary)" strokeWidth="2" fill="none" style={{marginBottom: '1rem'}}><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>
                <h3 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '0.5rem', color: 'var(--text-inv)' }}>Barcode Captured!</h3>
                <p style={{ fontSize: '15px', color: 'var(--text-muted)' }}>Now show the expiry date...</p>
             </div>
          )}
        </div>
      )}

      {/* Manual Entry — universal search */}
      {mode === 'manual' && (
        <div className="card anim" style={{ maxWidth: 440, margin: '0 auto', padding: '2rem' }}>
          <form onSubmit={handleManualSubmit}>
            <div className="form-group" style={{ marginBottom: '1.5rem' }}>
              <label className="label-text" htmlFor="manual-input" style={{ display: 'block', marginBottom: '0.5rem' }}>
                Search Medicine
              </label>
              <input 
                id="manual-input" 
                type="text" 
                value={manualInput} 
                onChange={(e) => setManualInput(e.target.value)}
                placeholder="Drug name, barcode, batch number, or NDC" 
                style={{ fontSize: '16px', fontWeight: 500, width: '100%' }}
                autoComplete="off" 
                autoFocus 
              />
              <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
                Accepts any identifier: brand name (Crocin, Dolo), generic name (Paracetamol), barcode, batch number, or US NDC code.
              </p>
            </div>
            <button 
              type="submit" 
              className="btn btn--primary" 
              disabled={!manualInput.trim()} 
              id="btn-manual-verify"
              style={{ marginBottom: '1rem', width: '100%' }}
            >
              Verify Medicine
            </button>
          </form>

          <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem' }}>
            <button 
              type="button" 
              className="btn btn--secondary" 
              onClick={() => switchToCamera('barcode')} 
              style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>
              Scan Barcode
            </button>
            <button 
              type="button" 
              className="btn btn--secondary" 
              onClick={() => switchToCamera('photo')} 
              style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.5rem' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg>
              AI Photo
            </button>
          </div>

          <div style={{ padding: '0.75rem 1rem', background: 'var(--bg-secondary)', borderRadius: '10px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <strong style={{ color: 'var(--text-main)' }}>Demo:</strong> Try entering <span style={{ fontFamily: 'monospace', color: 'var(--primary)', fontWeight: 600 }}>Paracetamol</span>, <span style={{ fontFamily: 'monospace', color: 'var(--primary)', fontWeight: 600 }}>Amoxicillin</span>, or NDC <span style={{ fontFamily: 'monospace', color: 'var(--primary)', fontWeight: 600 }}>59726-065-30</span>
          </div>
        </div>
      )}

      {/* Processing overlay */}
      {isProcessingAI && (
        <div className="card anim" style={{ maxWidth: 420, margin: '1rem auto 0', textAlign: 'center', padding: '2rem' }}>
          <div className="spinner" style={{ margin: '0 auto 1rem', width: 28, height: 28 }} />
          <p style={{ fontSize: '14px', fontWeight: 600, color: 'var(--text-main)' }}>Running OCR extraction...</p>
        </div>
      )}
    </div>
  );
}
