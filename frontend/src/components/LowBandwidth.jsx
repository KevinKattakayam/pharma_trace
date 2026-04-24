import React from 'react';
import { useConnection } from '../hooks/useConnection';

export default function LowBandwidth({ children }) {
  const { isLowBandwidth, isOffline, connectionType } = useConnection();

  React.useEffect(() => {
    if (isLowBandwidth) {
      document.documentElement.classList.add('low-bandwidth');
    } else {
      document.documentElement.classList.remove('low-bandwidth');
    }
  }, [isLowBandwidth]);

  return (
    <>
      {isOffline && (
        <div style={{
          position: 'fixed',
          top: 'var(--nav-h)',
          left: 0,
          right: 0,
          background: 'var(--warn-bg)',
          borderBottom: '1px solid rgba(251,191,36,0.2)',
          padding: '0.4rem 1rem',
          textAlign: 'center',
          fontSize: '0.625rem',
          color: 'var(--warn)',
          fontWeight: 700,
          zIndex: 99,
          letterSpacing: '0.08em',
          textTransform: 'uppercase'
        }}>
          Offline Mode — Using cached data
        </div>
      )}
      {isLowBandwidth && !isOffline && (
        <div style={{
          position: 'fixed',
          top: 'var(--nav-h)',
          left: 0,
          right: 0,
          background: 'var(--info-bg)',
          borderBottom: '1px solid rgba(59,130,246,0.2)',
          padding: '0.4rem 1rem',
          textAlign: 'center',
          fontSize: '0.625rem',
          color: 'var(--info)',
          fontWeight: 700,
          zIndex: 99,
          letterSpacing: '0.08em',
          textTransform: 'uppercase'
        }}>
          Low Bandwidth Mode ({connectionType}) — Reduced data usage
        </div>
      )}
      {children}
    </>
  );
}

