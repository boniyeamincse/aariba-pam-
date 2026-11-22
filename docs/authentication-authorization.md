# Authentication and authorization

> Proposed identity and access-control baseline · 2026-11-22

This document defines how Ariba PAM authenticates human and service identities, evaluates authorization, and propagates revocation. It complements [user roles and permissions](07-USER-ROLES-PERMISSIONS.md), [security requirements](13-SECURITY-REQUIREMENTS.md), and [the API specification](11-API-SPECIFICATION.md).

## Goals

- Default deny: no identity, role, resource scope, or active grant grants access.
- Separate authentication from authorization. Successful sign-in does not imply access to any asset or administrative action.
- Combine role membership, resource scope, policy state, target-account eligibility, grant state, and session state where applicable.
- Support enterprise identity federation without accepting identity-provider claims as authorization proof by themselves.
- Ensure suspension, revocation, expiry, and emergency access produce timely control-plane and gateway enforcement.

## Identity sources

| Identity type | Supported source | Normal use |
| --- | --- | --- |
| Workforce user | Enterprise OIDC or SAML IdP, provisioned and reconciled through SCIM or an approved connector | Portal sign-in, requests, approvals, and administrative access |
| Local service identity | Enrolled gateway or control-plane certificate or signed workload identity | Launch, renewal, lease, heartbeat, evidence, and termination APIs |
| Privileged account | Managed target account credential or key | Target authentication through gateway; never normal browser identity |
| Break-glass identity | Named emergency custodian identity with independent approval | Temporary emergency access under a separately controlled policy |

The pilot IdP is authoritative for workforce authentication and account-disablement signal. SCIM or IdP synchronization is authoritative for managed identity lifecycle only when the reconciliation state is current. A locally cached role or scope must never outlive an explicit suspension or revocation decision.

## Authentication flow

1. The browser starts authentication through the configured OIDC/SAML IdP.
2. The IdP validates the user's credentials and configured MFA factors.
3. Ariba PAM validates issuer, audience, signature, nonce/state, certificate, and token lifetime.
4. PAM validates the internal subject mapping and rejects unknown, disabled, suspended, locked, or unapproved identities.
5. PAM creates a short-lived server-side browser session. It does not store reusable IdP credentials in browser storage.
6. PAM derives permissions only from its own RBAC, resource-scope assignments, and approved policy data.
7. Sensitive operations require step-up authentication or MFA when required by role, policy, or risk.

### MFA requirements

- Privileged and administrative sign-in requires MFA or a phishing-resistant IdP factor.
- TOTP and WebAuthn/FIDO2 are supported local or IdP methods. Enterprise SSO may be OIDC or SAML.
- Step-up is required for credential or secret operations, role and policy changes, emergency activation, sensitive exports, playback, and grant or session termination.
- MFA enrollment and recovery codes use separate, audited transitions and recovery thresholds.
- Trusted-device state is only an assurance convenience. It never replaces MFA, role, scope, or grant checks.

## Authorization model

Ariba PAM uses deny-by-default role-based access control plus resource scope.

```text
allow(actor, action, resource)
  = authenticated
  AND account active
  AND role grants permission(action)
  AND role assignment is in valid scope
  AND scope permits resource
  AND approval-independent separation rules pass
  AND target/policy/grant state permits action
```

The following inputs are evaluated server-side for every protected operation:

| Input | Purpose |
| --- | --- |
| Principal identity | Stable subject and current account state |
| Permission | Role-authorized action, for example `sessions:terminate` |
| Resource scope | Asset, target, environment, zone, evidence, or tenant scope |
| Object state | Pending, approved, revoked, expired, disabled, suspended, or ended |
| Policy version | Version pinned to a request and decision |
| Grant state | Effective start/end, owner, target, and target account |
| Service identity | Gateway or control-plane identity and assigned zone |
| Step-up assurance | MFA assurance for a sensitive operation |

A role without scope does not authorize a resource. A resource scope without a matching role does not authorize an action. Cached role data cannot be used when authoritative authorization or account state is unavailable.

## Roles

Baseline roles are listed below. The exact names and permissions are configurable, but the separation rules remain mandatory.

| Role | Baseline responsibility |
| --- | --- |
| Super Administrator | Platform-wide approved administration. Sensitive assignments require independent review |
| PAM Administrator | Configure gateways, assignments, and operational scope |
| Security Administrator | Manage security controls and incident operations within assigned scope |
| Security Auditor | Review security evidence and audit events |
| Access Approver | Decide an assigned approval step for an assigned scope |
| Privileged User | Submit requests and launch approved grants within scope |
| Read-only Auditor | View permitted inventory and evidence without mutation |
| Evidence Custodian | Retention, hold, export, and recovery evidence controls |
| Gateway Service Identity | Consume launch, renew, obtain credential authorization, and emit evidence for an assigned zone |

Additional legacy role names in repository documents such as Requester, Asset Owner, Security Operator, and Emergency Custodian map to these responsibilities or remain explicitly named custom roles. Production assignments must use stable permission IDs rather than display names.

## Resource scope

Every resource is assigned an authorization boundary. Common boundaries include:

- Asset or asset group
- Environment or zone
- Target account
- Grant or session
- Recording or audit scope
- Notification and integration scope
- Administrative scope

Scope checks run before collection pagination and before returning existence information. An inaccessible resource must be returned as `404` where concealment is required, while a visible resource with an unauthorized action must return `403`. Scope assignments are denied if they cross a configured separation-of-duties boundary.

## Access request and approval authorization

- A requester may submit only for eligible assets/accounts and within policy limits.
- An approver may decide only an assigned approval step and a matching resource scope.
- Self-approval is denied even through another role or approved delegation.
- Approval delegation may be used only by an explicitly authorized delegation record with a bounded duration and scope.
- Delegation cannot remove approval independence or bypass target, policy, ticket, MFA, or asset constraints.
- Final approval atomically creates a grant and evidence event.
- A request pinned to an old policy version cannot be approved or launched after that policy is superseded.

## Grant and session authorization

A launch may be issued only when all required checks pass:

1. Requester owns or is delegated to the grant.
2. Request, policy, target, and account remain valid and current.
3. The grant is active within its effective window.
4. The gateway and target zone match the grant scope.
5. Recording and required evidence controls are available.
6. The designated gateway has an active enrolled identity.

Launch consumption is one-time and binds the grant owner, grant, gateway, target, account, time window, and launch. Session renewal rechecks authoritative grant and policy state. Renewal never extends beyond grant expiry. Grant expiry and revocation initiate session termination even if gateway control delivery is delayed.

## Suspension and revocation

Account suspension or disablement must trigger the following workflow:

1. Revoke active browser sessions and invalidate pending refresh/session tokens.
2. Revoke pending launch capability and credential authorization.
3. Initiate termination of active sessions owned by or attributed to the identity.
4. Preserve the grant as historical evidence or mark it revoked according to configured policy.
5. Propagate gateway termination promptly through the control channel.
6. Confirm gateway termination through session evidence before reporting a session as ended.
7. Record actor, reason, request/correlation ID, scope, and affected resource count.

User suspension, asset disablement, account disablement, policy supersession, grant revocation, gateway revocation, and emergency revocation have distinct semantics. Policy supersession does not retroactively terminate sessions established under an already pinned policy unless revocation or risk policy requires it.

## Service identity authorization

Gateway and control-plane identities are enrolled with:

- Unique service identity
- Certificate or signed credential rotation lifecycle
- Assigned zone and target scope
- Allowed API operations
- Enrollment and revocation state
- Heartbeat and last-seen evidence

Internal APIs require mutual or signed service authentication, replay-resistant timestamps/nonce or sequence values, and request authorization. Gateway inventory and health administration through browser APIs require an administrator role and scope. Credential lease issue is limited to the session, grant, target, gateway identity, and bounded lease lifetime.

On gateway revocation:

- Reject new launches and renewals.
- Revoke issued credential leases.
- Remove future target access.
- Initiate active session termination where gateway control is available.
- Preserve evidence and mark unconfirmed termination according to gateway recovery rules.

## Emergency access

Break-glass access follows a preapproved emergency policy:

- Named principal and named target scope
- Mandatory justification and ticket where configured
- MFA or step-up assurance
- Separate emergency approver where required
- Bounded duration
- Immediate notification
- Mandatory full session recording
- Immutable request and review evidence
- Independent post-incident review

Emergency access is never a normal approval bypass. It creates an auditable, revoked-at-expiry grant and still enforces role, target, service identity, scope, and recording controls.

## Credential and secret access

Passwords, private keys, API tokens, database credentials, and vault plaintext are never returned by normal account or user browser APIs. Credential metadata may include account category, vault reference, verification status, and rotation state.

Plaintext is disclosed only through a short-lived, gateway-issued credential lease. The lease binds the authenticated gateway, target, account, grant/session, and deadline. Revoke and acknowledge the lease through internal APIs and exclude secret values from URLs, logs, browser storage, and audit payloads.

## API enforcement conventions

- HTTP APIs use server-side authorization on every route, not portal navigation or UI visibility.
- Browser state changes require authenticated server-side sessions and CSRF protection.
- Internal APIs require gateway/control-plane service identities and assigned scope.
- Use `401` for unauthenticated requests, `403` for forbidden visible resources, and `404` for missing or concealed resources.
- Apply resource scope before cursor pagination.
- Use idempotency keys for sensitive creates, decisions, policy changes, credential operations, grant launches, exports, and emergency transitions.
- Use optimistic concurrency or `ETag`/`If-Match` for policy, role, account, asset, integration, and system configuration updates.
- Return a request/correlation ID in audit evidence and the consistent API error body.
- Never expose IdP secrets, service certificates, vault plaintext, signing material, or hidden scope in errors.

## Audit requirements

Authentication and authorization evidence should include:

- Stable event ID and outcome
- Principal and service identity
- Action and target resource
- Effective role and resource scope
- Policy or grant version
- MFA or step-up assurance
- Request/correlation ID
- RFC 3339 UTC timestamps
- Rejection reason code where safe

Denied authorization attempts are audited. Authentication failures are rate-limited and audited without creating account-enumeration signals. Evidence is append-oriented and independently retained; routine administrators cannot alter or delete historical evidence.

## Failure behavior

| Failure | Required behavior |
| --- | --- |
| IdP unavailable | Deny new authentication and protected operations; honor remaining active-session rules only for already authenticated and bounded sessions |
| Authorization data unavailable | Deny new access and sensitive changes; never fail open |
| Account state stale | Prefer the authoritative IdP/account-disablement signal or deny access and surface reconciliation status |
| Gateway unavailable | Stop new launches in the affected zone; renewals fail at remaining lease/grant deadline |
| Vault unavailable | Do not issue launch or credential lease; deny launch when target authentication is unavailable |
| Recorder unavailable | Block launch or pause forwarding for active sessions based on the approved interruption policy |
| Evidence store unavailable | Use bounded durable buffering for required evidence; deny launch when mandatory durable evidence cannot be accepted |
| Queue unavailable | Preserve committed audit outbox entries and retry delivery; cache or notification state never authorizes access |

## Verification scenarios

Verify at least:

- Valid role plus invalid scope is denied.
- Valid scope plus missing permission is denied.
- Disabled, suspended, locked, and unknown users are denied.
- MFA challenge failure blocks sensitive operations.
- Self-approval and delegated self-approval are denied.
- Stale policy, role, asset, or grant versions are rejected.
- Grant expiry revokes launch and active session authorization.
- Asset/account/gateway/user disablement immediately blocks new operations.
- Credential plaintext is absent from browser API responses and logs.
- Gateway identity outside its zone cannot consume a launch or lease.
- Repeated credential or launch operations remain idempotent.
- Emergency access has MFA, duration limits, recording, notification, revocation, and post-review evidence.

See [testing strategy](16-TESTING-STRATEGY.md) and [development roadmap](17-DEVELOPMENT-ROADMAP.md).
