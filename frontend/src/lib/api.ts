export const CORE_API = process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000';
export const RAG_API = process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8001';

export const SESSION_KEY = 'rag_session_v2';
export const IDENTITY_KEY = 'rag_identity_v2';
export const WS_COOKIE = 'ws_slug';

function normalizeList<T>(payload: T[] | { results?: T[] }): T[] {
  return Array.isArray(payload) ? payload : payload.results || [];
}

export function makeAuthHeaders(token: string) {
  return {
    Authorization: `Bearer ${token}`,
    'Content-Type': 'application/json',
  };
}

export async function apiGet<T>(path: string, token: string): Promise<T[]> {
  const res = await fetch(`${CORE_API}${path}`, { headers: makeAuthHeaders(token) });
  if (res.status === 401) throw new Error('Session expired. Please sign in again.');
  if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
  return normalizeList<T>(await res.json());
}

export async function apiFetch<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${CORE_API}${path}`, { headers: makeAuthHeaders(token) });
  if (res.status === 401) throw new Error('Session expired. Please sign in again.');
  if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${CORE_API}${path}`, {
    method: 'POST',
    headers: makeAuthHeaders(token),
    body: JSON.stringify(body),
  });
  if (res.status === 401) throw new Error('Session expired. Please sign in again.');
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || data.detail || `POST ${path} failed (${res.status})`);
  return data as T;
}

export async function apiPatch<T>(path: string, token: string, body: unknown): Promise<T> {
  const res = await fetch(`${CORE_API}${path}`, {
    method: 'PATCH',
    headers: makeAuthHeaders(token),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${path} failed (${res.status})`);
  return res.json() as Promise<T>;
}

export async function apiDelete(path: string, token: string): Promise<void> {
  const res = await fetch(`${CORE_API}${path}`, {
    method: 'DELETE',
    headers: makeAuthHeaders(token),
  });
  if (!res.ok) throw new Error(`DELETE ${path} failed (${res.status})`);
}

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleString();
}

export function buildCitationUrl(source: string, ragApi: string): string | null {
  if (!source) return null;
  if (/^https?:\/\//i.test(source)) return source;
  if (source.startsWith('/files/')) return `${ragApi}${source}`;
  if (source.startsWith('file://')) return `${ragApi}/files/${encodeURIComponent(source.slice('file://'.length))}`;
  const fileName = source.replaceAll('\\', '/').split('/').pop();
  return fileName ? `${ragApi}/files/${encodeURIComponent(fileName)}` : null;
}

export function setWsCookie(slug: string) {
  if (typeof document === 'undefined') return;
  document.cookie = `${WS_COOKIE}=${slug}; path=/; SameSite=Lax`;
}

export function clearWsCookie() {
  if (typeof document === 'undefined') return;
  document.cookie = `${WS_COOKIE}=; path=/; max-age=0`;
}
