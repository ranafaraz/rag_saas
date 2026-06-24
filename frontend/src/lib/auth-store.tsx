'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { CORE_API, SESSION_KEY, clearWsCookie, setWsCookie } from './api';
import type { PortalSession, Workspace } from './types';

type AuthContextValue = {
  session: PortalSession | null;
  loading: boolean;
  setSession: (s: PortalSession) => void;
  logout: () => void;
  onSessionExpired: (msg?: string) => void;
  lastError: string;
  setLastError: (e: string) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSessionState] = useState<PortalSession | null>(null);
  const [loading, setLoading] = useState(true);
  const [lastError, setLastError] = useState('');

  const persistSession = useCallback((s: PortalSession) => {
    localStorage.setItem(SESSION_KEY, JSON.stringify(s));
    setWsCookie(s.workspace.slug);
    setSessionState(s);
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    clearWsCookie();
    setSessionState(null);
  }, []);

  const onSessionExpired = useCallback((msg = 'Session expired. Please sign in again.') => {
    logout();
    setLastError(msg);
  }, [logout]);

  useEffect(() => {
    const bootstrap = async () => {
      try {
        const raw = localStorage.getItem(SESSION_KEY);
        if (!raw) return;
        const parsed = JSON.parse(raw) as PortalSession;
        const verify = await fetch(`${CORE_API}/api/auth/verify-user-token/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: parsed.accessToken }),
        });
        if (!verify.ok) {
          localStorage.removeItem(SESSION_KEY);
          clearWsCookie();
          return;
        }
        setWsCookie(parsed.workspace.slug);
        setSessionState(parsed);
      } catch {
        localStorage.removeItem(SESSION_KEY);
        clearWsCookie();
      } finally {
        setLoading(false);
      }
    };
    void bootstrap();
  }, []);

  return (
    <AuthContext.Provider value={{ session, loading, setSession: persistSession, logout, onSessionExpired, lastError, setLastError }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}

export function useRequireAuth(): PortalSession {
  const { session } = useAuth();
  if (!session) throw new Error('No session');
  return session;
}

export type { Workspace };
