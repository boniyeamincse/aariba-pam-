# Functional requirements

> Proposed SSH pilot requirements · 2026-11-22

| ID | Required behavior | Acceptance check |
| --- | --- | --- |
| FR-01 | Federate workforce identities through the pilot IdP, require phishing-resistant MFA for privileged access and PAM administration, and consume identity disablement signals. | Disabled identity cannot open access and its active grants are revoked. |
| FR-02 | Maintain scoped inventory of assets, target accounts, owners, environments, gateway zones, and trusted host identities. | Users see permitted assets only. Unknown or changed host identity blocks the connection. |
| FR-03 | Submit an immutable approval revision containing target, account, requested times, justification, and ticket reference when required. | An amendment requires a new approval revision. |
| FR-04 | Route approvals using policy, enforce distinct approvers where configured, and deny self-approval including through delegation. | Out-of-scope, duplicate, or concurrent decisions preserve the intended approval outcome. |
| FR-05 | Evaluate policy at grant issuance and session launch. Issue an approved, time-bound grant and a single-use launch authorization. | Expired, mismatched, revoked, and replayed launch authorizations are denied. |
| FR-06 | Establish interactive SSH through the assigned gateway using verified host identity and scoped target credentials. | Target credentials are absent from user-visible responses and normal direct SSH is blocked. |
| FR-07 | Enforce expiry at the gateway, support scoped session termination and grant revocation, and end active sessions on disablement or lease expiry. | All associated sessions terminate within the applicable limit. |
| FR-08 | Capture required terminal evidence and audit lifecycle events, denied actions, and administrative changes. | Recording failure invokes the defined pause and termination behavior and leaves correlated evidence. |
| FR-09 | Allow authorized reviewers to search and export evidence within their assigned scope. | Cross-scope access is denied and review or export is audited. |
| FR-10 | Notify relevant parties of request decisions, termination, and operational exceptions. | Retries preserve notifications and delivery failure is visible without granting access. |
| FR-11 | Support separately authorized emergency access with evidence, notification, and review. | Exercise the break-glass procedure during a simulated outage. |

The [feature specification](06-FEATURE-SPECIFICATION.md) provides scenarios. The [workflow](08-USER-WORKFLOW.md) owns lifecycle states and the [testing strategy](16-TESTING-STRATEGY.md) maps checks to evidence.
