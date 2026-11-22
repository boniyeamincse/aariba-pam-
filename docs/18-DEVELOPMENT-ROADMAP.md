# 18 · Development Roadmap: Ariba PAM

> Delivery Sequences, Milestones & Phase Backlog · 2026-11-22

The delivery roadmap organizes development into sequential, test-verified phases. Progression between phases requires passing all applicable pilot test catalog checks (`T-01` through `T-11`).

---

## Roadmap Overview

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phases 6–8
Discovery   Core        Workflow    SSH Gateway Credential  Production  Deferred
& Design    Platform    & Portal    in Lab      Custody     Pilot       Backlog
[DONE]      [DONE]      [DONE]      [ACTIVE]    [NEXT]      [PLANNED]   [FUTURE]
```

---

## Phase Breakdown & Status

### Phase 0 · Discovery & Baseline Architecture [COMPLETED]
- Establish product vision, problem space, and architecture baseline.
- Author 18 foundational design specifications (`docs/01` to `docs/18`).
- Formalize decision log (`ADR-001` through `ADR-009`) and development task backlog.

### Phase 1 · Core Platform [COMPLETED]
- Scaffold FastAPI control plane service and Pydantic configuration (`ariba_pam.main`, `config`).
- Implement SQLAlchemy 2.0 relational models and initial Alembic database migrations.
- Workforce authentication with phishing-resistant MFA check (`amr`), session tokens, and `/api/v1/me`.
- Server-side resource-scoped authorization engine (`ScopeChecker`) with 404 identifier concealment.
- Transactional audit outbox ensuring zero dual-writes on database rollback.
- Scoped asset and target inventory query endpoints (`GET /api/v1/assets`).
- Four-eyes administrative change management with self-review rejection.

### Phase 2 · Requests, Approvals & Grants [COMPLETED]
- Reviewed per-asset access policies with fail-closed request authorization (`policies.py`).
- Immutable request revisions (`POST /api/v1/requests`, `/revisions`) and cancellation.
- Scoped approver queue (`GET /api/v1/approvals`) and decision submission (`/decisions`) with SoD self-approval rejection and atomic grant issuance.
- Outbox notification dispatcher with retry resilience and deduplication (`notifications.py`).
- Interactive requester and approver portal flows (`/portal`) with tabbed workspace, request creation, revision replacement, and stale-decision feedback (`catalog.js`, `catalog.html`).

### Phase 3 · SSH Gateway in the Lab [IN PROGRESS]
- Zone-bound Go SSH Gateway service identity (`gateway/server.go`, `config.go`) [DONE].
- Strict target host key verification matching SHA256 fingerprints before authentication [DONE].
- Bounded lease watcher and local autonomous expiry enforcement [DONE].
- Operator grant revocation and session termination propagation [DONE].
- IdP account disablement signal consumption and session severance within 60s [DONE].
- Status reconciliation and terminal session protection [DONE].
- Complete single-use launch issuance and atomic consumption tests (`P3-02`, `P3-03`).
- Gateway lab milestone exit verification (`P3-09`).

### Phase 4 · Credential Custody [NEXT]
- **P4-01**: Isolated SSH certificate signing (issue short-lived OpenSSH certs bounded to grant window and target account; gateway cannot access CA key).
- **P4-02**: CA key rollover, revocation lists, and recovery rehearsal (T-06).
- **P4-03**: Scoped HashiCorp Vault integration for stored-credential targets with automatic post-session rotation.

### Phase 5 · Evidence & Production Pilot [PLANNED]
- **P5-01**: Delivery of audit and session records to independently administered WORM storage (S3 Object Lock).
- **P5-02**: Asciinema v2 terminal recording capture with SHA256 integrity block digests.
- **P5-03**: Gateway recording buffer pause/terminate handling on evidence delivery loss (T-07).
- **P5-04 & P5-05**: Scoped audit search, streaming playback, and auditable evidence exports (T-08).
- **P5-CONSOLE**: Build the Next.js / TypeScript Enterprise Web Console (`web/`) with Tailwind CSS, `shadcn/ui`, `xterm.js` live web terminal, and `asciinema-player` session replay.
- **P5-06**: SOC alerting and health monitoring integration (T-10).
- **P5-07 & P5-08**: Backup/restore rehearsal (RTO ≤ 15m, RPO ≤ 1m) and out-of-band emergency break-glass drills (T-09).
- **P5-10**: Phase 5 production pilot approval review.

### Phases 6–8 · Deferred Backlog [FUTURE]
- **P6-01 & P6-02**: RDP gateway implementation for Windows infrastructure with clipboard and drive restriction.
- **P7-01 & P7-02**: Wazuh SIEM adapter and Ariba SOC event streaming.
- **P7-04**: Direct ITSM ticketing integration (Jira / ServiceNow).
- **P8-01 to P8-03**: Multi-region control-plane and gateway failover and high-capacity scale tests.
