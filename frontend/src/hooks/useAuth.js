import { useState, useEffect, useCallback } from 'react';
import { setToken, clearToken } from '../utils/session';

export function useAuth() {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('pharmatrace_user');
    if (stored) {
      try {
        setUser(JSON.parse(stored));
      } catch {
        localStorage.removeItem('pharmatrace_user'); // corrupt profile: start signed out
      }
    }
    setLoading(false);
  }, []);

  const login = useCallback((userData) => {
    setUser(userData);
    const { token, ...profile } = userData;
    localStorage.setItem('pharmatrace_user', JSON.stringify(profile)); // profile only, never the token
    if (token) setToken(token);
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem('pharmatrace_user');
    clearToken();
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
