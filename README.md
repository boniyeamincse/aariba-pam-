# Ariba PAM

Ariba PAM is a planned privileged access management platform for controlling and auditing time-limited access to enterprise infrastructure. The first delivery path covers requester identity, approval, policy enforcement, and gateway-mediated Linux SSH.

This repository contains the product and engineering baseline. The runtime, deployment configuration, and pilot test evidence will be added as implementation progresses.

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
| 14 | [Technology stack](docs/14-TECHNOLOGY-STACK.md) | Proposed components and selection criteria |
| 15 | [Docker strategy](docs/15-DOCKER-STRATEGY.md) | Local, test, and pilot packaging and isolation |
| 16 | [Testing strategy](docs/16-TESTING-STRATEGY.md) | Test layers, pilot checks, and evidence |
| 17 | [Development roadmap](docs/17-DEVELOPMENT-ROADMAP.md) | Delivery sequence and exit criteria |
| 18 | [Future enhancements](docs/18-FUTURE-ENHANCEMENTS.md) | Deferred capabilities and prerequisites |

## Start Phase 0

1. Review deployment scope, identity provider, signing custody, and pilot criteria in the [decision log](decisions/architecture-decisions.md).
2. Take the first unblocked item in [TODO](tasks/TODO.md) and move it to [IN-PROGRESS](tasks/IN-PROGRESS.md). Record the owner and expected evidence.
3. Move the item to [COMPLETED](tasks/COMPLETED.md) once its evidence is available. Record material changes in the [changelog](CHANGELOG.md).

## Implementation specifications

| Area | Documents |
| --- | --- |
| Modules | [Control plane](specifications/modules/control-plane.md), [SSH gateway](specifications/modules/ssh-gateway.md), [Audit and recovery](specifications/modules/audit-and-recovery.md) |
| Pilot feature | [Interactive SSH access](specifications/features/ssh-access-request.md) |
| Integrations | [Enterprise identity](specifications/integrations/enterprise-identity.md), [Security events](specifications/integrations/security-events.md) |

The [issues directory](issues) is available for local issue records. Follow the [repository instructions](AGENTS.md) when making changes.
