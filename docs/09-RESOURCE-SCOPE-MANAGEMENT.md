# 09 · Resource Scope Management: Ariba PAM

> Hierarchical Infrastructure Boundaries & Scoping Logic · 2026-11-22

Resource Scoping is the structural foundation of Ariba PAM's zero-trust model. A user may possess a high-privilege role (such as `security_operator` or `approver`), but that role is completely inert unless bound to a specific **Resource Scope**.

---

## 1. Recommended Scope Hierarchy

Resource scopes form a directed acyclic tree representing the enterprise topology:

```
Organization (Ariba Enterprise)
 ├── Production Environment (prod)
 │    ├── Linux Servers (prod-linux)
 │    │    ├── payment-db-01.lab
 │    │    └── order-api-01.lab
 │    └── Network Devices (prod-net)
 │         └── core-switch-01.lab
 │
 ├── Development Environment (dev)
 │    ├── Linux Servers (dev-linux)
 │    │    └── sandbox-01.lab
 │    └── Windows Servers (dev-win)
 │         └── win-build-01.lab
 │
 └── Cloud Environment (cloud)
      ├── AWS (cloud-aws)
      │    └── us-east-1-cluster
      └── Azure (cloud-azure)
           └── westeurope-cluster
```

---

## 2. Scope Containment & Inheritance Rules

### Explicit Policy Inheritance
- In traditional directory trees, a user granted permissions on a parent node implicitly inherits unrestricted rights over all child nodes.
- **Ariba PAM Security Rule**: **Child scopes do NOT automatically inherit broad permissions from parent scopes.** Scope propagation requires an explicit inheritance flag (`inherit_children: true`) defined in the role assignment.
- For high-risk environments (such as `prod-linux` and `pci-zone`), role assignments must be anchored directly to that specific environment node or explicit asset group, preventing accidental privilege escalation from broad corporate root assignments.

### Multiple Scope Bindings
A user may hold different roles in different scopes:
- User Alice may be an `approver` in `dev-linux`.
- Alice may be a `requester` only in `prod-linux`.
- Alice has zero visibility or access into `prod-net`.

---

## 3. Scope Resolution & Evaluation

When a user invokes an operation on an asset:
1. The engine retrieves the asset's assigned scope IDs from `scope_resources`.
2. The engine traverses upwards from the asset's scope node to evaluate if any of the caller's active `user_role_assignments` bind to this node or a permitted parent node.
3. If no matching scope assignment exists:
   - The engine halts evaluation immediately.
   - The asset is concealed with **HTTP 404 Not Found**.
   - No error details indicating the asset's existence are leaked to the client.

```python
def is_asset_in_scope(user: User, asset: Asset, required_role: str) -> bool:
    """Evaluate whether an asset falls within caller's scoped role assignment."""
    user_assignments = [
        ra for ra in user.role_assignments 
        if ra.role.name == required_role and ra.status == "active"
    ]
    for assignment in user_assignments:
        if assignment.scope_type == "global" and assignment.scope_value == "*":
            return True
        if assignment.scope_type == "environment" and assignment.scope_value == asset.environment:
            return True
        if assignment.scope_type == "team" and assignment.scope_value == asset.team:
            return True
        if assignment.scope_type == "asset" and assignment.scope_value == asset.id:
            return True
    return False
```
