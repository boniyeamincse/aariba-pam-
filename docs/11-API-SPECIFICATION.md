# API specification

> Proposed v1 HTTP contract · 2026-11-22

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

## Example request

~~~json
{
  "asset_id": "asset_demo",
  "target_account_id": "account_demo",
  "requested_start_at": "2026-12-01T08:00:00Z",
  "requested_end_at": "2026-12-01T09:00:00Z",
  "justification": "Validate restart behavior in the pilot lab",
  "ticket_ref": "DEMO-12"
}
~~~

## Errors, retries, and session launch

- Return 401 for unauthenticated calls, 403 for forbidden actions where the resource is visible, 404 for missing or concealed resources, 409 for invalid state or conflicting retries, 422 for validation failures, and 503 when required authorization or evidence services cannot satisfy the operation.
- Use a consistent error body with machine-readable code, user-safe message, and request ID. Never expose secrets, stack traces, or concealed resource details.
- Require an idempotency key for request submissions, revisions, approval and administration decisions, and export creation. Replay the same key and payload without repeating the transition. A changed payload under the same key returns 409.
- Treat a pending termination as accepted work. The session record changes to Ended only when gateway termination is confirmed.
- Bind launch consumption to the grant owner, designated gateway, time window, and one launch. Deliver launch data through an authenticated channel. Keep launch secrets out of URLs, logs, persistence in browser storage, and audit payloads. After an ambiguous launch-creation failure, fetch existing session status before trying a fresh launch.

See [database constraints](10-DATABASE-DESIGN.md) and [workflow states](08-USER-WORKFLOW.md).
