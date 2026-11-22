# 06 · Identity and Access Management: Ariba PAM

> Enterprise Identity Federation & Lifecycle Management · 2026-11-22

Ariba PAM delegates user identity establishment to one organization-approved workforce Identity Provider (IdP) via OpenID Connect (OIDC). PAM never stores, manages, or verifies primary employee passwords.

---

## 1. Enterprise IdP Mapping & Federation

### Immutable Subject Binding
Workforce principals are mapped strictly by the composite key of `(idp_issuer, idp_subject)`:
- `idp_issuer`: The cryptographically verified OIDC issuer URL (e.g., `https://idp.ariba.example.com`).
- `idp_subject`: The immutable, unique subject identifier assigned by the IdP (UUID/GUID).
- **Security Rule**: Email addresses are considered volatile and mutable labels; access authorization is never anchored to email alone.

### Cryptographic Token Verification
The Control Plane validates incoming identity tokens using maintained cryptographic libraries:
1. Validates signature against IdP's published JWKS keys.
2. Enforces non-expired `exp` and valid `iat`.
3. Validates that `aud` matches Ariba PAM's registered OAuth client ID.
4. Validates that `iss` matches the trusted pilot IdP configuration.

---

## 2. Phishing-Resistant MFA & Authentication Assurance

Ariba PAM enforces mandatory **phishing-resistant multi-factor authentication** (SEC-01, FR-01):
- Privileged access operations (submitting requests, approving access, launching sessions, and administrative configuration) require proof of hardware-backed MFA.
- Validates the Authentication Method Reference (`amr`) claim in the identity token:
  - Required methods: `fido2`, `webauthn`, `hwk` (hardware token).
  - Legacy SMS, voice, or basic TOTP authenticator apps are explicitly rejected for privileged tiers.
- **MFA Freshness Window**: If an approver or administrator performs an action after 15 minutes of inactivity, Ariba PAM triggers a step-up reauthentication challenge.

---

## 3. Automated Disablement Signal & Rapid Propagation

The cornerstone of access offboarding in Ariba PAM is the automated consumption of IdP account disablement signals (FR-01, NFR-01, T-01):

```
[ Enterprise IdP / SCIM ]
           │
           │ 1. Account Disabled Webhook (event_id, user_subject)
           ▼
[ Ariba PAM Control Plane ]
  ├── 2. Invalidate Session Tokens (is_active = False)
  ├── 3. Revoke Active Grants (status = 'revoked')
  ├── 4. Flag Active Sessions (status = 'terminating')
  └── 5. Deduplicate Event (Idempotency Record)
           │
           │ 6. Next Renewal Call (≤ 30s)
           ▼
[ Ariba PAM SSH Gateway ]
  └── 7. Renewal Denied (HTTP 409 SESSION_TERMINATING)
  └── 8. Forcefully Closes Terminal Channel & Target Socket
```

### Propagation Latency Budget (NFR-01)
- Target: **≤ 60 seconds** end-to-end.
- Step 1: IdP delivers webhook to `/api/v1/auth/idp-events` (average: 1–3s).
- Step 2: Database transaction invalidates user and grants (average: 15–30ms).
- Step 3: Gateway lease renewal triggers every 30 seconds; upon receiving HTTP 409, the gateway immediately severs the SSH connection.
- Total elapsed time: well within the 60-second limit.

### Deduplication & Replay Protection
- Every IdP lifecycle event contains a unique `event_id`.
- The `IdempotencyService` caches processed event IDs in `idempotency_records`.
- Replayed or duplicate disablement events return cached responses without repeating queries.
- Older or out-of-order events can never re-enable a disabled identity.

---

## 4. Control Plane Session Tokens

- Upon successful IdP verification, the Control Plane issues a high-entropy, short-lived session token signed via HMAC-SHA256 (`ariba_pam.core.security`).
- Session tokens are stored strictly in memory by browser clients (cleared upon tab closure or sign-out). Zero tokens or credentials are saved to `localStorage` or `sessionStorage`.
- The token payload binds the caller identity, active roles, permitted scopes, and issued timestamp. Every API invocation re-verifies user active status (`user.is_active == True`).
