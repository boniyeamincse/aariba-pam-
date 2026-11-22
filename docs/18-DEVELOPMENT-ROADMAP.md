# 18 · Development Roadmap: Ariba PAM

> Delivery Sequences, Milestones & Phase Backlog · 2026-11-22

The delivery roadmap organizes development into sequential, test-verified phases. Progression between phases requires passing all applicable pilot test catalog checks (`T-01` through `T-11`).

---

## Roadmap Overview

```
Phase 0 ──▶ Phase 1 ──▶ Phase 2 ──▶ Phase 3 ──▶ Phase 4 ──▶ Phase 5 ──▶ Phase 6 ──▶ Phase 7 ──▶ Phase 8
Discovery   Core        Workflow    SSH Gateway Credential  Production  Windows     Security    Scale & HA
& Design    Platform    & Portal    in Lab      Custody     Pilot       RDP Proxy   SIEM/ITSM   Disaster Rec
[DONE]      [DONE]      [DONE]      [DONE]      [DONE]      [DONE]      [DONE]      [DONE]      [DONE]
```

---

## Phase Breakdown & Status

### Phase 0 · Discovery & Baseline Architecture [COMPLETED]
- Establish product vision, problem space, and architecture baseline.
- Author 18 foundational design specifications (`docs/01` to `docs/18`).
- Formalize decision log (`ADR-001` through `ADR-010`) and development task backlog.

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

### Phase 3 · SSH Gateway in the Lab [COMPLETED]
- Zone-bound Go SSH Gateway service identity (`gateway/server.go`, `config.go`).
- Strict target host key verification matching SHA256 fingerprints before authentication (`gateway/hostkey.go`).
- Bounded lease watcher and local autonomous expiry enforcement (`gateway/session.go`).
- Operator grant revocation and session termination propagation.
- IdP account disablement signal consumption and session severance within 60s.
- Status reconciliation and terminal session protection.
- Complete single-use launch issuance and atomic consumption verification (`P3-02`, `P3-03`).
- Gateway lab milestone exit verification (`P3-09`).

### Phase 4 · Credential Custody [COMPLETED]
- **P4-01**: Isolated SSH certificate signing (issues short-lived Ed25519 OpenSSH user certificates bounded to grant window and target account; gateway has zero access to CA private key).
- **P4-02**: CA key rollover, dual-trust retention, and multi-custodian recovery rehearsal (`T-06`).
- **P4-03**: Scoped HashiCorp Vault credential integration for stored-credential targets with automatic post-session rotation.

### Phase 5 · Evidence & Production Pilot [COMPLETED]
- **P5-01**: Delivery of audit and session records to independently administered WORM storage (S3 Object Lock).
- **P5-02**: Asciinema v2 terminal recording capture with SHA256 integrity block digests.
- **P5-03**: Gateway recording buffer pause/terminate handling on evidence delivery loss (`T-07`).
- **P5-04 & P5-05**: Scoped audit search, streaming playback, and auditable evidence exports (`T-08`).
- **P5-CONSOLE**: Built the Next.js 14 / TypeScript Enterprise Web Console (`web/`) with Tailwind CSS, `shadcn/ui`, `xterm.js` live web terminal, and `asciinema-player` session replay.
- **P5-06**: SOC alerting and health monitoring integration (`T-10`).
- **P5-07 & P5-08**: Backup/restore rehearsal (RTO ≤ 15m, RPO ≤ 1m) and out-of-band emergency break-glass drills (`T-09`).
- **P5-09**: Verified capacity, OpenSSH client compatibility, and deployment rollback (`T-10`).
- **P5-10**: Phase 5 production pilot approval review & formal `ADR-011` acceptance (All `T-01` through `T-11` verified).

### Phase 6 · Windows Infrastructure & RDP Proxy [COMPLETED]
- **P6-01**: Evaluated and selected RDP architecture under `ADR-012`, integrating TLS tunneling, non-exportable certificate verification, and clipboard/drive restriction policies.
- **P6-02**: Built Go RDP tunnel stream interception, automatic session lease renewal/termination watcher, and post-session Vault credential auto-rotation.

### Phase 7 · Enterprise SIEM, SOC & Identity Federation [COMPLETED]
- **P7-01**: Implemented Wazuh SIEM adapter (`ADR-013`) with OSSEC event mapping, cryptographic SHA-256 deduplication, and dead-letter retry queue.
- **P7-02**: Implemented Ariba SOC event streaming (`ADR-014`) with priority channels (`P1_CRITICAL` through `P4_INFO`), runbook enrichment, and circuit breaker protection.
- **P7-03**: Evaluated and implemented secondary IdP federation (`ADR-015`) with signed webhook deprovisioning and SCIM 2.0 user deactivation.
- **P7-04**: Validated ITSM service desk integration (`ADR-016`) enforcing ticket reference verification and cache SLAs.

### Phase 8 · High Availability, Rolling Upgrades & Scale Disaster Recovery [COMPLETED]
- **P8-01**: Validated multi-node Control Plane clustering and zone-redundant gateway failover (`ADR-017`) with < 1.5s failure detection and least-connections routing.
- **P8-02**: Implemented zero-downtime rolling upgrades and Expand/Contract schema evolution (`ADR-018`) with 0% active session loss during rolling node drains and rollbacks.
- **P8-03**: Benchmarked disaster recovery, multi-custodian split-key recovery, and forensic evidence retrieval at approved expanded capacity (500 assets, 2000 users, 5000 sessions, 10000 audit events) under `ADR-019`.

---

## Post-Roadmap · Day-2 Enterprise Operations & Continuous Assurance

With all core roadmap phases (0 through 8) delivered and verified:
1. **Continuous Compliance & Evidence Custody**: Automated daily WORM export integrity verification and immutable cryptographic ledger checks.
2. **Dynamic Machine Learning Anomaly Detection**: Behavioral typing rhythm and keystroke analysis for zero-trust session anomaly scoring.
3. **Multi-Cloud HSM Root of Trust**: Native hardware security module (AWS CloudHSM / Azure Key Vault Managed HSM) integration for signing custodian quorum.
