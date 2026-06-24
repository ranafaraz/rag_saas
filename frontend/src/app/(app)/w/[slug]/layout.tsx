'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useParams, usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-store';
import { WorkspaceProvider } from '@/lib/workspace-context';
import { CORE_API, IDENTITY_KEY, clearWsCookie } from '@/lib/api';
import type { Workspace } from '@/lib/types';
import { OnboardingChecklist } from '@/components/onboarding-checklist';
import { OnboardingTour } from '@/components/onboarding-tour';

const NAV_ITEMS = [
  { href: 'chat',      icon: '💬', label: 'Chat',        admin: false },
  { href: 'sources',   icon: '📚', label: 'Sources',     admin: false },
  { href: 'schedules', icon: '🔄', label: 'Schedules',   admin: false },
  { href: 'models',    icon: '🤖', label: 'AI Models',   admin: false },
  { href: 'usage',     icon: '📊', label: 'Usage',       admin: false },
  { href: 'members',   icon: '👥', label: 'Members',     admin: true  },
];

export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  const { slug } = useParams<{ slug: string }>();
  const pathname = usePathname();
  const router = useRouter();
  const { session, loading, logout, onSessionExpired } = useAuth();
  const [wsMenuOpen, setWsMenuOpen] = useState(false);
  const [allWorkspaces, setAllWorkspaces] = useState<Workspace[]>([]);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (loading) return;
    if (!session) { router.replace('/login'); return; }
    if (session.workspace.slug !== slug) {
      router.replace(`/w/${session.workspace.slug}/chat`);
    }
  }, [session, loading, slug, router]);

  useEffect(() => {
    if (!session) return;
    const loadWorkspaces = async () => {
      try {
        const res = await fetch(`${CORE_API}/api/auth/workspaces/`, {
          headers: { Authorization: `Bearer ${session.accessToken}` },
        });
        if (res.ok) setAllWorkspaces(await res.json());
      } catch { /* silent */ }
    };
    void loadWorkspaces();
  }, [session]);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setWsMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  const handleLogout = () => { logout(); router.replace('/login'); };

  const switchWorkspace = (ws: Workspace) => {
    setWsMenuOpen(false);
    if (ws.slug === slug) return;
    const identity = sessionStorage.getItem(IDENTITY_KEY);
    if (identity) {
      sessionStorage.setItem('rag_workspaces_v2', JSON.stringify(allWorkspaces));
      router.push('/select-workspace');
    } else {
      router.push('/login');
    }
  };

  if (loading || !session) {
    return <main className="app-shell grid place-items-center"><div className="status-note">Loading…</div></main>;
  }

  const isAdmin = session.user.is_tenant_admin || session.user.roles.includes('Admin');
  const visibleNav = NAV_ITEMS.filter(n => !n.admin || isAdmin);

  return (
    <WorkspaceProvider
      tenantId={session.user.tenant_id}
      token={session.accessToken}
      isAdmin={isAdmin}
    >
      <div className="app-frame">
        {/* Top nav */}
        <header className="top-nav">
          <div className="brand-lockup">
            <div className="brand-mark">R</div>
            <div>
              <strong>RAG SaaS</strong>
              <span>Knowledge Platform</span>
            </div>
          </div>

          <div className="top-nav-center">
            <div className="ws-switcher" ref={menuRef}>
              <button
                className="ws-switcher-btn"
                onClick={() => setWsMenuOpen(o => !o)}
              >
                <span className="ws-avatar" style={{ width: 22, height: 22, fontSize: '0.6rem', borderRadius: 4 }}>
                  {session.workspace.name.slice(0, 2).toUpperCase()}
                </span>
                {session.workspace.name}
                <span>▾</span>
              </button>
              {wsMenuOpen && (
                <div className="ws-switcher-menu">
                  {allWorkspaces.map(ws => (
                    <button
                      key={ws.slug}
                      className={`ws-switcher-item ${ws.slug === slug ? 'active' : ''}`}
                      onClick={() => void switchWorkspace(ws)}
                    >
                      <span style={{
                        background: 'linear-gradient(135deg,#0f766e,#1d4ed8)',
                        borderRadius: 5,
                        color: 'white',
                        display: 'grid',
                        fontSize: '0.6rem',
                        fontWeight: 700,
                        height: 22,
                        placeItems: 'center',
                        width: 22,
                      }}>
                        {ws.name.slice(0, 2).toUpperCase()}
                      </span>
                      {ws.name}
                    </button>
                  ))}
                  <hr style={{ border: 'none', borderTop: '1px solid #e2e8f0', margin: '6px 0' }} />
                  <button
                    className="ws-switcher-item"
                    onClick={() => { setWsMenuOpen(false); router.push('/login'); clearWsCookie(); }}
                  >
                    + Create or join workspace
                  </button>
                </div>
              )}
            </div>
          </div>

          <div className="top-actions">
            <div className="flex items-center gap-2">
              <div className="avatar">{session.user.username.slice(0, 2).toUpperCase()}</div>
              <span className="text-sm text-slate-600 hidden md:block">{session.user.username}</span>
            </div>
            <button className="btn-ghost" onClick={handleLogout}>Sign out</button>
          </div>
        </header>

        {/* Workspace body */}
        <div className="workspace-layout">
          {/* Sidebar */}
          <aside className="sidebar">
            <div className="sidebar-profile">
              <div className="avatar">{session.user.username.slice(0, 2).toUpperCase()}</div>
              <div className="min-w-0">
                <p>{session.user.username}</p>
                <span>{isAdmin ? 'Administrator' : session.workspace.role}</span>
              </div>
            </div>

            <nav className="side-nav" aria-label="Workspace">
              {visibleNav.map(item => {
                const href = `/w/${slug}/${item.href}`;
                const active = pathname === href || pathname.startsWith(`${href}/`);
                return (
                  <Link key={item.href} href={href} className={`side-nav-item ${active ? 'active' : ''}`}>
                    <span className="side-nav-icon">{item.icon}</span>
                    <span className="nav-label">{item.label}</span>
                  </Link>
                );
              })}
            </nav>

            <div className="sidebar-card">
              <p className="sidebar-card-label">Roles</p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {session.user.roles.length
                  ? session.user.roles.map(r => <span key={r} className="badge muted">{r}</span>)
                  : <span className="badge muted">No role</span>}
              </div>
            </div>
            <OnboardingChecklist slug={slug} />
            <OnboardingTour slug={slug} />
          </aside>

          {/* Main content */}
          <main className="workspace-main">{children}</main>
        </div>
      </div>
    </WorkspaceProvider>
  );
}
