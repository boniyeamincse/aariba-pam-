# 16 · Integration Architecture: Ariba PAM

> Enterprise Integrations, Security Events & External Adapters · 2026-11-22

Ariba PAM integrates into enterprise security, identity, ticketing, and event ecosystems through provider-neutral adapter interfaces.

---

## 1. Enterprise Identity Provider (OIDC / SCIM)

- **Protocols**: OpenID Connect Core 1.0 (Authorization Code Flow with PKCE for portal; synthetic JSON for lab automation).
- **Required Claims**: `sub` (stable unique user ID), `email`, `amr` (authentication method references including `fido2`), `exp`, `iss`.
- **Inbound Webhook**: Consumes real-time account lifecycle webhooks (`user.disabled`, `user.deprovisioned`) with HMAC webhook signature validation.

---

## 2. SIEM & SOC Event Adapters

```
[ Ariba PAM Audit Outbox Dispatcher ]
                   │
                   ├──▶ [ Wazuh SIEM Adapter ] (JSON over HTTPS / Syslog)
                   │    - Security Alerts (SoD violations, failed logins, unpinned host keys)
                   │    - Rule correlation & intrusion detection
                   │
                   └──▶ [ Enterprise SOC Adapter ] (Kafka / Splunk / Event Hub)
                        - High-priority session termination alerts
                        - Out-of-band emergency break-glass notifications
```

### Structured Event Payload Contract
All security events emitted by Ariba PAM adhere to a common schema:
```json
{
  "event_id": "aud_01HXYZ9876",
  "event_type": "ACCESS_GRANT_REVOKED",
  "timestamp": "2026-11-22T10:30:00Z",
  "correlation_id": "corr_grant_revoke_12",
  "actor": {
    "user_id": "usr_sec_operator_1",
    "role": "security_operator"
  },
  "resource": {
    "type": "access_grant",
    "id": "grn_payment_01",
    "asset_id": "ast_payment_db",
    "scope_id": "scp_prod_linux"
  },
  "payload": {
    "reason": "Host compromise suspicion",
    "terminated_sessions_count": 2
  }
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
