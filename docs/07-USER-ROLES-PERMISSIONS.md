# User roles and permissions

> Proposed authorization model · 2026-11-22

Permissions require both an assigned role and a matching resource scope. A user's role membership cannot override approval independence, gateway scope, or evidence custody rules.

| Role | Allowed actions | Scope |
| --- | --- | --- |
| Requester | View assets, submit or cancel requests, start eligible grants, end own sessions | Own requests and sessions, permitted assets and accounts |
| Approver | Review and decide pending approvals | Assigned approval step and asset scope |
| Asset owner | Manage onboarding proposals and approved account mappings, review access to owned assets | Assigned assets. Approval requires an assigned approver role |
| PAM administrator | Manage platform configuration, gateways, and scoped assignments | Assigned operational scope. Sensitive changes require an independent review |
| Security operator | Monitor sessions, terminate sessions, revoke grants, review incidents | Assigned environments and incident scope |
| Auditor | Read scoped evidence and history. Play back or export when explicitly permitted | Assigned audit scope |
| Evidence custodian | Manage evidence retention policy and approved holds | Dedicated evidence store and separation from routine administration |
| Signing or vault custodian | Manage key custody, rotation, and recovery policy | Dedicated signing or vault system |
| Emergency custodian | Use the documented break-glass process under emergency authorization | Named targets, documented time window, and independent review |
| Gateway service identity | Consume launch authorization, renew sessions, obtain scoped target authentication, emit evidence | Assigned zone and authorized sessions |

Require independent approval for sensitive changes to production policy, broad role assignments, and emergency access configuration. Record actor, effective scope, and rationale. Test combined roles and delegation for self-approval and unauthorized access. See [security controls](13-SECURITY-REQUIREMENTS.md).
