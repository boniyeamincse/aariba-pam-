# Ariba PAM vision

> Planning baseline · 2026-11-22

Ariba PAM gives infrastructure teams one controlled path to privileged access. A named user requests a defined action or account on an approved target. Approval, access duration, active session control, and audit evidence stay linked throughout the lifecycle.

## Users and outcomes

| Audience | Outcome |
| --- | --- |
| Operations and developers | Obtain the right temporary access and see clearly why it was approved, denied, or ended |
| Asset owners and approvers | Authorize access using the target, account, duration, business reason, and change or incident context |
| Security operations | Detect risky activity, terminate sessions, and correlate evidence |
| Auditors | Verify who did what, under whose approval, and during which session |

## Initial delivery boundary

Start with interactive Linux SSH for one organization and a small approved asset set. Use one enterprise identity provider for the production pilot. Ariba PAM owns its workflows and policy enforcement and uses maintained protocol and cryptography implementations. Additional protocols and shared hosting are roadmap items.

Pilot success means controlled paths work, unauthorized paths are denied, active access can be withdrawn within the agreed limit, and evidence survives realistic failure and recovery exercises.

See [software idea](01-SOFTWARE-IDEA.md), [business requirements](03-BUSINESS-REQUIREMENTS.md), and [pilot criteria](05-NON-FUNCTIONAL-REQUIREMENTS.md).
