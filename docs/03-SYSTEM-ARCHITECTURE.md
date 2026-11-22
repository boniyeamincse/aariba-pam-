# 03 · System Architecture: Ariba PAM

> System Architecture, Topologies & Trust Boundaries · 2026-11-22

## 1. High-Level Architecture Overview

Ariba PAM employs a microservice-oriented, zero-trust architecture physically separating the **Control Plane** (identity, policy evaluation, workflow orchestration, audit persistence) from the **Data Plane** (zone-distributed Session Gateways executing SSH proxying, host verification, credential injection, and terminal capture).

```
                                      ┌──────────────────────────────────────────────┐
                                      │           Enterprise Identity (IdP)          │
                                      │  OIDC Federation · Phishing-Resistant MFA   │
                                      └──────────────────────┬───────────────────────┘
                                                             │ 1. Authenticate & Token
                                                             ▼
┌─────────────────────────┐               ┌──────────────────────────────────────────┐
│   Workforce Requester   │──────────────▶│       Ariba PAM Control Plane            │
│       & Approver        │ 2. Submit Req │  - Hybrid Policy Engine (RBAC+ABAC+Scope)│
│       (Browser)         │ 3. Decisions  │  - Workflow & Approval State Machine     │
└─────────────────────────┘               │  - Transactional Outbox & Audit Store    │
                                          └────────────────────┬─────────────────────┘
                                                               │ 4. Issue Launch Token
                                                               ▼
┌─────────────────────────┐               ┌──────────────────────────────────────────┐
│     User Terminal       │──────────────▶│       Ariba PAM SSH Gateway              │
│      (SSH Client)       │ 5. Connect    │  - Zone-Bound Service Identity           │
│                         │    Token      │  - Strict Host Key Fingerprint Check     │
└─────────────────────────┘               │  - Bounded Lease Watcher & Local Expiry  │
                                          │  - Terminal Capture & Asciinema Streamer │
                                          └────────────────────┬─────────────────────┘
                                                               │ 6. Ephemeral SSH / injected creds
                                                               ▼
                                          ┌──────────────────────────────────────────┐
                                          │         Target Infrastructure            │
                                          │  Linux Servers · Private VPC / Subnet   │
                                          │  (Direct Client Network Access Denied)   │
                                          └──────────────────────────────────────────┘
```

---

## 2. Component Taxonomy

### A. Control Plane Service (Python / FastAPI / SQLAlchemy)
- **Identity & Context Manager**: Validates OIDC JWTs, checks AMR assurance (`pwd` + `fido2`/`webauthn`), evaluates current user account status, and processes inbound IdP lifecycle webhooks.
- **Hybrid Authorization Engine**: Implements RBAC + ABAC + Hierarchical Resource Scope evaluation. Ensures default-deny, evaluates explicit deny policies, checks separation-of-duties rules, and validates contextual parameters (schedule, IP, ticket).
- **Workflow & Lifecycle Coordinator**: Manages state transitions for access requests, immutable revisions, multi-step approval routing, and grant issuance.
- **Idempotency Engine**: SHA-256 fingerprinting on state-changing API operations guaranteeing zero duplicate state transitions or conflicting replays.
- **Transactional Audit Outbox**: Stores structured audit records within the primary database transaction, eliminating dual-write vulnerabilities.
- **Notification Dispatcher**: Durable background worker dispatching email/webhook alerts with exponential backoff and observability during delivery outages.

### B. Session Gateway Service (Go / `golang.org/x/crypto/ssh`)
- **Zone Service Identity**: Cryptographically enrolled service process tied to a specific `GatewayZone`.
- **Target Host Identity Verifier**: Pins target server host keys via SHA-256 fingerprints stored in the asset database. Rejects unknown, missing, or altered host keys immediately before credential presentation.
- **Launch Token Consumer**: Authenticates to the control plane, atomically consumes the single-use launch token, binds to the session, and receives the bounded lease.
- **Bounded Lease Watcher**: Continuously tracks session time boundaries (`min(lease_deadline, grant_expiry)`). Renews lease via the control plane every 30 seconds. If unreachable or if the lease expires, the gateway independently terminates the session locally.
- **Terminal Session Recorder**: Non-bypassable PTY capture streaming asciinema v2 format segments with SHA-256 block digests. Includes a 10 MB fail-closed buffer that pauses terminal input during storage hiccups and terminates the session if evidence persistence is permanently broken.

### C. Isolated Credential & CA Signer
- **Ephemeral Certificate Signer**: Isolated service holding the SSH User CA private key.
- Upon launch consumption, issues a short-lived (e.g. 5-minute) OpenSSH certificate specifying the exact target username, source gateway IP, and validity window.
- The SSH Gateway never has read access to the CA private signing key.

### D. Protected Evidence Store
- **Immutable Storage Bucket**: S3-compliant object store configured with Object Lock (WORM compliance).
- Administered through dedicated Evidence Custodian IAM credentials; standard PAM administrators cannot overwrite or purge recordings.

---

## 3. Network Topologies & Traffic Segmentation

Ariba PAM enforces strict physical and logical network separation:

```
[ Client Workstation Network ] 
             │
             ├── (HTTPS:443) ──────────────▶ [ Control Plane Load Balancer ]
             │                                              │
             │                                              ▼
             │                               [ Control Plane Application Subnet ]
             │                                 (PostgreSQL, Redis, KMS)
             │
             └── (SSH:2222) ───────────────▶ [ Gateway Zone Public / Ingress ]
                                                            │
                                              [ Gateway Private Egress ]
                                                            │
                                                            ▼
                                             [ Target Host Private Subnet ]
                                             (Port 22 only accepts Gateway IP)
```

1. **Direct Access Elimination**: Target hosts reside in isolated private subnets. Workstations have zero direct routable paths to target port 22.
2. **Zone Isolation**: Gateway zones are isolated per network tier (e.g., `prod-us-east`, `prod-eu-west`, `dmz`, `pci-zone`). A gateway enrolled in the `dmz` zone cannot reach assets in `pci-zone`.
3. **Mutual Gateway Authentication**: All internal API calls from Gateways to the Control Plane require TLS with mTLS / zone-bound service credentials.

---

## 4. Failure Domains & Partition Handling

| Failure Scenario | Control Plane Behavior | Gateway Behavior | User Experience |
| :--- | :--- | :--- | :--- |
| **Control Plane Outage** | Unreachable for new requests or approvals. | Active sessions continue safely until current lease deadline (≤ 60s). Ongoing lease renewals fail, triggering orderly local termination. | Active users see a grace period warning and connection terminates at lease expiry. New logins blocked. |
| **Network Partition (Gateway isolated)** | Reconciler flags gateway as unreachable. Marks pending sessions after timeout. | Gateway fails to renew lease. Local timer reaches expiry and immediately closes client and target sockets. | Connection severed precisely at lease boundary. No unauthorized standing access remains. |
| **Evidence Store Outage** | Records operational exception; denies new session launches requiring mandatory capture. | Gateway buffers keystrokes up to 10 MB. If buffer fills or outage exceeds 30s, forwarding pauses and session terminates fail-closed. | User sees terminal pause message; session terminates if storage is not restored. Forensics preserved. |
| **IdP Outage** | Blocks routine workforce logins. Emergency access path invoked. | Active sessions continue until grant expiry or operator intervention. | Existing approved sessions proceed; new requests require break-glass emergency activation. |
