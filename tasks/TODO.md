# Development tasks

Pick the first unblocked task in the current phase. A dependency is satisfied when its evidence is in [COMPLETED](COMPLETED.md). Assign an owner and move the row to [IN-PROGRESS](IN-PROGRESS.md) when work starts. Later phases are planned backlog. Start them after the relevant phase exit and approvals.

For an implementation task, read the linked requirement or specification, make the smallest change that satisfies the completion check, and run the relevant tests. Commit the reviewed change and documentation together and link the commit and test evidence in the completed row.

The identifiers below refer to [product requirements](../docs/02-PRODUCT-REQUIREMENTS.md), [functional requirements](../docs/02-PRODUCT-REQUIREMENTS.md#2-functional-requirements-fr), and [architecture decisions](../decisions/architecture-decisions.md).

## Phase 0 · Discovery and design

| ID | Task | Depends on | Proposed owner | Completion check |
| --- | --- | --- | --- | --- |
| P0-01 | Confirm sponsor, teams, pilot assets, and deployment scope | None | Product and infrastructure | Record the accepted asset list, business owners, normal access paths, and ADR-001 disposition |
| P0-02 | Select pilot IdP and MFA policy | P0-01 | IAM | Document identity mapping, assurance criteria, and the disablement signal with its latency budget under ADR-004 |
| P0-03 | Choose target credential and signing custody model | P0-01 | Security and infrastructure | Record target compatibility, CA ownership and recovery, and any vault prerequisites in ADR-003 |
| P0-04 | Review trust boundaries and permission scopes | P0-01, P0-02, P0-03 | PAM engineering and security | Review gateway isolation, approval independence, evidence custody, and failure paths. Record review actions |
| P0-05 | Approve pilot performance, recording, and recovery criteria | P0-01, P0-04 | Pilot sponsor, security, and platform | Record approved timing, load, retention, and recovery targets and owners in the NFR baseline |
| P0-06 | Select lab topology and evidence procedure | P0-04, P0-05 | Platform and QA | Specify isolated networks, synthetic fixtures, selected versions, and where test results will be recorded |
| P0-07 | Conduct Phase 0 exit review | P0-02, P0-03, P0-04, P0-05, P0-06 | Pilot sponsor | Record the decision log review and approval to begin the core platform |

## Phase 1 · Core platform

Detailed design lives in the [control plane module](../specifications/modules/control-plane.md), [database schema](../docs/05-DATABASE-SCHEMA.md), and [system architecture](../docs/03-SYSTEM-ARCHITECTURE.md).

Phase 1 tasks and their implementation evidence are listed in [COMPLETED.md](COMPLETED.md).

## Phase 2 · Requests, approvals, and grants

Use the [workflow state machine](../docs/17-WORKFLOW-STATE-MACHINE.md) and [API specification](../docs/04-API-SPECIFICATION.md).

All Phase 2 tasks (P2-01 through P2-09) and their implementation evidence have been completed and recorded in [COMPLETED.md](COMPLETED.md).

## Phase 3 · SSH gateway in the lab

All Phase 3 tasks (P3-01 through P3-09) and their implementation evidence have been completed and verified in [COMPLETED.md](COMPLETED.md).

## Phase 4 · Credential custody

All Phase 4 tasks (P4-01, P4-02, P4-03) and their implementation evidence have been completed, verified, and recorded in [COMPLETED.md](COMPLETED.md).

## Phase 5 · Evidence and production pilot

Use [audit and recovery](../specifications/modules/audit-and-recovery.md), [security event contracts](../specifications/integrations/security-events.md), and the [pilot test catalog](../docs/16-TESTING-STRATEGY.md#pilot-test-catalog).

All Phase 5 tasks (P5-01 through P5-10) and their implementation evidence have been completed, verified, and recorded in [COMPLETED.md](COMPLETED.md).

## Phases 6–8 · Deferred backlog

Prioritize these after the pilot review. See [future enhancements](../docs/18-FUTURE-ENHANCEMENTS.md).

| ID | Task | Depends on | Completion check |
| --- | --- | --- | --- |
| P6-01 | Select an RDP implementation and Windows lab matrix | P5-10 | Record maintained dependency, supported clients, and policy for clipboard, drive redirection, and recording |
| P6-02 | Validate RDP authorization and evidence in the lab | P6-01 | Demonstrate scoped access, revocation, confirmed termination, and recording failure handling |
| P7-01 | Add a Wazuh event adapter | P5-10 | Verify event filtering, authenticated delivery, deduplication, and observable retry |
| P7-02 | Add an Ariba SOC event adapter | P5-10 | Verify correlation identifiers, routed alerts, and delivery failure monitoring |
| P7-03 | Evaluate an additional IdP | P5-10 | Document assurance mapping and repeat disablement checks for the selected provider |
| P7-04 | Validate an ITSM ticket reference integration | P5-10 | Verify ticket validation, permissions, timeouts, and the access policy when the integration is unavailable |
| P8-01 | Validate control-plane and gateway failover | P5-10 | Measure availability and verify correct authorization during component failure |
| P8-02 | Exercise rolling upgrades and rollback | P8-01 | Verify active-session handling, compatible migrations, and rollback under load |
| P8-03 | Test recovery at the approved expanded capacity | P8-01 | Record restore, key recovery, and evidence retrieval timings for the larger environment |
