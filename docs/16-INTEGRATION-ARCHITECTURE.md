# 16 · Integration Architecture: Ariba PAM

> Enterprise Integrations, Security Events & External Adapters · 2026-11-22

Ariba PAM integrates into enterprise security, identity, ticketing, and event ecosystems through provider-neutral adapter interfaces.

---

## 1. Enterprise Identity Providers (OIDC / SCIM / Microsoft Entra ID) (P7-03, ADR-015)

- **Federation Protocols**: OpenID Connect Core 1.0 (Authorization Code Flow with PKCE for portal; synthetic JSON for lab automation) and SCIM 2.0 / Microsoft Graph change notification adapters.
- **Supported Identity Providers**:
  - **Primary Pilot IdP**: OpenID Connect provider (`https://idp.lab.ariba.internal`).
  - **Microsoft Entra ID (Secondary Evaluation)**: Microsoft identity platform v2.0 (`https://login.microsoftonline.com/{tenant_id}/v2.0`). Mapped via immutable object ID (`oid`).
  - **Okta Enterprise**: Okta OIDC/OAuth 2.0 (`https://{org}.okta.com`). Mapped via internal user ID (`00u...`).
- **Required Claims & Identity Anchor**:
  - Identity anchor: Composite key `(idp_issuer, idp_subject)` prevents account collision across multiple federated directories.
  - Required claims: `sub` / `oid` (immutable subject), `email` / `preferred_username`, `amr` (authentication method references), `exp`, `iss`.
- **Assurance Normalization**:
  - Translates provider-specific `amr` claims (`fido`, `fido2`, `webauthn`, `hwk`, `x509`) to NIST SP 800-63B Authenticator Assurance Level 3 (AAL3) Phishing-Resistant MFA.
  - Single-factor (`pwd`) and insecure telephony (`sms`) are denied for privileged operations.
- **Inbound Webhook & Deprovisioning Lifecycle**:
  - Ingests real-time account lifecycle events (`user.disabled`, `user.deprovisioned`, SCIM `active=false`, Microsoft Graph `accountEnabled=false`) with HMAC signature validation and idempotent deduplication.
  - Propagates instantaneous grant revocation and active session termination within the ≤ 60s NFR-01 SLA.

---

---

## 2. SIEM & SOC Event Adapters (P7-01, ADR-013)

```
[ Ariba PAM Audit Outbox Dispatcher / SOC Alerts ]
                   │
                   ├──▶ [ Wazuh SIEM Adapter ] (JSON over HTTPS)
                   │    - Authenticated Delivery (Bearer JWT / API Key / mTLS)
                   │    - Configurable Severity & Event Type Filtering
                   │    - SHA-256 Sliding Window Deduplication (5m TTL)
                   │    - Observable Exponential Backoff Retry & Dead-Letter Queue
                   │    - Pre-mapped Wazuh OSSEC Decoders & Rule Levels (8 - 15)
                   │
                   └──▶ [ Enterprise SOC Adapter ] (Kafka / Splunk / Webhook)
                        - High-priority session termination alerts
                        - Out-of-band emergency break-glass notifications
```

### Wazuh Adapter Architecture & Security Controls
1. **Authenticated Delivery**:
   - Transports structured JSON over TLS 1.3 to the Wazuh Manager / Indexer API (`POST /events` or `/api/v1/events`).
   - Supports Bearer Token (`Authorization: Bearer <token>`), Header API Key (`X-Wazuh-Key`), or Basic Auth.
2. **Policy-Based Event Filtering**:
   - Filter criteria: Minimum severity threshold (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`) and event type allowlist.
   - Low-noise administrative queries and internal health heartbeats are dropped at the edge, reserving SIEM pipeline throughput for actionable security signals.
3. **Cryptographic Deduplication**:
   - Deduplication key: Deterministic SHA-256 digest of `event_type + correlation_id + actor_id + resource_id + payload_digest`.
   - Sliding cache window suppresses duplicate alert delivery within a configurable window (default: 300 seconds), preventing alert storms during retry storms.
4. **Observable Exponential Backoff & Dead-Letter Handling**:
   - Transient network or 5xx/429 errors trigger bounded exponential retry:
     $$\text{Delay} = \min(\text{MaxDelay}, \text{BaseDelay} \times 2^{\text{attempt} - 1})$$
   - Tracks observable counters: `total_processed`, `total_delivered`, `total_filtered`, `total_duplicates_suppressed`, `total_retries`, `total_failed`.
   - Terminal delivery failures (exceeding `max_retries`) move to a dead-letter state and trigger a high-severity `DELIVERY_FAILURE` SOC alert.
5. **Wazuh OSSEC Rule & Decoder Taxonomy**:
   | Wazuh Rule ID | Event Type | Level | Classification |
   |---|---|---|---|
   | `100201` | `ACCESS_GRANT_REVOKED` | 10 | Access Control / Security Operator Action |
   | `100202` | `CAPTURE_FAILURE` | 15 | Evidence Custody / Terminal Recording Gap (Critical) |
   | `100203` | `UNSAFE_LAUNCH_BLOCKED` | 12 | Gateway Defense / Host Key Tampering |
   | `100204` | `LEASE_RENEWAL_FAILURE` | 9 | Session Anomaly / Revocation Invalidation |
   | `100205` | `EMERGENCY_ACCESS_ACTIVATED` | 14 | Break-Glass / Multi-Custodian Quorum |
   | `100206` | `ROTATION_FAILURE` | 11 | Credential Custody / Vault Rotation Error |
   | `100207` | `IDP_USER_DISABLED` | 8 | Identity Disablement Propagation |
   | `100208` | `RDP_TUNNEL_COMPILED` | 6 | Windows Infrastructure Remote Access |

### Structured Event Payload Contract
All security events emitted to Wazuh adhere to the standard schema:
```json
{
  "timestamp": "2026-11-22T10:30:00Z",
  "agent": {
    "id": "000",
    "name": "ariba-pam-control-plane"
  },
  "rule": {
    "id": "100201",
    "level": 10,
    "description": "Ariba PAM Access Grant Revoked",
    "groups": ["pam", "access_control"]
  },
  "data": {
    "ariba_pam": {
      "event_id": "aud_01HXYZ9876",
      "event_type": "ACCESS_GRANT_REVOKED",
      "correlation_id": "corr_grant_revoke_12",
      "severity": "HIGH",
      "actor_id": "usr_sec_operator_1",
      "asset_id": "ast_payment_db",
      "payload": {
        "reason": "Host compromise suspicion",
        "terminated_sessions_count": 2
      }
    }
  },
  "location": "ariba_pam.audit"
}
```

### 2.2 Ariba SOC Event Adapter Architecture & Controls (P7-02, ADR-014)

While the Wazuh SIEM adapter ingests all security outbox events for long-term audit compliance and OSSEC detection rules, the **Ariba SOC Event Adapter** routes actionable, real-time security alerts directly to the Security Operations Center triage pipelines, incident queues, and automated incident responders.

#### 1. Multi-Tier Priority Routing
Alerts are dynamically classified and routed to designated outbound webhook endpoints or message queues based on severity and operational impact:

| Priority Tier | Target Channel | Severity Threshold | Event Types Included | Destination / Action |
|---|---|---|---|---|
| **CRITICAL** | `critical_channel` | `CRITICAL` | `CAPTURE_FAILURE`, `EMERGENCY_ACCESS_ACTIVATED`, `UNPINNED_HOST_KEY`, `UNSAFE_LAUNCH_BLOCKED`, `SOC_DELIVERY_FAILURE` | PagerDuty / On-call security escalation webhook; requires immediate response within < 5 minutes |
| **TRIAGE** | `triage_channel` | `HIGH`, `MEDIUM` | `ACCESS_GRANT_REVOKED`, `LEASE_RENEWAL_FAILURE`, `ROTATION_FAILURE`, `IDP_USER_DISABLED`, `EVIDENCE_DELIVERY_FAILURE` | Security Operations triage queue / Slack/Teams alert webhook / ITSM incident creation |
| **STREAM** | `audit_stream_channel` | `LOW` | `SESSION_TERMINATION_REQUESTED`, `RDP_TUNNEL_COMPILED`, `SESSION_LAUNCH_CONSUMED` | Real-time SIEM event stream / telemetry bus |

#### 2. Correlation Identifier Propagation & Context Enrichment
Every incident payload emitted by the adapter enforces end-to-end distributed tracing invariants:
- **`correlation_id`**: Traceable identifier propagated across the initial access request, grant issuance, gateway launch, session duration, and alert triggers. If an incoming alert lacks a correlation ID, the adapter generates a deterministic `corr_soc_<uuid>` identifier.
- **`trace_id`**: Distributed trace identifier (`trc_<uuid>`) linking control plane API interactions with backend gateway proxy logs.
- **`incident_id`**: Unique incident identifier (`inc_<uuid>`) assigned at creation time.
- **Runbook Mapping**: Each alert is enriched with a prescriptive runbook identifier (e.g. `RB-SEC-01: Terminal Recording Capture Degradation`, `RB-SEC-02: Out-of-Band Emergency Break-Glass Authorization Review`, `RB-SEC-03: Gateway Host Key Mismatch Investigation`).

#### 3. Structured SOC Incident Contract
```json
{
  "incident_id": "inc_01HQST9876",
  "correlation_id": "corr_gap_payment_db_912",
  "trace_id": "trc_4b8f0291d98a",
  "timestamp": "2026-11-22T14:30:00Z",
  "severity": "CRITICAL",
  "channel": "critical_channel",
  "alert_type": "CAPTURE_FAILURE",
  "title": "Gateway recording buffer exhausted during upstream outage",
  "description": "Session ses_9812 encountered visual recording gap. Fail-closed termination invoked.",
  "suggested_runbook": "RB-SEC-01: Terminal Recording Capture Pipeline Degradation / Buffer Overflow",
  "source_component": "ariba-pam-control-plane",
  "actor_id": "gw_zone_internal",
  "asset_id": "ast_payment_db",
  "session_id": "ses_9812",
  "gateway_id": "gw_zone_internal",
  "details": {
    "recording_id": "rec_01HXYZ",
    "coverage_status": "gap",
    "size_bytes": 10485760
  }
}
```

#### 4. Delivery Failure Monitoring & Circuit Breaker Degradation
1. **Bounded Exponential Backoff**: Transient network errors (timeouts, HTTP 502/503/504, 429) trigger bounded exponential retry:
   $$\text{Delay} = \min(2.0\text{s}, \text{BaseDelay} \times 2^{\text{attempt}})$$
2. **Consecutive Failure Tracking**: The adapter tracks sequential delivery failures. If consecutive failures reach `soc_failure_threshold_for_alert` (default: 3):
   - The circuit breaker transitions state from `HEALTHY` to `DEGRADED`.
   - The adapter raises a local critical `SOC_DELIVERY_FAILURE` alert in the audit outbox and system health probes (`/health/readiness`).
3. **Automatic Recovery**: Upon the next successful HTTP delivery, the consecutive failure counter resets to 0 and the circuit status returns to `HEALTHY`.

---

## 3. ITSM Ticket Reference Integration (P7-04, ADR-016)

When an asset or target account is configured with `requires_ticket: true` in its active authorization policy:

### 1. Mandatory Ticket Reference Validation Workflow
1. **Format Validation**: Validates the ticket identifier against enterprise ticketing regex patterns (e.g., Jira `^[A-Z0-9]+-\d+$`, ServiceNow `^(INC|CHG|REQ|RITM|PRB)\d+$`, or generic `^[A-Z0-9_]+-[A-Z0-9_-]+$`).
2. **State & Lifecycle Verification**: Queries the enterprise ITSM provider (Jira REST API v2/v3, ServiceNow Table API, or synthetic lab mock) to confirm:
   - The ticket exists in the system.
   - The ticket is currently in an active or approved lifecycle state (e.g. `In Progress`, `Approved`, `Scheduled`, `Open`).
   - Requests referencing `Closed`, `Resolved`, `Rejected`, or `Cancelled` tickets are rejected with `HTTP 400 TICKET_INVALID_STATE`.
3. **Requester Permission & Assignee Matching**:
   - Compares the authenticated requester's email (`user.email`) or identity subject against the ticket's designated `assignee`, `reporter`, or authorized collaborator list.
   - Requesters attempting to utilize someone else's ticket without authorization are rejected with `HTTP 400 TICKET_ASSIGNEE_MISMATCH` to prevent ticket hijacking.

### 2. Bounded Network Latency & Timeout Protection
- Outbound API calls to external ITSM providers are subject to a strict timeout (default: **3.0 seconds**).
- Prevents slow external ticketing APIs from blocking Control Plane worker threads or degrading access request throughput.

### 3. Outage & Unavailability Fallback Policies
When the external ITSM provider is unreachable (DNS resolution failure, network timeout, or HTTP 5xx responses), the policy engine evaluates the configured fallback strategy:
- **`fail_closed` (Default Production Invariant)**:
  - If the ITSM provider cannot be reached to verify ticket status, the request is rejected immediately with **HTTP 503 Service Unavailable** (`TICKET_SYSTEM_UNAVAILABLE`).
  - Guarantees that unverified access cannot slip through during ticketing outages.
- **`manual_approval` (Emergency Operational Fallback)**:
  - If explicitly configured for lower-risk tiers, the request is allowed to submit with a `TICKET_VALIDATION_DEGRADED` warning flag.
  - Automatically escalates the approval workflow to require secondary manual manager approval and logs an audit outbox event.

### 4. Audit Trail & Evidence
- Successful validations log `TICKET_VALIDATED` in the transactional audit outbox.
- Degraded submissions log `TICKET_VALIDATION_DEGRADED` with failure details and timeout metrics.

---

## 4. Control Plane to Gateway Mutual Authentication

- Gateway instances authenticate to internal Control Plane endpoints (`/internal/v1/*`) using zone-bound cryptographic credentials or mTLS certificates.
- Requests without a valid `X-Gateway-Secret` or matching zone identity are rejected with **HTTP 401 GATEWAY_UNAUTHORIZED**.
