# Security requirements

> Proposed security baseline · 2026-11-22

## Threats and controls

| ID | Threat | Required control | Verification |
| --- | --- | --- | --- |
| SEC-01 | Account takeover or delayed offboarding | Use the pilot IdP, enforce phishing-resistant MFA, verify current account state, and propagate disablement | T-01 |
| SEC-02 | Unauthorized change or approval | Deny by default, check resource scope, block self-approval including delegation, and require independent review of sensitive admin changes | T-02 |
| SEC-03 | Direct or misdirected privileged access | Restrict target network paths, verify host identity, scope gateway service identities, and deny unapproved SSH channels | T-03 |
| SEC-04 | Launch replay or session surviving authorization | Use one-time launches with atomic consumption, gateway leases, and local expiry. Apply revocation across all associated sessions | T-04, T-05 |
| SEC-05 | Key theft or reusable credential exposure | Keep CA custody isolated. Restrict issuance to approved identities and accounts, audit use, and test rollover. Require vault safeguards for stored-credential targets | T-06 |
| SEC-06 | Evidence tampering, recording loss, or excess disclosure | Separate custody, restrict reads and exports, verify integrity, and enforce recording failure behavior and retention | T-07, T-08 |
| SEC-07 | Platform outage or emergency access misuse | Test restore and break-glass, track custody, review every use, and clean up emergency access | T-09 |
| SEC-08 | Dependency compromise or unsafe release | Inventory dependencies, scan source and images, review critical changes, and promote verified immutable artifacts | T-10 |

## Evidence and privacy

Record stable event IDs, actor, action, target, outcome, timestamps, and relevant request, grant, or session identifiers. Keep raw terminal data in the recording store. Limit forwarding to approved security metadata. Approve recording notice, retention, authorized export, legal holds where applicable, and handling of personal or sensitive content before live capture.

## Recovery and incident handling

Document containment for a compromised IdP, gateway, signer, or vault. Include service identity revocation, target trust recovery, protection of existing evidence, and criteria to reopen access. Assign operators for incident, evidence, and platform recovery. Review boundaries and failure cases before approving the pilot.

## Pre-pilot review

- Security and infrastructure review the gateway, target trust, and signer boundaries using the approved pilot asset list.
- IAM verifies the assurance criteria, account disablement signal, and identity recovery path with T-01.
- Evidence and privacy owners approve notice, retention, review rights, and incident escalation before live capture.
- Platform and security review restore and emergency drill results. Escalate unmitigated risks for a documented decision before opening access.

See [test catalog](16-TESTING-STRATEGY.md), [NIST SP 800-207](https://csrc.nist.gov/pubs/sp/800/207/final), and [NIST SP 800-63B-4](https://pages.nist.gov/800-63-4/sp800-63b.html).
