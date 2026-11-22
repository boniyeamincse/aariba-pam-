# Ariba PAM AI Agent & Developer Guidelines

This repository contains **Ariba PAM**, an enterprise Zero Standing Privilege (ZSP) Privileged Access Management platform.
All AI assistants (Antigravity, Codex, OpenCode, Claude, Copilot) and human engineers must adhere strictly to the repository architecture, standard file conventions, and security invariants described here.

---

## 1. Enterprise Project Taxonomy & Directory Layout

Every file must be placed in its designated layer according to Clean Architecture principles:

```
ariba_pam/
├── .github/                      # CI/CD workflows and Copilot instructions
│   └── copilot-instructions.md   # Guidelines for GitHub Copilot
├── alembic/                      # Database migrations
│   ├── versions/                 # Versioned migration scripts (0001_..., 0002_...)
│   └── env.py                    # Migration execution environment
├── decisions/                    # Architecture Decision Records
│   └── architecture-decisions.md # Formal ADR log (ADR-001 to ADR-010+)
├── docs/                         # Canonical 18-File Architecture Baseline
│   ├── 01-PROJECT-OVERVIEW.md    # Problem statement, boundaries, pilot scope
│   ├── 02-PRODUCT-REQUIREMENTS.md# BR-01..06, FR-01..11, NFR-01..08 requirements
│   ├── 03-SYSTEM-ARCHITECTURE.md # Microservices, Web Console, network topologies
│   ├── 04-API-SPECIFICATION.md   # REST API contracts and error responses
│   ├── 05-DATABASE-SCHEMA.md     # Relational schema, indexes, and constraints
│   ├── 06-IDENTITY-AND-ACCESS-MANAGEMENT.md # OIDC, MFA, disablement propagation
│   ├── 07-USER-ROLES-AND-PERMISSIONS.md     # Hybrid RBAC+ABAC, Custodian boundaries
│   ├── 08-AUTHORIZATION-POLICY-ENGINE.md    # Decision engine, default deny rules
│   ├── 09-RESOURCE-SCOPE-MANAGEMENT.md      # Hierarchical resource scope tree
│   ├── 10-SEPARATION-OF-DUTIES.md           # Conflict matrices and exception rules
│   ├── 11-APPROVAL-AND-DELEGATION.md        # Workflows and delegation guardrails
│   ├── 12-CREDENTIAL-VAULT-DESIGN.md        # Ephemeral SSH CA & Vault injection
│   ├── 13-SECURITY-REQUIREMENTS.md          # Threat model & 10 core security controls
│   ├── 14-SESSION-GATEWAY-DESIGN.md         # Go SSH gateway proxy architecture
│   ├── 15-AUDIT-AND-EVIDENCE-MANAGEMENT.md  # Outbox pattern & WORM custody
│   ├── 16-INTEGRATION-ARCHITECTURE.md       # IdP, SIEM (Wazuh), SOC integrations
│   ├── 17-WORKFLOW-STATE-MACHINE.md         # State machines and lifecycle transitions
│   ├── 18-DEVELOPMENT-ROADMAP.md            # Phased implementation roadmap
│   └── openapi.yaml              # OpenAPI 3.1 specification
├── gateway/                      # Go SSH Session Gateway Service
│   ├── go.mod, go.sum            # Go dependencies
│   ├── config.go                 # Gateway runtime configuration
│   ├── client.go                 # Mutual-secret authenticated Control Plane client
│   ├── hostkey.go                # Host key verification & SHA256 pinning
│   ├── server.go                 # SSH bastion listener & connection handshake
│   ├── session.go                # Bounded local lease watcher & pty proxy
│   └── gateway_test.go           # Gateway unit and integration tests
├── src/ariba_pam/                # Python Control Plane (FastAPI + SQLAlchemy)
│   ├── api/                      # Presentation Layer (HTTP routing & DTOs only)
│   │   ├── router.py             # Root FastAPI router
│   │   ├── schemas.py            # Pydantic v2 input and output models
│   │   ├── v1/                   # Public v1 endpoints
│   │   │   ├── admin.py          # Administrative proposals and system settings
│   │   │   ├── approvals.py      # Multi-step approvals and queue endpoints
│   │   │   ├── assets.py         # Scoped asset catalog
│   │   │   ├── audit.py          # Audit log retrieval and export authorization
│   │   │   ├── auth.py           # Authentication, tokens, IdP disablement webhook
│   │   │   ├── grants.py         # Access grants and launch token issuance
│   │   │   ├── requests.py       # Access requests and immutable revision lifecycles
│   │   │   └── sessions.py       # Active and historical session records
│   │   └── internal/             # Private microservice routes
│   │       └── gateway.py        # Gateway token validation & event ingestion
│   ├── core/                     # Cross-Cutting Core Utilities
│   │   ├── errors.py             # Standardized domain exception classes
│   │   ├── idempotency.py        # Idempotency token storage & replay guard
│   │   ├── scoping.py            # Resource scope containment & evaluation engine
│   │   └── security.py           # JWT signing/validation, cryptographic helpers
│   ├── db/                       # Persistence Layer
│   │   ├── base.py               # DeclarativeBase, Common Mixins (UUID, Timestamps)
│   │   ├── models.py             # SQLAlchemy ORM entity models
│   │   └── session.py            # Database engine and transaction context managers
│   ├── services/                 # Domain Business Logic (Clean Architecture)
│   │   ├── audit.py              # Transactional outbox service (atomic with DB writes)
│   │   ├── auth.py               # Identity, session tokens, disablement propagation
│   │   ├── notifications.py      # Resilient notification dispatcher
│   │   └── policies.py           # Access policy and boundary validation
│   ├── portal_assets/            # Lab portal static files (catalog.html, js, css)
│   ├── portal.py                 # Lab portal endpoint router
│   ├── config.py                 # Pydantic BaseSettings environment configuration
│   ├── main.py                   # FastAPI application initialization & middleware
│   └── lab_seed.py               # Synthetic test data fixture loader
├── tasks/                        # Task Tracking
│   ├── TODO.md                   # Unstarted roadmap tasks
│   ├── IN-PROGRESS.md            # Active tasks with assignee & target evidence
│   └── COMPLETED.md             # Completed tasks with verified test evidence
├── tests/                        # Automated Pytest Suite
│   ├── conftest.py               # Pytest fixtures and mock dependencies
│   └── test_*.py                 # Unit and integration test suites
├── web/                          # Enterprise Web Console (Next.js 14/15, TypeScript)
│   ├── app/                      # App router layouts and pages
│   ├── components/               # Accessible UI components (shadcn/ui)
│   ├── hooks/                    # TanStack Query data hooks
│   └── lib/                      # Generated OpenAPI TypeScript client
├── AGENTS.md                     # Agentic coding instructions (this file)
├── CLAUDE.md                     # Instructions for Claude Code / OpenCode
├── README.md                     # Repository entry point and document index
└── pyproject.toml                # Python package metadata and dependencies
```

---

## 2. Architectural Layering Rules (Strict Separation of Concerns)

1. **API Layer (`src/ariba_pam/api/`)**:
   - MUST only perform HTTP request validation, call the appropriate domain service in `services/`, and return response DTOs (`schemas.py`).
   - MUST NOT execute raw SQLAlchemy queries or business logic directly inside route handlers.
2. **Domain Service Layer (`src/ariba_pam/services/`)**:
   - Contains pure business logic, state machine validations, and workflow orchestration.
   - Responsible for committing atomic transactions and writing audit events to `AuditOutbox`.
3. **Core Layer (`src/ariba_pam/core/`)**:
   - Houses reusable security, scoping, and infrastructure algorithms.
   - Does NOT depend on high-level API routes.
4. **Persistence Layer (`src/ariba_pam/db/`)**:
   - SQLAlchemy ORM models only. Foreign keys and indexes must be explicitly defined.

---

## 3. Mandatory Security Invariants

All AI assistants MUST enforce these security rules when creating or modifying code:

1. **Default Deny**: All actions are denied by default unless an active, matching access policy and role permission exists.
2. **Identifier Concealment (Anti-Enumeration)**:
   - When a user queries an asset, request, or session outside their assigned resource scope, the system MUST return **HTTP 404 Not Found** (never HTTP 403 Forbidden).
3. **Separation of Duties (SoD)**:
   - A requester can never approve their own access request.
   - An approver can never approve a request if they are designated as the session user.
   - PAM Administrators cannot manage signing keys or evidence storage (partitioned to Signing Custodian and Evidence Custodian).
4. **Transactional Audit Outbox**:
   - Every state change (create request, approve, issue grant, launch session, revoke) MUST write an audit log row to the `audit_outbox` table in the *same* database transaction as the state change.
5. **Idempotency**:
   - All mutating operations must accept an `X-Idempotency-Key` header and return cached responses on duplicate submissions with the same key.
6. **No Real Secrets**:
   - Source code must NEVER contain hardcoded passwords, private keys, or API tokens. Synthetic test credentials only.

---

## 4. Coding & Testing Standards

- **Python**: PEP 8, full type annotations, Pydantic v2 schemas, SQLAlchemy 2.0 select syntax. Run `DEBUG=false pytest -v`.
- **Go**: Idiomatic Go, explicit error handling, context propagation, zero goroutine leaks. Run `go test -v ./...` in `gateway/`.
- **TypeScript**: Strict mode, functional React components, accessible ARIA roles.
- **Traceability**: Preserve stable requirement IDs (`BR-xx`, `FR-xx`, `NFR-xx`, `SEC-xx`, `ADR-xx`, `T-xx`).
