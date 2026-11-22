# Ariba PAM

Ariba PAM is a planned privileged access management platform for controlling and auditing time-limited access to enterprise infrastructure. The first delivery path covers requester identity, approval, policy enforcement, and gateway-mediated Linux SSH.

This repository contains the product and engineering baseline, a Python control plane, and an isolated lab portal.

## Read the documents in order

| Step | Document | What it defines |
| --- | --- | --- |
| 01 | [Project overview](docs/01-PROJECT-OVERVIEW.md) | Vision, problem statement, boundaries, and pilot scope |
| 02 | [Product requirements](docs/02-PRODUCT-REQUIREMENTS.md) | Business (BR), functional (FR), and non-functional (NFR) requirements |
| 03 | [System architecture](docs/03-SYSTEM-ARCHITECTURE.md) | System components, network topologies, and trust boundaries |
| 04 | [API specification](docs/04-API-SPECIFICATION.md) | REST API contract, error handling, and authorization endpoints |
| 05 | [Database schema](docs/05-DATABASE-SCHEMA.md) | Relational data models, constraints, and audit persistence |
| 06 | [Identity and access management](docs/06-IDENTITY-AND-ACCESS-MANAGEMENT.md) | OIDC federation, phishing-resistant MFA, and account disablement propagation |
| 07 | [User roles and permissions](docs/07-USER-ROLES-AND-PERMISSIONS.md) | Hybrid RBAC+ABAC matrix and anti-superuser custodian boundary isolation |
| 08 | [Authorization policy engine](docs/08-AUTHORIZATION-POLICY-ENGINE.md) | Canonical permissions, decision flow, explicit deny, and evaluation pipeline |
| 09 | [Resource scope management](docs/09-RESOURCE-SCOPE-MANAGEMENT.md) | Hierarchical scope tree, containment, and inheritance rules |
| 10 | [Separation of duties](docs/10-SEPARATION-OF-DUTIES.md) | Conflict rules, four-eyes principle, and controlled exception workflows |
| 11 | [Approval and delegation](docs/11-APPROVAL-AND-DELEGATION.md) | Workflow routing, immutable revisions, and 7 delegation rules |
| 12 | [Credential vault design](docs/12-CREDENTIAL-VAULT-DESIGN.md) | Ephemeral SSH certificate authority, key rollover, and vault secret injection |
| 13 | [Security requirements](docs/13-SECURITY-REQUIREMENTS.md) | Threat modeling, 10 core controls, and verification test mapping |
| 13A | [Authentication and authorization](docs/authentication-authorization.md) | Identity sources, MFA, RBAC, resource scope, revocation, and service authorization |
| 11A | [OpenAPI 3.1 specification](docs/openapi.yaml) | Machine-readable v1.1 API routes, schemas, security, and error contracts |
| 14 | [Technology stack](docs/14-TECHNOLOGY-STACK.md) | Proposed components and selection criteria |
| 15 | [Session gateway design](docs/15-SESSION-GATEWAY-DESIGN.md) | Go SSH gateway proxy, host pinning, and bounded local lease enforcement |
| 16 | [Audit and evidence management](docs/16-AUDIT-AND-EVIDENCE-MANAGEMENT.md) | Transactional outbox, terminal recordings, and WORM evidence custody |
| 17 | [Integration architecture](docs/17-INTEGRATION-ARCHITECTURE.md) | Enterprise IdP, Wazuh SIEM, Ariba SOC, and ITSM adapters |
| 18 | [Workflow state machine](docs/18-WORKFLOW-STATE-MACHINE.md) | Object lifecycles, state transition tables, and invariants |
| 19 | [Development roadmap](docs/19-DEVELOPMENT-ROADMAP.md) | Milestone phases, task dependencies, and backlog |

## Start Phase 0

1. Review deployment scope, identity provider, signing custody, and pilot criteria in the [decision log](decisions/architecture-decisions.md).
2. Take the first unblocked item in the [development task backlog](tasks/TODO.md) and move it to [IN-PROGRESS](tasks/IN-PROGRESS.md). Record the owner and expected evidence.
3. Move the item to [COMPLETED](tasks/COMPLETED.md) once its evidence is available. Record material changes in the [changelog](CHANGELOG.md).

## Implementation specifications

| Area | Documents |
| --- | --- |
| Modules | [Control plane](specifications/modules/control-plane.md), [SSH gateway](specifications/modules/ssh-gateway.md), [Audit and recovery](specifications/modules/audit-and-recovery.md) |
| Pilot feature | [Interactive SSH access](specifications/features/ssh-access-request.md) |
| Integrations | [Enterprise identity](specifications/integrations/enterprise-identity.md), [Security events](specifications/integrations/security-events.md) |

## Running and Testing

### Setup and Testing
```bash
# Set up Python virtual environment and dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Run full test suite
DEBUG=false pytest -v
```

### Start the lab portal

~~~bash
export ENVIRONMENT=lab DEBUG=false
alembic upgrade head
python -m ariba_pam.lab_seed
uvicorn ariba_pam.main:app --host 127.0.0.1 --port 8000
~~~

Use only synthetic data in this local lab. Sign in with synthetic email `catalog-demo@example.test` and subject `catalog-demo` to see the scoped inventory. Use `catalog-empty@example.test` and `catalog-empty` to see the empty state. Production sign-in requires the approved enterprise IdP. [Open the lab portal](http://127.0.0.1:8000/portal).

To run the browser checks, install the optional browser dependencies and Chromium.

~~~bash
pip install -e '.[dev,browser]'
python -m playwright install chromium
DEBUG=false python -m pytest tests/test_portal.py tests/test_portal_browser.py
~~~

Set `PAM_TEST_CHROMIUM` to use an existing Chromium executable instead of the Playwright-managed installation.

### Running with Docker Compose
```bash
# Start isolated database and control plane
docker compose up -d
```

The [issues directory](issues) is available for local issue records. Follow the [repository instructions](AGENTS.md) when making changes.
