# Business requirements

> Proposed pilot scope · 2026-11-22

| ID | Requirement | Acceptance evidence | Accountable role |
| --- | --- | --- | --- |
| BR-01 | Route routine privileged access to onboarded Linux targets through Ariba PAM | Approved asset list and network verification for representative user and gateway paths | Infrastructure owner |
| BR-02 | Link each session to a named user, approved target account, justification, and approved window | End-to-end evidence for approved and denied requests | Asset owner |
| BR-03 | Allow security operations to revoke access promptly | Timestamped revocation and account-disable tests | Security owner |
| BR-04 | Give authorized auditors independent evidence of access and policy changes | Scoped retrieval of representative approvals, sessions, and changes | Audit owner |
| BR-05 | Preserve controlled emergency access and recover service after failure | Signed review of outage and restore exercises | Platform owner |
| BR-06 | Minimize collection and exposure of sensitive recordings and credentials | Approved recording notice, retention, export and key-custody decisions | Security and privacy owners |

The sponsor confirms pilot assets, eligible teams, operating hours, service targets, and escalation ownership before production use. Measure eligible access through PAM, sessions linked to approvals, revocation delay, mandatory recording coverage, and restore drill results against the discovery baseline. Use request, gateway, audit, and recovery records as evidence.

See [functional requirements](04-FUNCTIONAL-REQUIREMENTS.md) and [non-functional requirements](05-NON-FUNCTIONAL-REQUIREMENTS.md).
