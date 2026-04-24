import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';

const Icons = {
  home: <svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>,
  scan: <svg viewBox="0 0 24 24"><path d="M3 7V5a2 2 0 012-2h2"/><path d="M17 3h2a2 2 0 012 2v2"/><path d="M21 17v2a2 2 0 01-2 2h-2"/><path d="M7 21H5a2 2 0 01-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/></svg>,
  interact: <svg viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>,
  map: <svg viewBox="0 0 24 24"><polygon points="1 6 1 22 8 18 16 22 23 18 23 2 16 6 8 2 1 6"/><line x1="8" y1="2" x2="8" y2="18"/><line x1="16" y1="6" x2="16" y2="22"/></svg>,
  dashboard: <svg viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
  batch: <svg viewBox="0 0 24 24"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/></svg>,
  report: <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><line x1="9" y1="15" x2="15" y2="15"/></svg>,
  menu: <svg viewBox="0 0 24 24"><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="18" x2="21" y2="18"/></svg>,
  close: <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>,
  dosage: <svg viewBox="0 0 24 24"><path d="M12 22c5.523 0 10-4.477 10-10S17.523 2 12 2 2 6.477 2 12s4.477 10 10 10z"/><path d="M12 6v6l4 2"/></svg>,
  generic: <svg viewBox="0 0 24 24"><path d="M19.5 12.572l-7.5 7.428-7.5-7.428A5 5 0 1112 6.006a5 5 0 017.5 6.572"/></svg>,
  sideeffect: <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>,
  api: <svg viewBox="0 0 24 24"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>,
  logo: <svg viewBox="0 0 28 28"><defs><linearGradient id="lg" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stopColor="#7c5cfc"/><stop offset="100%" stopColor="#3b82f6"/></linearGradient></defs><rect width="28" height="28" rx="7" fill="#111627"/><path d="M14 5v18M8 11h12M7 14.5h14" stroke="url(#lg)" strokeWidth="2.2" strokeLinecap="round"/><circle cx="14" cy="7" r="1.5" fill="#7c5cfc"/></svg>,
};

const navItems = [
  { path: '/', icon: 'home', label: 'Home' },
  { path: '/scan', icon: 'scan', label: 'Scan' },
  { path: '/interactions', icon: 'interact', label: 'Check' },
  { path: '/map', icon: 'map', label: 'Map' },
  { path: '/dashboard', icon: 'dashboard', label: 'Care' }
];

const toolsMenu = [
  { path: '/scan', icon: 'scan', label: 'Verify Medicine' },
  { path: '/interactions', icon: 'interact', label: 'Drug Interactions' },
  { path: '/side-effects', icon: 'sideeffect', label: 'Side Effect Explainer' },
  { path: '/dosage', icon: 'dosage', label: 'Dosage Personalizer' },
  { path: '/generics', icon: 'generic', label: 'Generic Finder' },
  { path: '/batch', icon: 'batch', label: 'Batch Verification' },
  { path: '/map', icon: 'map', label: 'Outbreak Map' },
  { path: '/report', icon: 'report', label: 'Report Medicine' },
  { path: '/dashboard', icon: 'dashboard', label: 'Caregiver Mode' },
  { path: '/api-docs', icon: 'api', label: 'API & SDK' },
];

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <>
      <nav className="navbar" id="main-navbar">
        <div className="navbar__inner">
          <NavLink to="/" className="navbar__logo">
            {Icons.logo}
            <span>Pharma<span className="navbar__logo-accent">Trace</span></span>
          </NavLink>
          <div className="navbar__actions">
            <NavLink to="/batch" className="btn btn--ghost" id="btn-batch-mode">
              <span className="bottom-nav__icon">{Icons.batch}</span> Batch
            </NavLink>
            <button className="btn btn--ghost" onClick={() => setMenuOpen(!menuOpen)} id="btn-tools-menu"
              aria-label="Tools menu">
              <span className="bottom-nav__icon">{menuOpen ? Icons.close : Icons.menu}</span> Tools
            </button>
          </div>
        </div>
      </nav>

      {/* Full Tools Menu */}
      {menuOpen && (
        <div style={{
          position: 'fixed', top: 'var(--nav-h)', left: 0, right: 0, bottom: 0,
          background: 'rgba(12,15,26,0.95)', backdropFilter: 'blur(24px)',
          zIndex: 99, overflowY: 'auto', padding: '1.5rem'
        }}>
          <div style={{ maxWidth: 480, margin: '0 auto' }}>
            <div style={{
              fontSize: '0.625rem', fontWeight: 700, color: 'var(--text-3)',
              textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: '0.75rem'
            }}>All Tools</div>
            {toolsMenu.map(item => (
              <NavLink
                key={item.path}
                to={item.path}
                onClick={() => setMenuOpen(false)}
                style={{
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                  padding: '0.85rem 1rem', borderRadius: '12px',
                  color: 'var(--text-1)', fontSize: '0.875rem', fontWeight: 500,
                  marginBottom: '0.25rem', transition: 'background 0.15s',
                  textDecoration: 'none', border: '1px solid transparent'
                }}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent-dim)'; e.currentTarget.style.borderColor = 'var(--border-2)'; }}
                onMouseLeave={e => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = 'transparent'; }}
              >
                <span className="bottom-nav__icon" style={{ color: 'var(--accent)' }}>{Icons[item.icon]}</span>
                {item.label}
              </NavLink>
            ))}
          </div>
        </div>
      )}

      <nav className="bottom-nav" id="bottom-navigation">
        {navItems.map(item => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) => `bottom-nav__item${isActive ? ' active' : ''}`}
            id={`nav-${item.label.toLowerCase()}`}
          >
            <span className="bottom-nav__icon">{Icons[item.icon]}</span>
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>
    </>
  );
}
