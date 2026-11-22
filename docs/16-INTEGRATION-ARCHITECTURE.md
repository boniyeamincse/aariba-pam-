# 16 · Integration Architecture: Ariba PAM

> Enterprise Integrations, Security Events & External Adapters · 2026-11-22

Ariba PAM integrates into enterprise security, identity, ticketing, and event ecosystems through provider-neutral adapter interfaces.

---

## 1. Enterprise Identity Provider (OIDC / SCIM)

- **Protocols**: OpenID Connect Core 1.0 (Authorization Code Flow with PKCE for portal; synthetic JSON for lab automation).
- **Required Claims**: `sub` (stable unique user ID), `email`, `amr` (authentication method references including `fido2`), `exp`, `iss`.
- **Inbound Webhook**: Consumes real-time account lifecycle webhooks (`user.disabled`, `user.deprovisioned`) with HMAC webhook signature validation.

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

---

## 3. ITSM Ticket Reference Integration

When an asset or target account is configured with `requires_ticket: true`:
1. The requester must supply a valid ticket reference (e.g. `JIRA-4819` or `INC-9912`).
2. An ITSM adapter validates ticket status:
   - Verifies the ticket exists and is currently in an `In Progress` or `Approved` state.
   - Verifies the requester is listed as an assignee or collaborator.
3. **Fail-Closed Fallback**: If the ticketing system is unreachable, the asset policy defines whether the request is rejected immediately or routed to secondary manual manager approval.

---

## 4. Control Plane to Gateway Mutual Authentication

- Gateway instances authenticate to internal Control Plane endpoints (`/internal/v1/*`) using zone-bound cryptographic credentials or mTLS certificates.
- Requests without a valid `X-Gateway-Secret` or matching zone identity are rejected with **HTTP 401 GATEWAY_UNAUTHORIZED**.
