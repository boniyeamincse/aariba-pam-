/**
 * Ariba PAM REST API TypeScript Definitions
 * Derived from docs/openapi.yaml (OpenAPI 3.1)
 */

export interface TargetAccount {
  id: string;
  username: string;
  is_active: boolean;
  requires_ticket: boolean;
  max_duration_seconds: number;
}

export interface Asset {
  id: string;
  name: string;
  environment: string;
  team: string;
  zone_id: string;
  host: string;
  port: number;
  is_active: boolean;
  accounts: TargetAccount[];
}

export interface AccessRequestSummary {
  id: string;
  requester_id: string;
  asset_id: string;
  asset_name: string;
  target_account_username: string;
  status: "pending" | "approved" | "rejected" | "expired" | "cancelled";
  current_revision_id: string;
  requested_start_at: string;
  requested_end_at: string;
  justification: string;
  created_at: string;
}

export interface ApprovalStepItem {
  step_id: string;
  request_id: string;
  revision_id: string;
  step_order: number;
  required_role: string;
  status: "pending" | "approved" | "rejected";
  asset_name: string;
  target_account: string;
  requester_email: string;
  justification: string;
  requested_start_at: string;
  requested_end_at: string;
  created_at: string;
}

export interface ActiveSession {
  id: string;
  grant_id: string;
  gateway_id: string;
  asset_name: string;
  target_host: string;
  target_username: string;
  status: "active" | "terminating" | "ended" | "failed";
  started_at: string;
  lease_deadline: string;
  effective_end_at: string;
  termination_reason?: string;
}

export interface AuditEvent {
  id: string;
  event_type: string;
  correlation_id: string;
  actor_id: string;
  created_at: string;
  payload: Record<string, any>;
}

export interface DashboardMetrics {
  totalAssets: number;
  activeSessions: number;
  pendingApprovals: number;
  activeGrants: number;
  outboxPendingCount: number;
}
