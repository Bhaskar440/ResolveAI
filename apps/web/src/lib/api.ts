export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

export type SystemStatus = {
  status: "ok" | "degraded";
  app: string;
  env: string;
  mode: string;
  checked_at: string;
  db: {
    connected: boolean;
    latency_ms: number;
    server_version: string | null;
    error: string | null;
  };
  counts: { disputes: number; runs: number; refunds: number };
  schema_tables: number;
  capabilities: { live_paypal: boolean; agents: boolean; replay: boolean };
  request_id: string;
};

export type Dispute = {
  id: string;
  paypal_case_number: string | null;
  reason_code: string;
  status: string;
  paypal_status: string;
  amount: string;
  currency: string;
  confidence: string | null;
  decision_code: string | null;
  requires_approval: boolean;
  response_due_by: string | null;
  updated_at: string;
};

export type DisputeList = {
  items: Dispute[];
  total: number;
  limit: number;
  offset: number;
};

/**
 * Server-side calls use API_INTERNAL_URL (docker: http://api:8000),
 * browser calls use NEXT_PUBLIC_API_URL. No fallback data, ever.
 */
export function apiBase(): string {
  return (
    process.env.API_INTERNAL_URL ??
    process.env.NEXT_PUBLIC_API_URL ??
    "http://localhost:8000"
  );
}

async function getJson<T>(path: string): Promise<ApiResult<T>> {
  const url = `${apiBase()}${path}`;
  try {
    const res = await fetch(url, {
      cache: "no-store",
      headers: { accept: "application/json" },
    });
    const text = await res.text();
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status} from ${url} — ${text.slice(0, 200)}` };
    }
    return { ok: true, data: JSON.parse(text) as T };
  } catch (err) {
    const message = err instanceof Error ? err.message : "network error";
    return { ok: false, error: `Cannot reach ${url} — ${message}` };
  }
}

export const getSystemStatus = () => getJson<SystemStatus>("/api/v1/system/status");
export const getDisputes = () => getJson<DisputeList>("/api/v1/disputes?limit=25");
