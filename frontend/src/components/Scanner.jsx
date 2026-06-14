import React, { useState, useCallback } from 'react';
import { useScanner } from '../hooks/useScanner';
import Tesseract from 'tesseract.js';
import { checkOfflineCache, requestPersistentStorage, saveOfflineScan } from '../utils/cache';
import { preprocessForOCR } from '../utils/imageProcess';

export default function Scanner({ onBarcodeScan, onImageCapture, onManualEntry, onCachedResult }) {
  const { videoRef, isScanning, error, startCamera, stopCamera, captureFrame } = useScanner();
  const [manualBarcode, setManualBarcode] = useState('');
  const [mode, setMode] = useState('manual');
  const [isProcessingAI, setIsProcessingAI] = useState(false);
  const [persistenceFailed, setPersistenceFailed] = useState(false);

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

  const [isAwaitingExpiry, setIsAwaitingExpiry] = useState(false);

  React.useEffect(() => {
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
                 }, 1500); // Wait 1.5s for user to reposition the box to show the expiry date
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
        // Step 1: Preprocess the frame and run Tesseract.js
        const processedFrame = await preprocessForOCR(frame);
        const { data: { text, confidence } } = await Tesseract.recognize(processedFrame, 'eng');
        if (confidence >= 70) {
          extractedText = text.trim();
          
          // Step 1.5: Offline PWA cache check
          const cached = await checkOfflineCache(extractedText);
          if (cached && onCachedResult) {
            setIsProcessingAI(false);
            const formatted = await formatCachedResult(cached);
            onCachedResult(formatted);
            return;
          }
        } else {
          console.log(`Tesseract confidence too low (${confidence}%), skipping OCR text.`);
        }
      } catch (err) {
        console.error("Tesseract extraction failed:", err);
      } finally {
        setIsProcessingAI(false);
      }
      
      // Pass both the image (without base64 prefix) and extracted text to the backend
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
    
    const query = manualBarcode.trim();
    if (query) { 
      const cached = await checkOfflineCache(query);
      if (cached && onCachedResult) {
        const formatted = await formatCachedResult(cached);
        onCachedResult(formatted);
      } else if (onManualEntry) {
        onManualEntry(query); 
      }
      setManualBarcode(''); 
    }
  }, [manualBarcode, onManualEntry, onCachedResult, persistenceFailed]);

  const modes = [
    { key: 'barcode', label: 'Scan Barcode', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg> },
    { key: 'photo', label: 'AI Photo ID', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/><circle cx="12" cy="13" r="4"/></svg> },
    { key: 'manual', label: 'Type NDC', icon: <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><polyline points="4 7 4 4 20 4 20 7"/><line x1="9" y1="20" x2="15" y2="20"/><line x1="12" y1="4" x2="12" y2="20"/></svg> }
  ];

  return (
    <div className="anim">
      {persistenceFailed && (
        <div style={{ background: 'var(--warn-bg)', color: 'var(--warn)', padding: '0.75rem', borderRadius: '8px', marginBottom: '1.5rem', border: '1px solid var(--warn)', fontSize: '0.8125rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
           <span>Your browser may clear offline data under storage pressure. Install the app for guaranteed offline access.</span>
           <button onClick={() => setPersistenceFailed(false)} style={{ background: 'transparent', border: 'none', color: 'var(--warn)', cursor: 'pointer', fontWeight: 'bold' }}>×</button>
        </div>
      )}
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
              boxShadow: mode === m.key ? 'var(--shadow-md)' : 'none'
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
              {isAwaitingExpiry && (
                <div className="anim" style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#fff', zIndex: 20, padding: '2rem', textAlign: 'center' }}>
                   <div style={{ fontSize: '3.5rem', marginBottom: '1rem', animation: 'bounce 1s infinite' }}>📅</div>
                   <h3 style={{ fontSize: '1.5rem', fontWeight: 900, marginBottom: '0.5rem', color: 'var(--safe)' }}>Barcode Captured!</h3>
                   <p style={{ fontSize: '1rem', fontWeight: 600, color: 'var(--text-inv)' }}>Now show the expiry date...</p>
                </div>
              )}
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
                {mode === 'barcode' ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-3)', fontSize: '0.875rem' }}>
                    Scanning for barcodes...
                  </div>
                ) : (
                  <button className="btn btn--primary btn--lg"
                    onClick={handleCapture}
                    id="btn-capture-photo">
                    Identify Package
                  </button>
                )}
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

