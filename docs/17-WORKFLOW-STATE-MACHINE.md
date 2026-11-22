# 17 · Workflow State Machine: Ariba PAM

> State Transitions, Concurrency & Invariants · 2026-11-22

Access requests, grants, and sessions transition through strictly bounded lifecycle states governed by transactional invariants.

---

## 1. Object State Taxonomy

| Object | Permitted States | Terminal States |
| :--- | :--- | :--- |
| **Access Request** | `pending`, `approved`, `rejected`, `cancelled`, `expired` | `approved`, `rejected`, `cancelled`, `expired` |
| **Request Revision** | `pending`, `approved`, `rejected`, `superseded` | `approved`, `rejected`, `superseded` |
| **Approval Step** | `waiting`, `pending`, `approved`, `rejected`, `superseded` | `approved`, `rejected`, `superseded` |
| **Access Grant** | `scheduled`, `active`, `expired`, `revoked` | `expired`, `revoked` |
| **Session Launch** | `active`, `consumed`, `expired` | `consumed`, `expired` |
| **Access Session** | `starting`, `active`, `terminating`, `ended`, `failed` | `ended`, `failed` |

---

## 2. Request Revision & Approval Transition Flow

```
                 [ Submit Request Revision 1 ]
                               │
                               ▼
                    [ Revision 1: pending ]
                               │
                ┌──────────────┴──────────────┐
                │                             │
    [ Requester Replaces ]         [ Approvers Vote ]
                │                             │
                ▼                             ├── All Approved ──▶ [ Grant Issued ]
    [ Revision 1: superseded ]               │
    [ Revision 2: pending ]                  └── Any Rejected ──▶ [ Request: rejected ]
                │
                ▼
        [ Restart Steps ]
```

### Invariants:
1. **Immutable Revisions**: A frozen revision's timestamps, justification, and accounts can never be updated in place.
2. **Sequential Step Progression**: Only Step 1 begins in `pending`. Step 2 remains in `waiting` until Step 1 is `approved`.
3. **Optimistic Locking**: Replacing a revision checks `expected_revision_id`. Concurrent decisions on superseded revisions return HTTP 409 `STALE_REVISION`.

---

## 3. Grant & Session Lifecycle

```
[ Final Approval Recorded ]
             │
             ▼
    [ Grant: scheduled ]
             │ (now >= effective_start_at)
             ▼
     [ Grant: active ] ────────── Operator Revokes / IdP Disabled ──────────▶ [ Grant: revoked ]
             │                                                                         │
             │ Issue Launch Token                                                      │
             ▼                                                                         │
    [ Launch: active (60s) ]                                                           │
             │ Gateway Consumes                                                        │
             ▼                                                                         │
    [ Session: starting ]                                                              │
             │ Connects Target Host                                                    │
             ▼                                                                         │
     [ Session: active ] ◀─────────────────────────────────────────────────────────────┘
             │                                                                         │
             ├── Lease Expiry / User Disconnect / Operator Termination ────────────────┤
             │                                                                         ▼
             │                                                              [ Session: terminating ]
             │                                                                         │
             │ Gateway Evidence Received (state: ended)                                │
             ▼                                                                         ▼
     [ Session: ended ] ◀──────────────────────────────────────────────────────────────┘
```

### Invariants:
1. **Single-Use Launch Consumption**: `SessionLaunch` can be consumed at most once. Concurrent consumption races are resolved via database row locks; only one session starts.
2. **Terminal Invariant**: Once a session reaches `ended` or `failed`, late or duplicate gateway events cannot reopen it.
3. **Lease Boundary**: An active session's lease deadline can never exceed the parent grant's `effective_end_at`.
