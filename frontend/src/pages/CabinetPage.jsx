import React, { useState, useEffect } from 'react';
import api from '../utils/api';

const USER_ID = localStorage.getItem('user_id') || 'anonymous';

const StatusBadge = ({ status }) => {
  const cfg = {
    expired:  { label: 'EXPIRED', cls: 'badge--danger', glow: 'var(--danger)' },
    expiring: { label: 'Expiring Soon', cls: 'badge--warn', glow: 'var(--warn)' },
    ok:       { label: 'Safe', cls: 'badge--safe', glow: 'var(--safe)' },
  };
  const c = cfg[status] || cfg.ok;
  return <span className={`badge ${c.cls}`} style={{ boxShadow: `0 0 12px ${c.glow}33` }}>{c.label}</span>;
};

export default function CabinetPage() {
  const [medicines, setMedicines] = useState([]);
  const [householdDupes, setHouseholdDupes] = useState([]);
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newMed, setNewMed] = useState({ name: '', expiry: '', quantity: '', dailyDose: '' });
  const [newMember, setNewMember] = useState({ name: '', age: '', conditions: '' });
  const [tab, setTab] = useState('cabinet');
  const [safetyCheckResult, setSafetyCheckResult] = useState(null);
  const [addWarning, setAddWarning] = useState('');
  const [pushEnabled, setPushEnabled] = useState(false);

  useEffect(() => {
    if ('Notification' in window && navigator.serviceWorker) {
      navigator.serviceWorker.ready.then(reg => {
        reg.pushManager.getSubscription().then(sub => {
          if (sub) setPushEnabled(true);
        });
      });
    }
  }, []);

  const enablePush = async () => {
    if (!('Notification' in window) || !navigator.serviceWorker) {
      alert("Push notifications are not supported in this browser.");
      return;
    }
    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
      alert("Permission denied.");
      return;
    }
    try {
      const { public_key } = await api.getPushPublicKey();
      const reg = await navigator.serviceWorker.ready;
      
      const padding = '='.repeat((4 - public_key.length % 4) % 4);
      const base64 = (public_key + padding).replace(/-/g, '+').replace(/_/g, '/');
      const rawData = window.atob(base64);
      const outputArray = new Uint8Array(rawData.length);
      for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
      }
      
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: outputArray
      });
      
      await api.subscribePush({
        endpoint: sub.endpoint,
        keys: {
          p256dh: btoa(String.fromCharCode.apply(null, new Uint8Array(sub.getKey('p256dh')))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, ''),
          auth: btoa(String.fromCharCode.apply(null, new Uint8Array(sub.getKey('auth')))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
        },
        user_id: USER_ID
      });
      
      setPushEnabled(true);
    } catch (err) {
      console.error(err);
      alert("Failed to enable push notifications.");
    }
  };

  const loadData = async () => {
    setLoading(true);
    try {
      const [m, f] = await Promise.all([api.getCabinetMedicines(USER_ID), api.getFamilyMembers(USER_ID)]);
      setMedicines(m.medicines || []);
      setHouseholdDupes(m.household_duplicates || []);
      setMembers(f);
    } catch (err) { console.error(err); }
    finally { setLoading(false); }
  };

  useEffect(() => { loadData(); }, []);

  const handleAddMed = async (e) => {
    e.preventDefault();
    setAddWarning('');
    try {
      const res = await api.addCabinetMedicine({ 
        user_id: USER_ID, 
        medicine_name: newMed.name, 
        expiry_date: new Date(newMed.expiry).toISOString(),
        quantity_remaining: newMed.quantity ? parseInt(newMed.quantity) : null,
        daily_dose_units: newMed.dailyDose ? parseInt(newMed.dailyDose) : null
      });
      if (res.duplicate_warning) setAddWarning(res.duplicate_warning);
      setNewMed({ name: '', expiry: '', quantity: '', dailyDose: '' }); 
      loadData();
    } catch (err) { console.error(err); }
  };

  const handleCheckSafety = async (medicineName, memberId) => {
    if (!memberId) return;
    try {
      const res = await api.checkMedicineSafety(medicineName, memberId);
      setSafetyCheckResult({ [medicineName]: res });
    } catch (err) { console.error(err); }
  };

  const handleAddMember = async (e) => {
    e.preventDefault();
    await api.addFamilyMember({ user_id: USER_ID, name: newMember.name, age: parseInt(newMember.age), conditions: newMember.conditions });
    setNewMember({ name: '', age: '', conditions: '' }); loadData();
  };

  const getExpiryStatus = (dateStr) => {
    try {
      let d = dateStr.replace('Z', '+00:00');
      if (d.length === 10) d += 'T00:00:00+00:00';
      const diff = (new Date(d) - new Date()) / 864e5;
      return diff < 0 ? 'expired' : diff <= 30 ? 'expiring' : 'ok';
    } catch { return 'ok'; }
  };

  const getDaysLeft = (dateStr) => {
    try {
      let d = dateStr.replace('Z', '+00:00');
      if (d.length === 10) d += 'T00:00:00+00:00';
      return Math.ceil((new Date(d) - new Date()) / 864e5);
    } catch { return 999; }
  };

  if (loading && medicines.length === 0) {
    return (
      <div className="page" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <div className="spinner" style={{ width: 32, height: 32 }} />
      </div>
    );
  }

  const expired = medicines.filter(m => getExpiryStatus(m.expiry_date) === 'expired').length;
  const expiring = medicines.filter(m => getExpiryStatus(m.expiry_date) === 'expiring').length;

  return (
    <div className="page anim">
      <div className="container">
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: '2.5rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '.75rem' }}>
            <span className="hero__tag-dot" /> Family Health Manager
          </div>
          <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '.5rem' }}>Medicine Cabinet</h1>
          <p style={{ color: 'var(--text-2)', fontSize: '0.9375rem', maxWidth: 480, margin: '0 auto' }}>
            Track your household medicines, monitor expiry dates, and protect family members from unsafe drugs.
          </p>
          {!pushEnabled && (
            <button onClick={enablePush} className="btn" style={{ marginTop: '1rem', background: 'var(--accent-dim)', color: 'var(--accent)', border: '1px solid var(--border-accent)', display: 'inline-flex', alignItems: 'center', gap: '0.5rem' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg>
              Enable Refill Notifications
            </button>
          )}
        </div>

        {/* Summary Cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1rem', marginBottom: '2rem' }} className="anim anim-d1">
          <div className="card" style={{ textAlign: 'center', padding: '1.25rem' }}>
            <div style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'var(--mono)', color: 'var(--accent)' }}>{medicines.length}</div>
            <div style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.1em', color: 'var(--text-3)' }}>Total Medicines</div>
          </div>
          <div className="card" style={{ textAlign: 'center', padding: '1.25rem', borderColor: expired > 0 ? 'rgba(239,68,68,0.2)' : undefined }}>
            <div style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'var(--mono)', color: expired > 0 ? 'var(--danger)' : 'var(--safe)' }}>{expired}</div>
            <div style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.1em', color: 'var(--text-3)' }}>Expired</div>
          </div>
          <div className="card" style={{ textAlign: 'center', padding: '1.25rem', borderColor: expiring > 0 ? 'rgba(251,191,36,0.2)' : undefined }}>
            <div style={{ fontSize: '2rem', fontWeight: 800, fontFamily: 'var(--mono)', color: expiring > 0 ? 'var(--warn)' : 'var(--safe)' }}>{expiring}</div>
            <div style={{ fontSize: '.7rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.1em', color: 'var(--text-3)' }}>Expiring Soon</div>
          </div>
        </div>

        {/* Tab Selector */}
        <div className="anim anim-d2" style={{ display: 'flex', gap: '.5rem', marginBottom: '1.5rem', padding: '.35rem', background: 'var(--bg-tertiary)', borderRadius: '14px', border: '1px solid var(--border-1)' }}>
          {[{ k: 'cabinet', l: 'Medicine Cabinet' }, { k: 'family', l: 'Family Members' }].map(t => (
            <button key={t.k} onClick={() => setTab(t.k)} style={{
              flex: 1, padding: '.65rem', borderRadius: '10px', fontSize: '.8125rem', fontWeight: 700,
              background: tab === t.k ? 'var(--accent)' : 'transparent',
              color: tab === t.k ? '#fff' : 'var(--text-2)',
              transition: 'all .3s var(--ease)', border: 'none', cursor: 'pointer'
            }}>{t.l}</button>
          ))}
        </div>

        {/* Household Duplicates Banner */}
        {householdDupes.length > 0 && tab === 'cabinet' && (
          <div className="anim anim-d3 card" style={{ marginBottom: '1.5rem', padding: '1rem', background: 'rgba(251,191,36,0.1)', borderColor: 'rgba(251,191,36,0.3)' }}>
            <div style={{ display: 'flex', gap: '.75rem', alignItems: 'flex-start' }}>
              <div style={{ fontSize: '1.25rem' }}>⚠️</div>
              <div>
                <strong style={{ display: 'block', color: 'var(--warn)', marginBottom: '.25rem', fontSize: '.9rem' }}>Household Duplicates Detected</strong>
                <p style={{ margin: 0, fontSize: '.8rem', color: 'var(--text-2)' }}>
                  You have multiple medications sharing the same active ingredient: 
                  {householdDupes.map(hd => ` ${hd.medicines.join(', ')}`).join('; ')}.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Add Warning Banner */}
        {addWarning && tab === 'cabinet' && (
          <div className="anim card" style={{ marginBottom: '1.5rem', padding: '1rem', background: 'rgba(239,68,68,0.1)', borderColor: 'rgba(239,68,68,0.3)' }}>
            <div style={{ display: 'flex', gap: '.75rem', alignItems: 'center' }}>
              <div style={{ fontSize: '1.25rem' }}>⚠️</div>
              <p style={{ margin: 0, fontSize: '.85rem', color: 'var(--danger)', fontWeight: 600 }}>{addWarning}</p>
              <button onClick={() => setAddWarning('')} className="btn" style={{ marginLeft: 'auto', background: 'transparent', padding: '.25rem .5rem', fontSize: '.75rem' }}>Dismiss</button>
            </div>
          </div>
        )}

        {/* Cabinet Tab */}
        {tab === 'cabinet' && (
          <div className="anim">
            <form onSubmit={handleAddMed} className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
              <div style={{ display: 'flex', gap: '.75rem', alignItems: 'flex-end', flexWrap: 'wrap' }}>
                <div style={{ flex: 2, minWidth: 160 }}>
                  <label className="form-label">Medicine Name</label>
                  <input required type="text" placeholder="e.g. Paracetamol" value={newMed.name} onChange={e => setNewMed({...newMed, name: e.target.value})} />
                </div>
                <div style={{ flex: 1, minWidth: 120 }}>
                  <label className="form-label">Expiry Date</label>
                  <input required type="date" value={newMed.expiry} onChange={e => setNewMed({...newMed, expiry: e.target.value})} />
                </div>
                <div style={{ flex: 1, minWidth: 80 }}>
                  <label className="form-label">Qty</label>
                  <input type="number" placeholder="e.g. 30" value={newMed.quantity} onChange={e => setNewMed({...newMed, quantity: e.target.value})} />
                </div>
                <div style={{ flex: 1, minWidth: 80 }}>
                  <label className="form-label">Daily Dose</label>
                  <input type="number" placeholder="e.g. 2" value={newMed.dailyDose} onChange={e => setNewMed({...newMed, dailyDose: e.target.value})} />
                </div>
                <button className="btn btn--primary" type="submit" style={{ height: 46 }}>Add</button>
              </div>
            </form>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
              {medicines.map((m, i) => {
                const st = getExpiryStatus(m.expiry_date);
                const days = getDaysLeft(m.expiry_date);
                const supply = m.days_supply_remaining;
                const showSupplyWarn = supply !== null && supply <= 5;
                const borderColor = st === 'expired' ? 'rgba(239,68,68,0.25)' : (st === 'expiring' || showSupplyWarn) ? 'rgba(251,191,36,0.25)' : 'var(--border-1)';
                const sCheck = safetyCheckResult?.[m.medicine_name];

                return (
                  <div key={i} className="card" style={{ padding: '1.15rem', borderColor, animationDelay: `${i * 0.05}s` }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1 }}>
                        <strong style={{ fontSize: '1rem', letterSpacing: '-0.02em' }}>{m.medicine_name}</strong>
                        <div style={{ fontSize: '.8rem', color: 'var(--text-3)', marginTop: '.35rem', fontFamily: 'var(--mono)', display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
                          <span>Exp: {new Date(m.expiry_date).toLocaleDateString()} {st !== 'expired' && days > 0 && <span style={{ color: 'var(--text-2)' }}>({days}d left)</span>}</span>
                          {supply !== null && (
                            <span style={{ color: showSupplyWarn ? 'var(--warn)' : 'inherit' }}>
                              Supply: {supply} day{supply !== 1 ? 's' : ''}
                            </span>
                          )}
                        </div>

                        {/* Safety Check UI */}
                        {members.length > 0 && (
                          <div style={{ marginTop: '.75rem', display: 'flex', gap: '.5rem', alignItems: 'center' }}>
                            <select 
                              className="form-input" 
                              style={{ width: 150, padding: '.3rem .5rem', fontSize: '.75rem', height: 'auto', minHeight: 0 }}
                              onChange={e => handleCheckSafety(m.medicine_name, e.target.value)}
                              defaultValue=""
                            >
                              <option value="" disabled>Check safety for...</option>
                              {members.map(mem => <option key={mem.id} value={mem.id}>{mem.name}</option>)}
                            </select>
                          </div>
                        )}
                        
                        {sCheck && (
                          <div style={{ marginTop: '.75rem', padding: '.75rem', background: sCheck.is_safe ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)', borderRadius: 8, fontSize: '.8rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '.5rem', marginBottom: '.25rem' }}>
                              <strong style={{ color: sCheck.is_safe ? 'var(--safe)' : 'var(--danger)' }}>
                                {sCheck.is_safe ? `Safe for ${sCheck.member}` : `Warning for ${sCheck.member}`}
                              </strong>
                              {sCheck.source === 'rxnorm_deterministic' && <span title="Deterministic RxNorm Data" style={{ color: 'var(--safe)' }}>🔒</span>}
                              {sCheck.source === 'llm_advisory' && <span title="LLM Advisory" style={{ color: 'var(--warn)' }}>⚠️</span>}
                            </div>
                            {sCheck.warning && <div style={{ color: 'var(--text-2)' }}>{sCheck.warning}</div>}
                          </div>
                        )}

                      </div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '.5rem', alignItems: 'flex-end' }}>
                        <StatusBadge status={st} />
                        {showSupplyWarn && <span className="badge badge--warn">Low Supply</span>}
                      </div>
                    </div>
                  </div>
                );
              })}
              {medicines.length === 0 && <p style={{ color: 'var(--text-3)', textAlign: 'center', padding: '2rem' }}>No medicines in the cabinet yet. Add your first one above.</p>}
            </div>
          </div>
        )}

        {/* Family Tab */}
        {tab === 'family' && (
          <div className="anim">
            <form onSubmit={handleAddMember} className="card" style={{ marginBottom: '1.5rem', padding: '1.25rem' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
                <div style={{ display: 'flex', gap: '.75rem' }}>
                  <div style={{ flex: 2 }}>
                    <label className="form-label">Name</label>
                    <input required type="text" placeholder="e.g. Mom" value={newMember.name} onChange={e => setNewMember({...newMember, name: e.target.value})} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <label className="form-label">Age</label>
                    <input required type="number" placeholder="65" value={newMember.age} onChange={e => setNewMember({...newMember, age: e.target.value})} />
                  </div>
                </div>
                <div>
                  <label className="form-label">Health Conditions</label>
                  <input required type="text" placeholder="e.g. Hypertension, Kidney disease" value={newMember.conditions} onChange={e => setNewMember({...newMember, conditions: e.target.value})} />
                </div>
                <button className="btn btn--primary" type="submit">Add Family Member</button>
              </div>
            </form>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '.75rem' }}>
              {members.map((m, i) => (
                <div key={i} className="card" style={{ padding: '1.25rem', animationDelay: `${i * 0.05}s` }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '.75rem' }}>
                    <div style={{ width: 44, height: 44, borderRadius: 12, background: 'linear-gradient(135deg, var(--accent-dim), var(--accent-2-dim))', border: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800, fontSize: '1rem', color: 'var(--accent)', flexShrink: 0 }}>
                      {m.name?.charAt(0)?.toUpperCase()}
                    </div>
                    <div>
                      <div style={{ fontWeight: 800, fontSize: '1rem', letterSpacing: '-0.02em' }}>{m.name}</div>
                      <div style={{ fontSize: '.75rem', color: 'var(--text-3)', fontFamily: 'var(--mono)' }}>{m.age} years</div>
                    </div>
                  </div>
                  <div style={{ padding: '.65rem .85rem', background: 'var(--bg-primary)', borderRadius: 8, border: '1px solid var(--border-1)' }}>
                    <div style={{ fontSize: '.65rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '.1em', color: 'var(--accent)', marginBottom: '.3rem' }}>Health Conditions</div>
                    <div style={{ fontSize: '.875rem', color: 'var(--text-2)', lineHeight: 1.5 }}>{m.conditions}</div>
                  </div>
                </div>
              ))}
              {members.length === 0 && <p style={{ color: 'var(--text-3)', textAlign: 'center', padding: '2rem' }}>No family members added yet.</p>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
