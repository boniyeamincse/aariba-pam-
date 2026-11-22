# 05 · Database Schema: Ariba PAM

> Relational Data Models & Constraints · 2026-11-22

Ariba PAM utilizes a relational database architecture (PostgreSQL in production; SQLite in isolated laboratory test runs) managed via SQLAlchemy 2.0 declarative mappings and Alembic migrations.

---

## 1. Entity-Relationship Model Overview

```
                                      ┌───────────────┐
                                      │  permissions  │
                                      └───────┬───────┘
                                              │ N:M (role_permissions)
                                              ▼
┌──────────────────┐    N:M (user_role) ┌───────────────┐
│      users       │◀───────────────────│     roles     │
└────────┬─────────┘                    └───────────────┘
         │
         │ 1:N
         ├───▶ [ user_role_assignments ] ───▶ [ resource_scopes ]
         │                                              │ 1:N
         ├───▶ [ delegations ]                          ▼
         │                                      [ scope_resources ]
         ├───▶ [ access_requests ]                      │
         │           │ 1:N                              ▼
         │           ▼                             [ assets ] ───▶ [ gateway_zones ]
         │     [ request_revisions ]                    │ 1:N
         │           │ 1:N                              ▼
         │           ├───▶ [ approval_steps ]     [ target_accounts ]
         │           │
         │           ▼
         │     [ access_grants ]
         │           │ 1:N
         │           ▼
         │     [ session_launches ]
         │           │ 1:1
         │           ▼
         └───▶ [ access_sessions ]
```

---

## 2. Authorization & RBAC Tables

### `permissions`
Canonical permission registry defining granular authorization identifiers.
- `id` (VARCHAR(64), PK): e.g. `prm_session_terminate`.
- `name` (VARCHAR(64), UNIQUE, NOT NULL): Canonical string (e.g. `session.terminate`).
- `category` (VARCHAR(32), NOT NULL): e.g. `session`, `asset`, `rbac`, `audit`.
- `description` (TEXT, NOT NULL).

### `roles`
System and custom administrative and workflow roles.
- `id` (VARCHAR(64), PK): e.g. `role_security_operator`.
- `name` (VARCHAR(64), UNIQUE, NOT NULL): Role name (e.g. `security_operator`).
- `description` (TEXT).
- `is_system` (BOOLEAN, DEFAULT FALSE): System roles cannot be deleted or weakened.
- `is_active` (BOOLEAN, DEFAULT TRUE).

### `role_permissions`
Many-to-many binding linking roles to canonical permissions.
- `role_id` (VARCHAR(64), FK `roles.id`, PK).
- `permission_id` (VARCHAR(64), FK `permissions.id`, PK).

### `resource_scopes`
Hierarchical scope nodes for infrastructure resource containment.
- `id` (VARCHAR(64), PK): e.g. `scp_prod_linux`.
- `name` (VARCHAR(128), NOT NULL).
- `scope_type` (VARCHAR(32), NOT NULL): `organization`, `environment`, `platform`, `team`.
- `parent_scope_id` (VARCHAR(64), FK `resource_scopes.id`, NULLABLE): Recursive hierarchy.
- `is_active` (BOOLEAN, DEFAULT TRUE).

### `scope_resources`
Mapping linking infrastructure assets and target accounts into scope nodes.
- `id` (VARCHAR(64), PK).
- `scope_id` (VARCHAR(64), FK `resource_scopes.id`, NOT NULL).
- `resource_type` (VARCHAR(32), NOT NULL): `asset`, `account`, `zone`.
- `resource_id` (VARCHAR(64), NOT NULL).
- Unique constraint: `(scope_id, resource_type, resource_id)`.

### `user_role_assignments`
Binds users to roles within a specific resource scope node.
- `id` (VARCHAR(64), PK).
- `user_id` (VARCHAR(64), FK `users.id`, NOT NULL).
- `role_id` (VARCHAR(64), FK `roles.id`, NOT NULL).
- `scope_id` (VARCHAR(64), FK `resource_scopes.id`, NOT NULL).
- `assigned_by_id` (VARCHAR(64), FK `users.id`, NOT NULL).
- `justification` (TEXT, NOT NULL).
- `valid_from` (TIMESTAMPTZ, NOT NULL).
- `expires_at` (TIMESTAMPTZ, NULLABLE): NULL for permanent, timestamp for time-bound.
- `status` (VARCHAR(32), DEFAULT 'active'): `active`, `revoked`, `expired`.
- Unique constraint: `(user_id, role_id, scope_id, status)`.

### `delegations`
Time-bounded delegation of approval authority.
- `id` (VARCHAR(64), PK).
- `delegator_id` (VARCHAR(64), FK `users.id`, NOT NULL).
- `delegate_id` (VARCHAR(64), FK `users.id`, NOT NULL).
- `scope_id` (VARCHAR(64), FK `resource_scopes.id`, NOT NULL).
- `valid_from` (TIMESTAMPTZ, NOT NULL).
- `expires_at` (TIMESTAMPTZ, NOT NULL).
- `status` (VARCHAR(32), DEFAULT 'active'): `active`, `revoked`, `expired`.
- Check constraints: `delegator_id != delegate_id`, `expires_at > valid_from`.

### `sod_rules` & `sod_violations` & `sod_exceptions`
Separation of Duties conflict definitions, detected anomalies, and approved waivers.
- `sod_rules`: `(id, rule_name, conflicting_permission_a, conflicting_permission_b, severity, is_active)`.
- `sod_violations`: `(id, rule_id, user_id, action_attempted, detected_at, context_json)`.
- `sod_exceptions`: `(id, rule_id, user_id, justification, approved_by_id, valid_from, expires_at, status)`.

### `authorization_decisions`
Tamper-evident log of all evaluated authorization queries (allow and deny).
- `id` (VARCHAR(64), PK).
- `principal_id` (VARCHAR(64), NOT NULL).
- `action` (VARCHAR(64), NOT NULL).
- `resource_id` (VARCHAR(64), NOT NULL).
- `decision` (VARCHAR(16), NOT NULL): `allow`, `deny`.
- `reason_code` (VARCHAR(64), NOT NULL): e.g. `OUT_OF_SCOPE`, `SOD_CONFLICT`, `SUCCESS`.
- `evaluated_at` (TIMESTAMPTZ, DEFAULT utc_now).

---

## 3. Infrastructure & Workflow Core Tables

### `gateway_zones`
- `(id PK, name UNIQUE, description, created_at)`.

### `assets`
- `(id PK, name, environment, team, zone_id FK, host, port, host_trust_ref, is_active, created_at)`.

### `target_accounts`
- `(id PK, asset_id FK, username, is_active, requires_ticket, max_duration_seconds, created_at)`.

### `access_policy_versions`
- `(id PK, asset_id FK, version INT, proposal_id, rules_json, published_at, published_by_id FK)`.
- Unique constraint: `(asset_id, version)`.

### `access_requests` & `request_revisions`
- `access_requests`: `(id PK, requester_id FK, status, current_revision_id, created_at, updated_at)`.
- `request_revisions`: `(id PK, request_id FK, revision_number INT, asset_id FK, target_account_id FK, requested_start_at, requested_end_at, justification, ticket_ref, policy_version_id, is_frozen, created_at)`.

### `approval_steps` & `approval_decisions`
- `approval_steps`: `(id PK, revision_id FK, step_order INT, status, required_role)`.
- `approval_decisions`: `(id PK, step_id FK, approver_id FK, decision, reason, decided_at)`.

### `access_grants` & `session_launches`
- `access_grants`: `(id PK, revision_id FK UNIQUE, requester_id FK, asset_id FK, target_account_id FK, effective_start_at, effective_end_at, status, revocation_reason, revoked_at, revoked_by_id FK)`.
- `session_launches`: `(id PK, grant_id FK, launch_token_digest UNIQUE, expires_at, is_consumed, consumed_at, consumed_by_gateway_id)`.

### `access_sessions`
- `(id PK, grant_id FK, launch_id FK UNIQUE, gateway_id, status, started_at, ended_at, termination_reason)`.

### `audit_outbox`
- `(id PK, event_type, correlation_id, actor_id, payload JSON, occurred_at, delivery_state, delivery_attempts, delivered_at)`.
- Index: `(delivery_state, occurred_at)`.

### `idempotency_records`
- `(id PK, operation, actor_id, idempotency_key, request_fingerprint, response_code, response_payload JSON, created_at)`.
- Unique constraint: `(actor_id, operation, idempotency_key)`.
