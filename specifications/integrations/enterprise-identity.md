# Enterprise identity integration

> Proposed provider-neutral contract · 2026-11-22

## Identity mapping

Use one organization-approved workforce IdP for the production pilot. OIDC is the preferred candidate pending IAM review. Map users by trusted issuer and stable subject, never email alone. Verify federation message authenticity, issuer, audience, expiry, and authentication flow bindings with a maintained library. Require a provider-specific mapping for the authentication assurance signal and its maximum age. The application continues to enforce Ariba PAM resource authorization.

## Account changes

| Input | Control-plane behavior |
| --- | --- |
| Verified eligible sign-in with required assurance | Establish the portal session and load scoped PAM permissions |
| Missing or stale MFA assurance | Deny privileged actions and provide an approved reauthentication path |
| Verified disabled or deprovisioned principal | Invalidate PAM sessions, prevent new grants and launches, and revoke active grants |
| Duplicate or delayed lifecycle event | Deduplicate by provider event identity and reconcile against authoritative identity state. Older events cannot restore access |
| Unavailable or unverifiable identity state | Deny new access requiring fresh verification. Apply the active-session lease policy |

IAM must select the supported lifecycle signal and reconciliation method, document its propagation budget, and verify the full 60-second revocation candidate from the IdP change to gateway closure. Treat local lab test identities and the separately authorized emergency path as separate identity flows.

See [ADR-004](../../decisions/architecture-decisions.md), [T-01](../../docs/16-TESTING-STRATEGY.md), and [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html).
