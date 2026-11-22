# 08 · Authorization Policy Engine: Ariba PAM

> Canonical Permissions & Dynamic Evaluation Pipeline · 2026-11-22

The Ariba PAM Authorization Policy Engine is the single server-side authority governing access to all platform resources and administrative actions. Frontend interface visibility never serves as an authorization mechanism.

---

## 1. Canonical Permission Registry

Permissions follow a hierarchical, dot-notated naming convention `<domain>.<resource>.<action>`:

```
identity.user.read
identity.user.create
identity.user.suspend

rbac.role.read
rbac.role.create
rbac.role.assign
rbac.permission.manage

scope.read
scope.create
scope.resource.assign

asset.read
asset.create
asset.update
asset.disable

account.read
account.create
account.update
account.rotate

access.request.create
access.request.cancel
access.approval.decide
access.grant.launch
access.grant.revoke

session.read
session.monitor
session.terminate

recording.read
recording.playback
recording.export

vault.secret.create
vault.secret.rotate
vault.secret.revoke

gateway.read
gateway.manage

audit.read
audit.verify

evidence.retention.manage
evidence.hold.manage

emergency.request
emergency.activate
emergency.revoke
```

---

## 2. Decision Pipeline & Logic

Every request processed by the Control Plane evaluates the following decision flow:

```
[ Incoming Request (Principal, Action, Target Resource, Context) ]
                             │
                             ▼
                 [ 1. Is Principal Active? ] ──NO──▶ [ DENY (Account Inactive) ]
                             │ YES
                             ▼
                [ 2. Check Explicit Deny ] ──YES─▶ [ DENY (Explicit Deny Policy) ]
                             │ NO
                             ▼
             [ 3. Has Base RBAC Permission? ] ──NO──▶ [ DENY (Permission Lacking) ]
                             │ YES
                             ▼
             [ 4. Within Resource Scope? ] ───NO──▶ [ DENY (Conceal as HTTP 404) ]
                             │ YES
                             ▼
             [ 5. MFA Assurance Satisfied? ] ─NO──▶ [ DENY (Step-up Required) ]
                             │ YES
                             ▼
             [ 6. SoD Violation Detected? ] ──YES─▶ [ DENY (SoD Conflict) ]
                             │ NO
                             ▼
            [ 7. ABAC Policy Constraints? ] ──NO──▶ [ DENY (Policy Violation) ]
                             │ YES
                             ▼
                    [ ALLOW OPERATION ]
                             │
                             ▼
             [ Record Decision in Audit Log ]
```

---

## 3. Formal Decision Pipeline Implementation

```python
def authorize(
    principal: Principal,
    action: str,
    resource: Optional[Resource],
    context: RequestContext,
) -> AuthorizationResult:
    """
    Evaluates authorization using Default Deny.
    Returns AuthorizationResult(allowed: bool, reason: str, code: str).
    """
    # 1. Identity Liveness Check
    if not principal.is_active:
        return AuthorizationResult(False, "User account is disabled", "ACCOUNT_DISABLED")

    # 2. Explicit Deny Evaluation (Explicit Deny overrides Allow)
    if is_explicitly_denied(principal, action, resource, context):
        return AuthorizationResult(False, "Explicit deny rule applied", "EXPLICIT_DENY")

    # 3. RBAC Entitlement Check
    if not principal.has_permission(action):
        return AuthorizationResult(False, f"Lacking permission: {action}", "FORBIDDEN")

    # 4. Resource Scope Enforcement
    if resource is not None and not principal.has_resource_scope(resource):
        # Conceal out-of-scope resources with 404
        return AuthorizationResult(False, "Resource not found within scope", "RESOURCE_NOT_FOUND")

    # 5. Contextual MFA Assurance
    if requires_mfa_step_up(action) and not context.is_phishing_resistant_mfa:
        return AuthorizationResult(False, "Phishing-resistant MFA required", "MFA_REQUIRED")

    # 6. Separation of Duties Validation
    sod_check = evaluate_sod(principal, action, resource, context)
    if not sod_check.valid:
        return AuthorizationResult(False, f"SoD violation: {sod_check.rule_name}", "SOD_CONFLICT")

    # 7. ABAC Policy Conditions (Schedule, Time-window, Ticket)
    if not evaluate_abac_conditions(principal, action, resource, context):
        return AuthorizationResult(False, "Environmental policy conditions not satisfied", "POLICY_REJECTED")

    # All checks passed
    return AuthorizationResult(True, "Authorized", "ALLOWED")
```

---

## 4. Decision Recording & Cache Invalidation

1. **Audit Trail**: Every evaluated decision (both `ALLOW` and `DENY`) is recorded in the `authorization_decisions` table with timestamps, principal identity, evaluated permission, and decision reason code.
2. **Dynamic Cache Invalidation**: When an administrator updates a role, reassigns scopes, or revokes grants, all cached authorization decisions and active token sessions are invalidated immediately, triggering dynamic re-evaluation on subsequent calls.
