import {
  Asset,
  AccessRequestSummary,
  ApprovalStepItem,
  ActiveSession,
  AuditEvent,
  DashboardMetrics,
} from "./api-types";

const API_BASE = process.env.NEXT_PUBLIC_PAM_API_URL || "http://127.0.0.1:8000";

let inMemoryToken: string | null = null;

export function setSessionToken(token: string | null) {
  inMemoryToken = token;
}

export function getSessionToken(): string | null {
  return inMemoryToken;
}

function generateIdempotencyKey(): string {
  return "idem_" + Math.random().toString(36).substring(2, 12) + Date.now().toString(36);
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");

  if (inMemoryToken) {
    headers.set("Authorization", `Bearer ${inMemoryToken}`);
  }

  // Inject Idempotency key for mutating requests if not provided
  if (
    options.method &&
    ["POST", "PUT", "PATCH", "DELETE"].includes(options.method.toUpperCase()) &&
    !headers.has("X-Idempotency-Key")
  ) {
    headers.set("X-Idempotency-Key", generateIdempotencyKey());
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    const message = errorBody.message || errorBody.detail || `HTTP ${response.status} Error`;
    const error = new Error(message) as Error & { code?: string; status?: number };
    error.code = errorBody.code;
    error.status = response.status;
    throw error;
  }

  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

export const pamApi = {
  // Assets
  getAssets: (): Promise<{ items: Asset[] }> =>
    request<{ items: Asset[] }>("/api/v1/assets"),

  // Requests
  createRequest: (payload: {
    asset_id: string;
    target_account_id: string;
    requested_start_at: string;
    requested_end_at: string;
    justification: string;
    ticket_ref?: string;
  }): Promise<{ request_id: string; revision_id: string; step_id: string }> =>
    request("/api/v1/requests", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  getRequests: (): Promise<{ items: AccessRequestSummary[] }> =>
    request<{ items: AccessRequestSummary[] }>("/api/v1/requests"),

  cancelRequest: (requestId: string): Promise<{ status: string }> =>
    request(`/api/v1/requests/${requestId}/cancel`, { method: "POST" }),

  // Approvals
  getApproverQueue: (): Promise<{ items: ApprovalStepItem[] }> =>
    request<{ items: ApprovalStepItem[] }>("/api/v1/approvals/queue"),

  submitDecision: (
    stepId: string,
    payload: { expected_revision_id: string; decision: "approved" | "rejected"; reason?: string }
  ): Promise<{ grant_id?: string; status: string }> =>
    request(`/api/v1/approval-steps/${stepId}/decisions`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Sessions
  getSessions: (): Promise<{ items: ActiveSession[] }> =>
    request<{ items: ActiveSession[] }>("/api/v1/sessions"),

  terminateSession: (sessionId: string, reason: string): Promise<{ status: string }> =>
    request(`/api/v1/sessions/${sessionId}/terminate`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),

  // Audit
  getRecentAudit: (): Promise<{ items: AuditEvent[] }> =>
    request<{ items: AuditEvent[] }>("/api/v1/audit/events?limit=10"),
};
