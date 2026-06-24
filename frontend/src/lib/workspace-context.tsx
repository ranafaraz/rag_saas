'use client';

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { apiGet, apiFetch } from './api';
import type { WorkspaceData } from './types';
import { emptyWorkspaceData } from './types';

type WorkspaceContextValue = {
  data: WorkspaceData;
  loading: boolean;
  status: string;
  reload: () => void;
  tenantId: string;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({
  children,
  tenantId,
  token,
  isAdmin,
}: {
  children: React.ReactNode;
  tenantId: string;
  token: string;
  isAdmin: boolean;
}) {
  const [data, setData] = useState<WorkspaceData>(emptyWorkspaceData);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState('');

  const load = useCallback(async () => {
    if (!token || !tenantId) return;
    setLoading(true);
    setStatus('Loading workspace data…');
    try {
      const [
        roles, users, apiKeys, documents, sources, schedules,
        prompts, runLogs, jobs, traces, members, aiModels,
        billing, savings,
      ] = await Promise.all([
        apiGet<WorkspaceData['roles'][0]>(`/api/roles/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['users'][0]>(`/api/users/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['apiKeys'][0]>(`/api/api-keys/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['documents'][0]>(`/api/documents/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['sources'][0]>(`/api/ingestion-sources/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['schedules'][0]>(`/api/ingestion-schedules/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['prompts'][0]>(`/api/base-prompts/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['runLogs'][0]>(`/api/ingestion-run-logs/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['jobs'][0]>(`/api/integration-jobs/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['traces'][0]>(`/api/rag-traces/?tenant=${tenantId}`, token),
        apiGet<WorkspaceData['members'][0]>('/api/memberships/', token).catch(() => []),
        apiGet<WorkspaceData['aiModels'][0]>('/api/ai-model-configs/', token).catch(() => []),
        isAdmin
          ? apiFetch<WorkspaceData['billing']>('/api/billing/summary/', token).catch(() => null)
          : Promise.resolve(null),
        apiFetch<WorkspaceData['savings']>('/api/usage/savings/', token).catch(() => null),
      ]);
      setData({
        roles, users, apiKeys, documents, sources, schedules,
        prompts, runLogs, jobs, traces, billing, members, aiModels, savings,
      });
      setStatus(`Loaded ${sources.length} sources, ${schedules.length} schedules, ${documents.length} docs.`);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : 'Failed to load workspace data.');
    } finally {
      setLoading(false);
    }
  }, [token, tenantId, isAdmin]);

  useEffect(() => { void load(); }, [load]);

  return (
    <WorkspaceContext.Provider value={{ data, loading, status, reload: load, tenantId }}>
      {children}
    </WorkspaceContext.Provider>
  );
}

export function useWorkspace() {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) throw new Error('useWorkspace must be used inside WorkspaceProvider');
  return ctx;
}
