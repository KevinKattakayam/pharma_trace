import React, { useState, useEffect, useCallback } from 'react';
import api from '../utils/api';

export default function CaregiverDashboard() {
  const [dashboard, setDashboard] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [linkCode, setLinkCode] = useState(null);
  const [acceptCode, setAcceptCode] = useState('');
  const [loading, setLoading] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState(null);

  const loadDashboard = useCallback(async () => {
    try {
      const [dash, alertData] = await Promise.all([
        api.getCaregiverDashboard(),
        api.getCaregiverAlerts()
      ]);
      setDashboard(dash);
      setAlerts(alertData.alerts || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadDashboard(); }, [loadDashboard]);

  const handleGenerateLink = async () => {
    setGenerating(true);
    try {
      const res = await api.generateCaregiverLink();
      setLinkCode(res.code);
    } catch (err) { setError(err.message); }
    finally { setGenerating(false); }
  };

  const handleAcceptLink = async () => {
    if (!acceptCode.trim()) return;
    setAccepting(true);
    try {
      await api.acceptCaregiverLink(acceptCode.trim());
      setAcceptCode('');
      await loadDashboard();
    } catch (err) { setError(err.message); }
    finally { setAccepting(false); }
  };

  return (
    <div className="page">
      <div className="container">
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '1.5rem', flexWrap: 'wrap', gap: '0.75rem' }} className="anim">
          <div>
            <div className="hero__tag" style={{ marginBottom: '0.6rem' }}>
              <span className="hero__tag-dot" /> Remote Monitoring
            </div>
            <h1 style={{ fontSize: '2rem', fontWeight: 900, letterSpacing: '-0.04em' }}>Caregiver Dashboard</h1>
            <p style={{ color: 'var(--text-3)', fontSize: '0.9375rem', marginTop: '0.35rem' }}>Monitor your loved ones' medication safety remotely</p>
          </div>
        </div>

        {/* Link Management */}
        <div className="card anim anim-d1" style={{ marginBottom: '1.5rem' }}>
          <div className="drug-result__section-title" style={{ marginBottom: '0.75rem' }}>Link a Care Recipient</div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            {/* Generate */}
            <div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginBottom: '0.5rem' }}>
                Generate an invite code and share it with your care recipient's device.
              </p>
              <button className="btn btn--primary" onClick={handleGenerateLink} disabled={generating} style={{ width: '100%' }}>
                {generating ? 'Generating…' : 'Generate Invite Code'}
              </button>
              {linkCode && (
                <div style={{
                  marginTop: '0.65rem', padding: '0.65rem 1rem', background: 'rgba(0,229,191,0.06)',
                  border: '1px solid rgba(0,229,191,0.12)', borderRadius: 8, textAlign: 'center'
                }}>
                  <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: '0.25rem' }}>Invite Code</div>
                  <div style={{ fontFamily: 'var(--mono)', fontSize: '1.25rem', fontWeight: 700, color: 'var(--accent)', letterSpacing: '0.1em' }}>{linkCode}</div>
                </div>
              )}
            </div>

            {/* Accept */}
            <div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', marginBottom: '0.5rem' }}>
                Enter the code received from a care recipient to start monitoring their medications.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem' }}>
                <input
                  type="text" value={acceptCode} onChange={e => setAcceptCode(e.target.value)}
                  placeholder="e.g., PT-A1B2C3" style={{ flex: 1 }}
                  onKeyDown={e => e.key === 'Enter' && handleAcceptLink()}
                />
                <button className="btn btn--secondary" onClick={handleAcceptLink} disabled={!acceptCode.trim() || accepting}>
                  {accepting ? '…' : 'Link'}
                </button>
              </div>
            </div>
          </div>
        </div>

        {error && (
          <div className="card card--danger anim" style={{ marginBottom: '1rem', textAlign: 'center' }}>
            <p style={{ color: 'var(--danger)', fontSize: '0.8125rem' }}>{error}</p>
          </div>
        )}

        {/* Stats */}
        {dashboard && (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.65rem', marginBottom: '1.25rem' }}>
            {[
              { val: dashboard.total_linked, label: 'Linked', color: 'var(--safe)' },
              { val: dashboard.pending_invites, label: 'Pending', color: 'var(--warn)' },
              { val: alerts.length, label: 'Alerts', color: alerts.length > 0 ? 'var(--danger)' : 'var(--text-3)' },
            ].map((s, i) => (
              <div key={i} className="card" style={{ textAlign: 'center', padding: '1rem' }}>
                <div style={{ fontFamily: 'var(--mono)', fontSize: '1.5rem', fontWeight: 700, color: s.color }}>{s.val}</div>
                <div style={{ fontSize: '0.625rem', color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{s.label}</div>
              </div>
            ))}
          </div>
        )}

        {/* Alerts */}
        {alerts.length > 0 && (
          <div className="card anim" style={{ marginBottom: '1.25rem' }}>
            <div className="drug-result__section-title" style={{ color: 'var(--danger)' }}>Active Alerts</div>
            {alerts.map((alert, i) => (
              <div key={i} style={{
                padding: '0.5rem 0.85rem', borderRadius: 8, marginBottom: '0.4rem',
                fontSize: '0.8125rem', lineHeight: 1.5,
                background: alert.severity === 'high' ? 'var(--danger-bg)' : 'var(--warn-bg)',
                color: alert.severity === 'high' ? 'var(--danger)' : 'var(--warn)',
                border: `1px solid ${alert.severity === 'high' ? 'rgba(239,68,68,0.1)' : 'rgba(245,158,11,0.1)'}`,
              }}>
                {alert.message}
              </div>
            ))}
          </div>
        )}

        {/* Recipients */}
        {dashboard && dashboard.recipients.length > 0 ? (
          <div className="cg-grid">
            {dashboard.recipients.map((person, pi) => (
              <div key={pi} className="card anim" style={{ animationDelay: `${0.1 * pi}s` }}>
                <div className="cg-card__header">
                  <div className="cg-card__avatar">{(person.name || person.code || '?')[0].toUpperCase()}</div>
                  <div>
                    <h3 style={{ fontSize: '1rem', fontWeight: 700 }}>{person.name || person.code}</h3>
                    <p style={{ fontSize: '0.6875rem', color: 'var(--text-3)' }}>
                      {person.medications?.length || 0} medication(s) tracked
                    </p>
                  </div>
                </div>

                {person.alerts && person.alerts.length > 0 && (
                  <div style={{ marginBottom: '1rem' }}>
                    {person.alerts.map((alert, ai) => (
                      <div key={ai} style={{
                        padding: '0.5rem 0.75rem', borderRadius: 8, marginBottom: '0.4rem',
                        fontSize: '0.75rem', background: 'var(--danger-bg)', color: 'var(--danger)',
                        border: '1px solid rgba(239,68,68,0.1)'
                      }}>
                        {alert.message}
                      </div>
                    ))}
                  </div>
                )}

                {person.medications && person.medications.length > 0 ? (
                  <>
                    <div className="drug-result__section-title">Medications</div>
                    <div className="batch-list">
                      {person.medications.map((med, mi) => (
                        <div key={mi} className="batch-item">
                          <span className={`batch-item__status batch-item__status--${med.status === 'verified' ? 'pass' : 'fail'}`} />
                          <span className="batch-item__name">{med.name}</span>
                          <span className="batch-item__confidence" style={{
                            color: med.confidence >= 80 ? 'var(--safe)' : med.confidence >= 50 ? 'var(--warn)' : 'var(--danger)'
                          }}>{med.confidence}%</span>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <p style={{ fontSize: '0.75rem', color: 'var(--text-3)', textAlign: 'center', padding: '1rem 0' }}>
                    No medications tracked yet. Verify drugs via the scanner to add them.
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : !loading && (
          <div className="card" style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-3)' }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" style={{ opacity: 0.2, margin: '0 auto 0.75rem', display: 'block' }}>
              <path d="M17 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 00-3-3.87"/><path d="M16 3.13a4 4 0 010 7.75"/>
            </svg>
            <p style={{ fontSize: '0.875rem', marginBottom: '0.5rem' }}>No care recipients linked yet</p>
            <p style={{ fontSize: '0.75rem' }}>Generate an invite code above and share it to start monitoring medications remotely.</p>
          </div>
        )}

        {loading && (
          <div style={{ textAlign: 'center', padding: '3rem 0' }}>
            <div className="spinner" style={{ margin: '0 auto 1rem', width: 28, height: 28 }} />
            <p style={{ color: 'var(--text-3)', fontSize: '0.8125rem' }}>Loading dashboard…</p>
          </div>
        )}
      </div>
    </div>
  );
}
