# Changelog

## Unreleased

### Added

- Added the lab sign-in and scoped asset catalog at `/portal`, with synthetic fixtures and browser tests.
- Restricted synthetic sign-in to the lab environment and to pre-enrolled identities.

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
