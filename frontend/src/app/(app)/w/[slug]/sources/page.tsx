'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-store';
import { useWorkspace } from '@/lib/workspace-context';
import { CORE_API, makeAuthHeaders, formatDate } from '@/lib/api';

export default function SourcesPage() {
  const { session } = useAuth();
  const { data, loading, status, reload, tenantId } = useWorkspace();
  const [sourceName, setSourceName] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  const [scheduleTitle, setScheduleTitle] = useState('');
  const [frequency, setFrequency] = useState('daily');
  const [createStatus, setCreateStatus] = useState('');
  const [busy, setBusy] = useState(false);

  if (!session) return null;
  const isAdmin = session.user.is_tenant_admin || session.user.roles.includes('Admin');
  const canIngest = isAdmin || session.user.roles.includes('Faculty');

  const handleCreate = async () => {
    if (!sourceName.trim() || !sourceUrl.trim() || !scheduleTitle.trim()) {
      setCreateStatus('Source name, URL, and schedule title are required.');
      return;
    }
    setBusy(true);
    setCreateStatus('Creating source and schedule…');
    try {
      const srcRes = await fetch(`${CORE_API}/api/ingestion-sources/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
        body: JSON.stringify({
          tenant: tenantId,
          name: sourceName.trim(),
          source_type: 'url',
          config: {
            urls: [sourceUrl.trim()],
            crawl_mode: 'section_recursive',
            include_pdfs: true,
            obey_robots_txt: true,
            max_depth: 2,
            max_pages: 50,
          },
          is_active: true,
        }),
      });
      const srcData = await srcRes.json();
      if (!srcRes.ok) throw new Error(`Source: ${JSON.stringify(srcData)}`);

      const apiKeyId = data.apiKeys[0]?.id;
      if (!apiKeyId) throw new Error('No active API key found for this tenant.');
      const roleIds = data.roles.filter(r => session.user.roles.includes(r.name)).map(r => r.id);

      const schRes = await fetch(`${CORE_API}/api/ingestion-schedules/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
        body: JSON.stringify({
          tenant: tenantId,
          source: srcData.id,
          api_key: apiKeyId,
          title: scheduleTitle.trim(),
          source_url: sourceUrl.trim(),
          roles: roleIds,
          frequency,
          is_active: true,
        }),
      });
      const schData = await schRes.json();
      if (!schRes.ok) throw new Error(`Schedule: ${JSON.stringify(schData)}`);
      setCreateStatus(`Created: ${schData.title}`);
      setSourceName(''); setSourceUrl(''); setScheduleTitle('');
      reload();
    } catch (err) {
      setCreateStatus(err instanceof Error ? err.message : 'Failed to create source.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>Sources</h1>
        <p>Knowledge sources that feed the RAG ingestion pipeline.</p>
      </div>

      <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
        {/* Sources list */}
        <div className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Knowledge sources</h2>
              <p className="panel-subtitle">{status}</p>
            </div>
            <button className="btn-secondary btn-small" onClick={reload} disabled={loading}>
              {loading ? 'Loading…' : 'Refresh'}
            </button>
          </div>
          {data.sources.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon text-2xl">📚</div>
              <p className="text-sm font-semibold text-slate-700 mt-2">No sources yet</p>
              <p className="text-xs text-slate-400 mt-1">Add a URL source to start ingesting knowledge.</p>
            </div>
          ) : (
            <div className="record-grid mt-4">
              {data.sources.map(src => (
                <div key={src.id} className="record-card">
                  <div className="flex items-start justify-between gap-2">
                    <h3>{src.name}</h3>
                    <span className={`badge ${src.is_active ? 'success' : 'muted'}`}>
                      {src.is_active ? 'active' : 'paused'}
                    </span>
                  </div>
                  <p>{src.source_type}</p>
                  <p className="mt-2 text-xs text-slate-500 truncate">{src.config.urls?.join(', ') || '—'}</p>
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    <span className="badge muted">{src.config.crawl_mode || 'single_page'}</span>
                    {src.config.max_pages && <span className="badge muted">max {src.config.max_pages}p</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Create form */}
        {canIngest && (
          <div className="panel">
            <div className="panel-header">
              <div>
                <h2 className="panel-title">Add source</h2>
                <p className="panel-subtitle">Create a URL source + ingestion schedule.</p>
              </div>
            </div>
            <div className="space-y-4">
              <div>
                <label className="field-label">Source name</label>
                <input className="field-input" value={sourceName} onChange={e => setSourceName(e.target.value)} placeholder="Stanford Policies" />
              </div>
              <div>
                <label className="field-label">Root URL</label>
                <input className="field-input" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} placeholder="https://example.edu/policies" />
              </div>
              <div>
                <label className="field-label">Schedule title</label>
                <input className="field-input" value={scheduleTitle} onChange={e => setScheduleTitle(e.target.value)} placeholder="Daily policy refresh" />
              </div>
              <div>
                <label className="field-label">Frequency</label>
                <select className="field-input" value={frequency} onChange={e => setFrequency(e.target.value)}>
                  <option value="hourly">Hourly</option>
                  <option value="daily">Daily</option>
                  <option value="weekly">Weekly</option>
                  <option value="monthly">Monthly</option>
                </select>
              </div>
              <button className="btn-primary w-full" onClick={handleCreate} disabled={busy}>
                {busy ? 'Creating…' : 'Create source + schedule'}
              </button>
              {createStatus && <p className={createStatus.startsWith('Failed') || createStatus.startsWith('Source') ? 'status-error' : 'status-note'}>{createStatus}</p>}
            </div>
          </div>
        )}
        {!canIngest && (
          <div className="panel">
            <p className="notice">Source creation requires Faculty or Admin role.</p>
          </div>
        )}
      </div>
    </div>
  );
}
