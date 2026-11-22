# 04 · API Specification: Ariba PAM

> Complete HTTP REST Contract · 2026-11-22

All API routes adhere to RESTful conventions, use UTC RFC 3339 timestamps, and enforce server-side authentication, resource scoping, and separation of duties.

---

## 1. General Conventions & Headers

### Request Headers
- `Authorization`: `Bearer <session_token>` (for workforce and portal users) or internal mTLS/service identity (for gateways).
- `X-Request-ID`: Client-supplied or server-generated UUID for cross-system distributed tracing.
- `X-Correlation-ID`: Operation-specific correlation identifier propagated to the transactional audit outbox.
- `X-Idempotency-Key`: Mandatory for all state-changing endpoints (`POST`, `PUT`, `PATCH`). Replays with matching payload return cached results; conflicting payloads return HTTP 409 `IDEMPOTENCY_CONFLICT`.

### Error Response Schema
```json
{
  "code": "STALE_REVISION",
  "message": "The proposal changed. Reload the current revision before accepting another decision.",
  "request_id": "req_8f192b49",
  "details": {
    "expected_revision_id": "rev_001",
    "actual_revision_id": "rev_002"
  }
}
```

### Identifier Concealment (Default Deny)
When a user attempts to access an asset, request, session, or evidence item outside their permitted resource scope, the server returns **HTTP 404 NOT_FOUND** (not HTTP 403 Forbidden). This prevents infrastructure discovery and enumeration.

---

## 2. Authentication & Identity APIs

| Method | Path | Description | Access | Success |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | Workforce login (synthetic IdP in lab; OIDC exchange in prod). | Public | 200 OK |
| `GET` | `/api/v1/me` | Current caller identity, active roles, and permitted resource scopes. | Authenticated | 200 OK |
| `POST` | `/api/v1/auth/idp-events` | Ingest IdP lifecycle events (`user.disabled`, `user.deprovisioned`). | IdP Webhook | 200 OK |

---

## 3. Role & Permission Management APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/roles` | List all system and custom roles within administrator scope. | 200 OK |
| `POST` | `/api/v1/admin/roles` | Create a custom role with metadata and permission set. | 201 Created |
| `GET` | `/api/v1/admin/roles/{role_id}` | Retrieve role details and bound permissions. | 200 OK |
| `PATCH` | `/api/v1/admin/roles/{role_id}` | Update role metadata (description, display name). | 200 OK |
| `GET` | `/api/v1/admin/roles/{role_id}/permissions` | List canonical permissions assigned to role. | 200 OK |
| `PUT` | `/api/v1/admin/roles/{role_id}/permissions` | Replace permission assignments for custom role. Built-in roles immutable. | 200 OK |
| `POST` | `/api/v1/admin/roles/{role_id}/disable` | Disable a custom role. Revokes active assignments. | 200 OK |

---

## 4. User Role Assignment APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/users/{user_id}/roles` | View all active and scheduled role assignments for a user. | 200 OK |
| `POST` | `/api/v1/admin/users/{user_id}/role-assignments` | Assign a role to a user bound to an explicit scope ID and expiration. | 201 Created |
| `GET` | `/api/v1/admin/role-assignments/{assignment_id}` | View detailed metadata of a specific assignment. | 200 OK |
| `POST` | `/api/v1/admin/role-assignments/{assignment_id}/revoke`| Immediately revoke a role assignment. | 200 OK |
| `GET` | `/api/v1/admin/users/{user_id}/effective-permissions` | Compute dynamic effective permissions across all active scopes. | 200 OK |

---

## 5. Resource Scope Management APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/scopes` | List hierarchical resource scopes. | 200 OK |
| `POST` | `/api/v1/admin/scopes` | Create a new resource scope (organization, environment, group). | 201 Created |
| `GET` | `/api/v1/admin/scopes/{scope_id}` | Get scope hierarchy node and child relations. | 200 OK |
| `PATCH` | `/api/v1/admin/scopes/{scope_id}` | Update scope metadata or parent node. | 200 OK |
| `GET` | `/api/v1/admin/scopes/{scope_id}/resources`| List assets and accounts mapped to this scope. | 200 OK |
| `PUT` | `/api/v1/admin/scopes/{scope_id}/resources`| Update asset-to-scope mappings. | 200 OK |
| `GET` | `/api/v1/admin/users/{user_id}/scopes` | List all resource scopes assigned to user. | 200 OK |

---

## 6. Separation of Duties (SoD) APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/sod/rules` | List configured separation of duties conflict rules. | 200 OK |
| `POST` | `/api/v1/admin/sod/rules` | Create a new SoD conflict rule (e.g. Requester vs Approver). | 201 Created |
| `PATCH` | `/api/v1/admin/sod/rules/{rule_id}` | Update SoD rule enforcement mode (strict deny vs exception). | 200 OK |
| `POST` | `/api/v1/admin/sod/evaluations` | Dry-run evaluate a proposed role assignment or access request for SoD violations. | 200 OK |
| `GET` | `/api/v1/admin/sod/violations` | List detected SoD violation attempts and audit records. | 200 OK |
| `POST` | `/api/v1/admin/sod/exceptions` | Request a controlled, temporary SoD exception requiring dual approval. | 201 Created |
| `POST` | `/api/v1/admin/sod/exceptions/{id}/decisions` | Independent authority approves or rejects SoD exception. | 200 OK |

---

## 7. Delegation APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/delegations` | List delegations created by the caller. | 200 OK |
| `POST` | `/api/v1/delegations` | Delegate approval authority to another eligible user with strict time window. | 201 Created |
| `GET` | `/api/v1/delegations/{delegation_id}` | View delegation scope, validity, and delegator/delegate identities. | 200 OK |
| `POST` | `/api/v1/delegations/{delegation_id}/revoke`| Immediately revoke an active delegation. | 200 OK |
| `GET` | `/api/v1/delegations/received` | List active delegations where caller is the acting delegate. | 200 OK |

---

## 8. Access Requests & Approvals APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/requests` | List requests visible to requester or scoped approver. | 200 OK |
| `POST` | `/api/v1/requests` | Submit initial access request with immutable revision 1. | 201 Created |
| `GET` | `/api/v1/requests/{request_id}` | View full request details, current revision, and decision history. | 200 OK |
| `POST` | `/api/v1/requests/{request_id}/revisions` | Submit replacement revision with `expected_revision_id`. Supersedes prior steps. | 201 Created |
| `POST` | `/api/v1/requests/{request_id}/cancel` | Cancel a pending request as requester. | 200 OK |
| `GET` | `/api/v1/approvals` | List pending approval steps assigned to caller. | 200 OK |
| `POST` | `/api/v1/approval-steps/{step_id}/decisions`| Record approval or rejection. Final step atomically issues Access Grant. | 201 Created |

---

## 9. Grants, Launches & Session APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/grants/{grant_id}` | View grant details, effective window, and status within scope. | 200 OK |
| `POST` | `/api/v1/grants/{grant_id}/launches` | Issue single-use, 60-second launch capability to grant owner. | 201 Created |
| `POST` | `/api/v1/grants/{grant_id}/revoke` | Revoke grant as security operator. Initiates session termination. | 202 Accepted |
| `GET` | `/api/v1/sessions` | List active and historical sessions within caller's scope. | 200 OK |
| `GET` | `/api/v1/sessions/{session_id}` | View session state, timestamps, and gateway reference. | 200 OK |
| `POST` | `/api/v1/sessions/{session_id}/terminate` | Request immediate session termination (owner or operator). | 202 Accepted |

---

## 10. Internal Gateway APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `POST` | `/internal/v1/launches/consume` | Gateway consumes launch token. Returns session ID, target parameters, and lease deadline. | 201 Created |
| `POST` | `/internal/v1/sessions/{session_id}/renew` | Gateway renews active lease. Returns deadline bounded by grant expiry. Returns 409 if revoked. | 200 OK |
| `POST` | `/internal/v1/sessions/{session_id}/events` | Gateway delivers lifecycle evidence (terminated, failure, recording digest). | 202 Accepted |

---

## 11. Evidence & Review APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/audit/events` | Query audit outbox events with cursor pagination within caller scope. | 200 OK |
| `POST` | `/api/v1/audit/export` | Authorize and initiate an immutable, signed audit trail export. | 202 Accepted |
| `GET` | `/api/v1/audit/exports/{export_id}/download` | Download verifiable audit export payload with SHA-256 custody digest. | 200 OK |
| `GET` | `/api/v1/recordings/{recording_id}` | View scoped recording metadata, file size, and coverage status. | 200 OK |
| `POST` | `/api/v1/recordings/{recording_id}/playback-sessions` | Authorize short-lived playback streaming URL for scoped auditor. | 201 Created |
| `POST` | `/api/v1/recordings/{recording_id}/exports` | Initiate an auditable, scoped evidence export job. | 202 Accepted |
| `GET` | `/api/v1/recordings/exports/{export_id}/download` | Retrieve authorized recording export archive. | 200 OK |

---

## 12. SOC Alerting, Circuit Breaker & Monitoring APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/alerts/events` | List SOC security alerts (recording degradation, lease failures, launch blocks). | 200 OK |
| `POST` | `/api/v1/alerts/events/{alert_id}/acknowledge` | Acknowledge SOC alert with analyst identity and triage notes. | 200 OK |
| `GET` | `/api/v1/alerts/circuit-breaker` | Inspect outbound SOC adapter and SIEM webhook circuit breaker state. | 200 OK |
| `POST` | `/api/v1/alerts/circuit-breaker/reset` | Manually reset tripped circuit breaker after upstream recovery. | 200 OK |

---

## 13. Emergency Out-of-Band Break-Glass APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `POST` | `/api/v1/emergency/requests` | Initiate high-urgency emergency access request bypassing standard queue. | 201 Created |
| `POST` | `/api/v1/emergency/requests/{request_id}/approve` | Multi-custodian or secondary authority emergency approval. | 200 OK |
| `POST` | `/api/v1/emergency/requests/{request_id}/launches` | Issue high-priority emergency session launch capability. | 201 Created |
| `GET` | `/api/v1/emergency/active` | Real-time monitoring of all active emergency break-glass sessions. | 200 OK |

---

## 14. Vault Credential & RDP Gateway Internal APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/internal/v1/sessions/{session_id}/vault-credentials` | Ephemeral retrieval of injected vault password for authenticated gateway. | 200 OK |
| `GET` | `/internal/v1/sessions/{session_id}/rdp-parameters` | Compile Windows RDP tunnel parameters and gateway proxy certificates. | 200 OK |
| `POST` | `/internal/v1/sessions/{session_id}/vault-credentials/rotate`| Trigger post-session automated credential rotation in Vault. | 200 OK |
| `POST` | `/internal/v1/sessions/{session_id}/sign-certificate` | Gateway requests short-lived Ed25519 OpenSSH user certificate from CA. | 201 Created |

---

## 15. Security SIEM & SOC Event Adapters

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/wazuh/status` | Wazuh SIEM adapter status, transmission queue, and dead-letter count. | 200 OK |
| `POST` | `/api/v1/admin/wazuh/test-event` | Send synthetic test event through Wazuh OSSEC transformer. | 200 OK |
| `GET` | `/api/v1/admin/soc/status` | Enterprise SOC streaming status, active priority channels, and metrics. | 200 OK |
| `POST` | `/api/v1/admin/soc/test-event` | Emit synthetic priority alert through SOC adapter. | 200 OK |
| `POST` | `/api/v1/admin/soc/circuit-breaker/reset` | Force reset SOC delivery circuit breaker. | 200 OK |

---

## 16. Multi-IdP Federation & SCIM 2.0 Ingestion

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/idp/status` | Multi-IdP federation configuration, health, and disablement sync status. | 200 OK |
| `POST` | `/api/v1/auth/idp/secondary/events` | Ingest Webhook events from secondary federated IdP with signature check. | 200 OK |
| `PATCH` | `/api/v1/auth/scim/v2/Users/{user_id}` | SCIM 2.0 deprovisioning endpoint (`active: false`) with instant session purge. | 200 OK |

---

## 17. High Availability & Rolling Upgrade APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/ha/status` | Multi-node Control Plane cluster topology, node health, and zone gateways. | 200 OK |
| `POST` | `/api/v1/admin/ha/gateways/heartbeat` | Gateway zone instance heartbeat and active connection count update. | 200 OK |
| `POST` | `/api/v1/admin/ha/simulate-failover` | Administrative simulation of primary node failure and switchover verification. | 200 OK |
| `GET` | `/api/v1/admin/upgrade/status` | Current cluster software versions, Expand/Contract schema state, and node drain status. | 200 OK |
| `POST` | `/api/v1/admin/upgrade/simulate-roll` | Administrative simulation of rolling upgrade across nodes with 0% session loss. | 200 OK |
| `POST` | `/api/v1/admin/upgrade/simulate-rollback` | Administrative simulation of emergency rollback under concurrent active session load. | 200 OK |

---

## 18. Disaster Recovery & Expanded Capacity APIs

| Method | Path | Purpose | Success |
| :--- | :--- | :--- | :--- |
| `GET` | `/api/v1/admin/recovery/expanded-status` | Database capacity profile, entity counts vs targets, and last DR rehearsal results. | 200 OK |
| `POST` | `/api/v1/admin/recovery/simulate-expanded-drill` | Execute full disaster recovery benchmark drill (restore, key recovery, evidence search). | 200 OK |
| `GET` | `/api/v1/admin/itsm/status` | ITSM service desk integration status, cache statistics, and ticket verification SLA. | 200 OK |

