import React, { useState, useCallback, useRef } from 'react';
import api from '../utils/api';

export default function BatchVerification() {
  const [items, setItems] = useState([]);
  const [barcodeInput, setBarcodeInput] = useState('');
  const inputRef = useRef(null);

  const addItem = useCallback(async (barcode) => {
    if (!barcode.trim()) return;
    const newItem = { id: Date.now(), barcode: barcode.trim(), name: 'Verifying…', status: 'pending', confidence: 0 };
    setItems(prev => [newItem, ...prev]);
    setBarcodeInput('');
    inputRef.current?.focus();

    try {
      const result = await api.verifyBarcode(barcode.trim());
      setItems(prev => prev.map(item =>
        item.id === newItem.id
          ? {
              ...item,
              name: result.brand_name || result.generic_name || barcode,
              status: result.verdict === 'authentic' ? 'pass' : 'fail',
              confidence: result.confidence || 0,
              result
            }
          : item
      ));
    } catch (err) {
      // No fake fallback — show the real error
      setItems(prev => prev.map(item =>
        item.id === newItem.id
          ? { ...item, name: `Error: ${err.message}`, status: 'fail', confidence: 0 }
          : item
      ));
    }
  }, []);

  const exportPDF = async () => {
    try {
      const { default: jsPDF } = await import('jspdf');
      const doc = new jsPDF();
      doc.setFontSize(16); doc.text('PharmaTrace — Batch Verification Report', 20, 20);
      doc.setFontSize(9);
      doc.text(`Generated: ${new Date().toLocaleString()}  |  Total: ${items.length}  |  Pass rate: ${passRate}%`, 20, 30);
      let y = 42;
      doc.setFontSize(8); doc.text('BARCODE', 20, y); doc.text('DRUG', 65, y); doc.text('STATUS', 145, y); doc.text('CONFIDENCE', 170, y); y += 6;
      items.forEach(item => {
        if (y > 280) { doc.addPage(); y = 20; }
        doc.text(item.barcode.slice(0, 20), 20, y); doc.text(item.name.slice(0, 35), 65, y);
        doc.text(item.status === 'pass' ? 'PASS' : 'FAIL', 145, y); doc.text(`${item.confidence}%`, 170, y); y += 5;
      });
      doc.save('pharmatrace-batch-report.pdf');
    } catch (err) { console.error('PDF export error:', err); }
  };

  const passCount = items.filter(i => i.status === 'pass').length;
  const failCount = items.filter(i => i.status === 'fail').length;
  const passRate = items.length > 0 ? Math.round(passCount / items.length * 100) : 0;

  return (
    <div className="page">
      <div className="container" style={{ maxWidth: 800 }}>
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
          <div style={{ display: 'flex', gap: '0.65rem', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label className="form-label" htmlFor="batch-barcode">Scan or Enter Barcode</label>
              <input ref={inputRef} id="batch-barcode" type="text" value={barcodeInput}
                onChange={(e) => setBarcodeInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addItem(barcodeInput)}
                placeholder="Scan barcode or type NDC — press Enter" autoComplete="off" autoFocus />
            </div>
            <button className="btn btn--primary" onClick={() => addItem(barcodeInput)} disabled={!barcodeInput.trim()}>+ Add</button>
          </div>
          <p style={{ fontSize: '0.6875rem', color: 'var(--text-3)', marginTop: '0.5rem' }}>
            Each barcode is verified against live OpenFDA databases. Use a USB scanner for rapid input.
          </p>
        </div>

        {items.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.65rem', marginBottom: '1.25rem' }}>
            {[
              { val: items.length, label: 'Total', color: 'var(--text-1)' },
              { val: passCount, label: 'Passed', color: 'var(--safe)' },
              { val: failCount, label: 'Failed', color: 'var(--danger)' },
              { val: `${passRate}%`, label: 'Pass Rate', color: passRate >= 80 ? 'var(--safe)' : passRate >= 50 ? 'var(--warn)' : 'var(--danger)' },
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
                <div key={item.id} className="batch-item">
                  <span className={`batch-item__status batch-item__status--${item.status}`} />
                  <span style={{ fontFamily: 'var(--mono)', fontSize: '0.6875rem', color: 'var(--text-3)', width: 90, flexShrink: 0 }}>{item.barcode}</span>
                  <span className="batch-item__name">{item.name}</span>
                  <span className="batch-item__confidence" style={{
                    color: item.confidence >= 80 ? 'var(--safe)' : item.confidence >= 50 ? 'var(--warn)' : 'var(--danger)'
                  }}>{item.status === 'pending' ? '…' : `${item.confidence}%`}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {items.length === 0 && (
          <div style={{ textAlign: 'center', padding: '4rem 0', color: 'var(--text-3)' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" style={{ opacity: 0.2, margin: '0 auto 0.75rem' }}>
              <rect x="3" y="3" width="18" height="18" rx="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/>
            </svg>
            <p style={{ fontSize: '0.875rem' }}>No items scanned yet. Enter barcodes above to verify against FDA databases.</p>
          </div>
        )}
      </div>
    </div>
  );
}
