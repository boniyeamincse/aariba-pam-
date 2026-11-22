# SSH gateway module

> Proposed implementation specification · 2026-11-22

## Trust and lifecycle

The gateway authenticates as a unique enrolled service assigned to a zone. It obtains target and account details from the authoritative authorization result and establishes SSH only to a trusted, onboarded host in its zone. Target credentials are scoped to the approved account and never surface in portal calls or session output. Use a maintained SSH implementation and default the pilot to interactive terminal sessions.

1. Receive the one-time launch through the authenticated session-client path. Confirm its owner binding using trusted identity context. Limit concurrent starting and active sessions by the approved load policy.
2. Consume the launch atomically through the control plane. Initiate the target handshake only after gateway policy and required recorder readiness checks pass. Verify host trust during the handshake before authenticating to the host or forwarding terminal traffic.
3. Establish the target connection and report Active once the terminal stream is usable. If failure occurs before the connection becomes usable, report Failed. A consumed launch remains consumed. A retry requires current authorization and a fresh launch.
4. Forward terminal traffic while grant and lease deadlines permit it. Recheck those deadlines before opening further traffic and locally close the connection at the earlier deadline. Apply explicit revocation and session termination as soon as the gateway receives them.
5. Close both directions on termination, end the local recording, persist the end event, and report the final reason. Reconcile after disconnection without extending an expired lease or reopening a closed session.

## Failure and concurrency

| Situation | Gateway behavior |
| --- | --- |
| Concurrent consumption | Accept at most one launch consumption. Other attempts cannot establish a target connection |
| Host identity mismatch | Abort before presenting the target credential. An independently authorized trust update is required |
| Scope or channel mismatch | Reject traffic outside the approved target, account, or allowed interactive session path |
| Authorization service unreachable | Deny unverifiable new launches. Bound active sessions by the existing lease and grant expiry |
| Mandatory capture unavailable | Block new connections. Pause forwarding in both directions for an active session and terminate at the configured limit if capture cannot resume |
| Evidence delivery unavailable | Persist required events in a bounded protected buffer and replay them after recovery. Deny new sessions when durable capacity cannot be reserved |
| Gateway process stops | Close owned connections. Report unresolved status after restart until reconciliation establishes the outcome |

## Acceptance

Use lab hosts with managed host keys and synthetic principals. Verify permitted path, denied channels, replay, grant expiry, renewal loss, revocation, and mandatory capture failure using T-03 through T-07 in the [test catalog](../../docs/16-TESTING-STRATEGY.md). The first pilot must use the approved target compatibility matrix and [deployment boundaries](../../docs/15-DOCKER-STRATEGY.md).

See [architecture](../../docs/09-SYSTEM-ARCHITECTURE.md) and [pilot timing targets](../../docs/05-NON-FUNCTIONAL-REQUIREMENTS.md).
