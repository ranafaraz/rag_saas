'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-store';
import { useWorkspace } from '@/lib/workspace-context';
import { CORE_API, makeAuthHeaders } from '@/lib/api';
import type { AIModelConfig } from '@/lib/types';

const PROVIDERS = [
  { value: 'groq',       label: 'Groq (free tier)',    note: 'Llama 3.3 70B — fastest free hosted LLM.' },
  { value: 'openai',     label: 'OpenAI',               note: 'GPT-4o, GPT-4 Turbo, GPT-3.5.' },
  { value: 'anthropic',  label: 'Anthropic (Claude)',   note: 'Claude 3.5 Sonnet, Opus, Haiku.' },
  { value: 'deepseek',   label: 'DeepSeek',             note: 'DeepSeek-V3 — cost-efficient reasoning.' },
  { value: 'ollama',     label: 'Ollama (self-hosted)', note: 'Local models via Ollama runtime.' },
  { value: 'custom',     label: 'Custom / vLLM',        note: 'Any OpenAI-compatible endpoint.' },
];

export default function ModelsPage() {
  const { session } = useAuth();
  const { data, reload } = useWorkspace();
  const [formOpen, setFormOpen] = useState(false);
  const [provider, setProvider] = useState('groq');
  const [name, setName] = useState('');
  const [modelName, setModelName] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [status, setStatus] = useState('');
  const [saving, setSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  if (!session) return null;
  const isAdmin = session.user.is_tenant_admin || session.user.roles.includes('Admin');

  const handleSave = async () => {
    if (!name.trim() || !provider) { setStatus('Name and provider are required.'); return; }
    setSaving(true); setStatus('Saving…');
    try {
      const res = await fetch(`${CORE_API}/api/ai-model-configs/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
        body: JSON.stringify({ name: name.trim(), provider, model_name: modelName.trim(), base_url: baseUrl.trim() || undefined, api_key: apiKey || undefined }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || data.detail || 'Save failed.');
      setStatus('Saved successfully.');
      setFormOpen(false); setName(''); setModelName(''); setBaseUrl(''); setApiKey(''); setProvider('groq');
      reload();
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Save failed.');
    } finally {
      setSaving(false);
    }
  };

  const setDefault = async (id: string) => {
    try {
      await fetch(`${CORE_API}/api/ai-model-configs/${id}/set_default/`, {
        method: 'POST',
        headers: makeAuthHeaders(session.accessToken),
      });
      reload();
    } catch { /* silent */ }
  };

  const deleteModel = async (id: string) => {
    setDeletingId(id);
    try {
      await fetch(`${CORE_API}/api/ai-model-configs/${id}/`, {
        method: 'DELETE',
        headers: makeAuthHeaders(session.accessToken),
      });
      reload();
    } catch { /* silent */ } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="content-panel">
      <div className="page-header">
        <h1>AI Models</h1>
        <p>Configure which LLM powers your workspace. Default is Groq free tier — no API key needed.</p>
      </div>

      {/* Default callout */}
      <div className="savings-callout mb-4">
        <p className="text-sm font-semibold text-emerald-800 mb-1">🆓 Free tier active by default</p>
        <p className="text-sm text-emerald-700">
          Groq's hosted Llama 3.3 70B is used when no tenant key is configured. It's fast, powerful, and costs you nothing.
          Paste your own API key below to switch to OpenAI, Claude, or DeepSeek — billed to you directly.
        </p>
      </div>

      {/* Model cards */}
      {data.aiModels.length === 0 ? (
        <div className="panel">
          <div className="empty-state">
            <div className="empty-state-icon text-2xl">🤖</div>
            <p className="text-sm font-semibold text-slate-700 mt-2">Using Groq free tier</p>
            <p className="text-xs text-slate-400 mt-1 max-w-xs">
              No custom model configured. Add one below to switch providers or enable BYOK.
            </p>
          </div>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 mb-4">
          {data.aiModels.map((m: AIModelConfig) => (
            <div key={m.id} className={`model-card ${m.is_default ? 'is-default' : ''}`}>
              <div className="flex items-start justify-between gap-2 mb-2">
                <div>
                  <h3 className="font-semibold text-slate-800">{m.name}</h3>
                  <p className="text-xs text-slate-500 mt-0.5">{m.provider} · {m.model_name || '—'}</p>
                </div>
                {m.is_default && <span className="badge success">Default</span>}
              </div>
              {m.api_key_hint && (
                <p className="text-xs text-slate-400 mt-1">Key: {m.api_key_hint}</p>
              )}
              {isAdmin && (
                <div className="flex gap-2 mt-3">
                  {!m.is_default && (
                    <button className="btn-small" onClick={() => void setDefault(m.id)}>Set default</button>
                  )}
                  <button
                    className="btn-small btn-danger"
                    disabled={deletingId === m.id}
                    onClick={() => void deleteModel(m.id)}
                  >
                    {deletingId === m.id ? '…' : 'Remove'}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add model form */}
      {isAdmin && (
        <div className="panel">
          <div className="panel-header">
            <div>
              <h2 className="panel-title">Add AI model (BYOK)</h2>
              <p className="panel-subtitle">Paste your own API key. Keys are encrypted at rest and never returned.</p>
            </div>
            <button className="btn-secondary btn-small" onClick={() => setFormOpen(o => !o)}>
              {formOpen ? 'Cancel' : '+ Add model'}
            </button>
          </div>

          {formOpen && (
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <label className="field-label">Display name</label>
                <input className="field-input" value={name} onChange={e => setName(e.target.value)} placeholder="My OpenAI key" />
              </div>
              <div>
                <label className="field-label">Provider</label>
                <select className="field-input" value={provider} onChange={e => setProvider(e.target.value)}>
                  {PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
                <p className="text-xs text-slate-400 mt-1">{PROVIDERS.find(p => p.value === provider)?.note}</p>
              </div>
              <div>
                <label className="field-label">Model name <span className="text-slate-400">(optional)</span></label>
                <input className="field-input" value={modelName} onChange={e => setModelName(e.target.value)} placeholder="gpt-4o" />
              </div>
              <div>
                <label className="field-label">Base URL <span className="text-slate-400">(optional override)</span></label>
                <input className="field-input" value={baseUrl} onChange={e => setBaseUrl(e.target.value)} placeholder="https://api.openai.com/v1" />
              </div>
              <div className="sm:col-span-2">
                <label className="field-label">API key</label>
                <input
                  className="field-input"
                  type="password"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder="sk-… or gsk_… — stored encrypted, never returned"
                />
              </div>
              <div className="sm:col-span-2 flex items-center gap-3">
                <button className="btn-primary" onClick={handleSave} disabled={saving}>
                  {saving ? 'Saving…' : 'Save model'}
                </button>
                {status && <p className={status.startsWith('Saved') ? 'status-note' : 'status-error'}>{status}</p>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
