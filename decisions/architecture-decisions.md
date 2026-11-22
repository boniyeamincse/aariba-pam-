# Architecture decision log

> Phase 0 working record · 2026-11-22

Proposed choices guide the documentation and require review by the listed roles. When a decision is accepted, record the approver, date, and supporting evidence. Keep superseded entries and link their replacements.

| ID | Status | Proposal and alternatives | Rationale and consequences | Owner and verification |
| --- | --- | --- | --- | --- |
| ADR-001 | Proposed | Pilot within one organization with scoped teams and assets. Defer shared hosting | Limit the initial trust boundary. Revisit before a second organization shares infrastructure | Pilot sponsor and security. Confirm pilot participants and scope |
| ADR-002 | Proposed | Separate the control plane and zone-scoped SSH gateway. Consider a combined process only if isolation and operability can still be demonstrated | The control plane owns decisions and the gateway handles terminal traffic. Requires mutual authentication and lease reconciliation | PAM and infrastructure. Review boundaries and run T-03 and T-05 |
| ADR-003 | Proposed | Use short-lived SSH certificates with protected CA custody. Use a scoped vault only when an approved target requires a stored credential | Limits reusable credential exposure. Requires compatible targets, trust distribution, rollover, and recovery | Security and infrastructure. Validate against T-06 |
| ADR-004 | Proposed | Federate through one enterprise IdP. Prefer OIDC if it satisfies assurance and account-disable requirements. Use local identities for lab tests and documented emergency access | Centralizes workforce identity lifecycle. Requires a reliable disablement signal, MFA policy, and an independent emergency path | IAM. Review selected provider and run T-01 |
| ADR-005 | Proposed | Use a transactional authorization store and bounded gateway leases. Use queues for delivery and cache for acceleration | Revocation remains authoritative during retry or queue failure. The gateway must close sessions after lease expiry | PAM engineering. Exercise T-04 and T-05 |
| ADR-006 | Proposed | Keep audit and recording custody independent of routine platform administration. Use protected durable buffering for short interruptions | Protects evidence during disruption and administrative compromise. Requires retention ownership and monitored capacity | Security operations. Exercise T-07 and T-08 |
| ADR-007 | Proposed | Use Compose for isolated local and CI environments. Select pilot runtime after validating network boundaries and restore | Limits lab setup cost and makes production dependency checks explicit | Platform operations. Validate deployment, rollback, and restore |
| ADR-008 | Proposed | Use the draft revocation, interruption, and recovery targets in the NFR baseline. Revise based on owner review and lab measurements before approval | Turns pilot expectations into measurable tests. IdP notification latency and backup capability may require architectural changes | Pilot sponsor with IAM, security, and platform. Review NFR-01 through NFR-04 |
| ADR-009 | Accepted | Adopt Hybrid RBAC + ABAC + Hierarchical Resource Scope with Anti-Superuser Custodian Separation | Formalize the production authorization foundation combining Role (RBAC) + Conditions (ABAC) + Boundaries (Resource Scope) + Independence (SoD). Partition high-risk administrative duties away from PAM Administrator to dedicated Evidence, Signing, and Emergency Custodians | CISO and Security Architect. Verified against pilot requirements |

Source documents are [system architecture](../docs/03-SYSTEM-ARCHITECTURE.md), [user roles and permissions](../docs/07-USER-ROLES-AND-PERMISSIONS.md), [authorization policy engine](../docs/08-AUTHORIZATION-POLICY-ENGINE.md), and [security requirements](../docs/13-SECURITY-REQUIREMENTS.md).

