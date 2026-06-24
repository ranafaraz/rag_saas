'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-store';
import { useWorkspace } from '@/lib/workspace-context';
import { CORE_API, makeAuthHeaders, formatDate } from '@/lib/api';
import type { ScheduleRow } from '@/lib/types';

export default function SchedulesPage() {
  const { session } = useAuth();
  const { data, loading, reload } = useWorkspace();
  const [actionStatus, setActionStatus] = useState('');

  if (!session) return null;
  const isAdmin = session.user.is_tenant_admin || session.user.roles.includes('Admin');

  const patchSchedule = async (schedule: ScheduleRow, changes: Partial<ScheduleRow>) => {
    setActionStatus(`Updating ${schedule.title}…`);
    try {
      const res = await fetch(`${CORE_API}/api/ingestion-schedules/${schedule.id}/`, {
        method: 'PATCH',
        headers: makeAuthHeaders(session.accessToken),
        body: JSON.stringify(changes),
      });
      if (!res.ok) throw new Error(`Update failed (${res.status})`);
      setActionStatus(`Updated ${schedule.title}.`);
      reload();
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Update failed.');
    }
  };

  const runNow = async (schedule: ScheduleRow) => {
    setActionStatus(`Queueing ${schedule.title}…`);
    try {
      const res = await fetch(`${CORE_API}/api/ingestion-schedules/${schedule.id}/run_now/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload.details || `Run failed (${res.status})`);
      setActionStatus(`Queued: ${payload.details}`);
      reload();
    } catch (err) {
      setActionStatus(err instanceof Error ? err.message : 'Run failed.');
    }
  };

  const runDue = async () => {
    setActionStatus('Triggering due schedules…');
    try {
      const res = await fetch(`${CORE_API}/api/ingestion-schedules/run_due/`, {
        method: 'POST',
        headers: { 'X-Scheduler-Token': 'dev-scheduler-token-change-in-prod' },
      });
      const payload = await res.json();
      if (!res.ok) throw new Error(JSON.stringify(payload));
      setActionStatus(`Processed: ${payload.processed} due schedules.`);
      reload();
    } catch {
      setActionStatus('Unable to trigger due schedules.');
    }
  };

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>Schedules</h1>
        <p>Enable, pause, or run ingestion schedules asynchronously.</p>
      </div>

      <div className="panel">
        <div className="panel-header">
          <div>
            <h2 className="panel-title">Ingestion schedules</h2>
            <p className="panel-subtitle">{data.schedules.length} schedule{data.schedules.length !== 1 ? 's' : ''} configured.</p>
          </div>
          <div className="flex gap-2">
            {isAdmin && (
              <button className="btn-secondary btn-small" onClick={runDue}>Run due</button>
            )}
            <button className="btn-secondary btn-small" onClick={reload} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
        </div>

        {actionStatus && <p className="status-note mb-4">{actionStatus}</p>}

        {data.schedules.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon text-2xl">🔄</div>
            <p className="text-sm font-semibold text-slate-700 mt-2">No schedules yet</p>
            <p className="text-xs text-slate-400 mt-1">Create a source in the Sources tab to generate a schedule.</p>
          </div>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Schedule</th>
                  <th>Frequency</th>
                  <th>Status</th>
                  <th>Next run</th>
                  <th>Last run</th>
                  {isAdmin && <th>Actions</th>}
                </tr>
              </thead>
              <tbody>
                {data.schedules.map(s => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.title}</strong>
                      <small>{s.source_url || data.sources.find(src => src.id === s.source)?.name || '—'}</small>
                    </td>
                    <td>{s.frequency}</td>
                    <td>
                      <span className={`badge ${s.is_active ? 'success' : 'muted'}`}>{s.is_active ? 'active' : 'paused'}</span>
                      {s.last_status && <small className="ml-1 text-slate-400">{s.last_status}</small>}
                    </td>
                    <td><small>{formatDate(s.next_run_at)}</small></td>
                    <td><small>{formatDate(s.last_run_at)}</small></td>
                    {isAdmin && (
                      <td>
                        <div className="flex gap-2">
                          <button className="btn-small" onClick={() => void runNow(s)}>Run</button>
                          <button className="btn-small" onClick={() => void patchSchedule(s, { is_active: !s.is_active })}>
                            {s.is_active ? 'Pause' : 'Resume'}
                          </button>
                        </div>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Activity log */}
      {data.runLogs.length > 0 && (
        <div className="panel">
          <div className="panel-header">
            <h2 className="panel-title">Recent run logs</h2>
          </div>
          <div className="log-list">
            {data.runLogs.map(log => (
              <div key={log.id} className="log-row">
                <span className={`badge ${log.status === 'success' ? 'success' : log.status === 'error' ? 'danger' : 'muted'}`}>
                  {log.status}
                </span>
                <span className="min-w-0 flex-1 truncate text-slate-600 text-sm">{log.details || 'No details'}</span>
                <span className="text-xs text-slate-400">{formatDate(log.created_at)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
