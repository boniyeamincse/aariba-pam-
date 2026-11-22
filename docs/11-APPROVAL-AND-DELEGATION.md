# 11 · Approval and Delegation: Ariba PAM

> Workflow Routing, Immutable Revisions & Controlled Delegation · 2026-11-22

Access requests and administrative changes in Ariba PAM are governed by policy-driven approval workflows and auditable delegation mechanisms.

---

## 1. Multi-Step Approval Workflows

1. **Policy-Driven Routing**: When an access request is submitted, the engine inspects the asset's active policy (`access_policy_versions`). If the policy requires $N$ approvals (between 1 and 5), $N$ sequential `approval_steps` are automatically generated.
2. **Distinct Approver Enforcement**: Each step must be approved by a distinct human approver within the asset's scope. An approver who recorded a decision on Step 1 cannot vote on Step 2.
3. **Atomic Grant Issuance**: When the final required approval step is recorded as `approved`, the database transaction atomically issues an `access_grant` and schedules its validity window.

---

## 2. Immutable Revisions & Stale Decision Handling

- When an access request is submitted, it is frozen as **Revision 1**.
- If the requester needs to change the time window or justification before approval, they cannot mutate Revision 1 in place. Instead, they submit a **replacement revision** (`POST /api/v1/requests/{id}/revisions`), generating **Revision 2**.
- Submitting Revision 2 supersedes all pending approval steps linked to Revision 1.
- **Stale-Decision Protection**:
  - Approvers must include `expected_revision_id` in their decision payload.
  - If an approver submits a decision while a replacement revision was being created, the server rejects the decision with **HTTP 409 Conflict (`STALE_REVISION`)**.
  - The approver interface receives clear feedback:
    > *"Notice: The proposal changed. Reload the current revision before accepting another decision."*

---

## 3. Delegation Engine & Rules

When an approver is on leave or unavailable, approval authority may be delegated under seven strict constraints:

| Rule | Description |
| :--- | :--- |
| **Rule 1 · Delegation Authority** | The delegator must explicitly hold the `access.approval.delegate` permission within their active role. |
| **Rule 2 · Delegate Competence** | The selected delegate must possess the base `approver` role in the organization. |
| **Rule 3 · Scope Non-Expansion** | The delegated scope can never exceed the delegator's assigned resource scope. If Delegator Bob has scope over `payments`, he cannot delegate authority over `analytics`. |
| **Rule 4 · Strict Bounded Windows** | Every delegation must have explicit `valid_from` and `expires_at` timestamps (maximum 14 days). Open-ended delegations are rejected. |
| **Rule 5 · Anti-Circularity & Self-Delegation** | Self-delegation ($A \to A$) is rejected. Circular delegation chains ($A \to B \to A$ or $A \to B \to C \to A$) are detected and blocked at creation time. |
| **Rule 6 · Self-Approval Prohibition Across Delegation** | A delegate cannot use delegated authority to approve their own personal access requests. |
| **Rule 7 · Dual-Identity Auditing** | Whenever a delegate records an approval, the audit trail immutably records both the **original delegator** (`delegator_id`) and the **acting delegate** (`acting_user_id`), preserving complete accountability. |
