# GitHub Copilot Instructions for Ariba PAM

Ariba PAM is an enterprise Zero Standing Privilege (ZSP) Privileged Access Management platform.
All code generated or modified must strictly follow the architectural patterns, security invariants, and directory structures defined here.

## 1. Directory Structure & Layer Responsibilities

```
ariba_pam/
├── src/ariba_pam/                # Python Control Plane (FastAPI, SQLAlchemy, Alembic)
│   ├── api/                      # Presentation Layer (HTTP controllers, routing, DTOs)
│   │   ├── router.py             # Root API router assembling all sub-routers
│   │   ├── schemas.py            # Pydantic v2 input/output schemas (DTOs)
│   │   ├── v1/                   # Public REST API v1 endpoints
│   │   │   ├── admin.py          # Administrative proposals, reviews, system config
│   │   │   ├── approvals.py      # Multi-step approval decisions & queue
│   │   │   ├── assets.py         # Scoped asset catalog & target inventory
│   │   │   ├── audit.py          # Audit log retrieval & playback authorization
│   │   │   ├── auth.py           # OIDC auth, token exchange, IdP disablement events
│   │   │   ├── grants.py         # Ephemeral grant lifecycles & launch tokens
│   │   │   ├── requests.py       # Access requests & immutable revision lifecycle
│   │   │   └── sessions.py       # Active and historic session tracking
│   │   └── internal/             # Internal control plane routes (Gateway communication)
│   │       └── gateway.py        # Gateway token validation, heartbeat, session state updates
│   ├── core/                     # Cross-Cutting Infrastructure
│   │   ├── errors.py             # Centralized application exception definitions
│   │   ├── idempotency.py        # Idempotency key caching and replay protection
│   │   ├── scoping.py            # Hierarchical resource scope evaluation & matching
│   │   └── security.py           # JWT signing/validation, cryptographic verification
│   ├── db/                       # Data Persistence Layer
│   │   ├── base.py               # DeclarativeBase, UUID generators, timestamp mixins
│   │   ├── models.py             # SQLAlchemy ORM entity models with relationships
│   │   └── session.py            # Database engine, sessionmaker, transaction utilities
│   ├── services/                 # Domain / Business Logic Layer (Clean Architecture)
│   │   ├── audit.py              # Transactional outbox event publisher & evidence tracking
│   │   ├── auth.py               # Principal authentication, assurance checks, disablement
│   │   ├── notifications.py      # Scoped notification delivery and retry logic
│   │   └── policies.py           # Access policy evaluation, validation, and enforcement
│   ├── config.py                 # Pydantic BaseSettings environment configuration
│   ├── main.py                   # FastAPI application factory, middleware, lifecycle
│   ├── portal.py                 # Lightweight lab portal router
│   ├── portal_assets/            # Lab UI assets (catalog.html, catalog.js, catalog.css)
│   └── lab_seed.py               # Deterministic synthetic test fixture seeder
├── gateway/                      # Go SSH Session Gateway Daemon
│   ├── go.mod, go.sum            # Go module definitions
│   ├── config.go                 # Gateway configuration & environment variables
│   ├── client.go                 # Secure HTTP client to Control Plane with mutual secret
│   ├── hostkey.go                # Target SSH host key verification & SHA256 pinning
│   ├── server.go                 # SSH bastion listener, connection acceptance, handshake
│   ├── session.go                # Active session watcher, local lease enforcement, pty proxy
│   └── gateway_test.go           # Go test suite for host key pinning & lease expiry
├── web/                          # Enterprise Web Console (Next.js, TypeScript, Tailwind)
│   ├── app/                      # Next.js App Router pages and layouts
│   ├── components/               # UI components (shadcn/ui primitives, modals, tables)
│   ├── hooks/                    # Custom React hooks (TanStack Query hooks)
│   └── lib/                      # Type-safe API client generated from openapi.yaml
├── docs/                         # Design Baseline (Docs 01-18 + openapi.yaml)
├── decisions/                    # Architecture Decision Records (ADR-001 through ADR-010)
├── tasks/                        # Workflow task tracking (TODO.md, IN-PROGRESS.md, COMPLETED.md)
├── tests/                        # Automated Pytest Suite
│   ├── conftest.py               # Database fixtures, mocked OIDC, synthetic identities
│   └── test_*.py                 # Unit and integration test suites
└── alembic/                      # Database Schema Migrations
```

## 2. Mandatory Coding Conventions & Invariants

### A. Layering Isolation
- **No Database Queries in API Routes**: `api/` routes must only parse requests, call `services/`, and return response schemas.
- **Transactional Outbox**: All audit events must be written atomically within the same database transaction as the business operation (`AuditOutboxService.record_event`).
- **No Direct Secrets**: Secrets must never be stored in source code. Use environment variables with `ariba_pam.config.Settings`.

### B. Security Invariants
- **Default Deny**: Unless explicitly permitted by policy and resource scope, all access is denied.
- **Identifier Concealment**: Attempting to query an asset, session, or request outside the user's resource scope must return **HTTP 404 Not Found**, NEVER HTTP 403 Forbidden, to prevent enumeration attacks.
- **Separation of Duties (SoD)**:
  - Requesters can NEVER approve their own requests.
  - Approvers can NEVER self-grant access.
  - PAM Administrators cannot access evidence custody or CA signing keys (Custodian boundaries).
- **Idempotency**: All mutating operations (`POST /requests`, `POST /approvals`, `POST /grants/launch`) must support and enforce `X-Idempotency-Key` deduplication.

### C. Language & Framework Standards
- **Python**: Python 3.11+, typed annotations everywhere, Pydantic v2 schemas, SQLAlchemy 2.0 style queries (`select()`).
- **Go**: Idiomatic Go, error wrapping, explicit context cancellation, no goroutine leaks on session termination.
- **TypeScript / Next.js**: Strict typing, functional React components, accessible ARIA roles.
