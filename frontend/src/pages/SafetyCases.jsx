import { useEffect, useState } from 'react';
import api from '../utils/api';

const ISSUE_TYPES = [
  ['suspected_falsified', 'Suspected falsified medicine'],
  ['recall', 'Recall or regulator alert'],
  ['quality_defect', 'Packaging or quality defect'],
  ['storage_concern', 'Storage or temperature concern'],
  ['adverse_event', 'Possible adverse event'],
  ['other', 'Other safety concern'],
];

export default function SafetyCases() {
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState('');
  const [form, setForm] = useState({ medicine_name: '', batch_number: '', issue_type: 'suspected_falsified', notes: '', quarantined: false });

  const load = async () => {
    try { setCases(await api.getSafetyCases()); }
    catch (error) { setMessage(error.message); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const submit = async (event) => {
    event.preventDefault();
    setSubmitting(true); setMessage('');
    try {
      const created = await api.createSafetyCase(form);
      setCases((current) => [created, ...current]);
      setForm({ medicine_name: '', batch_number: '', issue_type: 'suspected_falsified', notes: '', quarantined: false });
      setMessage('Safety case opened. Keep the medicine separate and wait for professional review.');
    } catch (error) { setMessage(error.message); }
    finally { setSubmitting(false); }
  };

  return <main className="page"><div className="container" style={{ maxWidth: 820 }}>
    <header className="page-heading">
      <p className="label-text">Safety operations</p>
      <h1>Open a medicine safety case</h1>
      <p className="legal-text">Create an auditable record for a suspect pack, recall, quality issue, storage concern, or adverse event. This does not replace emergency care.</p>
    </header>
    <div className="safety-review-banner"><strong>Immediate action:</strong> Do not dispense or consume a suspect medicine. Keep its package, batch details, and proof of purchase available for the pharmacist or regulator.</div>
    <form className="card" onSubmit={submit}>
      <div className="form-grid">
        <div className="form-group"><label className="form-label">Medicine name</label><input required value={form.medicine_name} onChange={(e) => update('medicine_name', e.target.value)} placeholder="Medicine name" /></div>
        <div className="form-group"><label className="form-label">Batch / lot number</label><input value={form.batch_number} onChange={(e) => update('batch_number', e.target.value)} placeholder="Optional" /></div>
      </div>
      <div className="form-group"><label className="form-label">Issue type</label><select value={form.issue_type} onChange={(e) => update('issue_type', e.target.value)}>{ISSUE_TYPES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></div>
      <div className="form-group"><label className="form-label">What happened?</label><textarea required minLength="10" value={form.notes} onChange={(e) => update('notes', e.target.value)} rows="4" placeholder="Describe the package, label, storage issue, or event. Do not include unnecessary personal medical details." /></div>
      <label className="case-check"><input type="checkbox" checked={form.quarantined} onChange={(e) => update('quarantined', e.target.checked)} /> I have separated this medicine from usable stock.</label>
      <button className="btn btn--primary" disabled={submitting}>{submitting ? 'Opening case…' : 'Open safety case'}</button>
    </form>
    {message && <p className="case-message" role="status">{message}</p>}
    <section className="case-list"><h2>My open and recent cases</h2>{loading ? <p className="legal-text">Loading cases…</p> : cases.length === 0 ? <p className="legal-text">No safety cases yet.</p> : cases.map((item) => <article className="card case-item" key={item.id}><div><p className="label-text">{item.status.replace('_', ' ')}</p><h3>{item.medicine_name}</h3><p className="legal-text">{item.issue_type.replaceAll('_', ' ')} · {item.quarantined ? 'Quarantined' : 'Not marked quarantined'}</p></div><time className="legal-text">{new Date(item.created_at).toLocaleDateString()}</time></article>)}</section>
  </div></main>;
}
