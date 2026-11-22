# Development roadmap

> Proposed sequence and exit criteria · 2026-11-22

| Phase | Deliverable | Exit criteria |
| --- | --- | --- |
| 0. Discovery and architecture | Agree pilot scope, IdP, target credential model, trust boundaries, thresholds, and owners | Approved decisions and a testable pilot baseline |
| 1. Core platform | Portal and API, identity, roles, inventory, audit foundation | Authorized users see permitted assets. Permission and audit checks pass |
| 2. Request and approval | Requests, approval revisions, policy decisions, grants, notifications | Approval independence and grant scope verified. The first milestone supports login, scoped assets, and auditable requests |
| 3. SSH gateway lab | Interactive proxying, host trust, scoped test credentials, launches, expiry, and termination | Gateway and session controls pass on isolated hosts |
| 4. Credential controls | Protected SSH signer, custody, rollover, and recovery. Add scoped vault controls for targets that need stored credentials | Approved target credential path passes issuance, recovery, and rotation exercises |
| 5. Evidence and pilot readiness | Recording, evidence review, alerts, restore, emergency drill, limited production pilot | Applicable tests pass and security and infrastructure owners approve pilot access |
| 6. RDP evaluation | Windows compatibility and protocol-specific control design | Lab validation of authorization, recording, and termination before any RDP rollout |
| 7. Enterprise integrations | Wazuh, Ariba SOC, additional IdPs, and ticketing as prioritized | Contract, retry, and delivery monitoring verified for each integration |
| 8. Enterprise scale | HA, capacity expansion, upgrade automation, disaster recovery improvements | Capacity, failover, restore, and support processes validated for the expanded deployment |

Basic pilot recovery and an available SOC alert path are part of Phase 5. Expand formal integrations and HA as later milestones. The pilot can proceed after Phase 5 acceptance. RDP and broader integrations have independent readiness checks.

## First implementation sequence

1. Establish the development project and test harness with isolated synthetic data.
2. Build workforce identity handling and resource-scoped asset visibility. Verify access denials and evidence creation.
3. Add request revisions, approval decisions, and atomic grant issuance. Verify revision conflicts, self-approval denial, retries, and rollback.
4. Add the gateway and credential path after the relevant trust decisions are reviewed. Verify session closure and protected recording in the lab before the production pilot.

For each change, record the requirement and expected check, implement the smallest complete workflow, run the corresponding tests, record actual results, and commit the reviewed change and supporting documentation.

Track work in [TODO](../tasks/TODO.md) and acceptance in the [test plan](16-TESTING-STRATEGY.md).
