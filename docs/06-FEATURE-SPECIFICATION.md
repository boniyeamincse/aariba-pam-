# Feature specification

> Proposed SSH pilot behavior · 2026-11-22

| Feature | User action and system response | Acceptance scenario |
| --- | --- | --- |
| Scoped asset catalog | A user filters permitted targets by environment and requests a listed target account. Admins onboard assets with an owner, gateway zone, and verified host identity. | A requester who guesses an out-of-scope asset ID receives no asset details. FR-02 |
| Access requests and approvals | A requester submits justification and times. An eligible approver decides on the exact revision. The system issues a grant after required approvals and policy checks. | Self-approval fails. Changing the requested account requires a new approval. FR-03–05 |
| Authorized SSH launch | The user starts an eligible grant from the portal. The gateway validates the launch and opens only the approved interactive connection. | Concurrent attempts to use the same launch authorization produce at most one session. FR-05–06 |
| Session oversight | A permitted operator views status and terminates a session or revokes the grant. The portal shows termination pending until confirmed. | Revocation prevents further launches and terminates every attached session. FR-07 |
| Evidence review | An authorized reviewer filters by user, asset, request, grant, or session. Recording playback and export require scoped permissions. | An authorized export creates an audit event. A forbidden export returns no recording location. FR-08–09 |
| Notifications | Notify requesters and approvers of workflow updates and SOC of high-risk events. Failed deliveries retry within policy. | Duplicate delivery does not repeat an approval or change a session state. FR-10 |
| Emergency access | Approved custodians use the outage procedure and capture independent evidence for review. | A drill produces the required notification, evidence, and credential cleanup record. FR-11 |

See [roles](07-USER-ROLES-PERMISSIONS.md), [workflow](08-USER-WORKFLOW.md), and [portal guidelines](12-UI-UX-GUIDELINES.md).
