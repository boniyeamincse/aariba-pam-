# 13 · Security Requirements: Ariba PAM

> Threat Matrix, Core Controls & Verification Mapping · 2026-11-22

Security requirements define non-negotiable architectural invariants and controls enforced across all Ariba PAM components.

---

## 1. Core Security Invariants (10 Mandatory Rules)

| Control | Invariant Requirement | Enforcement Layer |
| :--- | :--- | :--- |
| **1. Default Deny** | Any action or resource access without an explicit matching permission grant is denied immediately. | Authorization Policy Engine |
| **2. Least Privilege** | Users and service accounts operate with the absolute minimum set of permissions necessary for the specific task window. | Role & Scope Engine |
| **3. Scope Enforcement** | Every database read, API call, and gateway connection verifies the caller's resource scope. Unscoped resources return HTTP 404. | `ScopeChecker` / API routers |
| **4. Explicit Deny** | Explicit deny rules override any allow permissions across policies and role assignments. | Policy Engine |
| **5. Approval Independence** | An actor cannot approve their own requests, revisions, or administrative proposals (including via delegation). | Workflow State Machine / SoD |
| **6. Time-Bound Access** | Standing access is prohibited. All role assignments, grants, leases, and launch tokens expire automatically without manual intervention. | Lease Watcher / DB Timers |
| **7. MFA Enforcement** | Privileged operations and administrative changes require proof of hardware-backed, phishing-resistant MFA (FIDO2/WebAuthn). | Identity Service (`amr` check) |
| **8. Session Revocation** | Role suspension, grant revocation, or IdP disablement immediately invalidates active sessions, terminates gateway channels, and closes target sockets. | Outbox & Lease Reconciler |
| **9. Audit Logging** | Every administrative decision, authentication attempt, permission evaluation, and terminal keystroke is immutably recorded. | Transactional Outbox & WORM |
| **10. Cache Invalidation** | Role, permission, or scope changes immediately purge authorization caches, forcing fresh evaluation on subsequent requests. | Cache Manager / Engine |

---

## 2. Threat Matrix & Pilot Verification Mapping

| Threat ID | Threat Description | Mitigating Control | Pilot Check |
| :--- | :--- | :--- | :--- |
| **SEC-01** | **Account Takeover / Stale Offboarding** | Federate through enterprise IdP, require FIDO2 MFA, consume disablement webhook, and propagate revocation within 60s. | **T-01** |
| **SEC-02** | **Self-Approval & Collusion** | Enforce SoD rules, separation of duties, four-eyes review on policy changes, and immutable request revision tracking. | **T-02** |
| **SEC-03** | **Network Bypass & Untrusted Targets** | Deny direct SSH workstation traffic at firewall. Gateway verifies target host key fingerprint before authenticating. | **T-03** |
| **SEC-04** | **Launch Token Replay / Stealing** | Ephemeral, single-use launch tokens with 60-second expiry. Consumed atomically in a database lock. Raw tokens never logged. | **T-04** |
| **SEC-05** | **Partitioned Gateway Access Extension** | Local gateway lease watcher independently terminates SSH sessions upon lease expiry during network partitions. | **T-05** |
| **SEC-06** | **Credential Extraction / CA Compromise** | Ephemeral SSH certificate signing in isolated enclave. Gateway never reads CA private keys. Automatic rotation. | **T-06** |
| **SEC-07** | **Evidence Tampering & Blind Spots** | Fail-closed PTY recording buffer. Storage outage pauses or terminates session. WORM compliance on S3 bucket. | **T-07**, **T-08** |
| **SEC-08** | **Privilege Escalation via Administrator** | Anti-superuser partitioning. Evidence, Signing, and Emergency Custodians isolated from standard PAM Admins. | **T-02**, **T-09** |

---

## 3. Dynamic Revalidation on Role Revocation

A critical vulnerability in legacy PAM systems is that revoking a user's role stops *future* logins but leaves existing active SSH sessions and issued grants intact.

In Ariba PAM, invoking `/api/v1/admin/role-assignments/{id}/revoke`:
1. Marks the assignment as `revoked`.
2. Automatically identifies all active `access_grants` issued to the user under that role and scope.
3. Transitions those grants to `revoked`.
4. Marks all running `access_sessions` as `terminating`.
5. Emits an audit outbox event.
6. The next gateway lease renewal cycle (within 30 seconds) rejects renewal, terminating the active terminal session immediately.
