export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export type SystemStatus = {
  status: "ok" | "degraded";
  app: string;
  env: string;
  mode: string;
  checked_at: string;
  db: { connected: boolean; latency_ms: number; server_version: string | null; error: string | null };
  counts: { disputes: number; runs: number; refunds: number };
  schema_tables: number;
  capabilities: {
    paypal_credentials: boolean;
    live_paypal: boolean;
    agents: boolean;
    replay: boolean;
  };
  request_id: string;
};

export type Dispute = {
  id: string;
  paypal_dispute_id: string;
  paypal_case_number: string | null;
  buyer_label: string | null;
  reason_code: string;
  reason_detail: string | null;
  status: string;
  paypal_status: string;
  lifecycle_stage: string;
  amount: string;
  currency: string;
  confidence: string | null;
  decision_code: string | null;
  requires_approval: boolean;
  agent_summary: string | null;
  response_due_by: string | null;
  created_at: string;
  updated_at: string;
  resolved_at: string | null;
  recovered_amount: string | null;
  is_demo: boolean;
};

export type DisputeList = { items: Dispute[]; total: number; limit: number; offset: number };

export type Run = {
  id: string;
  dispute_id: string;
  status: string;
  trigger: string;
  iterations: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
  model_primary: string | null;
  error_code: string | null;
  error_detail: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
};

export type Step = {
  seq: number;
  node: string;
  agent: string;
  step_type: string;
  summary: string | null;
  payload: Record<string, unknown>;
  latency_ms: number | null;
  tokens: number | null;
  created_at: string;
};

export type AgentMessage = {
  seq: number;
  from_agent: string;
  to_agent: string;
  msg_type: string;
  claim: string;
  evidence_refs: string[];
  confidence: string | null;
  constraints: Record<string, unknown>;
  rationale: string | null;
};

export type RunDetail = { run: Run; steps: Step[]; messages: AgentMessage[] };

export type PolicyCitation = {
  chunk_id: string;
  title: string;
  text: string;
  score: number;
  source: string;
  document: string;
  section: string;
  category: string;
  retrieval_mode: string;
  embedding_model: string;
};

export type Decision = {
  id: string;
  decision_code: string;
  amount: string;
  currency: string;
  confidence: string | null;
  rationale: string | null;
  reasoning: string | null;
  missing_evidence: string[];
  policy_citations: PolicyCitation[];
  cited_evidence: string[];
  requires_approval: boolean;
  status: string;
  decided_by: string;
  created_at: string;
};

export type Approval = {
  id: string;
  dispute_id: string;
  decision_id: string;
  status: string;
  requested_at: string;
  expires_at: string | null;
  resolved_at: string | null;
  note: string | null;
  decision_code: string | null;
  amount: string | null;
  currency: string | null;
  confidence: string | null;
  rationale: string | null;
  case_number: string | null;
  reason_code: string | null;
};

export type Refund = {
  id: string;
  paypal_refund_id: string | null;
  amount: string;
  currency: string;
  status: string;
  reason: string | null;
  initiated_by: string;
  simulated: boolean;
  created_at: string;
};

export type PolicyEval = {
  id: string;
  ruleset_version: string;
  result: string;
  matched_rules: { id: string; outcome: string; reason: string }[];
  envelope: Record<string, unknown>;
  created_at: string;
};

export type DisputeMessage = {
  id: string;
  direction: string;
  channel: string;
  author_type: string;
  body: string;
  sent_at: string | null;
  created_at: string | null;
};

export type DisputeDetail = {
  dispute: Dispute;
  order: {
    paypal_order_id: string;
    item_title: string | null;
    amount: string;
    currency: string;
    status: string;
  } | null;
  capture: {
    paypal_capture_id: string;
    status: string;
    amount: string;
    currency: string;
    seller_protection_status: string;
  } | null;
  messages: DisputeMessage[];
  latest_run: Run | null;
  decision: Decision | null;
  policy: PolicyEval | null;
  approvals: Approval[];
  refunds: Refund[];
};

export type Metrics = {
  open_disputes: number;
  awaiting_approval: number;
  resolved: number;
  escalated: number;
  pending_approvals: number;
  total_at_risk: string;
  recovered: string;
  auto_executed: number;
  human_executed: number;
  median_run_seconds: number | null;
  by_reason: Record<string, number>;
};

export type Complaint = {
  dispute_id: string;
  paypal_case_number: string | null;
  paypal_dispute_id: string;
  buyer_label: string | null;
  reason_code: string;
  reason_detail: string | null;
  status: string;
  amount: string;
  currency: string;
  response_due_by: string | null;
  created_at: string;
  message_count: number;
  last_message: string | null;
  last_message_at: string | null;
  last_message_direction: string | null;
};

export type ComplaintList = {
  items: Complaint[];
  total: number;
  limit: number;
  offset: number;
};

export type Analytics = {
  total_disputes: number;
  resolved_cases: number;
  pending_cases: number;
  escalated_cases: number;
  awaiting_approval: number;
  resolution_rate: number;
  total_at_risk: string;
  refunded_total: string;
  by_status: { status: string; count: number }[];
  by_reason: {
    reason_code: string;
    count: number;
    at_risk: string;
    resolved: number;
    refunded: string;
  }[];
  refunds: {
    count: number;
    completed: number;
    pending: number;
    failed: number;
    simulated: number;
    live: number;
    amount_total: string;
    amount_completed: string;
    amount_simulated: string;
  };
  trend: { date: string; created: number; resolved: number }[];
  median_run_seconds: number | null;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string;
  role: string;
  merchant_id: string;
  merchant_name: string;
  merchant_slug: string;
};

export type AuthSession = {
  user: AuthUser;
  expires_at: string;
  mode: string;
};

export type KnowledgeStatus = {
  ready: boolean;
  pgvector_version: string | null;
  documents: number;
  chunks: number;
  categories: { category: string; documents: number }[];
  embedding_models: { model: string; chunks: number }[];
  last_ingested_at: string | null;
  settings: {
    embedding_model: string;
    dimensions: number;
    top_k: number;
    chunk_chars: number;
    chunk_overlap: number;
  };
};

export type KnowledgeDocument = {
  id: string;
  title: string;
  source_key: string;
  category: string;
  version: string;
  chunk_count: number;
  embedding_model: string;
  updated_at: string | null;
};

export type KnowledgeDocuments = { total: number; documents: KnowledgeDocument[] };

export type KnowledgeSearch = {
  citations: PolicyCitation[];
  query: string;
  mode: string;
  embedding_model: string;
  used_fallback: boolean;
  warning: string | null;
  latency_ms: number;
};

export const SESSION_COOKIE = "resolveai_session";

function withScheme(value: string): string {
  return /^https?:\/\//.test(value) ? value : `http://${value}`;
}

export function apiBase(): string {
  const internal = process.env.API_INTERNAL_URL;
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;
  // Server components call the API directly. The browser uses a relative URL so
  // the /api/v1 route handler proxies through this origin (first-party cookies).
  if (typeof window === "undefined") {
    return withScheme(internal ?? publicUrl ?? "http://localhost:8000");
  }
  return publicUrl ?? "";
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${apiBase()}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      cache: "no-store",
      credentials: "include",
      headers: { accept: "application/json", ...(init?.headers ?? {}) },
    });
  } catch (err) {
    throw new ApiError(
      `Cannot reach ${url} — ${err instanceof Error ? err.message : "network error"}`,
      0,
      "NETWORK_ERROR",
    );
  }
  const text = await res.text();
  if (!res.ok) {
    let message = `HTTP ${res.status} from ${url}`;
    let code: string | undefined;
    try {
      const body = JSON.parse(text);
      if (body?.error?.message) message = body.error.message;
      code = body?.error?.code;
    } catch {
      if (text) message += ` — ${text.slice(0, 200)}`;
    }
    throw new ApiError(message, res.status, code);
  }
  return (text ? JSON.parse(text) : ({} as T)) as T;
}

export const getSystemStatus = () => request<SystemStatus>("/api/v1/system/status");
export const getMetrics = () => request<Metrics>("/api/v1/metrics");
export type PolicyRules = {
  version: string;
  thresholds: {
    auto_resolve_cap: number;
    auto_offer_cap: number;
    hard_cap: number;
    auto_approve_confidence: number;
    escalate_confidence: number;
    deadline_pressure_hours: number;
  };
  fraud_reasons: string[];
  actions_by_reason: Record<string, string[]>;
  confidence_bands?: Record<string, [number, number]>;
  [key: string]: unknown;
};
export const getPolicyRules = () => request<PolicyRules>("/api/v1/policy/rules");
export const getDisputes = (params: {
  limit?: number;
  offset?: number;
  sort?: string;
  q?: string;
  status?: string;
  reason?: string;
} = {}) => {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 25));
  search.set("offset", String(params.offset ?? 0));
  if (params.sort) search.set("sort", params.sort);
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.reason) search.set("reason", params.reason);
  return request<DisputeList>(`/api/v1/disputes?${search.toString()}`);
};
export const getDispute = (id: string) => request<DisputeDetail>(`/api/v1/disputes/${id}`);
export const runDispute = (id: string) =>
  request<Run>(`/api/v1/disputes/${id}/run`, { method: "POST" });
export const getRun = (id: string) => request<RunDetail>(`/api/v1/runs/${id}`);
export const listApprovals = (status = "pending") =>
  request<Approval[]>(`/api/v1/approvals?status=${status}`);
export const decideApproval = (id: string, approve: boolean, note?: string) =>
  request<Approval>(`/api/v1/approvals/${id}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ approve, note }),
  });
export const seedDemo = () => request<{ disputes: number; mode: string }>("/api/v1/demo/seed", { method: "POST" });
export const resetDemo = () => request<{ status: string }>("/api/v1/demo/reset", { method: "POST" });

export const login = (email: string, password: string) =>
  request<AuthSession>("/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email, password }),
  });

export const logout = () => request<{ status: string }>("/api/v1/auth/logout", { method: "POST" });

export const getAuthSession = (token?: string) =>
  request<AuthSession>("/api/v1/auth/session", {
    headers: token ? { cookie: `${SESSION_COOKIE}=${token}` } : undefined,
  });

export const getComplaints = (params: {
  q?: string;
  status?: string;
  reason?: string;
  limit?: number;
  offset?: number;
} = {}) => {
  const search = new URLSearchParams();
  search.set("limit", String(params.limit ?? 100));
  search.set("offset", String(params.offset ?? 0));
  if (params.q) search.set("q", params.q);
  if (params.status) search.set("status", params.status);
  if (params.reason) search.set("reason", params.reason);
  return request<ComplaintList>(`/api/v1/complaints?${search.toString()}`);
};

export const sendCaseMessage = (id: string, body: string) =>
  request<DisputeMessage>(`/api/v1/disputes/${id}/messages`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ body }),
  });

export const getAnalytics = () => request<Analytics>("/api/v1/metrics/analytics");

export const getKnowledgeStatus = () => request<KnowledgeStatus>("/api/v1/knowledge/status");

export const getKnowledgeDocuments = () =>
  request<KnowledgeDocuments>("/api/v1/knowledge/documents");

export const searchKnowledge = (query: string, reason_code?: string, k = 5) =>
  request<KnowledgeSearch>("/api/v1/knowledge/search", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, reason_code, k }),
  });

export const ingestKnowledge = (force = false) =>
  request<Record<string, unknown>>("/api/v1/knowledge/ingest", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ force, allow_fallback: true }),
  });
