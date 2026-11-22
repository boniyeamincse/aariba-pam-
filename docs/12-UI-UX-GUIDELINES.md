# UI and UX guidelines

> Proposed portal behavior · 2026-11-22

| Area | Primary information and action |
| --- | --- |
| Requester | Permitted assets, target account, access window, justification, request status, and eligible session launch |
| Approver | Exact revision, risk context, reason, duration, associated ticket, previous decisions, and approve or reject |
| Security operations | Active sessions, target, start and expiry, recording health, revoke grant, and terminate session |
| Administration | Asset ownership, gateway zone, account mapping, host trust state, roles, policy, and health |
| Auditor | Filterable events, correlated timeline, and explicitly scoped playback or export |

Keep request, grant, and session status distinct in the interface. Show the access window with a timezone and display expiry during the terminal session. Mark a termination as pending until the gateway confirms it. When mandatory recording pauses the terminal, explain why input is paused and whether the session has ended. Provide a clear recording notice before launch.

## Screen states and recovery

| Screen | State | User action or feedback |
| --- | --- | --- |
| Asset catalog | Empty permitted scope | Explain how to request access through the approved channel. Omit restricted asset names |
| Request detail | Pending approval | Show the current revision and status. Offer cancellation or submission of a revised request where permitted |
| Approval detail | Decision conflicts with a changed revision | Explain that the proposal changed. Reload the current revision before accepting another decision |
| Session | Starting or terminating | Show the status and refresh it. Restrict duplicate actions until their outcome is known |
| Session | Recording paused or connection unavailable | Show whether the gateway is retrying or the session ended. Prevent input while forwarding is paused |
| Evidence review | Recording incomplete or export expired | Show capture coverage and the reason where available. Allow a scoped reviewer to request a new export |

## Interaction and accessibility

- Make forms, filters, menus, and dialogs keyboard accessible. Provide visible focus, descriptive labels, and status text alongside colors.
- Show loading, empty, expired, denied, and degraded states. A failure should provide a safe retry or escalation path without exposing restricted information.
- Confirm disruptive actions with the exact user, target, and impact. A grant revocation ends all linked sessions. A session termination ends only the selected session.
- Keep target credentials and launch authorization material out of rendered text and telemetry. Keep playback controls and downloads scoped to the authorized evidence item.
- Test zoom, narrow layouts, screen-reader announcements, and keyboard entry and exit from the terminal surface.

See [roles](07-USER-ROLES-PERMISSIONS.md) and [feature scenarios](06-FEATURE-SPECIFICATION.md).
