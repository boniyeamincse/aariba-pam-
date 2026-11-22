# API specification

> Proposed v1.1 HTTP contract · 2026-11-22

Portal calls use an authenticated browser session and require CSRF protection for state-changing requests. Internal gateway calls use mutually authenticated service identities. Every resource access applies the caller's role and resource scope. Use UTC RFC 3339 timestamps and opaque resource IDs.

## Portal endpoints

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/me | Current principal and permitted scopes | 200 |
| GET /api/v1/assets | List assets and accounts visible to caller | 200 |
| GET /api/v1/requests | List requests visible to the requester or reviewer | 200 |
| POST /api/v1/requests | Submit access window, target, account, justification, and optional ticket reference where policy permits | 201 |
| GET /api/v1/requests/{request_id} | View a scoped request and current revision | 200 |
| POST /api/v1/requests/{request_id}/revisions | Replace a pending revision with the changed fields and expected revision ID | 201 |
| POST /api/v1/requests/{request_id}/cancel | Cancel a pending request as the requester | 200 |
| GET /api/v1/approvals | List pending steps assigned to caller | 200 |
| POST /api/v1/approval-steps/{step_id}/decisions | Record a decision for the specified revision as its eligible approver | 201 |
| GET /api/v1/grants/{grant_id} | View authorization and effective window within caller scope | 200 |
| POST /api/v1/grants/{grant_id}/launches | Create a single-use launch for the grant owner | 201 |
| POST /api/v1/grants/{grant_id}/revoke | Commit revocation as a scoped security operator and initiate session termination | 202 |
| GET /api/v1/sessions | List visible sessions by state and asset | 200 |
| GET /api/v1/sessions/{session_id} | View session state within caller scope | 200 |
| POST /api/v1/sessions/{session_id}/terminate | End own session or one in operator scope | 202 |
| GET /api/v1/audit-events | Query permitted evidence with cursor pagination | 200 |
| GET /api/v1/recordings/{recording_id} | View scoped recording metadata and coverage status | 200 |
| POST /api/v1/recordings/{recording_id}/playback-sessions | Authorize short-lived playback for an explicitly scoped reviewer | 201 |
| POST /api/v1/recordings/{recording_id}/exports | Start an auditable, scoped evidence export | 202 |
| GET /api/v1/recording-exports/{export_id} | Check scoped export state and retrieve an expiring download reference when ready | 200 |

### Identity and authentication APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/auth/methods | List enabled authentication methods | 200 |
| POST /api/v1/auth/mfa/enroll | Begin MFA enrollment for the caller | 201 |
| POST /api/v1/auth/mfa/verify | Verify an MFA challenge or enrollment | 200 |
| POST /api/v1/auth/mfa/disable | Disable MFA after step-up authentication and scoped authorization | 200 |
| POST /api/v1/auth/mfa/recovery-codes | Generate one-time recovery codes | 201 |
| POST /api/v1/auth/step-up | Start step-up authentication for a sensitive action | 200 |
| GET /api/v1/auth/devices | List trusted devices visible to the caller | 200 |
| DELETE /api/v1/auth/devices/{device_id} | Revoke a trusted device | 200 |
| GET /api/v1/users | List users within caller scope | 200 |
| POST /api/v1/users | Create a user in an authorized identity scope | 201 |
| GET /api/v1/users/{user_id} | View a scoped user | 200 |
| PATCH /api/v1/users/{user_id} | Update allowed user attributes with optimistic concurrency | 200 |
| POST /api/v1/users/{user_id}/activate | Activate a suspended or disabled user | 200 |
| POST /api/v1/users/{user_id}/suspend | Suspend a user and revoke pending launches and active authorized sessions | 202 |
| POST /api/v1/users/{user_id}/unlock | Reset a lockout only after the required verification | 200 |
| GET /api/v1/users/{user_id}/access | Summarize scoped roles, assets, grants, and effective access | 200 |
| GET /api/v1/users/{user_id}/sessions | List active sessions for the user within caller scope | 200 |

Supported MFA methods are TOTP, WebAuthn/FIDO2, and enterprise SSO/IdP factors. LDAP/Active Directory and OIDC/SAML remain enterprise identity integration methods rather than local password factors. Use step-up authentication for credential disclosure (when this is ever permitted), policy modification, emergency activation, role assignment, audit export, and session termination. Suspension is a security transition: it revokes pending launch capability and initiates termination of active sessions, with the final session state confirmed by gateway evidence.

### RBAC and permission management

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/admin/roles | List roles visible to an administrator | 200 |
| POST /api/v1/admin/roles | Create a role and its initial resource scope policy | 201 |
| PATCH /api/v1/admin/roles/{role_id} | Update role metadata or scope with optimistic concurrency | 200 |
| GET /api/v1/admin/permissions | List available permissions | 200 |
| PUT /api/v1/admin/roles/{role_id}/permissions | Replace role permission assignments atomically | 200 |
| GET /api/v1/admin/users/{user_id}/roles | View assigned roles and effective scope | 200 |
| PUT /api/v1/admin/users/{user_id}/roles | Replace a user's authorized role assignments | 200 |
| DELETE /api/v1/admin/users/{user_id}/roles/{role_id} | Remove one role assignment | 200 |

Recommended baseline roles are Super Administrator, PAM Administrator, Security Administrator, Security Auditor, Access Approver, Privileged User, and Read-only Auditor. Resource scope is evaluated independently of role membership. Administrative role or permission changes require a reviewed proposal, separation of duties where configured, idempotency, and audit evidence.

### Asset and privileged account management

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| POST /api/v1/assets | Register an asset | 201 |
| GET /api/v1/assets/{asset_id} | View an asset within caller scope | 200 |
| PATCH /api/v1/assets/{asset_id} | Update asset inventory fields and scope | 200 |
| POST /api/v1/assets/{asset_id}/disable | Disable future access and launch to an asset | 202 |
| GET /api/v1/assets/{asset_id}/accounts | List privileged accounts associated with the asset | 200 |
| POST /api/v1/assets/{asset_id}/discovery | Trigger a scoped discovery job | 202 |
| GET /api/v1/assets/{asset_id}/health | Read non-sensitive connectivity health | 200 |
| GET /api/v1/accounts | List privileged accounts within caller scope | 200 |
| POST /api/v1/accounts | Register a privileged account | 201 |
| GET /api/v1/accounts/{account_id} | View account metadata and credential references | 200 |
| PATCH /api/v1/accounts/{account_id} | Update account metadata or target configuration | 200 |
| POST /api/v1/accounts/{account_id}/disable | Disable future use of a privileged account | 202 |
| GET /api/v1/accounts/{account_id}/health | Read account connectivity or validation status | 200 |
| POST /api/v1/accounts/{account_id}/verify | Verify the configured credential without returning it | 202 |
| POST /api/v1/accounts/{account_id}/rotate | Trigger credential rotation for the account | 202 |
| GET /api/v1/accounts/{account_id}/rotation-history | List credential rotation history and reconciliations | 200 |

Asset types include Linux Server, Windows Server, Network Device, Firewall, Database Server, Cloud Infrastructure, Virtualization Platform, and Kubernetes Infrastructure. Account categories include root, administrator, service account, database administrator, network administrator, and platform-specific privileged account types. Account and asset APIs return metadata only; passwords, private keys, API tokens, and secrets must never be returned in normal API responses.

### Credential vault APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/vault/secrets | List secret metadata | 200 |
| POST /api/v1/vault/secrets | Create or import secret metadata and protected material | 201 |
| GET /api/v1/vault/secrets/{secret_id} | View secret metadata; never secret plaintext | 200 |
| PUT /api/v1/vault/secrets/{secret_id} | Update metadata or create a new encrypted version | 200 |
| POST /api/v1/vault/secrets/{secret_id}/rotate | Rotate or replace the secret | 202 |
| POST /api/v1/vault/secrets/{secret_id}/verify | Verify secret usability | 202 |
| POST /api/v1/vault/secrets/{secret_id}/revoke | Revoke the secret or selected delivery authorization | 200 |
| GET /api/v1/vault/secrets/{secret_id}/versions | List encrypted version metadata | 200 |

Normal browser APIs do not retrieve plaintext credentials. The gateway obtains credentials only through authenticated internal credential lease APIs.

### Credential lease internal APIs

| Method and path | Purpose | Success |
| --- | --- | --- |
| POST /internal/v1/credentials/leases | Issue a short-lived credential lease to an authenticated gateway and assigned session | 201 |
| POST /internal/v1/credentials/leases/{lease_id}/revoke | Revoke a credential lease | 200 |
| POST /internal/v1/credentials/leases/{lease_id}/acknowledge | Confirm authenticated delivery and record lease custody evidence | 200 |

Lease issue is limited to the session, grant, target, gateway identity, and lease deadline. Leases are one-purpose, short-lived, audited, and excluded from browser routes.

### Session monitoring and gateway APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/sessions/{session_id}/events | List visible session lifecycle events | 200 |
| GET /api/v1/sessions/{session_id}/activity | List session activity summaries within caller scope | 200 |
| GET /api/v1/sessions/{session_id}/risk | Read the current risk assessment | 200 |
| POST /api/v1/sessions/{session_id}/pause | Pause an active session | 202 |
| POST /api/v1/sessions/{session_id}/resume | Resume a paused session | 202 |
| POST /api/v1/sessions/{session_id}/monitoring | Update approved monitoring state | 200 |
| GET /api/v1/sessions/{session_id}/recording | Read recording status and coverage | 200 |
| GET /api/v1/sessions/{session_id}/commands | List authorized command activity | 200 |
| POST /api/v1/admin/gateways/register | Create a gateway enrollment request | 201 |
| GET /api/v1/admin/gateways | List gateways visible to administrators | 200 |
| GET /api/v1/admin/gateways/{gateway_id}/health | Read gateway health | 200 |
| POST /api/v1/admin/gateways/{gateway_id}/drain | Stop new session acceptance while preserving active sessions | 202 |
| POST /api/v1/admin/gateways/{gateway_id}/revoke | Revoke a gateway identity and terminate authorization | 202 |

Gateway administration is restricted to authorized administrators. Internal routes require the enrolled gateway service identity, zone assignment, certificate or signed identity, and replay-resistant requests.

### Credential rotation and discovery

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| POST /api/v1/rotation/jobs | Create a credential rotation job | 201 |
| GET /api/v1/rotation/jobs | List visible rotation jobs | 200 |
| GET /api/v1/rotation/jobs/{job_id} | View rotation state and reconciliation status | 200 |
| POST /api/v1/rotation/jobs/{job_id}/cancel | Cancel a cancellable pending rotation job | 202 |
| GET /api/v1/rotation/policies | List rotation policies | 200 |
| POST /api/v1/rotation/policies | Create a rotation policy | 201 |
| PATCH /api/v1/rotation/policies/{policy_id} | Update a policy with optimistic concurrency | 200 |
| POST /api/v1/discovery/jobs | Start least-privilege privileged-account discovery | 202 |
| GET /api/v1/discovery/jobs | List visible discovery jobs | 200 |
| GET /api/v1/discovery/jobs/{job_id} | View discovery status and diagnostics | 200 |
| GET /api/v1/discovery/results | List discovered account findings | 200 |
| POST /api/v1/discovery/results/{result_id}/adopt | Adopt a finding as a reviewed privileged account | 201 |
| POST /api/v1/discovery/results/{result_id}/ignore | Ignore a finding with a reason | 200 |

Rotation order is: validate account and target connectivity, generate replacement, update target, verify replacement, publish a vault version, then revoke the old credential. Target or vault failures enter reconciliation; the platform must expose inconsistent state and never claim completed rotation without target verification and vault publication. Discovery agents use least privilege and findings are not automatically promoted to managed accounts.

### Emergency access APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| POST /api/v1/emergency-requests | Request break-glass access with justification and bounded duration | 201 |
| GET /api/v1/emergency-requests | List visible emergency requests | 200 |
| GET /api/v1/emergency-requests/{emergency_id} | View emergency request details | 200 |
| POST /api/v1/emergency-requests/{emergency_id}/approve | Approve under the emergency policy | 201 |
| POST /api/v1/emergency-requests/{emergency_id}/activate | Require MFA and activate a limited-duration emergency grant | 200 |
| POST /api/v1/emergency-requests/{emergency_id}/revoke | Revoke emergency access immediately | 202 |
| GET /api/v1/emergency-requests/{emergency_id}/review | View the required post-access review | 200 |

Emergency access requires mandatory justification, step-up or MFA, a maximum bounded duration, immediate notification, full recording coverage, immutable evidence, and post-access review. It does not bypass role, scope, audit, or target-account controls and is never a general substitute for the normal approval workflow.

### Integration and notification APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/integrations | List configured integrations | 200 |
| POST /api/v1/integrations | Register an integration | 201 |
| GET /api/v1/integrations/{integration_id} | View safe integration metadata | 200 |
| PATCH /api/v1/integrations/{integration_id} | Update allowed configuration fields | 200 |
| POST /api/v1/integrations/{integration_id}/test | Test configured connectivity | 202 |
| POST /api/v1/integrations/{integration_id}/sync | Start synchronization | 202 |
| POST /api/v1/integrations/{integration_id}/disable | Disable an integration | 200 |
| GET /api/v1/integrations/{integration_id}/logs | View scoped integration delivery logs | 200 |
| GET /api/v1/notifications | List notifications for the caller | 200 |
| POST /api/v1/notifications/{notification_id}/read | Mark a notification as read | 200 |
| POST /api/v1/notifications/read-all | Mark all visible notifications as read | 200 |
| GET /api/v1/admin/notification-channels | List notification channels | 200 |
| POST /api/v1/admin/notification-channels | Configure a notification channel | 201 |
| GET /api/v1/admin/webhooks | List webhooks | 200 |
| POST /api/v1/admin/webhooks | Register a webhook | 201 |
| PATCH /api/v1/admin/webhooks/{webhook_id} | Update a webhook | 200 |
| POST /api/v1/admin/webhooks/{webhook_id}/test | Test a webhook | 202 |
| GET /api/v1/admin/webhooks/{webhook_id}/deliveries | List delivery history | 200 |

Typical integrations include Active Directory/LDAP, Entra ID, SIEM, ticketing, SMTP, syslog, webhooks, cloud providers, Kubernetes, and HSM or vault services. Notification events include requests, approvals, session start/end, rotation failure, emergency activation, gateway loss, policy changes, and suspicious privileged activity. Webhooks use HMAC signatures, timestamp validation, replay protection, bounded retries, and dead-letter handling. Secrets and signing keys are never included in integration responses.

### Reporting, compliance, and evidence APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/reports | List available reports permitted by scope | 200 |
| POST /api/v1/reports/generate | Generate a scoped evidence report asynchronously | 202 |
| GET /api/v1/reports/{report_id} | Read report generation status | 200 |
| GET /api/v1/reports/{report_id}/download | Retrieve an expiring download reference | 200 |
| GET /api/v1/audit-events/{event_id} | View permitted audit event details | 200 |
| GET /api/v1/audit-events/verify | Verify a permitted range of audit integrity evidence | 200 |
| GET /api/v1/compliance/summary | Read compliance summary | 200 |
| GET /api/v1/compliance/access-review | Read current access-review findings | 200 |
| POST /api/v1/compliance/access-reviews | Start a scoped access review | 201 |
| POST /api/v1/compliance/access-reviews/{review_id}/decisions | Record an access-review decision | 201 |

Available reports include privileged-user activity, approval history, active sessions, credential-rotation compliance, inactive accounts, emergency access, failed logins, recording coverage, and policy violations. Audit evidence is append-oriented and administrators cannot silently modify or delete it. Where implemented, hash chaining, restricted write identities, independent retention, and integrity verification are required.

### Platform health and administration APIs

| Method and path | Purpose and access | Success |
| --- | --- | --- |
| GET /api/v1/health | Application health summary | 200 or 503 |
| GET /api/v1/health/ready | Readiness for serving traffic | 200 or 503 |
| GET /api/v1/health/live | Process liveness | 200 |
| GET /api/v1/admin/system/info | Read safe system and component information | 200 |
| GET /api/v1/admin/system/config | Read safe configuration metadata | 200 |
| PATCH /api/v1/admin/system/config | Update allowlisted system configuration | 200 |
| GET /api/v1/admin/system/services | Read service status | 200 |
| GET /api/v1/admin/system/jobs | Read background job status | 200 |
| GET /api/v1/admin/system/storage | Read storage utilization | 200 |
| GET /api/v1/admin/system/metrics | Read operational metrics permitted for the caller | 200 |

Health responses must expose neither credentials nor secrets and must not disclose internal hostnames, tokens, stack details, or sensitive infrastructure topology. Detailed dependencies and metrics remain subject to administrator scope.

### Internal gateway lifecycle APIs

| Method and path | Purpose | Success |
| --- | --- | --- |
| POST /internal/v1/gateways/register | Enroll a gateway identity with zone assignment | 201 |
| POST /internal/v1/gateways/heartbeat | Report gateway health and active service state | 200 |
| GET /internal/v1/gateways | Read gateway inventory for authorized control-plane callers | 200 |
| GET /internal/v1/gateways/{gateway_id}/health | Read gateway health | 200 |
| POST /internal/v1/gateways/{gateway_id}/drain | Stop accepting new sessions | 202 |
| POST /internal/v1/gateways/{gateway_id}/revoke | Revoke gateway identity | 202 |

Gateway enrollment, certificate rotation, revocation, heartbeat, and zone assignment are lifecycle operations. Administrative routes require administrator authorization; internal routes require enrolled gateway or control-plane service identity. Revocation must invalidate future credential leases and launches promptly, and no user browser route retrieves gateway or vault credentials.

## Administration and gateway interfaces

| Method and path | Contract | Success |
| --- | --- | --- |
| POST /api/v1/admin/change-proposals | Submit a scoped inventory, role, or policy change with resource type, expected version, intended change, and reason | 201 |
| GET /api/v1/admin/change-proposals/{proposal_id} | Read the scoped proposal and review state | 200 |
| POST /api/v1/admin/change-proposals/{proposal_id}/decisions | Apply or reject an independently reviewed change. Reject stale versions | 201 |
| POST /internal/v1/launches/consume | Assigned gateway presents the launch and trusted requester binding. Return session ID, target reference, credential authorization reference, and lease deadline | 201 |
| POST /internal/v1/sessions/{session_id}/renew | Confirm current authorization and return a deadline bounded by grant expiry | 200 |
| POST /internal/v1/sessions/{session_id}/events | Accept gateway lifecycle evidence with stable source event ID, session sequence, state, reason code, and occurrence time. Deduplicate retries | 202 |

Internal routes authorize by enrolled service identity and assigned zone. A renewal failure never extends the prior deadline. An authenticated control channel can deliver termination instructions promptly. Renewal checks authoritative status even when delivery is delayed.

### Reviewed asset policy

Submit a `policy` change proposal with the asset ID as `resource_id`. Use `expected_version: 0` for the first policy and the current version number for a replacement. The `change_payload` has this form.

~~~json
{
  "allowed_target_account_ids": ["account_demo"],
  "max_duration_seconds": 3600,
  "required_approvals": 2,
  "requires_ticket": true
}
~~~

The policy requires one to five distinct, ordered approvals. Request duration is limited by both the policy and the target account. The policy or the target account can require a ticket. Applying the proposal requires a different reviewer with scope on the asset, and the existing decision endpoint returns `policy_version_id` and `policy_version` with HTTP 200 for a policy publication. A competing proposal based on the superseded version returns `409 STALE_POLICY_VERSION`.

Submission requires a published policy and returns the `policy_version_id` pinned to the request revision. Approval, launch issuance, and launch consumption verify that this version is still current. A superseded or unversioned revision needs a fresh request. Publishing a replacement does not itself terminate sessions that were already established.

## Response and validation conventions

- Collection responses provide items and an optional opaque next cursor. Apply resource scope before pagination.
- Request responses include request ID, revision ID, state, scope, and timestamps. Decision submission includes the expected revision ID and decision. A rejection requires a reason.
- A valid decision may leave a request pending when more approvals are required. Final approval atomically issues a grant and returns its reference.
- Grant responses include subject, target, target account, effective window, and status. Session responses include grant ID, gateway reference, status, a reason code when present, and observed timestamps. Keep target authentication material in the credential service.
- Recheck permission at playback, export creation, and export retrieval. Use expiring references and audit permitted and denied access. Playback authorization does not grant export permission.

### API contract conventions

- Publish the public and internal contracts as OpenAPI 3.1 documents. Generated schemas must be consistent with validation behavior and security requirements; breaking changes require a new major API version.
- Keep `/api/v1` backward-compatible. Additive fields and endpoints are preferred. A breaking schema or state-transition change is introduced under a new version and documented with a migration period.
- Use cursor-based pagination for collections. Every collection response includes `items` and an opaque `next_cursor` only when another page exists. Ordering must be deterministic and applied after resource scoping.
- Support optimistic concurrency for requests, policies, roles, accounts, assets, integrations, rotation policies, and system configuration. Use `ETag` and `If-Match` for HTTP resources and `expected_version` for explicit proposal-style mutations. A stale update returns `409 STALE_RESOURCE_VERSION`.
- Use a request ID/correlation ID header on every call, for example `X-Request-ID`. Accept a caller-provided ID only under the configured format and length; otherwise generate one. Propagate it through internal services and audit evidence, but never return secrets or customer payloads with it.
- Return a consistent error object:

~~~json
{
  "code": "STALE_RESOURCE_VERSION",
  "message": "The resource changed after it was read.",
  "request_id": "req_demo",
  "details": []
}
~~~

- Apply rate limits per principal and service identity, with tighter limits for authentication, MFA, emergency access, credential operations, launch creation, and internal gateway enrollment. Return `429` for exceeded limits and include retry timing.
- Apply request-size and response-size limits. Reject oversized, malformed, unknown-sensitive, or unauthorized credential fields with validation or authorization errors rather than partially processing them.
- Authentication and authorization failures are audited consistently. Do not include a reason that reveals hidden roles, scopes, assets, or approval state.
- Require idempotency keys for all state-changing operations that can create resources, issue grants or credentials, make decisions, publish policies, adopt discovery findings, start jobs, send notifications, or export evidence. Replay matching key and payload; reject a reused key with a changed payload with `409 IDENTITY_KEY_REUSE`.
- Idempotency records include key scope, principal/service identity, method, canonical payload hash, status, and bounded retention. Sensitive payload values remain in protected storage and do not become idempotency or audit payload fields.
- Record approval delegation, grant expiration, emergency access activation/revocation, credential lease issue/revoke/acknowledge, and gateway identity lifecycle in immutable audit evidence.
