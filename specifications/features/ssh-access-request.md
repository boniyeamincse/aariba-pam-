# Interactive SSH access feature

> Proposed pilot feature · 2026-11-22

## Main scenario

1. A requester signs in through the selected IdP and opens the asset catalog. The catalog shows only eligible targets and accounts.
2. The requester enters a window, reason, and required reference. The API returns a frozen request revision and its state.
3. An assigned approver with current scope reviews that revision. When the final required approval succeeds, the requester receives a grant for that exact scope and window.
4. Inside the grant window, the requester starts a session. Each attempt obtains a one-time launch. The assigned gateway verifies host trust, recording readiness, and target authorization before connecting.
5. The requester sees active state and expiry. If access is withdrawn, the grant expires, or required recording cannot recover, the gateway ends the session and the portal shows the confirmed result.

## Alternate scenarios

| Scenario | Expected outcome |
| --- | --- |
| Requester enters a disallowed account or guesses a target | Conceal resources outside scope. Return a safe validation error for visible but invalid inputs |
| Request changes after submission | Retain the earlier revision. Submit the changed scope through a new approval flow |
| Required step is rejected | Stop progression. Preserve the decision and show permitted feedback to the requester |
| Approver role is removed while the request is pending | Deny the decision when it is attempted. Reassignment follows audited policy |
| User opens the terminal before the start time or after the end time | Deny launch. Show the reason and window |
| User retries a consumed launch | Reject reuse. A new launch requires a fresh authorization decision |
| Operator revokes access | Block new launches and initiate termination of each session linked to the grant. Show progress until confirmed |
| Required capture fails | Pause traffic. The gateway resumes only when capture is restored within policy, otherwise it terminates |

Use [requirements](../../docs/04-FUNCTIONAL-REQUIREMENTS.md), [roles](../../docs/07-USER-ROLES-PERMISSIONS.md), and [test cases](../../docs/16-TESTING-STRATEGY.md) as acceptance references.
