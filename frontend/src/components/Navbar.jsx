import React, { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';

const Icons = {
  home: <svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  scan: <svg viewBox="0 0 24 24"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>,
  cabinet: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="9" y1="21" x2="9" y2="9"/></svg>,
  map: <svg viewBox="0 0 24 24"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>,
  batch: <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></svg>,
  more: <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="1"/><circle cx="12" cy="5" r="1"/><circle cx="12" cy="19" r="1"/></svg>,
  interact: <svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>,
  safety: <svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M12 8v5"/><circle cx="12" cy="16.5" r=".7"/></svg>,
  dashboard: <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
  report: <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>,
  close: <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  dosage: <svg viewBox="0 0 24 24"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>,
  generic: <svg viewBox="0 0 24 24"><path d="M19.5 12.572l-7.5 7.428-7.5-7.428A5 5 0 1112 6.006a5 5 0 017.5 6.572"/></svg>,
  sideeffect: <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
  prescription: <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M9 15h6M9 12h6M9 18h6"/></svg>,
  api: <svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>,
  logo: <svg viewBox="0 0 28 28"><rect width="28" height="28" rx="7" fill="#ffffff" /><path d="M14 5v18M8 11h12M7 14.5h14" stroke="#0B6E6E" strokeWidth="2.2" strokeLinecap="round"/><circle cx="14" cy="7" r="1.5" fill="#F59E0B"/></svg>,
};

const navItems = [
  { path: '/scan', icon: 'scan', label: 'Scan' },
    { path: '/pack-check', icon: 'scan', label: 'Pack Check' },
    { path: '/price-check', icon: 'scan', label: 'Price Check' },
  { path: '/cabinet', icon: 'cabinet', label: 'Cabinet' },
  { path: '/map', icon: 'map', label: 'Map' },
  { path: '/batch', icon: 'batch', label: 'Batch' },
];

const toolsMenu = [
  { path: '/', icon: 'home', label: 'Dashboard' },
  { path: '/prescription', icon: 'prescription', label: 'Visit Summarizer' },
  { path: '/interactions', icon: 'interact', label: 'Drug Interactions' },
  { path: '/side-effects', icon: 'sideeffect', label: 'Side Effect Explainer' },
  { path: '/dosage', icon: 'dosage', label: 'Dosage Personalizer' },
  { path: '/generics', icon: 'generic', label: 'Generic Finder' },
  { path: '/report', icon: 'report', label: 'Report Medicine' },
  { path: '/safety-cases', icon: 'safety', label: 'Safety Cases', enterprise: true },
  { path: '/dashboard', icon: 'dashboard', label: 'Caregiver Mode' },
  { path: '/clinic', icon: 'dashboard', label: 'Clinic Admin', enterprise: true },
  { path: '/adverse-event', icon: 'report', label: 'Adverse Event', enterprise: true },
  { path: '/api-docs', icon: 'api', label: 'API & SDK' },
];

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navigate = useNavigate();

  return (
    <>
      <nav className="navbar" id="main-navbar">
        <div className="navbar__inner">
          <NavLink to="/" className="navbar__logo">
            {Icons.logo}
            <span>Pharma<span style={{color: 'var(--accent)'}}>Trace</span></span>
          </NavLink>
        </div>
      </nav>

      {/* Slide-up Tools Menu */}
      <div className={`result-sheet ${menuOpen ? 'open' : ''}`} style={{zIndex: 105, maxHeight: '75vh', overflowY: 'auto'}}>
        <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem', paddingBottom: '0.75rem', borderBottom: '1px solid var(--border-light)'}}>
          <div>
            <h2 className="section-header" style={{margin: 0, fontSize: '20px', fontWeight: 800}}>Clinical Intelligence Suite</h2>
            <span style={{fontSize: '11px', color: 'var(--primary)', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em'}}>Safety workspace</span>
          </div>
          <button onClick={() => setMenuOpen(false)} style={{background: 'var(--bg-secondary)', borderRadius: '50%', width: '38px', height: '38px', display: 'flex', alignItems: 'center', justify: 'center', transition: 'all 0.2s var(--spring)'}}>
            <svg viewBox="0 0 24 24" width="20" height="20" stroke="currentColor" strokeWidth="2.5"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.6rem'}}>
          {toolsMenu.map(item => (
            <div
              key={item.path}
              onClick={() => {
                 setMenuOpen(false);
                 navigate(item.path);
              }}
              className="evidence-row"
              style={{
                display: 'flex', alignItems: 'center', gap: '0.85rem',
                padding: '1rem 1.15rem', borderRadius: '16px',
                color: 'var(--text-main)', fontSize: '15px', fontWeight: 700,
                background: 'var(--bg-secondary)', border: '1px solid var(--border-light)',
                cursor: 'pointer', transition: 'all 0.25s var(--spring)'
              }}
            >
              <span style={{ color: 'var(--primary)', width: 28, height: 28, display: 'flex', alignItems: 'center', justify: 'center', background: 'var(--safe-bg)', borderRadius: '10px' }}>{Icons[item.icon]}</span>
              <span style={{flex: 1}}>{item.label}</span>
              {item.enterprise && <span className="verdict-badge verdict-badge--genuine" style={{ fontSize: '10px', padding: '0.2rem 0.6rem' }}>PRO</span>}
            </div>
          ))}
        </div>
      </div>

      <nav className="bottom-nav" id="bottom-navigation">
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            className={({ isActive }) => `bottom-nav__item${isActive ? ' active' : ''}`}
            id={`nav-${item.label.toLowerCase()}`}
          >
            <span className="bottom-nav__icon" style={{fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round'}}>{Icons[item.icon]}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
        {/* More Tab */}
        <div 
          className={`bottom-nav__item ${menuOpen ? 'active' : ''}`} 
          onClick={() => setMenuOpen(!menuOpen)}
          style={{cursor: 'pointer'}}
        >
          <span className="bottom-nav__icon" style={{fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round'}}>{Icons.more}</span>
          <span>More</span>
        </div>
      </nav>
      {menuOpen && <div style={{position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 104}} onClick={() => setMenuOpen(false)} />}
    </>
  );
}
