# Ariba PAM Project Guidance for Claude & OpenCode

Follow [AGENTS.md](AGENTS.md) and [.github/copilot-instructions.md](.github/copilot-instructions.md) for full enterprise repository layout, layer separation rules, and mandatory security invariants.

## Quick Summary
- **Product Name**: Ariba PAM (Zero Standing Privilege platform).
- **Core Stacks**:
  - Control Plane: Python 3.11+, FastAPI, SQLAlchemy, Alembic, Pydantic v2.
  - Session Gateway: Go SSH daemon (`gateway/`), host key pinning, bounded local lease enforcement.
  - Enterprise Web Console: Next.js, React, TypeScript, Tailwind CSS, shadcn/ui (`web/`).
- **Layering Rules**:
  - `src/ariba_pam/api/`: Presentation only (FastAPI routers, DTOs). No direct database queries.
  - `src/ariba_pam/services/`: Domain business logic, state machines, and atomic audit outbox writes.
  - `src/ariba_pam/core/`: Security, scoping engine, idempotency, exceptions.
  - `src/ariba_pam/db/`: SQLAlchemy ORM entity models.
- **Security Invariants**:
  - Default Deny.
  - Identifier Concealment (HTTP 404 for out-of-scope resources to prevent enumeration).
  - Separation of Duties (requesters cannot self-approve; approvers cannot self-grant).
  - Transactional Outbox pattern for audit events.
  - Ephemeral credentials (no long-lived keys or passwords).
- **Verification Commands**:
  - Python tests: `DEBUG=false pytest -v`
  - Go gateway tests: `cd gateway && go test -v ./...`
