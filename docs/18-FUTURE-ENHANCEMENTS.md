# Future enhancements

> Candidate backlog · 2026-11-22

| Capability | Prerequisite or decision |
| --- | --- |
| RDP access | Select a maintained implementation. Define Windows account, clipboard, drive redirection, recording, and termination policies |
| Database, network-device, and Kubernetes access | Define protocol-specific target identity, least privilege, session boundaries, and evidence coverage |
| Automated credential rotation | Define failure and rollback behavior, ownership, reconciliation, and dependency discovery |
| Cloud roles and service accounts | Define machine identity, workload scope, approval model, and audit integration |
| Advanced approvals and access risk | Validate signal quality and define predictable policy decisions and overrides |
| Wazuh, Ariba SOC, and ITSM integrations | Agree event schema, data filtering, ownership, retry behavior, and integration health indicators |
| Multiple sites and higher availability | Establish capacity requirements, recovery objectives, regional dependencies, and gateway failover behavior |
| Shared hosting for multiple organizations | Approve a tenancy model. Prove isolation in API, gateways, credentials, evidence, background jobs, and exports before shared onboarding |

Prioritize these with the pilot sponsor after reviewing discovery evidence and operational results. See [roadmap](17-DEVELOPMENT-ROADMAP.md) and [decision log](../decisions/architecture-decisions.md).
