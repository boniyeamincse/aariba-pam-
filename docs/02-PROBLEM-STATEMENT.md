# Problem statement

> Discovery baseline · 2026-11-22

Privileged access can become difficult to govern when teams manage host access, approval, secrets, and audit evidence in separate tools. Discovery must establish which gaps exist in the pilot environment and how frequently they occur.

| Risk to validate | Operational impact | Evidence to collect |
| --- | --- | --- |
| Shared or long-lived accounts | Unclear attribution and lingering access | Inventory of account types, credential owners, and expiry policies |
| Direct administration paths | Access can bypass centralized approval and recording | Approved network paths and representative host configurations |
| Inconsistent approval and removal | Access may exceed the approved task or time window | Sample tickets and elapsed time from disable or revoke to access removal |
| Fragmented evidence | Investigation requires manual reconstruction | Sample incident timeline with approvals, target events, and missing fields |
| Dependence on the central access path | A PAM or IdP outage can block emergency maintenance | Existing emergency procedure and restore drill results |

Collect access patterns and representative samples with asset owners and security operations. Record the sampling period, environments, exclusions, and measurement owner. Use synthetic or sanitized evidence in the repository.

See [business outcomes](03-BUSINESS-REQUIREMENTS.md) and the [Phase 0 tasks](../tasks/TODO.md).
