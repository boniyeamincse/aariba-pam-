# Control plane module

> Proposed implementation specification · 2026-11-22

## Responsibilities

The control plane manages workforce principals, scoped inventory, approval policy, requests, grants, and gateway authorization. PostgreSQL is authoritative for state transitions. The gateway owns target connectivity and wire-level session handling. The portal displays the recorded lifecycle and uses the public API.

| Operation | Preconditions | Result |
| --- | --- | --- |
| Authenticate | Trusted IdP assertion, active principal, required assurance and freshness | Server-side session bound to the stable workforce identity |
| Publish inventory | Authorized asset owner or administrator, independent approval where required, validated zone and host trust | Versioned asset and target account mapping. Drafts cannot be requested |
| Submit request | Eligible requester, active asset and account, valid access window, applicable policy | Frozen revision, assigned approval steps and audit outbox event |
| Record decision | Current pending revision, active assignee with current scope, distinct requester and approver | Durable decision and resulting state. Final approval and grant issuance are atomic |
| Authorize launch | Grant owner, current policy, valid grant and gateway mapping | Short-lived capability bound to one owner, grant and gateway |
| Revoke grant | Scoped security operator or authorized identity/policy event | Durable revocation that blocks new launches and initiates termination of linked sessions |

## Approval policy

An active policy version defines the permitted accounts and duration, justification requirements, ticket requirement, eligible approvers and step order. If a required approver cannot be assigned or a policy cannot be evaluated, deny progression and preserve the reason. High-risk policies can require distinct decision makers across consecutive steps. Authorization depends on the current scope of each deciding principal and the exact frozen request revision.

If current policy, scope, or target mapping would materially change what was reviewed, refuse issuance or launch and require a new request revision. Time passing can make a pending request expire without changing its reviewed fields. Replacing a revision retains historical decisions and invalidates any unfinished steps tied to that revision.

## Audit and administration

State-changing operations commit their required audit event alongside the state change. The administration workflow must require independent review of sensitive policy, role, host trust, or gateway zone changes. Record actor, approving actor, scoped object and version, reason, and outcome. Audit also covers access denials without disclosing concealed resources to callers.

## Acceptance

Use synthetic assets with different scopes. Verify cross-scope visibility and denial, immutable request details, self-approval rejection, competing decisions, retries after a response is lost, and rollback when durable audit state cannot be committed. See T-02, T-04, and T-11 in the [test catalog](../../docs/16-TESTING-STRATEGY.md).

See [workflow](../../docs/08-USER-WORKFLOW.md), [data design](../../docs/10-DATABASE-DESIGN.md), and [API contracts](../../docs/11-API-SPECIFICATION.md).
