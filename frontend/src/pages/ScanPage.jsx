import React, { useState, useCallback } from 'react';
import Scanner from '../components/Scanner';
import DrugResult from '../components/DrugResult';
import api from '../utils/api';

export default function ScanPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  const handleBarcodeScan = useCallback(async (imageData) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyImage(imageData);
      setResult(res);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const handleImageCapture = useCallback(async (imageData) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyImage(imageData);
      setResult(res);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const handleManualEntry = useCallback(async (barcode) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyBarcode(barcode);
      setResult(res);
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  return (
    <div className="page">
      <div className="container">
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '0.75rem' }}>
            <span className="hero__tag-dot" /> Verification Engine
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '0.5rem' }}>
            Verify Medicine
          </h1>
          <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem' }}>
            Scan a barcode, photograph the packaging, or enter the NDC code
          </p>
        </div>


        {!result && !loading && (
          <div className="anim anim-d1">
            <Scanner
              onBarcodeScan={handleBarcodeScan}
              onImageCapture={handleImageCapture}
              onManualEntry={handleManualEntry}
            />
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', padding: '4rem 0' }} className="anim">
            <div className="spinner" style={{ margin: '0 auto 1rem', width: 32, height: 32 }} />
            <p style={{ color: 'var(--text-2)', fontSize: '0.875rem', fontWeight: 500 }}>
              Querying FDA databases…
            </p>
            <p style={{ color: 'var(--text-3)', fontSize: '0.75rem', marginTop: '0.35rem' }}>
              Checking NDC registry • Recall database • Cold chain
            </p>
          </div>
        )}

        {error && (
          <div className="card card--danger anim" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
            <div style={{ fontSize: '1.5rem', marginBottom: '0.75rem' }}>⚠</div>
            <p style={{ color: 'var(--danger)', marginBottom: '1rem', fontWeight: 500 }}>{error}</p>
            <button className="btn btn--secondary" onClick={() => { setError(null); setResult(null); }}>
              Try Again
            </button>
          </div>
        )}

        {result && (
          <div className="anim">
            <DrugResult data={result} />
            <div style={{ textAlign: 'center', marginTop: '1.5rem' }}>
              <button className="btn btn--secondary btn--lg" onClick={() => { setResult(null); setError(null); }} id="btn-scan-another">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>
                Scan Another Medicine
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
