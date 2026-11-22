# Ariba PAM

Ariba PAM is a planned privileged access management platform for controlling and auditing time-limited access to enterprise infrastructure. The first delivery path covers requester identity, approval, policy enforcement, and gateway-mediated Linux SSH.

This repository contains the product and engineering baseline, a Python control plane, and an isolated lab portal.

## Read the documents in order

| Step | Document | What it defines |
| --- | --- | --- |
| 00 | [Vision](docs/00-VISION.md) | Product outcome, audience, and boundaries |
| 01 | [Software idea](docs/01-SOFTWARE-IDEA.md) | Original product foundation and module overview |
| 02 | [Problem statement](docs/02-PROBLEM-STATEMENT.md) | Current risk hypotheses and discovery evidence |
| 03 | [Business requirements](docs/03-BUSINESS-REQUIREMENTS.md) | Outcomes and sponsor acceptance |
| 04 | [Functional requirements](docs/04-FUNCTIONAL-REQUIREMENTS.md) | Required system behavior |
| 05 | [Non-functional requirements](docs/05-NON-FUNCTIONAL-REQUIREMENTS.md) | Measurable service and pilot criteria |
| 06 | [Feature specification](docs/06-FEATURE-SPECIFICATION.md) | Pilot feature behavior and acceptance scenarios |
| 07 | [Roles and permissions](docs/07-USER-ROLES-PERMISSIONS.md) | Scope and separation of duties |
| 08 | [User workflow](docs/08-USER-WORKFLOW.md) | Request, grant, session, and emergency workflows |
| 09 | [System architecture](docs/09-SYSTEM-ARCHITECTURE.md) | Components, traffic paths, and failure behavior |
| 10 | [Database design](docs/10-DATABASE-DESIGN.md) | Entities, constraints, and consistency |
| 11 | [API specification](docs/11-API-SPECIFICATION.md) | Proposed v1 interfaces and errors |
| 12 | [UI/UX guidelines](docs/12-UI-UX-GUIDELINES.md) | Portal navigation, interaction, and state |
| 13 | [Security requirements](docs/13-SECURITY-REQUIREMENTS.md) | Threats, controls, and verification |
| 13A | [Authentication and authorization](docs/authentication-authorization.md) | Identity sources, MFA, RBAC, resource scope, revocation, and service authorization |
| 14 | [Technology stack](docs/14-TECHNOLOGY-STACK.md) | Proposed components and selection criteria |
| 15 | [Docker strategy](docs/15-DOCKER-STRATEGY.md) | Local, test, and pilot packaging and isolation |
| 16 | [Testing strategy](docs/16-TESTING-STRATEGY.md) | Test layers, pilot checks, and evidence |
| 17 | [Development roadmap](docs/17-DEVELOPMENT-ROADMAP.md) | Delivery sequence and exit criteria |
| 18 | [Future enhancements](docs/18-FUTURE-ENHANCEMENTS.md) | Deferred capabilities and prerequisites |

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
