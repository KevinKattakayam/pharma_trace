import { useState, useEffect, useCallback } from 'react';
import { storeEncryptedTokenInIndexedDB } from '../utils/cryptoStorage';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('pharmatrace_user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {}
    }
    setLoading(false);
  }, []);

  const login = useCallback((userData) => {
    setUser(userData);
    localStorage.setItem('pharmatrace_user', JSON.stringify(userData));
    if (userData.token) {
      localStorage.setItem('pharmatrace_token', userData.token);
      storeEncryptedTokenInIndexedDB(userData.token);
    }
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem('pharmatrace_user');
    localStorage.removeItem('pharmatrace_token');
  }, []);

  const updatePreferences = useCallback((prefs) => {
    setUser(prev => {
      const updated = { ...prev, preferences: { ...prev?.preferences, ...prefs } };
      localStorage.setItem('pharmatrace_user', JSON.stringify(updated));
      return updated;
    });
  }, []);

  return { user, loading, login, logout, updatePreferences };
}
