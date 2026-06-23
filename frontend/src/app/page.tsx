'use client';

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const CORE_API = process.env.NEXT_PUBLIC_CORE_API_URL || 'http://localhost:8000';
const RAG_API = process.env.NEXT_PUBLIC_RAG_API_URL || 'http://localhost:8001';
const SESSION_KEY = 'tenant_portal_session_v1';
const DEMO_TENANT_ID = '00000000-0000-0000-0000-000000000001';

const demoAccounts = [
	{ role: 'Student', username: 'stanford_student', password: 'password123', note: 'Chat and citations' },
	{ role: 'Faculty', username: 'stanford_faculty', password: 'password123', note: 'Chat, sources, schedules' },
	{ role: 'Admin', username: 'stanford_admin', password: 'password123', note: 'Full data and scheduler controls' },
];

type PortalSession = {
	accessToken: string;
	user: {
		id: string;
		username: string;
		email: string;
		tenant_id: string;
		roles: string[];
		is_tenant_admin: boolean;
	};
};

type Citation = { id: number; title: string; source: string; score: number };
type Message = { role: 'user' | 'bot'; text: string; timestamp: number; citations?: Citation[]; insufficient_evidence?: boolean };
type ApiList<T> = { results?: T[] };
type RoleRow = { id: string; name: string; tenant: string };
type UserRow = { id: string; username: string; email: string; roles: string[]; is_tenant_admin: boolean };
type ApiKeyRow = { id: string; name: string; key_prefix: string; roles: string[]; is_active: boolean; created_at: string };
type DocumentRow = { id: string; title: string; source_type: string; source_uri: string; roles: string[]; status: string };
type SourceRow = { id: string; name: string; source_type: string; config: { urls?: string[]; crawl_mode?: string; max_pages?: number }; is_active: boolean };
type ScheduleRow = {
	id: string;
	title: string;
	source: string;
	source_url: string;
	frequency: string;
	next_run_at: string | null;
	last_run_at: string | null;
	last_status: string;
	last_error: string;
	is_active: boolean;
	roles: string[];
	api_key: string;
};
type BasePromptRow = { id: string; name: string; role: string | null; prompt: string; is_active: boolean };
type RunLogRow = { id: string; schedule: string; status: string; details: string; created_at: string };
type EntitlementRow = { id: string; feature: string; limit: number; used: number; source: string };
type InvoiceRow = { id: string; stripe_invoice_id: string; status: string; amount_due_cents: number; amount_paid_cents: number; hosted_invoice_url: string; issued_at: string | null };
type BillingSummary = {
	subscription: null | {
		status: string;
		plan_code: string;
		plan_name: string;
		seats: number;
		seat_limit: number;
		document_quota: number;
		source_quota: number;
		ingestion_runs_per_month: number;
		chat_messages_per_month: number;
		current_period_end: string | null;
	};
	entitlements: EntitlementRow[];
	invoices: InvoiceRow[];
	usage: { usage: Record<string, number>; period_start: string };
};
type WorkspaceData = {
	roles: RoleRow[];
	users: UserRow[];
	apiKeys: ApiKeyRow[];
	documents: DocumentRow[];
	sources: SourceRow[];
	schedules: ScheduleRow[];
	prompts: BasePromptRow[];
	runLogs: RunLogRow[];
	billing: BillingSummary | null;
};

const emptyData: WorkspaceData = {
	roles: [],
	users: [],
	apiKeys: [],
	documents: [],
	sources: [],
	schedules: [],
	prompts: [],
	runLogs: [],
	billing: null,
};

type TabId = 'chat' | 'sources' | 'schedules' | 'data' | 'billing' | 'activity';

const tabCopy: Record<TabId, { label: string; help: string }> = {
	chat: { label: 'Chat', help: 'Ask questions against role-filtered vector data and review citations.' },
	sources: { label: 'Sources', help: 'Review and create URL sources that feed the RAG ingestion pipeline.' },
	schedules: { label: 'Schedules', help: 'Enable, pause, or run source refresh schedules asynchronously through the API.' },
	data: { label: 'Data', help: 'Inspect tenant relations loaded from Django: users, roles, keys, documents, and prompts.' },
	billing: { label: 'Billing', help: 'Review subscription status, entitlements, monthly usage, and invoice mirrors.' },
	activity: { label: 'Activity', help: 'Review ingestion run logs and current operational status.' },
};

function normalizeList<T>(payload: T[] | ApiList<T>): T[] {
	return Array.isArray(payload) ? payload : payload.results || [];
}

function formatDate(value?: string | null): string {
	if (!value) return 'Not set';
	return new Date(value).toLocaleString();
}

export default function TenantPortalPage() {
	const [session, setSession] = useState<PortalSession | null>(null);
	const [authLoading, setAuthLoading] = useState(true);
	const [authError, setAuthError] = useState('');
	const [authMode, setAuthMode] = useState<'manual' | string>('manual');
	const [username, setUsername] = useState('');
	const [password, setPassword] = useState('');

	const [activeTab, setActiveTab] = useState<TabId>('chat');
	const [data, setData] = useState<WorkspaceData>(emptyData);
	const [dataLoading, setDataLoading] = useState(false);
	const [dataStatus, setDataStatus] = useState('Workspace data has not been loaded yet.');

	const [messages, setMessages] = useState<Message[]>([]);
	const [query, setQuery] = useState('');
	const [chatLoading, setChatLoading] = useState(false);
	const [chatError, setChatError] = useState('');
	const [citationError, setCitationError] = useState('');

	const [sourceName, setSourceName] = useState('');
	const [sourceUrl, setSourceUrl] = useState('');
	const [scheduleTitle, setScheduleTitle] = useState('');
	const [scheduleFrequency, setScheduleFrequency] = useState('daily');
	const [createStatus, setCreateStatus] = useState('');
	const [actionStatus, setActionStatus] = useState('');
	const [busy, setBusy] = useState(false);

	const bottomRef = useRef<HTMLDivElement>(null);
	const roles = useMemo(() => session?.user.roles || [], [session?.user.roles]);
	const isAdmin = Boolean(session?.user.is_tenant_admin || roles.includes('Admin'));
	const canIngest = Boolean(isAdmin || roles.includes('Faculty'));
	const visibleTabs = useMemo<TabId[]>(() => {
		const tabs: TabId[] = isAdmin
			? ['chat', 'sources', 'schedules', 'data', 'billing', 'activity']
			: ['chat', 'sources', 'schedules', 'data', 'activity'];
		return canIngest ? tabs : ['chat', 'data'];
	}, [canIngest, isAdmin]);

	const authHeaders = useCallback(() => ({
		Authorization: `Bearer ${session?.accessToken || ''}`,
		'Content-Type': 'application/json',
	}), [session?.accessToken]);

	const apiGet = useCallback(async <T,>(path: string): Promise<T[]> => {
		const res = await fetch(`${CORE_API}${path}`, { headers: authHeaders() });
		if (res.status === 401) throw new Error('Session expired. Please sign in again.');
		if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
		return normalizeList<T>(await res.json());
	}, [authHeaders]);

	const apiFetch = useCallback(async <T,>(path: string): Promise<T> => {
		const res = await fetch(`${CORE_API}${path}`, { headers: authHeaders() });
		if (res.status === 401) throw new Error('Session expired. Please sign in again.');
		if (!res.ok) throw new Error(`GET ${path} failed (${res.status})`);
		return await res.json() as T;
	}, [authHeaders]);

	const loadWorkspaceData = useCallback(async () => {
		if (!session) return;
		setDataLoading(true);
		setDataStatus('Loading tenant data from Django API...');
		try {
			const tenant = session.user.tenant_id;
			const [roleRows, userRows, keyRows, documentRows, sourceRows, scheduleRows, promptRows, logRows, billing] = await Promise.all([
				apiGet<RoleRow>(`/api/roles/?tenant=${tenant}`),
				apiGet<UserRow>(`/api/users/?tenant=${tenant}`),
				apiGet<ApiKeyRow>(`/api/api-keys/?tenant=${tenant}`),
				apiGet<DocumentRow>(`/api/documents/?tenant=${tenant}`),
				apiGet<SourceRow>(`/api/ingestion-sources/?tenant=${tenant}`),
				apiGet<ScheduleRow>(`/api/ingestion-schedules/?tenant=${tenant}`),
				apiGet<BasePromptRow>(`/api/base-prompts/?tenant=${tenant}`),
				apiGet<RunLogRow>(`/api/ingestion-run-logs/?tenant=${tenant}`),
				isAdmin ? apiFetch<BillingSummary>('/api/billing/summary/') : Promise.resolve(null),
			]);
			setData({
				roles: roleRows,
				users: userRows,
				apiKeys: keyRows,
				documents: documentRows,
				sources: sourceRows,
				schedules: scheduleRows,
				prompts: promptRows,
				runLogs: logRows,
				billing,
			});
			setDataStatus(`Loaded ${roleRows.length} roles, ${sourceRows.length} sources, and ${scheduleRows.length} schedules.`);
		} catch (err) {
			setDataStatus(err instanceof Error ? err.message : 'Unable to load workspace data.');
		} finally {
			setDataLoading(false);
		}
	}, [apiFetch, apiGet, isAdmin, session]);

	useEffect(() => {
		bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
	}, [messages, chatLoading]);

	useEffect(() => {
		const bootstrap = async () => {
			try {
				const raw = localStorage.getItem(SESSION_KEY);
				if (!raw) {
					setAuthLoading(false);
					return;
				}
				const parsed = JSON.parse(raw) as PortalSession;
				const verify = await fetch(`${CORE_API}/api/auth/verify-user-token/`, {
					method: 'POST',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ token: parsed.accessToken }),
				});
				if (!verify.ok) {
					localStorage.removeItem(SESSION_KEY);
					setAuthLoading(false);
					return;
				}
				setSession(parsed);
			} catch {
				localStorage.removeItem(SESSION_KEY);
			} finally {
				setAuthLoading(false);
			}
		};
		void bootstrap();
	}, []);

	useEffect(() => {
		if (session) void loadWorkspaceData();
	}, [session, loadWorkspaceData]);

	const logout = () => {
		localStorage.removeItem(SESSION_KEY);
		setSession(null);
		setData(emptyData);
		setMessages([]);
		setAuthError('');
		setChatError('');
		setCitationError('');
	};

	const performLogin = async (credentials: { username: string; password: string; tenantId?: string }, mode = 'manual') => {
		setAuthError('');
		if (!credentials.username.trim() || !credentials.password) {
			setAuthError('Username and password are required.');
			return;
		}
		setAuthMode(mode);
		setAuthLoading(true);
		try {
			const res = await fetch(`${CORE_API}/api/auth/login/`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					username: credentials.username.trim(),
					password: credentials.password,
					tenant_id: credentials.tenantId || DEMO_TENANT_ID,
				}),
			});
			const payload = await res.json();
			if (!res.ok) {
				setAuthError(payload.error || 'Login failed');
				return;
			}
			const nextSession: PortalSession = { accessToken: payload.access_token, user: payload.user };
			localStorage.setItem(SESSION_KEY, JSON.stringify(nextSession));
			setSession(nextSession);
			setMessages([]);
			setActiveTab('chat');
		} catch {
			setAuthError('Unable to connect to auth service.');
		} finally {
			setAuthLoading(false);
			setAuthMode('manual');
		}
	};

	const handleLogin = async (e: FormEvent<HTMLFormElement>) => {
		e.preventDefault();
		await performLogin({ username, password });
	};

	const handleUnauthorized = (message = 'Session expired. Please sign in again.') => {
		localStorage.removeItem(SESSION_KEY);
		setSession(null);
		setMessages([]);
		setAuthError(message);
		setChatError('');
	};

	const buildCitationUrl = (source: string): string | null => {
		if (!source) return null;
		if (/^https?:\/\//i.test(source)) return source;
		if (source.startsWith('/files/')) return `${RAG_API}${source}`;
		if (source.startsWith('file://')) return `${RAG_API}/files/${encodeURIComponent(source.slice('file://'.length))}`;
		const fileName = source.replaceAll('\\', '/').split('/').pop();
		return fileName ? `${RAG_API}/files/${encodeURIComponent(fileName)}` : null;
	};

	const openOrDownloadCitation = async (source: string, download = false) => {
		setCitationError('');
		const url = buildCitationUrl(source);
		if (!url) {
			setCitationError('Citation file is not available.');
			return;
		}
		if (/^https?:\/\//i.test(url) && !url.includes(`${RAG_API}/files/`)) {
			window.open(url, '_blank', 'noopener,noreferrer');
			return;
		}
		if (!session) return;
		try {
			const res = await fetch(download ? `${url}?download=true` : url, {
				headers: { Authorization: `Bearer ${session.accessToken}` },
			});
			if (res.status === 401) {
				handleUnauthorized();
				return;
			}
			if (!res.ok) throw new Error(`Unable to open citation (${res.status})`);
			const objectUrl = URL.createObjectURL(await res.blob());
			if (download) {
				const link = document.createElement('a');
				link.href = objectUrl;
				link.download = source.split('/').pop() || 'citation';
				document.body.appendChild(link);
				link.click();
				document.body.removeChild(link);
			} else {
				window.open(objectUrl, '_blank', 'noopener,noreferrer');
			}
			setTimeout(() => URL.revokeObjectURL(objectUrl), 1200);
		} catch (err) {
			setCitationError(err instanceof Error ? err.message : 'Unable to open citation.');
		}
	};

	const sendChat = async () => {
		if (!session || !query.trim() || chatLoading) return;
		const userText = query.trim();
		const ts = Date.now();
		setMessages(prev => [...prev, { role: 'user', text: userText, timestamp: ts }, { role: 'bot', text: '', timestamp: ts + 1 }]);
		setChatLoading(true);
		setChatError('');
		setQuery('');
		try {
			const res = await fetch(`${RAG_API}/chat/stream`, {
				method: 'POST',
				headers: {
					'Content-Type': 'application/json',
					Authorization: `Bearer ${session.accessToken}`,
					'X-Tenant-ID': session.user.tenant_id,
				},
				body: JSON.stringify({ query: userText }),
			});
			if (res.status === 401) {
				handleUnauthorized('Session expired during chat. Please sign in again.');
				return;
			}
			if (!res.ok || !res.body) throw new Error(`Chat failed (${res.status})`);
			const reader = res.body.getReader();
			const decoder = new TextDecoder();
			let buffer = '';
			let streamed = '';
			while (true) {
				const { done, value } = await reader.read();
				if (done) break;
				buffer += decoder.decode(value, { stream: true });
				const parts = buffer.split('\n\n');
				buffer = parts.pop() || '';
				for (const frame of parts) {
					const line = frame.trim();
					if (!line.startsWith('data: ')) continue;
					const payload = JSON.parse(line.slice(6)) as { chunk: string; done: boolean; citations?: Citation[]; insufficient_evidence?: boolean };
					if (!payload.done) {
						streamed += payload.chunk;
						setMessages(prev => prev.map(m => (m.timestamp === ts + 1 ? { ...m, text: streamed } : m)));
					} else {
						setMessages(prev => prev.map(m => (m.timestamp === ts + 1 ? { ...m, text: streamed, citations: payload.citations || [], insufficient_evidence: payload.insufficient_evidence || false } : m)));
					}
				}
			}
		} catch (err) {
			const msg = err instanceof Error ? err.message : 'Chat error';
			setChatError(msg);
			setMessages(prev => prev.map(m => (m.timestamp === ts + 1 ? { ...m, text: `Error: ${msg}` } : m)));
		} finally {
			setChatLoading(false);
		}
	};

	const createSourceAndSchedule = async () => {
		if (!session || !canIngest) return;
		if (!sourceName.trim() || !sourceUrl.trim() || !scheduleTitle.trim()) {
			setCreateStatus('Source name, URL, and schedule title are required.');
			return;
		}
		setBusy(true);
		setCreateStatus('Creating source and schedule asynchronously...');
		try {
			const sourceRes = await fetch(`${CORE_API}/api/ingestion-sources/`, {
				method: 'POST',
				headers: authHeaders(),
				body: JSON.stringify({
					tenant: session.user.tenant_id,
					name: sourceName.trim(),
					source_type: 'url',
					config: {
						urls: [sourceUrl.trim()],
						crawl_mode: 'section_recursive',
						include_pdfs: true,
						obey_robots_txt: true,
						max_depth: 2,
						max_pages: 50,
						max_pdfs: 25,
						max_pdf_size_mb: 20,
						requests_per_second: 1,
					},
					is_active: true,
				}),
			});
			const sourceData = await sourceRes.json();
			if (!sourceRes.ok) throw new Error(`Source creation failed: ${JSON.stringify(sourceData)}`);
			const roleIds = data.roles.filter(r => roles.includes(r.name)).map(r => r.id);
			const apiKeyId = data.apiKeys[0]?.id;
			if (!apiKeyId) throw new Error('No active API key found for this tenant.');
			const scheduleRes = await fetch(`${CORE_API}/api/ingestion-schedules/`, {
				method: 'POST',
				headers: authHeaders(),
				body: JSON.stringify({
					tenant: session.user.tenant_id,
					source: sourceData.id,
					api_key: apiKeyId,
					title: scheduleTitle.trim(),
					source_url: sourceUrl.trim(),
					roles: roleIds,
					frequency: scheduleFrequency,
					cron_expression: scheduleFrequency === 'cron' ? '*/30 * * * *' : '',
					is_active: true,
				}),
			});
			const scheduleData = await scheduleRes.json();
			if (!scheduleRes.ok) throw new Error(`Schedule creation failed: ${JSON.stringify(scheduleData)}`);
			setCreateStatus(`Created schedule: ${scheduleData.title}`);
			setSourceName('');
			setSourceUrl('');
			setScheduleTitle('');
			await loadWorkspaceData();
		} catch (err) {
			setCreateStatus(err instanceof Error ? err.message : 'Unable to create source/schedule.');
		} finally {
			setBusy(false);
		}
	};

	const patchSchedule = async (schedule: ScheduleRow, changes: Partial<ScheduleRow>) => {
		setActionStatus(`Updating ${schedule.title}...`);
		try {
			const res = await fetch(`${CORE_API}/api/ingestion-schedules/${schedule.id}/`, {
				method: 'PATCH',
				headers: authHeaders(),
				body: JSON.stringify(changes),
			});
			if (!res.ok) throw new Error(`Update failed (${res.status})`);
			setActionStatus(`Updated ${schedule.title}.`);
			await loadWorkspaceData();
		} catch (err) {
			setActionStatus(err instanceof Error ? err.message : 'Unable to update schedule.');
		}
	};

	const runScheduleNow = async (schedule: ScheduleRow) => {
		setActionStatus(`Queueing ${schedule.title}...`);
		try {
			const res = await fetch(`${CORE_API}/api/ingestion-schedules/${schedule.id}/run_now/`, {
				method: 'POST',
				headers: authHeaders(),
			});
			const payload = await res.json();
			if (!res.ok) throw new Error(payload.details || `Run failed (${res.status})`);
			setActionStatus(`Queued ${schedule.title}: ${payload.details}`);
			await loadWorkspaceData();
		} catch (err) {
			setActionStatus(err instanceof Error ? err.message : 'Unable to run schedule.');
		}
	};

	const runDueNow = async () => {
		setActionStatus('Triggering due ingestions...');
		try {
			const res = await fetch(`${CORE_API}/api/ingestion-schedules/run_due/`, {
				method: 'POST',
				headers: { 'X-Scheduler-Token': 'dev-scheduler-token-change-in-prod' },
			});
			const payload = await res.json();
			if (!res.ok) throw new Error(JSON.stringify(payload));
			setActionStatus(`Processed due schedules: ${payload.processed}`);
			await loadWorkspaceData();
		} catch {
			setActionStatus('Unable to trigger due schedules.');
		}
	};

	if (authLoading) return <main className="app-shell grid place-items-center text-slate-500">Loading portal...</main>;

	if (!session) {
		return (
			<main className="app-shell flex items-center justify-center px-4 py-10">
				<section className="login-panel w-full max-w-[440px]">
					<div className="mb-8">
						<p className="eyebrow">RAG SaaS Portal</p>
						<h1 className="mt-2 text-3xl font-semibold text-slate-950">Tenant sign in</h1>
						<p className="mt-2 text-sm leading-6 text-slate-600">Use username/password or pick a seeded demo role. Tenant routing is handled by the app.</p>
					</div>
					<form onSubmit={handleLogin} className="space-y-5">
						<TooltipLabel label="Username" tip="The Django user account for this tenant. Demo users are listed below.">
							<input className="field-input mt-1" value={username} onChange={e => setUsername(e.target.value)} />
						</TooltipLabel>
						<TooltipLabel label="Password" tip="For seeded demo accounts, use password123.">
							<input className="field-input mt-1" type="password" value={password} onChange={e => setPassword(e.target.value)} />
						</TooltipLabel>
						<button type="submit" className="btn-primary w-full" disabled={authLoading}>{authLoading && authMode === 'manual' ? 'Signing in...' : 'Sign in'}</button>
					</form>
					{authError ? <p className="status-error mt-4">{authError}</p> : null}
					<div className="demo-box mt-6">
						<div className="mb-3 flex items-center justify-between gap-3">
							<div>
								<p className="text-sm font-semibold text-slate-950">Demo accounts</p>
								<p className="text-xs text-slate-500">One-click login with role-specific permissions.</p>
							</div>
							<span className="badge muted" title="Seeded tenant: Stanford University Demo">Stanford demo</span>
						</div>
						<div className="space-y-2">
							{demoAccounts.map(account => (
								<button key={account.role} type="button" className="demo-account" disabled={authLoading} title={`Log in as ${account.role}: ${account.note}`} onClick={() => void performLogin({ username: account.username, password: account.password, tenantId: DEMO_TENANT_ID }, account.role)}>
									<span><strong>{account.role}</strong><small>{account.username} - {account.note}</small></span>
									<span className="demo-action">{authLoading && authMode === account.role ? 'Signing in...' : 'Use'}</span>
								</button>
							))}
						</div>
					</div>
				</section>
			</main>
		);
	}

	return (
		<main className="app-frame">
			<header className="top-nav">
				<div className="brand-lockup" title="RAG SaaS tenant operations console">
					<div className="brand-mark">R</div>
					<div>
						<strong>RAG SaaS</strong>
						<span>Knowledge Operations</span>
					</div>
				</div>
				<div className="top-nav-center">
					<span className="workspace-chip" title="Current demo tenant. The UUID is kept internal for normal users.">Stanford University Demo</span>
					<span className="sync-chip" title="Workspace data is loaded asynchronously from Django REST APIs.">{dataLoading ? 'Syncing data...' : 'Data synced'}</span>
				</div>
				<div className="top-actions">
					<button onClick={() => void loadWorkspaceData()} className="btn-secondary" title="Reload all tenant records from the backend API." disabled={dataLoading}>{dataLoading ? 'Refreshing...' : 'Refresh'}</button>
					<button onClick={logout} className="btn-secondary" title="Clear browser session and return to login.">Logout</button>
				</div>
			</header>

			<div className="workspace-layout">
				<aside className="sidebar">
					<div className="sidebar-profile" title="Current signed-in user and roles loaded from Django auth.">
						<div className="avatar">{session.user.username.slice(0, 2).toUpperCase()}</div>
						<div className="min-w-0">
							<p>{session.user.username}</p>
							<span>{isAdmin ? 'Administrator' : canIngest ? 'Faculty workspace' : 'Student workspace'}</span>
						</div>
					</div>

					<nav className="side-nav" aria-label="Workspace sections">
						{visibleTabs.map(tab => (
							<button key={tab} className={`side-nav-item ${activeTab === tab ? 'active' : ''}`} title={tabCopy[tab].help} onClick={() => setActiveTab(tab)}>
								<span className="side-nav-icon" aria-hidden="true">{tabCopy[tab].label.slice(0, 1)}</span>
								<span>
									<strong>{tabCopy[tab].label}</strong>
									<small>{tabCopy[tab].help}</small>
								</span>
							</button>
						))}
					</nav>

					<div className="sidebar-card" title="Role permissions decide which tools are visible.">
						<p className="sidebar-card-label">Access profile</p>
						<div className="mt-2 flex flex-wrap gap-1.5">
							{roles.length ? roles.map(role => <span key={role} className="badge" title={`Role: ${role}`}>{role}</span>) : <span className="badge muted">No role</span>}
						</div>
					</div>

					<div className="sidebar-card" title="Seeded tenant data loaded into relational tables.">
						<p className="sidebar-card-label">Tenant data</p>
						<div className="sidebar-stats">
							<span><strong>{data.sources.length}</strong> sources</span>
							<span><strong>{data.schedules.length}</strong> schedules</span>
							<span><strong>{data.documents.length}</strong> docs</span>
						</div>
					</div>
				</aside>

				<section className="workspace-main">
					<div className="content-toolbar">
						<div>
							<p className="eyebrow">Workspace</p>
							<h1>{tabCopy[activeTab].label}</h1>
							<p>{tabCopy[activeTab].help}</p>
						</div>
						<div className="toolbar-metrics">
							<div title="Documents currently registered in the relational database."><strong>{data.documents.length}</strong><span>Documents</span></div>
							<div title="Ingestion sources available to schedules."><strong>{data.sources.length}</strong><span>Sources</span></div>
							<div title="Schedulers that can refresh sources."><strong>{data.schedules.length}</strong><span>Schedules</span></div>
						</div>
					</div>

					<p className="status-note mt-4" title="All workspace records are fetched asynchronously from the backend API.">{dataStatus}</p>

					<div className="content-panel">
						{activeTab === 'chat' ? renderChat() : null}
						{activeTab === 'sources' ? renderSources() : null}
						{activeTab === 'schedules' ? renderSchedules() : null}
						{activeTab === 'data' ? renderDataBrowser() : null}
						{activeTab === 'billing' ? renderBilling() : null}
						{activeTab === 'activity' ? renderActivity() : null}
					</div>
				</section>
			</div>
		</main>
	);

	function renderChat() {
		return (
			<section className="panel flex min-h-[640px] flex-col">
				<div className="panel-header">
					<div>
						<h2 className="panel-title">Role-aware chat</h2>
						<p className="panel-subtitle">Streams answers from the RAG API using tenant and role claims for this user.</p>
					</div>
					<span className={canIngest ? 'state-pill success' : 'state-pill'} title="Determined by role membership.">{canIngest ? 'Ingestion enabled' : 'Chat only'}</span>
				</div>
				<div className="mt-4 flex flex-wrap gap-2">
					{['What financial aid is available?', 'Summarize undergraduate admissions.', 'What student policies are available?'].map(prompt => (
						<button key={prompt} className="prompt-chip" title="Click to place this prompt into the composer." onClick={() => setQuery(prompt)}>{prompt}</button>
					))}
				</div>
				<div className="chat-scroll mt-4 flex-1">
					{messages.length === 0 ? (
						<div className="empty-state">
							<p className="text-base font-medium text-slate-900">Start with a question</p>
							<p className="mt-1 max-w-md text-sm leading-6 text-slate-600">Answers are grounded in ingested Stanford demo sources and include citations when evidence is found.</p>
						</div>
					) : messages.map(m => (
						<div key={`${m.timestamp}-${m.role}`} className={`message-row ${m.role === 'user' ? 'is-user' : ''}`}>
							<div className={`message-bubble ${m.role === 'user' ? 'user' : m.insufficient_evidence ? 'warning' : 'assistant'}`}>
								<p className="whitespace-pre-wrap">{m.text}</p>
								{m.citations?.length ? (
									<div className="mt-4 space-y-2">
										<p className="text-xs font-semibold uppercase text-slate-500">Citations ({m.citations.length})</p>
										{m.citations.map(c => (
											<div key={`${m.timestamp}-c-${c.id}`} className="citation-item" title="Citation returned by the RAG API.">
												<div className="font-medium text-slate-900">[{c.id}] {c.title || 'Source'}</div>
												<div className="mt-1 break-all text-slate-500">{c.source}</div>
												<div className="mt-2 flex gap-2">
													<button onClick={() => void openOrDownloadCitation(c.source, false)} className="btn-small" title="Open a web source or tenant-scoped uploaded file.">Open</button>
													<button onClick={() => void openOrDownloadCitation(c.source, true)} className="btn-small" title="Download uploaded citation files when available.">Download</button>
												</div>
											</div>
										))}
									</div>
								) : null}
							</div>
						</div>
					))}
					<div ref={bottomRef} />
				</div>
				<div className="composer mt-4">
					<textarea className="field-input min-h-12 flex-1 resize-none" title="Press Enter to send, Shift+Enter for a new line." placeholder="Ask a question about the tenant knowledge base..." value={query} onChange={e => setQuery(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void sendChat(); } }} />
					<button onClick={sendChat} className="btn-primary self-stretch px-5" disabled={chatLoading || !query.trim()} title="Send the question to the streaming RAG endpoint.">{chatLoading ? 'Sending...' : 'Send'}</button>
				</div>
				{chatError ? <p className="status-error mt-3">{chatError}</p> : null}
				{citationError ? <p className="status-error mt-3">{citationError}</p> : null}
			</section>
		);
	}

	function renderSources() {
		return (
			<div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
				<section className="panel">
					<SectionHead title="Knowledge sources" help="Sources describe where the ingestion worker should crawl or import content." />
					<div className="record-grid mt-4">
						{data.sources.map(source => (
							<RecordCard key={source.id} title={source.name} meta={`${source.source_type} - ${source.is_active ? 'active' : 'inactive'}`} help="Configured source used by ingestion schedules.">
								<p className="truncate text-sm text-slate-600">{source.config.urls?.join(', ') || 'No URLs configured'}</p>
								<div className="mt-3 flex flex-wrap gap-2">
									<span className="badge muted">Mode: {source.config.crawl_mode || 'single_page'}</span>
									<span className="badge muted">Max pages: {source.config.max_pages || 'n/a'}</span>
								</div>
							</RecordCard>
						))}
					</div>
				</section>
				<section className="panel">
					<SectionHead title="Create source + schedule" help="This creates an IngestionSource and an IngestionSchedule with async API calls." />
					{canIngest ? (
						<div className="mt-4 space-y-4">
							<TooltipLabel label="Source name" tip="Human-readable label for the URL source."><input className="field-input mt-1" value={sourceName} onChange={e => setSourceName(e.target.value)} /></TooltipLabel>
							<TooltipLabel label="Source URL" tip="Root URL to crawl. Section recursive mode stays under this path."><input className="field-input mt-1" placeholder="https://example.edu/policies" value={sourceUrl} onChange={e => setSourceUrl(e.target.value)} /></TooltipLabel>
							<TooltipLabel label="Schedule title" tip="Name shown in scheduler and logs."><input className="field-input mt-1" value={scheduleTitle} onChange={e => setScheduleTitle(e.target.value)} /></TooltipLabel>
							<TooltipLabel label="Frequency" tip="Controls next_run_at calculation in Django."><select className="field-input mt-1" value={scheduleFrequency} onChange={e => setScheduleFrequency(e.target.value)}><option value="hourly">Hourly</option><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option><option value="cron">Cron</option></select></TooltipLabel>
							<button onClick={createSourceAndSchedule} className="btn-primary w-full" disabled={busy} title="Create both records, then refresh this tab.">{busy ? 'Creating...' : 'Create source and schedule'}</button>
							{createStatus ? <p className="status-note">{createStatus}</p> : null}
						</div>
					) : <div className="notice mt-4">Student role can inspect data but cannot create ingestion sources.</div>}
				</section>
			</div>
		);
	}

	function renderSchedules() {
		return (
			<section className="panel">
				<SectionHead title="Source schedulers" help="Admins can run, pause, or resume ingestion schedules. Faculty can inspect them." />
				<div className="mt-4 flex flex-wrap gap-2">
					<button onClick={runDueNow} className="btn-secondary" disabled={!isAdmin} title="Triggers the protected run_due scheduler endpoint. Admin only.">Run due now</button>
					<button onClick={() => void loadWorkspaceData()} className="btn-secondary" title="Refresh schedules and logs from the API.">Refresh</button>
				</div>
				{actionStatus ? <p className="status-note mt-3">{actionStatus}</p> : null}
				<div className="table-wrap mt-4">
					<table className="data-table">
						<thead><tr><th>Schedule</th><th>Frequency</th><th>Status</th><th>Next run</th><th>Actions</th></tr></thead>
						<tbody>
							{data.schedules.map(schedule => (
								<tr key={schedule.id}>
									<td><strong>{schedule.title}</strong><small>{schedule.source_url || data.sources.find(s => s.id === schedule.source)?.name || 'All source URLs'}</small></td>
									<td>{schedule.frequency}</td>
									<td><span className={schedule.is_active ? 'badge' : 'badge muted'}>{schedule.is_active ? 'active' : 'paused'}</span><span className="ml-2 text-xs text-slate-500">{schedule.last_status || 'no run'}</span></td>
									<td>{formatDate(schedule.next_run_at)}</td>
									<td>
										<div className="flex flex-wrap gap-2">
											<button className="btn-small" disabled={!isAdmin} title="Queue this schedule immediately through Django and Celery." onClick={() => void runScheduleNow(schedule)}>Run</button>
											<button className="btn-small" disabled={!isAdmin} title="Toggle is_active on this schedule with PATCH." onClick={() => void patchSchedule(schedule, { is_active: !schedule.is_active })}>{schedule.is_active ? 'Pause' : 'Resume'}</button>
										</div>
									</td>
								</tr>
							))}
						</tbody>
					</table>
				</div>
			</section>
		);
	}

	function renderDataBrowser() {
		return (
			<div className="space-y-5">
				<div className="grid gap-4 md:grid-cols-4">
					<Metric label="Users" value={data.users.length} help="Django User records assigned to this tenant." />
					<Metric label="Roles" value={data.roles.length} help="Role records used for API key and document authorization." />
					<Metric label="Documents" value={data.documents.length} help="Document metadata records in the relational database." />
					<Metric label="Prompts" value={data.prompts.length} help="Base prompts that shape answers per tenant or role." />
				</div>
				<section className="panel">
					<SectionHead title="Tenant relations" help="Loaded asynchronously from Django REST endpoints. IDs are hidden unless needed for debugging." />
					<div className="split-grid mt-4">
						<DataList title="Users" rows={data.users.map(u => [`${u.username}${u.is_tenant_admin ? ' (admin)' : ''}`, u.email || 'No email'])} />
						<DataList title="API keys" rows={data.apiKeys.map(k => [k.name, `${k.key_prefix}... - ${k.is_active ? 'active' : 'inactive'}`])} />
						<DataList title="Documents" rows={data.documents.map(d => [d.title, `${d.source_type} - ${d.status}`])} />
						<DataList title="Base prompts" rows={data.prompts.map(p => [p.name, p.is_active ? 'active' : 'inactive'])} />
					</div>
				</section>
			</div>
		);
	}

	function renderBilling() {
		const billing = data.billing;
		if (!isAdmin) return <div className="notice">Billing is available to tenant administrators.</div>;
		if (!billing) return <div className="notice">Billing summary is loading or unavailable.</div>;
		const subscription = billing.subscription;
		const usage = billing.usage?.usage || {};
		return (
			<div className="space-y-5">
				<div className="grid gap-4 md:grid-cols-4">
					<Metric label="Plan" value={subscription?.plan_name || 'Not configured'} help="Current Stripe-backed subscription plan." />
					<Metric label="Status" value={subscription?.status || 'missing'} help="Subscription state mirrored from Stripe webhooks." />
					<Metric label="Seats" value={`${subscription?.seats || data.users.length}/${subscription?.seat_limit || 'n/a'}`} help="Current seats against subscription seat limit." />
					<Metric label="Chat usage" value={usage.chat_message || 0} help="Chat messages recorded for the current billing period." />
				</div>
				<section className="panel">
					<SectionHead title="Subscription entitlements" help="Limits are enforced by backend tenant and usage controls." />
					<div className="record-grid mt-4">
						{billing.entitlements.map(entitlement => (
							<RecordCard key={entitlement.id} title={entitlement.feature.replaceAll('_', ' ')} meta={`${entitlement.used} used of ${entitlement.limit}`} help="Entitlement mirrored from the active plan or subscription override.">
								<div className="usage-bar" title={`${entitlement.used} of ${entitlement.limit}`}>
									<span style={{ width: `${Math.min(100, entitlement.limit ? (entitlement.used / entitlement.limit) * 100 : 0)}%` }} />
								</div>
								<p className="mt-2 text-sm text-slate-600">Source: {entitlement.source}</p>
							</RecordCard>
						))}
					</div>
				</section>
				<section className="panel">
					<SectionHead title="Invoices" help="Stripe invoice mirrors keep tenant billing visible inside the app." />
					<div className="table-wrap mt-4">
						<table className="data-table">
							<thead><tr><th>Invoice</th><th>Status</th><th>Due</th><th>Paid</th><th>Issued</th></tr></thead>
							<tbody>
								{billing.invoices.length ? billing.invoices.map(invoice => (
									<tr key={invoice.id}>
										<td><strong>{invoice.stripe_invoice_id}</strong>{invoice.hosted_invoice_url ? <small><a href={invoice.hosted_invoice_url} target="_blank" rel="noreferrer">Open invoice</a></small> : null}</td>
										<td>{invoice.status || 'unknown'}</td>
										<td>${(invoice.amount_due_cents / 100).toFixed(2)}</td>
										<td>${(invoice.amount_paid_cents / 100).toFixed(2)}</td>
										<td>{formatDate(invoice.issued_at)}</td>
									</tr>
								)) : <tr><td colSpan={5}>No invoices have been mirrored yet.</td></tr>}
							</tbody>
						</table>
					</div>
				</section>
			</div>
		);
	}

	function renderActivity() {
		return (
			<section className="panel">
				<SectionHead title="Activity and run logs" help="IngestionRunLog records show scheduler activity and queue results." />
				<div className="log-list mt-4">
					{data.runLogs.length ? data.runLogs.map(log => (
						<div key={log.id} className="log-row" title="Ingestion run log from Django.">
							<span className="badge muted">{log.status}</span>
							<span className="min-w-0 flex-1 truncate text-slate-600">{log.details || 'No details'}</span>
							<span className="text-xs text-slate-400">{formatDate(log.created_at)}</span>
						</div>
					)) : <div className="notice">No run logs yet.</div>}
				</div>
			</section>
		);
	}
}

function TooltipLabel({ label, tip, children }: { label: string; tip: string; children: React.ReactNode }) {
	return <label className="field-label" title={tip}>{label}<span className="help-dot" aria-hidden="true">?</span>{children}</label>;
}

function SectionHead({ title, help }: { title: string; help: string }) {
	return <div className="panel-header"><div><h2 className="panel-title">{title}<span className="help-dot" title={help}>?</span></h2><p className="panel-subtitle">{help}</p></div></div>;
}

function Metric({ label, value, help }: { label: string; value: number | string; help: string }) {
	return <div className="metric" title={help}><span className="metric-label">{label}</span><strong>{value}</strong></div>;
}

function RecordCard({ title, meta, help, children }: { title: string; meta: string; help: string; children: React.ReactNode }) {
	return <article className="record-card" title={help}><div className="flex items-start justify-between gap-3"><div><h3>{title}</h3><p>{meta}</p></div><span className="help-dot">?</span></div>{children}</article>;
}

function DataList({ title, rows }: { title: string; rows: string[][] }) {
	return (
		<div className="data-list">
			<h3>{title}</h3>
			{rows.length ? rows.map(([primary, secondary], index) => <div key={`${title}-${index}`} className="data-list-row"><strong>{primary}</strong><span>{secondary}</span></div>) : <p className="text-sm text-slate-500">No records.</p>}
		</div>
	);
}
