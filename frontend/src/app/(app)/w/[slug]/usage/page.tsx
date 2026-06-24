'use client';

import { useWorkspace } from '@/lib/workspace-context';
import { formatDate } from '@/lib/api';

export default function UsagePage() {
  const { data, loading, reload } = useWorkspace();
  const s = data.savings;
  const traces = data.traces;

  const total = traces.length;
  const cited = traces.filter(t => t.citation_count > 0).length;
  const insufficient = traces.filter(t => t.insufficient_evidence).length;
  const avgLatency = total ? Math.round(traces.reduce((a, t) => a + (t.latency_ms || 0), 0) / total) : 0;

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>Usage &amp; Savings</h1>
        <p>Cost and energy transparency — see what you're saving by using the free Groq tier vs GPT-4-class pricing.</p>
      </div>

      {/* Savings callout */}
      {s ? (
        <div className="savings-callout mb-4">
          <div className="flex items-center justify-between gap-4 flex-wrap">
            <div>
              <p className="eyebrow mb-1">Estimated savings vs GPT-4</p>
              <p className="savings-number">${s.est_savings_usd.toFixed(2)}</p>
              <p className="text-sm text-emerald-700 mt-1">
                over the last {s.period_days} days · {s.total_queries} queries · est. {s.est_energy_kwh.toFixed(3)} kWh saved
              </p>
            </div>
            <div className="text-right">
              <p className="text-xs text-emerald-700 font-semibold uppercase tracking-wide">Actual cost</p>
              <p className="text-2xl font-bold text-emerald-900">${s.est_cost_usd.toFixed(2)}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="notice mb-4">
          {loading ? 'Loading savings data…' : 'No usage data yet. Ask a question in Chat to start tracking.'}
        </div>
      )}

      {/* Quality metrics */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4 mb-4">
        <div className="metric">
          <span className="metric-label">Total queries</span>
          <span className="metric-value">{total}</span>
        </div>
        <div className="metric">
          <span className="metric-label">Citation rate</span>
          <span className="metric-value">{total ? `${Math.round((cited / total) * 100)}%` : '—'}</span>
          <span className="metric-delta">{cited} of {total} grounded</span>
        </div>
        <div className="metric">
          <span className="metric-label">Insufficient evidence</span>
          <span className="metric-value">{insufficient}</span>
          <span className="metric-delta" style={{ color: '#dc2626' }}>{total ? `${Math.round((insufficient / total) * 100)}%` : '—'} of queries</span>
        </div>
        <div className="metric">
          <span className="metric-label">Avg latency</span>
          <span className="metric-value">{avgLatency > 0 ? `${avgLatency}ms` : '—'}</span>
        </div>
      </div>

      {/* Savings breakdown */}
      {s && (
        <div className="panel mb-4">
          <div className="panel-header">
            <h2 className="panel-title">Cost comparison</h2>
            <button className="btn-secondary btn-small" onClick={reload}>Refresh</button>
          </div>
          <div className="grid gap-4 sm:grid-cols-3 mt-2">
            <div className="record-card">
              <p className="text-xs text-slate-500 uppercase tracking-wide font-semibold">Actual cost (Groq)</p>
              <p className="text-2xl font-bold text-slate-800 mt-1">${s.est_cost_usd.toFixed(3)}</p>
              <p className="text-xs text-slate-400 mt-1">est. based on {s.total_queries} queries</p>
            </div>
            <div className="record-card">
              <p className="text-xs text-slate-500 uppercase tracking-wide font-semibold">GPT-4-class cost</p>
              <p className="text-2xl font-bold text-slate-400 mt-1 line-through">${(s.est_cost_usd + s.est_savings_usd).toFixed(2)}</p>
              <p className="text-xs text-slate-400 mt-1">est. at $0.03/1K tokens</p>
            </div>
            <div className="record-card" style={{ borderColor: '#86efac' }}>
              <p className="text-xs text-emerald-600 uppercase tracking-wide font-semibold">You saved</p>
              <p className="text-2xl font-bold text-emerald-700 mt-1">${s.est_savings_usd.toFixed(2)}</p>
              <p className="text-xs text-slate-400 mt-1">≈ {s.est_energy_kwh.toFixed(3)} kWh energy</p>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-4">
            * Estimates use transparent assumptions: Groq ≈ $0.0001/1K tokens, GPT-4 ≈ $0.03/1K tokens.
            Actual costs depend on model and token usage.
          </p>
        </div>
      )}

      {/* RAG traces table */}
      <div className="panel">
        <div className="panel-header">
          <h2 className="panel-title">Recent RAG traces</h2>
        </div>
        {traces.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon text-2xl">📊</div>
            <p className="text-sm font-semibold text-slate-700 mt-2">No traces yet</p>
            <p className="text-xs text-slate-400 mt-1">Traces appear after your first Chat query.</p>
          </div>
        ) : (
          <div className="table-wrap mt-2">
            <table className="data-table">
              <thead>
                <tr><th>Query</th><th>Key</th><th>Citations</th><th>Status</th><th>Latency</th><th>Time</th></tr>
              </thead>
              <tbody>
                {traces.map(t => (
                  <tr key={t.id}>
                    <td><strong>{t.query}</strong></td>
                    <td><small>{t.api_key_prefix || 'user'}</small></td>
                    <td>{t.citation_count}</td>
                    <td>
                      <span className={`badge ${t.insufficient_evidence ? 'warning' : t.status === 'success' ? 'success' : 'muted'}`}>
                        {t.insufficient_evidence ? 'insufficient' : t.status}
                      </span>
                    </td>
                    <td>{t.latency_ms}ms</td>
                    <td><small>{formatDate(t.created_at)}</small></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
