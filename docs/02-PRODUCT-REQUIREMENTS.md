# 02 · Product Requirements: Ariba PAM

> Baseline Requirements Catalog · 2026-11-22

This specification establishes the business, functional, and non-functional requirements governing Ariba PAM. All requirement identifiers (`BR-*`, `FR-*`, `NFR-*`) are stable and linked directly to verification test cases in the test catalog.

---

## 1. Business Requirements (BR)

| ID | Title | Business Outcome | Verification Owner |
| :--- | :--- | :--- | :--- |
| **BR-01** | Zero Standing Privilege | Eliminate permanent root/administrator accounts on pilot servers. All interactive access requires JIT authorization. | Infrastructure Lead |
| **BR-02** | Independent Dual Authorization | Critical infrastructure access and administrative policy changes require explicit, independent dual authorization. | Security Architect |
| **BR-03** | Rapid Threat Neutralization | Security operations must have the capability to revoke grants and terminate active sessions within 60 seconds of threat detection or employee departure. | Security Operations Manager |
| **BR-04** | Complete Auditability | Every keystroke, terminal session, administrative action, and approval decision must be tamper-evidently recorded for compliance (SOC 2, ISO 27001, PCI-DSS). | Compliance & Internal Audit |
| **BR-05** | Custodian Duty Separation | Eliminate the "Super Administrator" vulnerability by enforcing separation between platform operators, credential custodians, and evidence custodians. | CISO / Risk Sponsor |
| **BR-06** | Out-of-Band Emergency Break-Glass | Ensure operational continuity during complete IdP or PAM control-plane outages via an auditable, multi-custodian break-glass protocol. | Platform Operations Lead |

---

## 2. Functional Requirements (FR)

| ID | Title | Required Behavior | Acceptance Check |
| :--- | :--- | :--- | :--- |
| **FR-01** | Identity & Phishing-Resistant MFA | Federate workforce identities through enterprise OIDC IdP. Require phishing-resistant MFA (FIDO2/WebAuthn) for privileged access and PAM administration. Ingest automated account disablement signals. | Disabled identity cannot request access, and all its active grants and sessions are immediately revoked (T-01). |
| **FR-02** | Scoped Inventory Management | Maintain a strictly scoped inventory of assets, target accounts, gateway zones, host trust keys, and owners. | Users only see assets within their assigned resource scope. Probing unassigned assets returns HTTP 404 (T-02, T-03). |
| **FR-03** | Immutable Request Revisions | Access requests submit an immutable revision containing target asset, target account, requested time window, justification, and ticket reference. Any modification creates a new revision and supersedes prior steps. | Request amendments create a new revision and cancel pending steps (T-02). |
| **FR-04** | Policy Routing & Separation of Duties | Route approval workflows according to published asset policy. Enforce distinct approvers where configured. Strictly prohibit self-approval (including through delegation). | Approver cannot approve own request. Stale revision decisions are rejected with HTTP 409 (T-02). |
| **FR-05** | Policy Evaluation & Single-Use Launch | Re-evaluate active policy upon approval, grant issuance, and session launch. Issue time-bound access grants and single-use, short-lived (60s) launch capabilities. | Expired, revoked, mismatched, or replayed launch tokens are rejected (T-04). |
| **FR-06** | Protocol Gateway & Ephemeral Signing | Establish interactive SSH through the assigned gateway zone using verified host public key fingerprints and short-lived certificate signing. Target credentials remain inaccessible to end users. | Direct SSH bypass is denied. Unknown host keys reject connection (T-03, T-06). |
| **FR-07** | Bounded Leases & Immediate Revocation | Gateway enforces local lease deadlines strictly bounded by grant expiry. Support operator session termination and grant revocation. Immediate termination on IdP disablement or lease timeout. | Partitions cannot extend access. Sessions terminate within the 60-second budget (T-01, T-05). |
| **FR-08** | Transactional Audit & Session Capture | Capture ordered terminal session recordings (asciinema/typescript) with SHA256 integrity digests. Commit lifecycle audit events via transactional outbox. | Recording failure triggers fail-closed pause or termination. Evidence gaps trigger alerts (T-07). |
| **FR-09** | Scoped Evidence Review & Export | Permit authorized reviewers and auditors to search, stream, and export recordings strictly within their assigned resource scope. Downloads utilize short-lived, signed URLs. | Out-of-scope evidence returns 404. Every playback and export is audited (T-08). |
| **FR-10** | Resilient Notification Delivery | Deliver approval requests, grant state changes, and session termination notices through an asynchronous outbox dispatcher resilient to external network outages. | Outbox retries preserve state transitions. Duplicate notifications are deduplicated (T-11). |
| **FR-11** | Controlled Emergency Access | Support multi-custodian emergency break-glass access when the control plane or IdP is unreachable. Generate independent tamper-evident records. | Emergency drill executes successfully without IdP or primary DB (T-09). |

---

## 3. Non-Functional Requirements (NFR)

| ID | Title | Target Metric | Verification Method |
| :--- | :--- | :--- | :--- |
| **NFR-01** | Revocation & Disablement Latency | ≤ 60 seconds from grant revocation or IdP account disablement signal to active terminal termination. | Automated timestamp comparison between IdP event ingestion and gateway channel closure (T-01, T-05). |
| **NFR-02** | Gateway Autonomous Enforcement | Gateway enforces local lease expiry within ±1 second of deadline, even during total network disconnection from control plane. | Disconnect gateway network cable during active session; verify local timer terminates SSH (T-05). |
| **NFR-03** | Evidence Delivery & Recording Buffer | Gateway must buffer up to 10 MB of terminal stream during storage network blips before pausing interactive input. Terminal closes after 30s of buffer stall. | Simulate recording storage interruption; verify input pause and fail-closed termination (T-07). |
| **NFR-04** | Recovery Time & Point Objectives | Disaster Recovery: RTO ≤ 15 minutes, RPO ≤ 1 minute for transactional database and audit outbox. | Automated backup restore rehearsal in isolated staging environment (T-09). |
| **NFR-05** | API Latency & Gateway Throughput | Control plane API p99 latency ≤ 150 ms (excluding IdP network transit). SSH Gateway proxy adds ≤ 15 ms latency to keystroke round-trip. | Benchmark suite under 200 concurrent active SSH streams (T-10). |
| **NFR-06** | Network Isolation & Default Deny | Direct routine SSH connections from workstation subnets to target hosts are blocked at network firewall (drop traffic). | Nmap and SSH connectivity scan verifying only Gateway Zone egress IP is accepted (T-03). |
| **NFR-07** | Evidence Storage Protection | Stored terminal recordings and audit events must be write-once, read-many (WORM). Standard PAM admins have zero delete or overwrite capabilities. | Attempt administrative DELETE/UPDATE API calls on evidence bucket; verify S3 Object Lock denial (T-08). |
| **NFR-08** | Availability & Health Monitoring | Control Plane and Gateway target 99.95% uptime during business hours. Heartbeats report health every 15 seconds. | Synthetic liveness probes and Prometheus alert verification (T-10). |
