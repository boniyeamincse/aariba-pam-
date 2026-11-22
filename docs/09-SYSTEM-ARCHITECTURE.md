# System architecture

> Proposed control-plane and gateway design · 2026-11-22

## Components and trust boundaries

~~~mermaid
flowchart LR
    User[User or approver] --> Portal[Web portal]
    Portal --> API[Control API and session orchestration]
    Portal <--> IdP[Enterprise IdP]
    API --> DB[(PostgreSQL)]
    API --> Queue[Background work and notifications]
    User <-->|Interactive session| Gateway[Zone-scoped SSH gateway]
    Gateway <-->|Mutual authentication| API
    Gateway <-->|Host identity verification| Host[Approved Linux target]
    Gateway --> Signer[Protected SSH signer or scoped vault]
    Gateway --> Recordings[(Protected recording storage)]
    Gateway --> Audit[(Independent audit storage)]
    API --> Audit
    Audit --> SOC[SOC and SIEM adapter]
~~~

| Boundary | Responsibility |
| --- | --- |
| Workforce to portal and API | Establish session identity, enforce MFA and resource authorization, prevent CSRF, and reject privilege changes without review |
| Control plane to gateway | Authenticate service identities, bind launch and renewal to a gateway and an approved target, and reconcile session status |
| Gateway to target | Restrict egress by zone, verify host identity, authenticate with scoped target credentials, and enforce session deadlines |
| Gateway to signer or vault | Authorize only the approved target account and grant. Keep signing key or reusable secret custody separate |
| Components to evidence services | Deliver attributable events and encrypted recordings to independently administered storage. Report loss or delay |
| Evidence to SOC | Export approved event metadata through authenticated transport. Track retries and delivery health |

## Authorization and consistency

PostgreSQL is authoritative for grants, persistent policy, and approval decisions. Commit a state change and the corresponding audit outbox entry in the same transaction. Use an expiring gateway lease for active sessions. Send revocation promptly and check authoritative grant state at renewal. Treat cache and notification delivery as accelerators. They cannot authorize a new session or extend an existing lease.

The gateway handles terminal traffic. On startup or reconnect, reconcile active session state with authoritative grant state. A failed or disconnected gateway must never cause the portal to report confirmed termination until evidence is received.

## Failure and recovery

| Failure | Required behavior |
| --- | --- |
| IdP or authoritative authorization unavailable | Deny new sessions when identity or authorization cannot be verified. Active sessions obey the remaining authorization lease and grant expiry |
| Gateway cannot renew | Terminate at lease expiry or grant expiry, whichever is earlier |
| Mandatory recorder unavailable | Block launch or pause forwarding for an active session. Terminate after the configured interruption limit |
| Remote evidence store unavailable | Use bounded durable buffering for required audit events. Alert on delivery lag and gaps. Deny launch when required events cannot be retained durably |
| Queue unavailable | Preserve committed outbox events, retry after recovery, surface delivery lag |
| Restore from backup | Keep access closed until identity, policy, gateway state, signer, and evidence retrieval have been verified |

See [database design](10-DATABASE-DESIGN.md), [security requirements](13-SECURITY-REQUIREMENTS.md), and [deployment boundaries](15-DOCKER-STRATEGY.md).
