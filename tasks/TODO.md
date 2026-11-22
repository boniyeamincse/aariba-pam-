# Development tasks

Pick the first unblocked task in the current phase. A dependency is satisfied when its evidence is in [COMPLETED](COMPLETED.md). Assign an owner and move the row to [IN-PROGRESS](IN-PROGRESS.md) when work starts. Later phases are planned backlog. Start them after the relevant phase exit and approvals.

For an implementation task, read the linked requirement or specification, make the smallest change that satisfies the completion check, and run the relevant tests. Record the actual result in the [test result format](../docs/16-TESTING-STRATEGY.md#execution-and-result-record). Commit the reviewed change and documentation together and link the commit and test evidence in the completed row.

The identifiers below refer to [functional requirements](../docs/04-FUNCTIONAL-REQUIREMENTS.md), [non-functional requirements](../docs/05-NON-FUNCTIONAL-REQUIREMENTS.md), [pilot test cases](../docs/16-TESTING-STRATEGY.md#pilot-test-catalog), and [architecture decisions](../decisions/architecture-decisions.md).

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

Detailed design lives in the [control plane module](../specifications/modules/control-plane.md), [database design](../docs/10-DATABASE-DESIGN.md), and [Docker strategy](../docs/15-DOCKER-STRATEGY.md).

Phase 1 tasks and their implementation evidence are listed in [COMPLETED.md](COMPLETED.md).

## Phase 2 · Requests, approvals, and grants

Use the [access workflow](../docs/08-USER-WORKFLOW.md), [API contracts](../docs/11-API-SPECIFICATION.md), and [interaction guidelines](../docs/12-UI-UX-GUIDELINES.md).

All Phase 2 tasks (P2-01 through P2-09) and their implementation evidence have been completed and recorded in [COMPLETED.md](COMPLETED.md).

## Phase 3 · SSH gateway in the lab

Use the [SSH gateway specification](../specifications/modules/ssh-gateway.md). All connections in this phase use isolated synthetic hosts and lab credentials.

| ID | Task | Depends on | Check or reference | Completion check |
| --- | --- | --- | --- | --- |
| P3-02 | Issue a short-lived one-time launch authorization | P3-01 | FR-05, T-04 | Current policy, grant ownership, gateway mapping, and time window are checked. Launch secrets stay out of URLs and logs |
| P3-03 | Atomically consume a launch and reserve a starting session | P3-02 | FR-05, T-04 | Concurrent consumption produces at most one starting session. Expired, revoked, and mismatched launches are denied |
| P3-09 | Verify the gateway lab milestone | P3-07, P3-08 | Phase 3 exit | Record evidence for allowed SSH, denied paths, launch replay, expiry, revocation, and partition tests |

Completed Phase 3 tasks (P3-01, P3-04, P3-05, P3-06, P3-07, P3-08) with verification evidence have been moved to [COMPLETED.md](COMPLETED.md).

## Phase 4 · Credential custody

| ID | Task | Depends on | Check or reference | Completion check |
| --- | --- | --- | --- | --- |
| P4-01 | Integrate isolated SSH certificate signing | P3-09 | FR-06, SEC-05, T-06 | The signer issues only for the approved target account and remaining grant window. The gateway cannot read the CA key |
| P4-02 | Test CA rollover, revocation, and recovery | P4-01 | SEC-05, T-06 | Document and verify the custody and recovery procedure with representative lab hosts |
| P4-03 | Add scoped vault-backed target access when required | P4-01, approved vault need from P0-03 | FR-06, SEC-05, T-06 | Verify scoped secret use, non-disclosure, rotation, and recovery before onboarding any stored-credential target |

## Phase 5 · Evidence and production pilot

Use [audit and recovery](../specifications/modules/audit-and-recovery.md), [security event contracts](../specifications/integrations/security-events.md), and the [pilot test catalog](../docs/16-TESTING-STRATEGY.md#pilot-test-catalog).

| ID | Task | Depends on | Check or reference | Completion check |
| --- | --- | --- | --- | --- |
| P5-01 | Deliver audit events to independently administered storage | P4-02 | FR-08, NFR-07, T-08 | Protected evidence is verifiable. Routine PAM administrators cannot overwrite or delete it |
| P5-02 | Capture and store scoped SSH recordings | P4-02 | FR-08, T-07 | Persist ordered, protected recording segments with integrity metadata and a visible coverage status |
| P5-03 | Handle recording and audit delivery failure at the gateway | P5-01, P5-02 | FR-08, NFR-03, T-07 | Block unsafe launches. Pause forwarding on capture loss and terminate after the approved limit. Alert on evidence gaps |
| P5-04 | Add scoped audit search and recording playback | P5-01, P5-02 | FR-09, NFR-07, T-08 | A scoped reviewer can find and play eligible evidence. Cross-scope attempts return no recording details |
| P5-05 | Add separately scoped recording exports | P5-04 | FR-09, T-08 | Creation and retrieval each recheck scope. Expiring references and export activity are auditable |
| P5-06 | Configure pilot SOC alerts and health monitoring | P5-03 | FR-10, NFR-08, T-07, T-10 | Test alerts for capture, evidence delivery, renewal, and signing failures through the approved receiving path |
| P5-07 | Run backup and restore rehearsal | P5-01, P5-02 | NFR-04, T-09 | Measure RTO and RPO. Verify restored evidence and confirm stale grants stay closed |
| P5-08 | Drill out-of-band emergency access | P5-06 | FR-11, T-09 | Simulate PAM and IdP outage. Record scoped access, SOC notice, independent evidence, review, and cleanup |
| P5-09 | Verify capacity, client compatibility, and deployment rollback | P5-03, P5-05, P5-06 | NFR-05, NFR-08, T-10 | Record latency and capacity under representative load. Verify artifacts, migration, and rollback with existing data |
| P5-10 | Review evidence and approve the limited production pilot | P5-04, P5-05, P5-06, P5-07, P5-08, P5-09, P4-03 for vault-backed targets | Phase 5 exit | Confirm all applicable T-01 through T-11 checks pass. Record approvals from security and infrastructure before enabling approved assets |

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
