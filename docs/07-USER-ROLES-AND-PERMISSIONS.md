# 07 · User Roles and Permissions: Ariba PAM

> Hybrid RBAC + ABAC Architecture & Custodian Boundary Separation · 2026-11-22

Ariba PAM does not rely on simple, flat RBAC. To satisfy the demands of enterprise zero-trust infrastructure, authorization is evaluated as:

$$\text{Authorization Decision} = \text{RBAC (Action)} \land \text{ABAC (Conditions)} \land \text{Resource Scope (Boundary)} \land \text{SoD (Independence)}$$

---

## 1. Role Permission Matrix

| Permission | Requester | Approver | Asset Owner | PAM Admin | Security Operator | Auditor |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **View assets** | Scoped | Scoped | Scoped | Scoped | Scoped | Scoped |
| **Submit request** | Yes | No | Yes | Scoped | No | No |
| **Approve request** | No | Yes | Assigned | No | No | No |
| **Manage assets** | No | No | Yes | Scoped | No | No |
| **Manage accounts** | No | No | Yes | Scoped | No | No |
| **Manage policies** | No | No | Propose | Propose | No | No |
| **Revoke grants** | No | No | No | Scoped | Yes | No |
| **Terminate sessions** | Own | No | No | Scoped | Yes | No |
| **Playback recording** | No | No | No | No | Scoped | Permitted |
| **Export evidence** | No | No | No | No | No | Permitted |
| **Manage gateways** | No | No | No | Scoped | No | No |
| **Manage RBAC** | No | No | No | Scoped | No | No |

> **Rule**: "Yes" indicates the role possesses the base entitlement; every concrete operation must still satisfy the caller's assigned **Resource Scope**, active **Asset Policy**, and **Separation of Duties** checks.

---

## 2. Custodian Boundary Isolation (Anti-Superuser Architecture)

A critical vulnerability in traditional enterprise PAM systems is the all-powerful "Super Administrator" or root PAM Admin. In Ariba PAM, high-risk administrative duties are partitioned across separate, isolated security boundaries:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        Ariba PAM Roles & Boundaries                    │
│                                                                        │
│   ┌───────────────────────────┐    ┌───────────────────────────────┐   │
│   │         PAM Admin         │    │      Evidence Custodian       │   │
│   │ - Manage roles & scopes   │    │ - Manages WORM evidence bucket│   │
│   │ - Onboard gateway zones   │    │ - Sets retention & legal holds│   │
│   │ - CANNOT access secrets   │    │ - Independent of PAM Admin    │   │
│   │ - CANNOT modify audit logs│    └───────────────────────────────┘   │
│   └───────────────────────────┘                                        │
│                                                                        │
│   ┌───────────────────────────┐    ┌───────────────────────────────┐   │
│   │   Signing/Vault Custodian │    │      Emergency Custodian      │   │
│   │ - Manages User CA root key│    │ - Holds break-glass shares    │   │
│   │ - Root key rotation       │    │ - Unilateral activation DENIED│   │
│   │ - HSM custody             │    │ - Multi-party drill authority │   │
│   └───────────────────────────┘    └───────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Evidence Custodian**:
   - Manages the independent WORM evidence repository, retention periods, and legal holds.
   - **Isolation**: Standard PAM Administrators have zero delete, update, or overwrite permissions on evidence stores.
2. **Signing / Vault Custodian**:
   - Maintains custody over the SSH User Certificate Authority (CA) private key, hardware security modules (HSMs), and credential vault roots.
   - **Isolation**: The PAM Control Plane and SSH Gateways only possess automated signing capabilities; human PAM Admins cannot export or read private CA root keys.
3. **Emergency Custodian**:
   - Holds credentials for out-of-band break-glass procedures during complete PAM/IdP disasters.
   - **Isolation**: Emergency credentials require multi-party threshold authorization and immediately notify security operations upon assembly.

---

## 3. Role Hierarchy & Built-In System Roles

1. **`requester`**: Regular engineer or contractor requesting temporary administrative access.
2. **`approver`**: Team lead or manager authorized to review and approve access requests for systems within their resource scope.
3. **`asset_owner`**: System owner managing asset metadata, target account definitions, and proposing access policies.
4. **`pam_admin`**: Platform administrator managing infrastructure inventory, gateway enrollment, role assignments, and scope definitions.
5. **`security_operator`**: Security operations team member monitoring real-time sessions, enforcing immediate revocation, and terminating active sessions.
6. **`auditor`**: Compliance and security auditor inspecting historical audit logs, playing back session recordings, and requesting compliance exports.
7. **`evidence_custodian`**: Specialized role administering evidence retention and compliance holds.
8. **`signing_custodian`**: Cryptographic key administrator overseeing CA rollover and recovery.
9. **`emergency_custodian`**: Multi-party break-glass trustee.
10. **`system_gateway`**: Zone-bound automated service identity for SSH proxying and evidence ingestion.

### Protection of System Roles
Custom roles may be defined via the API, but built-in system security roles are immutable: they cannot be deleted, renamed, or modified to weaken mandatory security restrictions.
