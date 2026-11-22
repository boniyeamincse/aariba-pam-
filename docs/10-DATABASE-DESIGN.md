# Database design

> Proposed logical schema · 2026-11-22

PostgreSQL owns transactional application data. Store secret material and raw recordings in their dedicated services. Database rows may reference external objects with scoped identifiers and integrity metadata.

| Entity | Key relationships and invariants |
| --- | --- |
| users | Unique identity provider issuer and stable subject. Track account status and security version |
| roles, permissions, role_assignments | Role assignments relate a user to a role and explicit team, asset, or environment scope |
| assets, target_accounts, gateway_zones | Accounts belong to targets. Store ownership, environment, host trust reference, and gateway zone |
| access_requests, request_revisions | Requests belong to a user. Revisions retain immutable approved fields and policy context. Requested end must follow start |
| approval_steps, approval_decisions | Decisions tie to a revision and step. Store approver, decision, and time. Prevent duplicate votes and enforce independence |
| approval_assignees | Associates eligible principals with a specific step. Recheck each principal's scope when deciding |
| access_policy_versions | Immutable rules, publication time, independently reviewed proposal reference, and unique version number per asset. The highest published version is current |
| admin_change_proposals | Scoped proposed changes, expected resource version, author, reviewer, state, and applied version |
| access_grants | Grant references request revision and approved scope. Store window, revocation and policy information. Limit issuance to one grant per approved revision |
| session_launches, access_sessions | A launch belongs to a grant. Store launch digest, expiry, and consumed time. A session maps uniquely to a consumed launch and assigned gateway |
| recordings | Session, storage object reference, capture state, integrity digest, and retention class |
| recording_exports | Recording reference, requester, authorization scope, status, generated artifact reference, and expiry |
| audit_outbox | Stable event ID, event type, correlation IDs, occurred time, and delivery state. Copy to the independent evidence store |
| idempotency_records | Unique operation, actor, and key within the retention window. Retain request fingerprint and non-sensitive result reference |

## Transactions and retention

- In one transaction, validate the current request revision and eligibility, record a vote, and persist the workflow outcome and outbox events.
- Key each revision by request and revision number. Store the current revision on the request and validate that it belongs to that request. Tie the approved account to its target with a database constraint so competing updates cannot create an invalid pairing.
- Uniquely identify each approval decision by step and principal. Prevent the same actor from satisfying distinct steps where policy requires separate approvers. Insert the grant and final decision together so retry or rollback cannot leave an approved revision without a grant.
- Serialize conflicting mutations on the relevant request or grant. At consume time, verify unchanged authorization and update the launch only if it is valid and unconsumed. Reserve the starting session and persist the launch event in that transaction.
- Store session state and latest accepted gateway sequence separately from raw gateway evidence. Preserve out-of-order end evidence for reconciliation and never allow an older event to reopen a terminal session.
- Index pending approvals by approver scope, grants by subject and effective window, and sessions by grant and gateway. Keep timestamps as UTC instants.
- Prevent routine administrative edits to past decisions and evidence references. Use retention and hold rules approved under the security requirements.
- Add migrations with constraints and representative existing records. Verify that deployment and rollback preserve authorization data and evidence. Consider restore and reconciliation when a migration cannot be rolled back safely.

Migration `0002_access_policy_versions` preserves existing access records. It creates no default policy and does not rewrite placeholder policy references on old revisions. An asset requires independent policy publication before further requests can be authorized.

See [lifecycle states](08-USER-WORKFLOW.md) and [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html).
