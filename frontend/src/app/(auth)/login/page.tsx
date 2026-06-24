'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-store';
import { CORE_API, IDENTITY_KEY } from '@/lib/api';
import type { Workspace } from '@/lib/types';

const DEMO_ACCOUNTS = [
  {
    label: 'Student',
    username: 'stanford_student',
    password: 'password123',
    email: 'student@example.edu',
    description: 'Admissions, financial aid & academic calendar',
    icon: '🎓',
    color: '#0f766e',
  },
  {
    label: 'Faculty',
    username: 'stanford_faculty',
    password: 'password123',
    email: 'faculty@example.edu',
    description: 'Teaching policy, advising & course admin',
    icon: '📚',
    color: '#1d4ed8',
  },
  {
    label: 'Admin',
    username: 'stanford_admin',
    password: 'password123',
    email: 'admin@example.edu',
    description: 'Source governance, audit & full access',
    icon: '🛡️',
    color: '#7c3aed',
  },
] as const;

export default function LoginPage() {
  const router = useRouter();
  const { setSession, lastError, setLastError } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [demoLoading, setDemoLoading] = useState<string | null>(null);
  const [error, setError] = useState(lastError || '');

  const doLogin = async (username: string, pwd: string) => {
    const res = await fetch(`${CORE_API}/api/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password: pwd }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || data.detail || 'Login failed.');

    const { identity_token, workspaces } = data as {
      identity_token: string;
      workspaces: Workspace[];
    };
    if (!workspaces || workspaces.length === 0)
      throw new Error('No workspaces found for this account.');

    sessionStorage.setItem(IDENTITY_KEY, identity_token);

    if (workspaces.length === 1) {
      await selectWorkspace(identity_token, workspaces[0]);
    } else {
      sessionStorage.setItem('rag_workspaces_v2', JSON.stringify(workspaces));
      router.push('/select-workspace');
    }
  };

  const selectWorkspace = async (identityToken: string, workspace: Workspace) => {
    const res = await fetch(`${CORE_API}/api/auth/workspace/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identity_token: identityToken, workspace_slug: workspace.slug }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'Workspace login failed.');
    setSession({ accessToken: data.access_token, user: data.user, workspace });
    router.replace(`/w/${workspace.slug}/chat`);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    setLastError('');
    if (!email.trim() || !password) {
      setError('Email/username and password are required.');
      return;
    }
    setLoading(true);
    try {
      await doLogin(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to connect to the authentication service.');
    } finally {
      setLoading(false);
    }
  };

  const handleDemoLogin = async (username: string, pwd: string, label: string) => {
    setError('');
    setLastError('');
    setDemoLoading(label);
    try {
      await doLogin(username, pwd);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Demo login failed. Make sure the backend is seeded.');
    } finally {
      setDemoLoading(null);
    }
  };

  const isAnyLoading = loading || demoLoading !== null;

  return (
    <div className="auth-card">
      <div className="auth-logo">R</div>
      <h1 className="auth-title">Welcome back</h1>
      <p className="auth-sub">Sign in to your RAG SaaS workspace.</p>

      {/* ── Demo accounts ─────────────────────────────────────── */}
      <div className="demo-section">
        <p className="demo-section-label">Try a demo account</p>
        <div className="demo-grid">
          {DEMO_ACCOUNTS.map((acc) => (
            <button
              key={acc.label}
              type="button"
              className="demo-btn"
              style={{ '--demo-color': acc.color } as React.CSSProperties}
              disabled={isAnyLoading}
              onClick={() => handleDemoLogin(acc.username, acc.password, acc.label)}
              title={`Sign in as ${acc.email}`}
            >
              <span className="demo-btn-icon">{acc.icon}</span>
              <span className="demo-btn-body">
                <span className="demo-btn-label">
                  {demoLoading === acc.label ? 'Signing in…' : acc.label}
                </span>
                <span className="demo-btn-desc">{acc.description}</span>
              </span>
            </button>
          ))}
        </div>
      </div>

      <div className="auth-or-divider">
        <span>or sign in with your account</span>
      </div>

      <form onSubmit={handleSubmit} className="mt-5 space-y-5">
        <div>
          <label className="field-label" htmlFor="email">Email or username</label>
          <input
            id="email"
            className="field-input"
            type="text"
            autoComplete="username"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@example.com"
            disabled={isAnyLoading}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="password">Password</label>
          <input
            id="password"
            className="field-input"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="••••••••"
            disabled={isAnyLoading}
          />
        </div>

        {error && <p className="status-error">{error}</p>}

        <button type="submit" className="btn-primary w-full" disabled={isAnyLoading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <hr className="auth-divider" />

      <p className="text-center text-sm text-slate-500">
        New to RAG SaaS?{' '}
        <Link href="/signup" className="auth-link">Create an account</Link>
      </p>
    </div>
  );
}
