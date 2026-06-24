'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { CORE_API } from '@/lib/api';

export default function SignupPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [workspaceName, setWorkspaceName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError('');
    if (!username.trim() || !email.trim() || !password || !workspaceName.trim()) {
      setError('All fields are required.');
      return;
    }
    setLoading(true);
    try {
      const res = await fetch(`${CORE_API}/api/auth/signup/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: username.trim(),
          email: email.trim(),
          password,
          workspace_name: workspaceName.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        const msg = data.error || data.detail ||
          Object.values(data).flat().join(' ') ||
          'Signup failed.';
        setError(String(msg));
        return;
      }
      setDone(true);
    } catch {
      setError('Unable to connect to the server.');
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="auth-card text-center">
        <div className="auth-logo" style={{ margin: '0 auto 20px' }}>✓</div>
        <h1 className="auth-title">Check your email</h1>
        <p className="auth-sub mt-3">
          We sent a verification link to <strong>{email}</strong>. Click it to activate your account and access your workspace.
        </p>
        <button
          className="btn-secondary mt-6 w-full"
          onClick={() => router.push('/login')}
        >
          Back to sign in
        </button>
      </div>
    );
  }

  return (
    <div className="auth-card">
      <div className="auth-logo">R</div>
      <h1 className="auth-title">Create your account</h1>
      <p className="auth-sub">Set up your workspace in under 2 minutes.</p>

      <form onSubmit={handleSubmit} className="mt-8 space-y-4">
        <div>
          <label className="field-label" htmlFor="username">Username</label>
          <input
            id="username"
            className="field-input"
            autoComplete="username"
            value={username}
            onChange={e => setUsername(e.target.value)}
            placeholder="jsmith"
            disabled={loading}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="email">Work email</label>
          <input
            id="email"
            className="field-input"
            type="email"
            autoComplete="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            placeholder="you@company.com"
            disabled={loading}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="password">Password</label>
          <input
            id="password"
            className="field-input"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="8+ characters"
            disabled={loading}
          />
        </div>
        <div>
          <label className="field-label" htmlFor="ws">Workspace name</label>
          <input
            id="ws"
            className="field-input"
            value={workspaceName}
            onChange={e => setWorkspaceName(e.target.value)}
            placeholder="Acme Inc."
            disabled={loading}
          />
          <p className="text-xs text-slate-400 mt-1">Your team's shared knowledge space.</p>
        </div>

        {error && <p className="status-error">{error}</p>}

        <button type="submit" className="btn-primary w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <hr className="auth-divider" />

      <p className="text-center text-sm text-slate-500">
        Already have an account?{' '}
        <Link href="/login" className="auth-link">Sign in</Link>
      </p>
    </div>
  );
}
