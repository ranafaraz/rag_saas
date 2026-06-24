'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-store';
import { useWorkspace } from '@/lib/workspace-context';
import { CORE_API, makeAuthHeaders, formatDate } from '@/lib/api';

export default function MembersPage() {
  const { session } = useAuth();
  const { data, reload } = useWorkspace();
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('member');
  const [inviteStatus, setInviteStatus] = useState('');
  const [busy, setBusy] = useState(false);

  if (!session) return null;
  const isAdmin = session.user.is_tenant_admin || session.user.roles.includes('Admin');

  const invite = async () => {
    if (!inviteEmail.trim()) { setInviteStatus('Email is required.'); return; }
    setBusy(true); setInviteStatus('Sending invite…');
    try {
      const res = await fetch(`${CORE_API}/api/auth/invitations/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
        body: JSON.stringify({ email: inviteEmail.trim(), role: inviteRole }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || d.detail || 'Invite failed.');
      setInviteStatus(`Invite sent to ${inviteEmail}.`);
      setInviteEmail('');
      reload();
    } catch (err) {
      setInviteStatus(err instanceof Error ? err.message : 'Invite failed.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>Members</h1>
        <p>Manage workspace members and invitations.</p>
      </div>

      {/* Members list */}
      <div className="panel mb-4">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Workspace members</h2>
            <p className="panel-subtitle">{data.users.length} member{data.users.length !== 1 ? 's' : ''}</p>
          </div>
          <button className="btn-secondary btn-small" onClick={reload}>Refresh</button>
        </div>
        {data.users.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon text-2xl">👥</div>
            <p className="text-sm font-semibold text-slate-700 mt-2">No members yet</p>
          </div>
        ) : (
          <div className="table-wrap mt-2">
            <table className="data-table">
              <thead>
                <tr><th>User</th><th>Email</th><th>Roles</th><th>Admin</th></tr>
              </thead>
              <tbody>
                {data.users.map(u => (
                  <tr key={u.id}>
                    <td>
                      <div className="flex items-center gap-2">
                        <div className="avatar" style={{ width: 28, height: 28, fontSize: '0.7rem', flexShrink: 0 }}>
                          {u.username.slice(0, 2).toUpperCase()}
                        </div>
                        <strong>{u.username}</strong>
                      </div>
                    </td>
                    <td><small>{u.email || '—'}</small></td>
                    <td>
                      <div className="flex flex-wrap gap-1">
                        {u.roles.length ? u.roles.map(r => <span key={r} className="badge muted">{r}</span>) : <span className="badge muted">—</span>}
                      </div>
                    </td>
                    <td>{u.is_tenant_admin ? <span className="badge success">Admin</span> : <span className="badge muted">No</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Invite */}
      {isAdmin && (
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Invite member</h2>
          </div>
          <div className="grid gap-4 sm:grid-cols-[1fr_160px_auto] mt-2">
            <div>
              <label className="field-label">Email address</label>
              <input
                className="field-input"
                type="email"
                value={inviteEmail}
                onChange={e => setInviteEmail(e.target.value)}
                placeholder="colleague@company.com"
              />
            </div>
            <div>
              <label className="field-label">Role</label>
              <select className="field-input" value={inviteRole} onChange={e => setInviteRole(e.target.value)}>
                <option value="member">Member</option>
                <option value="admin">Admin</option>
              </select>
            </div>
            <div className="flex items-end">
              <button className="btn-primary" onClick={invite} disabled={busy}>
                {busy ? 'Sending…' : 'Send invite'}
              </button>
            </div>
          </div>
          {inviteStatus && (
            <p className={`mt-3 ${inviteStatus.startsWith('Invite sent') ? 'status-note' : 'status-error'}`}>
              {inviteStatus}
            </p>
          )}
        </div>
      )}
      {!isAdmin && (
        <div className="notice">Only administrators can invite new members.</div>
      )}
    </div>
  );
}
