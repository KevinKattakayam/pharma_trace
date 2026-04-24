import { useState, useEffect } from 'react';

export function useConnection() {
  const [connectionType, setConnectionType] = useState('4g');
  const [isLowBandwidth, setIsLowBandwidth] = useState(false);
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const conn = navigator.connection || navigator.mozConnection || navigator.webkitConnection;

    function updateConnection() {
      if (conn) {
        setConnectionType(conn.effectiveType || '4g');
        const slow = conn.effectiveType === 'slow-2g' || conn.effectiveType === '2g'
          || (conn.downlink && conn.downlink < 0.5);
        setIsLowBandwidth(slow);
      }
    }

    function handleOnline() { setIsOffline(false); }
    function handleOffline() { setIsOffline(true); }

    updateConnection();
    if (conn) conn.addEventListener('change', updateConnection);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      if (conn) conn.removeEventListener('change', updateConnection);
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { connectionType, isLowBandwidth, isOffline };
}
