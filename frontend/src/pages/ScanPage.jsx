import React, { useState, useCallback, useEffect } from 'react';
import Scanner from '../components/Scanner';
import DrugResult from '../components/DrugResult';
import api from '../utils/api';
import { getSyncQueue, updateSyncQueueRetry } from '../utils/sync-queue';

export default function ScanPage() {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [failedSyncs, setFailedSyncs] = useState([]);

  useEffect(() => {
    const checkSyncQueue = async () => {
       try {
         const queue = await getSyncQueue();
         // Find items older than 7 days or max retries
         const now = Date.now();
         const failed = queue.filter(item => 
            item.retry_count >= 5 || (now - item.created_at > 7 * 24 * 60 * 60 * 1000)
         );
         setFailedSyncs(failed);
       } catch (err) {}
    };
    checkSyncQueue();
    
    const bc = new BroadcastChannel('sync-updates');
    bc.onmessage = (event) => {
       if (event.data && event.data.type === 'OUTBOX_UPDATE') {
           checkSyncQueue();
       }
    };
    
    return () => bc.close();
  }, []);

  const handleRetrySync = async (id) => {
     await updateSyncQueueRetry(id, 0);
     if ('serviceWorker' in navigator && 'sync' in ServiceWorkerRegistration.prototype) {
        navigator.serviceWorker.ready.then(reg => reg.sync.register('process-outbox'));
     }
     setFailedSyncs(prev => prev.filter(item => item.id !== id));
  };

  const performCrossCheck = async (res) => {
    if (!res) return res;
    try {
      const drugName = res.brand_name || res.generic_name || 'this medicine';
      const userId = localStorage.getItem('user_id') || 'anonymous';
      const members = await api.getFamilyMembers(userId);
      const safetyChecks = await Promise.all(members.map(m => api.checkMedicineSafety(drugName, m.id)));
      const warnings = safetyChecks.filter(c => !c.is_safe).map(c => c.warning);
      return { ...res, family_warnings: warnings };
    } catch (err) {
      console.error("Family safety check failed:", err);
      return res;
    }
  };

  const handleBarcodeScan = useCallback(async (imageData) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyImage(imageData);
      setResult(await performCrossCheck(res));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const handleImageCapture = useCallback(async (imageData) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyImage(imageData);
      setResult(await performCrossCheck(res));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const handleManualEntry = useCallback(async (barcode) => {
    setLoading(true); setError(null);
    try {
      const res = await api.verifyBarcode(barcode);
      setResult(await performCrossCheck(res));
    } catch (err) { setError(err.message); }
    finally { setLoading(false); }
  }, []);

  const handleCachedResult = async (res) => {
    setResult(await performCrossCheck(res));
  };

  const handleRecheckLive = async () => {
    if (!result) return;
    setLoading(true); setError(null);
    try {
      const liveResRaw = await api.verifyBarcode(result.brand_name || result.generic_name);
      const liveRes = await performCrossCheck(liveResRaw);
      
      let conflictText = null;
      if (liveRes.verdict !== result.verdict) {
          conflictText = `Local cache indicated ${result.verdict.toUpperCase()}, but live FDA check returned ${liveRes.verdict.toUpperCase()}. Do not use.`;
      } else if (Math.abs(liveRes.confidence - result.confidence) > 5) {
          conflictText = `Live confidence score is ${liveRes.confidence}% vs cached ${result.confidence}%. Updated information available.`;
      } else if (liveRes.has_recall !== result.has_recall) {
          conflictText = `New recall status detected in live database. Please review updated evidence.`;
      } else if ((liveRes.evidence?.length || 0) !== (result.evidence?.length || 0)) {
          conflictText = `New safety flags or clinical evidence detected in live database.`;
      }
      
      if (conflictText) {
         setResult({
            ...liveRes,
            conflict_warning: {
               cached_verdict: result.verdict.toUpperCase(),
               live_verdict: liveRes.verdict.toUpperCase(),
               message: conflictText,
               is_severe: liveRes.verdict !== result.verdict
            }
         });
      } else {
         setResult(liveRes);
      }
    } catch (err) {
      setError("Live re-check failed: " + err.message);
    } finally {
      setLoading(false);
    }
  };

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
          <p style={{ color: 'var(--text-2)', fontSize: '0.9375rem', maxWidth: 480, margin: '0 auto' }}>
            Scan a barcode, photograph the packaging, or search by drug name, batch number, or barcode.
          </p>
        </div>

        {!result && !loading && (
          <div className="anim anim-d1">
            {failedSyncs.length > 0 && (
              <div style={{ maxWidth: 400, margin: '0 auto 1.5rem' }}>
                {failedSyncs.map(fs => (
                  <div key={fs.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'var(--danger-bg)', color: 'var(--danger)', padding: '0.75rem 1rem', borderRadius: '8px', border: '1px solid rgba(239,68,68,.3)', marginBottom: '0.5rem', fontSize: '0.8125rem', fontWeight: 600 }}>
                     <span>Failed to sync offline record</span>
                     <button onClick={() => handleRetrySync(fs.id)} style={{ background: 'var(--danger)', color: 'white', border: 'none', padding: '0.25rem 0.5rem', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 700, cursor: 'pointer' }}>Tap to retry</button>
                  </div>
                ))}
              </div>
            )}
            <Scanner
              onBarcodeScan={handleBarcodeScan}
              onImageCapture={handleImageCapture}
              onManualEntry={handleManualEntry}
              onCachedResult={handleCachedResult}
            />
          </div>
        )}

        {loading && (
          <div className="card anim" style={{ textAlign: 'center', padding: '4rem 2rem', maxWidth: 480, margin: '0 auto' }}>
            <div className="spinner" style={{ margin: '0 auto 1.25rem', width: 36, height: 36 }} />
            <h3 style={{ fontWeight: 800, fontSize: '1.1rem', marginBottom: '.5rem' }}>Verifying medicine...</h3>
            <div style={{ display: 'flex', gap: '.5rem', justifyContent: 'center', flexWrap: 'wrap' }}>
              {['Drug registry', 'Recall database', 'Safety check'].map(s => (
                <span key={s} style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.08em', color: 'var(--text-3)', padding: '.3rem .65rem', background: 'var(--bg-tertiary)', borderRadius: 8, border: '1px solid var(--border-1)' }}>{s}</span>
              ))}
            </div>
          </div>
        )}

        {error && (
          <div className="card card--danger anim" style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
            <div style={{ width: 40, height: 40, borderRadius: '50%', background: 'var(--danger-bg)', border: '1px solid rgba(239,68,68,.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1rem', color: 'var(--danger)', fontSize: '1.25rem', fontWeight: 800 }}>!</div>
            <p style={{ color: 'var(--danger)', marginBottom: '1rem', fontWeight: 600, fontSize: '.9375rem' }}>{error}</p>
            <button className="btn btn--secondary" onClick={() => { setError(null); setResult(null); }}>Try Again</button>
          </div>
        )}

        {result && !loading && !error && (
          <div className="anim">
            <DrugResult data={result} onRecheck={handleRecheckLive} />
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
