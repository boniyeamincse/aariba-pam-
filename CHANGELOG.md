# Changelog

## Unreleased

### Added

- Added Requester and Approver portal flows (`/portal`) with tabbed workspace, access request submission, request revision amendment, cancellation, and SSH session launch dialog (P2-08).
- Added Approver queue review interface with exact revision presentation, approval/rejection recording, and stale-decision conflict detection and recovery (FR-04, T-02, P2-08).
- Implemented `GET /api/v1/sessions/{session_id}` endpoint with server-side scoping and out-of-scope 404 concealment.
- Implemented IdP lifecycle event handler (`POST /api/v1/auth/idp-events`) propagating user account disablement to immediately revoke active/scheduled grants, mark linked sessions for termination, reject ongoing gateway renewals with HTTP 409, and reject subsequent auth calls (P3-07, T-01).
- Guarded gateway session event reconciliation against late or duplicate events reopening ended sessions (P3-08).
- Added the lab sign-in and scoped asset catalog at `/portal`, with synthetic fixtures and browser tests.
- Restricted synthetic sign-in to the lab environment and to pre-enrolled identities.
- Added independently reviewed per-asset access policies. Request approvals and new session launches now require a current published policy version.
- Implemented request revision replacement (`POST /api/v1/requests/{request_id}/revisions`) with optimistic locking against stale revisions, and complete request history retrieval (`GET /api/v1/requests/{request_id}`).
- Implemented transactional idempotency engine (`src/ariba_pam/core/idempotency.py`) supporting `X-Idempotency-Key` and returning HTTP 409 on payload fingerprint conflict.
- Built outbox notification dispatcher (`src/ariba_pam/services/notifications.py`) ensuring network delivery outages preserve decisions, retry attempts are auditable, and duplicate events are deduplicated.
- Implemented the Go SSH Gateway service (`gateway/`) with host key fingerprint verification, single-use launch consumption, bounded lease watcher with active renewal, and local lease expiration enforcement.

### Added

- Scaffolding for Ariba PAM FastAPI control plane service and configuration (`ariba_pam.config`, `ariba_pam.main`).
- Full relational schema in SQLAlchemy 2.0 (`User`, `Role`, `RoleAssignment`, `Asset`, `TargetAccount`, `AccessRequest`, `RequestRevision`, `ApprovalStep`, `ApprovalDecision`, `AccessGrant`, `SessionLaunch`, `AccessSession`, `AuditOutbox`, `AdminChangeProposal`, `IdempotencyRecord`).
- Alembic migration runner and initial migration `0001_initial_schema`.
- Workforce authentication with phishing-resistant MFA assurance validation, session creation, and `/api/v1/me`.
- Server-side resource-scoped authorization (`ScopeChecker`) enforcing default deny and 404 identifier concealment.
- Transactional audit outbox service ensuring atomicity on database rollback and resilient at-least-once delivery.
- Scoped asset and target inventory query endpoints (`GET /api/v1/assets`, `GET /api/v1/assets/{asset_id}`).
- Independent four-eyes administrative change management with self-review rejection and stale proposal protection.
- Complete access request, approval, atomic grant issuance, launch token generation, and internal gateway consumption lifecycle.
- Comprehensive pytest test suite with 18 passing tests covering smoke, migrations, auth, scoping, outbox atomicity, inventory reads, four-eyes review, and full workflow lifecycle.
- Dockerfile and Docker Compose manifests with network isolation for the PostgreSQL database.
