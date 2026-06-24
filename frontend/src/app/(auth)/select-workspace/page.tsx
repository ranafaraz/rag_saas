'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-store';
import { CORE_API, IDENTITY_KEY } from '@/lib/api';
import type { Workspace } from '@/lib/types';

export default function SelectWorkspacePage() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [selecting, setSelecting] = useState<string | null>(null);

  useEffect(() => {
    const identityToken = sessionStorage.getItem(IDENTITY_KEY);
    const wsRaw = sessionStorage.getItem('rag_workspaces_v2');
    if (!identityToken || !wsRaw) {
      router.replace('/login');
      return;
    }
    setWorkspaces(JSON.parse(wsRaw) as Workspace[]);
  }, [router]);

  const pick = async (ws: Workspace) => {
    const identityToken = sessionStorage.getItem(IDENTITY_KEY);
    if (!identityToken) { router.replace('/login'); return; }
    setSelecting(ws.slug);
    setError('');
    setLoading(true);
    try {
      const res = await fetch(`${CORE_API}/api/auth/workspace/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${identityToken}`,
        },
        body: JSON.stringify({ workspace_slug: ws.slug }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Workspace login failed.');
      sessionStorage.removeItem(IDENTITY_KEY);
      sessionStorage.removeItem('rag_workspaces_v2');
      setSession({ accessToken: data.access_token, user: data.user, workspace: ws });
      router.replace(`/w/${ws.slug}/chat`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to enter workspace.');
    } finally {
      setLoading(false);
      setSelecting(null);
    }
  };

  return (
    <div className="auth-card">
      <div className="auth-logo">L</div>
      <h1 className="auth-title">Choose a workspace</h1>
      <p className="auth-sub">Select the workspace you want to sign in to.</p>

      <div className="mt-6 space-y-3">
        {workspaces.map(ws => (
          <button
            key={ws.slug}
            className="ws-card"
            disabled={loading}
            onClick={() => void pick(ws)}
          >
            <div className="ws-avatar">
              {ws.name.slice(0, 2).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0 text-left">
              <p className="ws-name">{ws.name}</p>
              <p className="ws-role">{ws.role} · {ws.slug}</p>
            </div>
            {selecting === ws.slug && (
              <span className="text-xs text-slate-400">Entering…</span>
            )}
          </button>
        ))}
      </div>

      {error && <p className="status-error mt-4">{error}</p>}

      <hr className="auth-divider" />
      <p className="text-center text-sm text-slate-500">
        <button className="auth-link" onClick={() => router.push('/login')}>
          ← Back to sign in
        </button>
      </p>
    </div>
  );
}
