export type Workspace = {
  slug: string;
  name: string;
  role: string;
  is_admin: boolean;
};

export type SessionUser = {
  id: string;
  username: string;
  email: string;
  tenant_id: string;
  roles: string[];
  is_tenant_admin: boolean;
};

export type PortalSession = {
  accessToken: string;
  user: SessionUser;
  workspace: Workspace;
};

export type Citation = { id: number; title: string; source: string; score: number };
export type Message = {
  role: 'user' | 'bot';
  text: string;
  timestamp: number;
  citations?: Citation[];
  insufficient_evidence?: boolean;
};

export type ApiList<T> = { results?: T[] };
export type RoleRow = { id: string; name: string; tenant: string };
export type UserRow = { id: string; username: string; email: string; roles: string[]; is_tenant_admin: boolean };
export type ApiKeyRow = {
  id: string;
  name: string;
  key_prefix: string;
  roles: string[];
  scopes?: string[];
  rate_limit_per_minute?: number;
  last_used_at?: string | null;
  is_active: boolean;
  created_at: string;
};
export type DocumentRow = {
  id: string;
  title: string;
  source_type: string;
  source_uri: string;
  roles: string[];
  status: string;
};
export type SourceRow = {
  id: string;
  name: string;
  source_type: string;
  config: { urls?: string[]; crawl_mode?: string; max_pages?: number };
  is_active: boolean;
};
export type ScheduleRow = {
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
export type AIModelConfig = {
  id: string;
  name: string;
  provider: string;
  model_name: string;
  base_url?: string;
  api_key_hint?: string;
  is_default: boolean;
  is_active: boolean;
  created_at: string;
};
export type SavingsData = {
  total_queries: number;
  grounded_rate: number;
  refusal_rate: number;
  avg_latency_ms: number;
  est_cost_usd: number;
  est_savings_usd: number;
  est_energy_kwh: number;
  period_days: number;
};
export type MemberRow = {
  id: string;
  user: { id: string; username: string; email: string };
  role: string;
  status: string;
  joined_at: string;
};
export type BasePromptRow = { id: string; name: string; role: string | null; prompt: string; is_active: boolean };
export type RunLogRow = { id: string; schedule: string; status: string; details: string; created_at: string };
export type IntegrationJobRow = {
  id: string;
  job_type: string;
  status: string;
  external_task_id: string;
  error: string;
  created_at: string;
};
export type RAGTraceRow = {
  id: string;
  api_key_prefix: string;
  query: string;
  citation_count: number;
  insufficient_evidence: boolean;
  latency_ms: number;
  status: string;
  created_at: string;
};
export type EntitlementRow = { id: string; feature: string; limit: number; used: number; source: string };
export type InvoiceRow = {
  id: string;
  stripe_invoice_id: string;
  status: string;
  amount_due_cents: number;
  amount_paid_cents: number;
  hosted_invoice_url: string;
  issued_at: string | null;
};
export type BillingSummary = {
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
export type WorkspaceData = {
  roles: RoleRow[];
  users: UserRow[];
  apiKeys: ApiKeyRow[];
  documents: DocumentRow[];
  sources: SourceRow[];
  schedules: ScheduleRow[];
  prompts: BasePromptRow[];
  runLogs: RunLogRow[];
  jobs: IntegrationJobRow[];
  traces: RAGTraceRow[];
  billing: BillingSummary | null;
  members: MemberRow[];
  aiModels: AIModelConfig[];
  savings: SavingsData | null;
};

export const emptyWorkspaceData: WorkspaceData = {
  roles: [],
  users: [],
  apiKeys: [],
  documents: [],
  sources: [],
  schedules: [],
  prompts: [],
  runLogs: [],
  jobs: [],
  traces: [],
  billing: null,
  members: [],
  aiModels: [],
  savings: null,
};
