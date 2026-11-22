# Audit, recording, and recovery module

> Proposed implementation specification · 2026-11-22

## Evidence contract

| Evidence | Required data | Custody |
| --- | --- | --- |
| Audit event | Stable source event ID, UTC occurrence and ingestion times, actor, action, scoped resource, outcome, reason code, correlation IDs | Independent audit storage |
| Recording | Session ID, recorder identity, segment order, start and end times, coverage state, integrity metadata, retention class, and storage reference | Protected recording storage |
| Approval history | Immutable revision, step, deciding principal, permission context, decision, reason and timestamp | Transactional history plus audit evidence |
| Recovery and emergency record | Exercise or incident reference, operator, target scope, start and close times, verification results, reviewer, and evidence location | Approved incident or audit store |

Do not include secret values, session capabilities, raw terminal content, or confidential request justification in forwarded security events. Sanitize values before logging. Evidence queries must apply the reviewer's scope before returning metadata, objects, or download details.

Accept repeated delivery by stable source event ID. Detect gaps and document which source reported them. Serialize retention changes and legal holds through a separate custody role. Verify integrity on ingest and before playback or export. An incomplete recording must remain visibly incomplete.

## Restore and emergency exercises

1. Establish the exercise reference, backup cut-off, approved RTO/RPO, and isolated environment.
2. Restore authorization data, policy, gateway registrations, evidence indexes, and signer or vault access. Verify the protected recording and audit stores independently.
3. Keep launch closed while validating identity and policy freshness. Reconcile grant and session state and verify that revoked or expired access cannot be reactivated by a restore.
4. Drill the named emergency custodian path with PAM and IdP unavailable. Exercise independent evidence capture, SOC notification, and post-use access cleanup.
5. Record elapsed recovery time, allowable data loss, discrepancies, and approval to reopen access. Track failed checks to closure.

Test T-07, T-08, and T-09 using the [evidence procedure](../../docs/16-TESTING-STRATEGY.md). See [security controls](../../docs/13-SECURITY-REQUIREMENTS.md) and [retention and recovery criteria](../../docs/05-NON-FUNCTIONAL-REQUIREMENTS.md).
