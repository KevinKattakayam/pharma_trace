import React, { useState } from 'react';
import PageHeader from '../components/PageHeader';
import ScopeNotice from '../components/ScopeNotice';
import api from '../utils/api';
import { friendlyError, priceStatus } from '../utils/copy';

/** Compare a printed MRP with India's notified ceiling price for essential medicines. */
export default function PriceCheck() {
  const [form, setForm] = useState({ drug_name: '', printed_mrp: '', units_in_pack: '' });
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      setResult(await api.priceCheck({
        drug_name: form.drug_name.trim(),
        printed_mrp: form.printed_mrp === '' ? null : Number(form.printed_mrp),
        units_in_pack: form.units_in_pack === '' ? null : Number(form.units_in_pack),
      }));
    } catch (err) {
      setError(friendlyError(err));
      setResult(null);
    } finally {
      setLoading(false);
    }
  };

  const status = result && priceStatus(result);

  return (
    <div className="page container">
      <PageHeader
        title="Check the price on a pack"
        sub="For essential medicines, the government sets a maximum price. Enter what is printed on the pack to compare."
      />
      <ScopeNotice compact />

      <form className="card" onSubmit={submit} style={{ maxWidth: 520 }}>
        <div className="field">
          <label className="field__label" htmlFor="price-name">Medicine name, with strength</label>
          <input id="price-name" value={form.drug_name} onChange={set('drug_name')} maxLength={200}
            placeholder="Paracetamol tablets 500 mg" required />
          <span className="field__hint">Copy the generic name and strength exactly as printed.</span>
        </div>
        <div style={{ display: 'grid', gap: 'var(--space-3)', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))' }}>
          <div className="field">
            <label className="field__label" htmlFor="price-mrp">Printed MRP (₹)</label>
            <input id="price-mrp" type="number" inputMode="decimal" step="0.01" min="0" value={form.printed_mrp} onChange={set('printed_mrp')} placeholder="30.00" />
          </div>
          <div className="field">
            <label className="field__label" htmlFor="price-units">Tablets or ml in the pack</label>
            <input id="price-units" type="number" inputMode="numeric" min="1" value={form.units_in_pack} onChange={set('units_in_pack')} placeholder="15" />
          </div>
        </div>
        <button type="submit" className="btn btn--primary btn--lg" style={{ width: '100%' }} disabled={loading || !form.drug_name.trim()}>
          {loading ? 'Checking…' : 'Check price'}
        </button>
      </form>

      {error && <div role="alert" className="card card--danger" style={{ maxWidth: 520, marginTop: 'var(--space-3)' }}>{error}</div>}

      {result && (
        <section aria-live="polite" className="card" style={{ maxWidth: 520, marginTop: 'var(--space-3)' }}>
          <p className={`status status--${status.tone}`}><span className="status__dot" />{status.label}</p>
          <p className="prose" style={{ marginTop: 'var(--space-2)' }}>{result.message}</p>
          {result.status === 'above_ceiling' && result.report_url && (
            <p className="small-print">
              You can report overcharging to NPPA: <a href={result.report_url} target="_blank" rel="noreferrer noopener">nppaindia.nic.in</a>
            </p>
          )}
          {result.notification && (
            <p className="small-print">
              Source: {result.notification}, effective {result.effective_from}.{' '}
              <a href={result.source_url} target="_blank" rel="noreferrer noopener">NPPA ceiling prices</a>
            </p>
          )}
          {result.coverage?.is_sample_data && (
            <p className="small-print" style={{ color: 'var(--danger-amber-dark)', fontWeight: 700 }}>
              Demo data: these are sample prices, not real NPPA notifications.
            </p>
          )}
          <p className="small-print">{result.disclaimer}</p>
        </section>
      )}
    </div>
  );
}
