import React, { useState, useCallback, useRef, useEffect } from 'react';
import api from '../utils/api';
import Scanner from '../components/Scanner';
import Tesseract from 'tesseract.js';
import { preprocessForOCR } from '../utils/imageProcess';
import { extractExpiryDate } from '../utils/expiry';

export default function BatchVerification() {
  const [items, setItems] = useState([]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const [toast, setToast] = useState(null);
  const inputRef = useRef(null);
  const inFlightRef = useRef(0);

  const processQueue = useCallback(async () => {
    if (inFlightRef.current >= 3) return;
    
    setItems(currentItems => {
        const pendingItem = currentItems.find(i => i.status === 'pending');
        if (!pendingItem) return currentItems;
        
        inFlightRef.current += 1;
        const newItems = currentItems.map(i => i.id === pendingItem.id ? { ...i, status: 'verifying', name: 'Verifying with FDA...' } : i);
        
        api.verifyBarcode(pendingItem.barcode).then(result => {
             setItems(prev => prev.map(item =>
                item.id === pendingItem.id
                  ? {
                      ...item,
                      name: result.brand_name || result.generic_name || pendingItem.barcode,
                      status: result.has_recall ? 'recalled' : (
                          pendingItem.expiry_info?.status === 'expired' ? 'failed' :
                          pendingItem.expiry_info?.status === 'expiring_soon' ? 'expiry_warning' :
                          result.verdict === 'authentic' ? 'pass' : 'fail'
                      ),
                      confidence: result.confidence || 0,
                      result
                    }
                  : item
              ));
        }).catch(err => {
             setItems(prev => prev.map(item =>
                item.id === pendingItem.id
                  ? { ...item, name: `Error: ${err.message}`, status: 'failed', confidence: 0 }
                  : item
              ));
        }).finally(() => {
             inFlightRef.current -= 1;
             processQueue();
        });
        
        return newItems;
    });
  }, []);

  useEffect(() => {
     processQueue();
  }, [items, processQueue]);

  const addItem = useCallback(async (barcodeStr) => {
    const barcode = barcodeStr.trim();
    if (!barcode) return;
    
    setItems(prev => {
        const existing = prev.find(i => i.barcode === barcode);
        if (existing) {
            setToast('Already scanned');
            setTimeout(() => setToast(null), 2000);
            return prev.map(i => i.barcode === barcode ? { ...i, highlight: true } : { ...i, highlight: false });
        }
        return [{ 
           id: Date.now(), 
           barcode: barcode, 
           name: 'Queued', 
           status: 'pending', 
           confidence: 0,
           expiry_info: null 
        }, ...prev.map(i => ({...i, highlight: false}))];
    });
    setBarcodeInput('');
    inputRef.current?.focus();
  }, []);

  const handleBarcodeScan = useCallback(async (barcode, frame) => {
     addItem(barcode);
     if (frame) {
         try {
             const processedFrame = await preprocessForOCR(frame);
             const { data: { text, confidence } } = await Tesseract.recognize(processedFrame, 'eng');
             if (confidence >= 70) {
                 const expiry = extractExpiryDate(text.trim());
                 if (expiry.status !== 'unknown') {
                     setItems(prev => prev.map(i => 
                         i.barcode === barcode 
                           ? { ...i, expiry_info: expiry } 
                           : i
                     ));
                 }
             }
         } catch (err) {
             console.error("Batch OCR Error:", err);
         }
     }
  }, [addItem]);

  const retryItem = (id) => {
      setItems(prev => prev.map(i => i.id === id ? { ...i, status: 'pending', name: 'Queued' } : i));
  }

  const exportPDF = async () => {
    try {
      const payload = items.map(i => ({ barcode: i.barcode, status: i.status, confidence: i.confidence }));
      const res = await fetch('/api/v1/verify/batch-audit', {
         method: 'POST',
         headers: { 'Content-Type': 'application/json' },
         body: JSON.stringify({ items: payload })
      });
      const data = await res.json();
      const audit_hash = data.audit_hash || 'HASH_UNAVAILABLE';
    
      const { default: jsPDF } = await import('jspdf');
      const doc = new jsPDF();
      doc.setFontSize(16); doc.text('PharmaTrace — Batch Verification Report', 20, 20);
      doc.setFontSize(9);
      doc.text(`Generated: ${new Date().toLocaleString()}  |  Total: ${items.length}  |  Pass rate: ${passRate}%`, 20, 30);
      let y = 42;
      doc.setFontSize(8); doc.text('BARCODE', 20, y); doc.text('DRUG', 65, y); doc.text('STATUS', 145, y); doc.text('CONFIDENCE', 170, y); y += 6;
      items.forEach(item => {
        if (y > 270) { doc.addPage(); y = 20; }
        doc.text(item.barcode.slice(0, 20), 20, y); doc.text(item.name.slice(0, 35), 65, y);
        doc.text(item.status.toUpperCase(), 145, y); doc.text(`${item.confidence}%`, 170, y); y += 5;
      });
      
      const expiringItems = items.filter(i => i.expiry_info && i.expiry_info.status === 'expiring_soon');
      if (expiringItems.length > 0) {
          doc.addPage();
          y = 20;
          doc.setFontSize(14); doc.text('Expiring Within 90 Days', 20, y); y += 10;
          doc.setFontSize(8); doc.text('BARCODE', 20, y); doc.text('DRUG', 65, y); doc.text('EXPIRY DATE', 145, y); y += 6;
          expiringItems.forEach(item => {
              if (y > 270) { doc.addPage(); y = 20; }
              doc.text(item.barcode.slice(0, 20), 20, y); doc.text(item.name.slice(0, 35), 65, y);
              doc.text(item.expiry_info.expiry_date, 145, y); y += 5;
          });
      }
      
      doc.setFontSize(7);
      doc.setTextColor(100);
      doc.text(`Cryptographic Audit Hash: ${audit_hash}`, 20, 290);
      doc.save('pharmatrace-batch-report.pdf');
    } catch (err) { console.error('PDF export error:', err); }
  };

  const passCount = items.filter(i => i.status === 'pass').length;
  const failCount = items.filter(i => i.status === 'fail' || i.status === 'failed').length;
  const recallCount = items.filter(i => i.status === 'recalled').length;
  const totalProcessed = items.filter(i => i.status !== 'pending' && i.status !== 'verifying').length;
  const passRate = totalProcessed > 0 ? Math.round(passCount / totalProcessed * 100) : 0;
  
  const passRateColor = passRate >= 98 ? 'var(--safe)' : passRate >= 90 ? 'var(--warn)' : 'var(--danger)';

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 800 }}>
        {toast && <div style={{ position: 'fixed', top: 20, right: 20, background: 'var(--warn-bg)', color: 'var(--warn)', padding: '0.75rem 1.5rem', borderRadius: '8px', zIndex: 1000, border: '1px solid var(--warn)', fontWeight: 'bold' }}>{toast}</div>}
        
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }} className="anim">
          <div>
            <div className="hero__tag" style={{ marginBottom: '0.6rem' }}>
              <span className="hero__tag-dot" /> Health Worker Tools
            </div>
            <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em' }}>Batch Verification</h1>
            <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', marginTop: '0.35rem' }}>Rapid-scan mode — verify multiple drugs against live FDA databases</p>
          </div>
          {items.length > 0 && (
            <button className="btn btn--secondary" onClick={exportPDF} id="btn-export-pdf">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
              Export PDF
            </button>
          )}
        </div>

        <div className="card anim anim-d1" style={{ marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'flex-end', marginBottom: '1rem' }}>
            <div style={{ flex: 1 }}>
              <label className="form-label" htmlFor="batch-barcode">Scan or Enter Barcode</label>
              <input ref={inputRef} id="batch-barcode" type="text" value={barcodeInput}
                onChange={(e) => setBarcodeInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addItem(barcodeInput)}
                placeholder="Scan barcode or type NDC — press Enter" autoComplete="off" autoFocus />
            </div>
            <button className="btn btn--primary" onClick={() => addItem(barcodeInput)} disabled={!barcodeInput.trim()}>+ Add</button>
          </div>
          
          <div style={{ marginTop: '1rem', borderTop: '1px solid var(--border-1)', paddingTop: '1rem' }}>
             <Scanner onBarcodeScan={handleBarcodeScan} onManualEntry={handleBarcodeScan} requireExpiry={true} />
          </div>
        </div>

        {items.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(6, 1fr)', gap: '0.65rem', marginBottom: '1.25rem' }}>
            {[
              { val: items.length, label: 'Total Scans', color: 'var(--text-1)' },
              { val: passCount, label: 'Passed', color: 'var(--safe)' },
              { val: failCount, label: 'Failed', color: 'var(--danger)' },
              { val: items.filter(i => i.status === 'expiry_warning').length, label: 'Expiring Soon', color: 'var(--warn)' },
              { val: recallCount, label: 'Recalls', color: 'var(--danger)' },
              { val: `${passRate}%`, label: 'Pass Rate', color: passRateColor },
            ].map((s, i) => (
              <div key={i} className="card" style={{ textAlign: 'center', padding: '0.85rem' }}>
                <div style={{ fontFamily: 'var(--mono)', fontSize: '1.25rem', fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: '0.5625rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {items.length > 0 && (
          <div className="card anim">
            <div className="drug-result__section-title">Verification Results</div>
            <div className="batch-list">
              {items.map(item => (
                <div key={item.id} className="batch-item" style={item.highlight ? { background: 'var(--warn-bg)', transition: 'background 0.3s' } : {}}>
                  <span className={`batch-item__status batch-item__status--${item.status === 'failed' || item.status === 'recalled' ? 'fail' : item.status === 'verifying' ? 'warn' : item.status === 'expiry_warning' ? 'warn' : item.status}`} />
                  <span style={{ fontFamily: 'var(--mono)', fontSize: '0.6875rem', color: 'var(--text-3)', width: 90, flexShrink: 0 }}>{item.barcode}</span>
                  <span className="batch-item__name">{item.name}</span>
                  <span className="batch-item__confidence" style={{
                    color: item.status === 'failed' ? 'var(--danger)' : item.status === 'recalled' ? 'var(--danger)' : item.confidence >= 80 ? 'var(--safe)' : item.confidence >= 50 ? 'var(--warn)' : 'var(--danger)'
                  }}>
                     {item.status === 'pending' ? '…' : item.status === 'verifying' ? '...' : `${item.confidence}%`}
                  </span>
                  {item.status === 'failed' && (
                     <button onClick={() => retryItem(item.id)} style={{ marginLeft: '10px', background: 'var(--bg-tertiary)', border: 'none', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.75rem' }}>Retry</button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '4rem 0', color: 'var(--text-3)' }}>
            <p style={{ fontSize: '0.875rem' }}>No items scanned yet. Enter barcodes above to verify against FDA databases.</p>
          </div>
        )}
      </div>
    </div>
  );
}
