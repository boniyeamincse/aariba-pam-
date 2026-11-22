# 15 · Audit and Evidence Management: Ariba PAM

> Transactional Outbox, Terminal Capture & WORM Compliance · 2026-11-22

Audit integrity and forensic non-repudiation are foundational to Ariba PAM. The platform guarantees that no privileged operation can execute without an atomic, immutable audit trail.

---

## 1. Transactional Audit Outbox Pattern

To eliminate the classic distributed systems "dual-write" failure (where a database state change succeeds but an audit logging call to an external service fails or is rolled back), Ariba PAM uses the **Transactional Outbox Pattern**:

```
[ Control Plane HTTP Request ]
              │
              ▼
    [ Database Transaction ]
    ├── 1. Apply Business State Change (e.g., Issue Grant)
    ├── 2. Insert Event into `audit_outbox`
    └── 3. COMMIT (Atomic Guarantee)
              │
              ▼
[ Outbox Notification & Audit Dispatcher ]
    ├── 4. Poll Pending Outbox Records
    ├── 5. Deliver to External SIEM / SOC (Wazuh, Splunk, Kafka)
    └── 6. Mark Event as `delivered` (or increment retry count)
```

- If the database transaction rolls back due to an error, the audit outbox record rolls back automatically.
- External logging outages never cause state inconsistency or uncommitted ghost audit records.

---

## 2. Terminal Recording Capture & Integrity Digests

1. **Asciinema v2 Stream Format**:
   - Interactive terminal traffic is captured as timestamped JSON lines containing input, output, and window geometry changes.
   - Example line: `[0.123456, "o", "root@prod-db-01:~# "]`
2. **Block Integrity Digests**:
   - Every 1 MB chunk of recording stream is hashed with SHA-256.
   - When the session concludes, the Gateway computes a composite hash manifest and signs it with the Gateway zone identity key.
   - The digest manifest is committed to the database and correlated with the `access_sessions` record.

---

## 3. Scoped Evidence Playback & Exports (FR-09, T-08)

1. **Explicit Scope Enforcement**:
   - Only users with the `auditor` or `security_operator` role bound to the asset's resource scope can view recording metadata or authorize playback.
   - Cross-scope playback attempts return **HTTP 404 Not Found**.
2. **Next.js Web Player & Streaming**:
   - The Enterprise Web Console embeds a hardened `asciinema-player` component.
   - Features include: interactive timeline scrubbing, pause/play, variable playback speeds (0.5x, 1x, 2x, 4x), timestamp jump points, and full-text terminal transcript search.
   - Streaming URLs are pre-signed with short expiration windows (e.g. 15 minutes), locked to the auditor's IP, and cannot be cached.
3. **Auditable Evidence Exports**:
   - Creating an evidence export bundle requires an explicit operational justification.
   - Every export job is recorded in the audit outbox with the auditor ID, correlation reference, target scope, and SHA-256 manifest.


---

## 4. Independent Evidence Custody & WORM Compliance (BR-05, NFR-07)

- Evidence storage buckets are managed exclusively by the **Evidence Custodian** role.
- Buckets are configured with Object Lock in Compliance Mode (Write-Once, Read-Many).
- Neither standard PAM Administrators, Security Operators, nor compromised Control Plane application credentials possess IAM permissions to execute `DeleteObject`, `PutObjectRetention`, or overwrite existing recordings.
