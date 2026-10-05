import React, { useState, useEffect, useCallback } from 'react';
import api from '../utils/api';

const StatCard = ({ label, value, icon, color = 'var(--accent)' }) => (
  <div className="card anim" style={{ padding: '1.5rem', textAlign: 'center', flex: '1 1 140px', minWidth: 140 }}>
    <div style={{ fontSize: '2rem', marginBottom: '0.5rem' }}>{icon}</div>
    <div style={{ fontSize: '2rem', fontWeight: 900, color, letterSpacing: '-0.04em', fontFamily: 'var(--mono)' }}>{value}</div>
    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-3)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: '0.25rem' }}>{label}</div>
  </div>
);

const DrugRow = ({ name, count, rank }) => (
  <div style={{
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    padding: '0.75rem 1rem', borderRadius: '10px',
    background: rank <= 3 ? 'rgba(99,102,241,0.06)' : 'transparent',
    border: '1px solid var(--border-1)', marginBottom: '0.5rem'
  }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
      <span style={{
        width: 28, height: 28, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.7rem', fontWeight: 800, fontFamily: 'var(--mono)',
        background: rank <= 3 ? 'var(--accent)' : 'var(--bg-tertiary)',
        color: rank <= 3 ? '#fff' : 'var(--text-3)'
      }}>{rank}</span>
      <span style={{ fontWeight: 700, fontSize: '0.875rem' }}>{name}</span>
    </div>
    <span style={{ fontFamily: 'var(--mono)', fontWeight: 800, fontSize: '0.875rem', color: 'var(--accent)' }}>{count}</span>
  </div>
);

export default function ClinicDashboard() {
  const [clinicId, setClinicId] = useState(() => localStorage.getItem('pharmatrace_clinic_id') || '');
  const [dashboard, setDashboard] = useState(null);
  const [workers, setWorkers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Registration form
  const [showRegister, setShowRegister] = useState(false);
  const [regName, setRegName] = useState('');
  const [regEmail, setRegEmail] = useState('');
  const [regAddr, setRegAddr] = useState('');

  // Audit export
  const [exportFormat, setExportFormat] = useState('csv');
  const [exportStart, setExportStart] = useState('');
  const [exportEnd, setExportEnd] = useState('');

  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');

  const loadDashboard = async (id) => {
    const [dash, work] = await Promise.all([api.getClinicDashboard(id), api.getClinicWorkers(id)]);
    setDashboard(dash);
    setWorkers(work.workers || []);
    localStorage.setItem('pharmatrace_clinic_id', id);
    setClinicId(id);
  };

  // Clinic access requires the administrator's e-mail and password; a clinic ID alone grants nothing.
  const handleLogin = async () => {
    if (!loginEmail || !loginPassword) return;
    setLoading(true);
    setError('');
    try {
      const authRes = await api.loginClinic(loginEmail, loginPassword);
      await api.setToken(authRes.access_token);
      setLoginPassword('');
      await loadDashboard(authRes.clinic_id);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const resumeSession = async (id) => {
    setLoading(true);
    try {
      await loadDashboard(id);
    } catch {
      localStorage.removeItem('pharmatrace_clinic_id'); // expired or revoked: show sign-in
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const savedId = localStorage.getItem('pharmatrace_clinic_id');
    if (savedId) resumeSession(savedId);
  }, []);

  const handleRegister = async (e) => {
    e.preventDefault();
    if (!regName.trim()) return;
    setLoading(true);
    try {
      // Clinic accounts are created by platform administrators (POST /clinic/create is admin-only).
      await api.createClinic({ name: regName, contact_email: regEmail, address: regAddr });
      setShowRegister(false);
      setError('Clinic registered. Sign in with the administrator e-mail and password.');
      setLoading(false);
    } catch (e) {
      setError(e.message);
      setLoading(false);
    }
  };

  const [exporting, setExporting] = useState(false);

  const handleExport = async () => {
    try {
      setExporting(true);
      setError('');
      const blob = await api.downloadAuditExport(exportFormat, exportStart, exportEnd, clinicId);
      
      // Create object URL and trigger download
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `pharmatrace_audit.${exportFormat}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);
    } catch (e) {
      setError(e.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="page anim">
      <div className="container" style={{ maxWidth: 900, margin: '0 auto' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }} className="anim">
          <div className="hero__tag" style={{ justifyContent: 'center', marginBottom: '.75rem' }}>
            <span className="hero__tag-dot" /> Enterprise Administration
          </div>
          <h1 style={{ fontSize: '2.25rem', fontWeight: 900, letterSpacing: '-0.04em', marginBottom: '.5rem' }}>
            Clinic Dashboard
          </h1>
          <p style={{ color: 'var(--text-2)', fontSize: '.9375rem', maxWidth: 500, margin: '0 auto' }}>
            Aggregate verification analytics across your organization's health workers.
          </p>
        </div>

        {/* Clinic ID Input */}
        {!dashboard && !showRegister && (
          <div className="card anim" style={{ maxWidth: 460, margin: '0 auto', padding: '2rem', textAlign: 'center' }}>
            <div style={{ fontSize: '3rem', marginBottom: '1rem' }}>🏥</div>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1rem' }}>Access Your Clinic</h2>
            <div style={{ display: 'flex', gap: '0.75rem', marginBottom: '1.5rem' }}>
              <form onSubmit={(e) => { e.preventDefault(); handleLogin(); }} style={{ display: 'grid', gap: '0.75rem', flex: 1 }}>
                <label htmlFor="clinic-email" className="sr-only">Administrator e-mail</label>
                <input id="clinic-email" type="email" autoComplete="username" value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)} placeholder="Administrator e-mail" required />
                <label htmlFor="clinic-password" className="sr-only">Password</label>
                <input id="clinic-password" type="password" autoComplete="current-password" value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)} placeholder="Password" required />
                <button type="submit" className="btn btn--primary" disabled={!loginEmail || !loginPassword || loading}>
                  {loading ? 'Signing in…' : 'Sign in'}
                </button>
              </form>
            </div>
            <div style={{ fontSize: '0.8125rem', color: 'var(--text-3)' }}>
              Don't have a clinic account?{' '}
              <button onClick={() => setShowRegister(true)} style={{ color: 'var(--accent)', fontWeight: 700, background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                Register now
              </button>
            </div>
          </div>
        )}

        {/* Registration Form */}
        {showRegister && (
          <div className="card anim" style={{ maxWidth: 460, margin: '0 auto', padding: '2rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: '1rem' }}>Register New Clinic</h2>
            <form onSubmit={handleRegister}>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Clinic Name *</label>
                <input type="text" value={regName} onChange={(e) => setRegName(e.target.value)} placeholder="City Primary Health Center" required />
              </div>
              <div className="form-group" style={{ marginBottom: '1rem' }}>
                <label className="form-label">Contact Email</label>
                <input type="email" value={regEmail} onChange={(e) => setRegEmail(e.target.value)} placeholder="admin@clinic.org" />
              </div>
              <div className="form-group" style={{ marginBottom: '1.5rem' }}>
                <label className="form-label">Address</label>
                <input type="text" value={regAddr} onChange={(e) => setRegAddr(e.target.value)} placeholder="District, State" />
              </div>
              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button type="submit" className="btn btn--primary btn--lg" style={{ flex: 1 }} disabled={loading}>
                  {loading ? 'Creating...' : 'Create Clinic'}
                </button>
                <button type="button" className="btn btn--secondary" onClick={() => setShowRegister(false)}>Cancel</button>
              </div>
            </form>
          </div>
        )}

        {error && (
          <div className="card card--danger anim" style={{ maxWidth: 460, margin: '1rem auto', textAlign: 'center', padding: '1rem' }}>
            <p style={{ color: 'var(--danger)', fontWeight: 600 }}>{error}</p>
          </div>
        )}

        {/* Dashboard */}
        {dashboard && (
          <>
            <div className="anim" style={{ textAlign: 'center', marginBottom: '1.5rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 900 }}>{dashboard.clinic_name}</h2>
              <span style={{ fontSize: '0.7rem', fontFamily: 'var(--mono)', color: 'var(--text-3)' }}>
                ID: {dashboard.clinic_id.slice(0, 8)}…
              </span>
            </div>

            {/* Stat Cards */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '2rem' }}>
              <StatCard label="Scans This Month" value={dashboard.total_scans_this_month} icon="📊" />
              <StatCard label="All-Time Scans" value={dashboard.total_scans_all_time} icon="🔬" />
              <StatCard label="Recall Encounters" value={dashboard.recall_encounters} icon="⚠️" color="var(--warning)" />
              <StatCard label="Counterfeit Flags" value={dashboard.counterfeit_flags} icon="🚨" color="var(--danger)" />
              <StatCard label="Pass Rate" value={`${dashboard.pass_rate}%`} icon="✅" color="var(--safe)" />
            </div>

            {/* Top Drugs + Daily Activity */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
              <div className="card anim" style={{ padding: '1.5rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '1rem' }}>
                  Most Verified Drugs
                </h3>
                {dashboard.top_drugs.length === 0 ? (
                  <p style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>No data yet</p>
                ) : (
                  dashboard.top_drugs.map((d, i) => (
                    <DrugRow key={i} name={d.name} count={d.count} rank={i + 1} />
                  ))
                )}
              </div>

              <div className="card anim" style={{ padding: '1.5rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '1rem' }}>
                  Daily Activity (Last 30 days)
                </h3>
                {dashboard.daily_activity.length === 0 ? (
                  <p style={{ color: 'var(--text-3)', fontSize: '0.875rem' }}>No activity recorded</p>
                ) : (
                  <div style={{ display: 'flex', alignItems: 'flex-end', gap: '3px', height: '120px', padding: '0.5rem 0' }}>
                    {dashboard.daily_activity.map((d, i) => {
                      const max = Math.max(...dashboard.daily_activity.map(x => x.scans));
                      const height = max > 0 ? (d.scans / max) * 100 : 0;
                      return (
                        <div key={i} title={`${d.date}: ${d.scans} scans`} style={{
                          flex: 1, minWidth: 4, borderRadius: '3px 3px 0 0',
                          height: `${Math.max(height, 4)}%`,
                          background: `linear-gradient(to top, var(--accent), var(--accent-2))`,
                          opacity: 0.7 + (height / 300),
                          transition: 'height 0.4s var(--ease)'
                        }} />
                      );
                    })}
                  </div>
                )}
              </div>
            </div>

            {/* Workers Table */}
            {workers.length > 0 && (
              <div className="card anim" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
                <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '1rem' }}>Health Worker Activity</h3>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.8125rem' }}>
                    <thead>
                      <tr style={{ borderBottom: '2px solid var(--border-1)' }}>
                        <th style={{ padding: '0.75rem', textAlign: 'left', fontWeight: 800, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: '0.1em', color: 'var(--text-3)' }}>Method</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 800, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: '0.1em', color: 'var(--text-3)' }}>Scans</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 800, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: '0.1em', color: 'var(--text-3)' }}>Recalls</th>
                        <th style={{ padding: '0.75rem', textAlign: 'right', fontWeight: 800, textTransform: 'uppercase', fontSize: '0.65rem', letterSpacing: '0.1em', color: 'var(--text-3)' }}>Flags</th>
                      </tr>
                    </thead>
                    <tbody>
                      {workers.map((w, i) => (
                        <tr key={i} style={{ borderBottom: '1px solid var(--border-1)' }}>
                          <td style={{ padding: '0.75rem', fontWeight: 700 }}>{w.method}</td>
                          <td style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'var(--mono)' }}>{w.scans}</td>
                          <td style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'var(--mono)', color: w.recalls > 0 ? 'var(--warning)' : 'var(--text-3)' }}>{w.recalls}</td>
                          <td style={{ padding: '0.75rem', textAlign: 'right', fontFamily: 'var(--mono)', color: w.flags > 0 ? 'var(--danger)' : 'var(--text-3)' }}>{w.flags}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Audit Export */}
            <div className="card anim" style={{ padding: '1.5rem', marginBottom: '2rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 800, marginBottom: '0.5rem' }}>
                📋 Regulatory Audit Export
              </h3>
              <p style={{ color: 'var(--text-3)', fontSize: '0.8125rem', marginBottom: '1.25rem' }}>
                Generate a signed audit chain export for drug inspectors. Each record includes its SHA-256 hash and tamper verification status.
              </p>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', alignItems: 'flex-end' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: '0.25rem' }}>Start Date</label>
                  <input type="date" value={exportStart} onChange={(e) => setExportStart(e.target.value)} style={{ padding: '0.5rem' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: '0.25rem' }}>End Date</label>
                  <input type="date" value={exportEnd} onChange={(e) => setExportEnd(e.target.value)} style={{ padding: '0.5rem' }} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase', color: 'var(--text-3)', marginBottom: '0.25rem' }}>Format</label>
                  <select value={exportFormat} onChange={(e) => setExportFormat(e.target.value)} style={{ padding: '0.5rem' }}>
                    <option value="csv">CSV</option>
                    <option value="pdf">PDF</option>
                  </select>
                </div>
                <button className="btn btn--primary" onClick={handleExport} disabled={exporting} style={{ height: 'fit-content' }}>
                  {exporting ? 'Generating...' : 'Export Audit Chain'}
                </button>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
