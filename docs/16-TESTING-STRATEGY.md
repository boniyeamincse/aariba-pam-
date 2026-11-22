# Testing strategy

> Proposed verification plan · 2026-11-22

| Layer | Coverage |
| --- | --- |
| Unit | Policy decisions, approval independence, transition rules, expiry, and evidence redaction |
| Integration | Transaction conflicts, durable outbox, IdP events, gateway authentication, SSH target identity, and evidence storage |
| End-to-end lab | Request approval, grant launch, live SSH, revocation, termination, and auditor review on synthetic hosts |
| Reliability | Clock skew, retries, gateway partitions, recording outage, buffer exhaustion, key rollover, restore, and representative load |
| Release | Compatibility, artifact review, migration, rollback, security review, and approval evidence |

## Pilot test catalog

| ID | Scenario and evidence |
| --- | --- |
| T-01 | Verify phishing-resistant MFA and disable an IdP user with an active session. Compare IdP and gateway timestamps against NFR-01 |
| T-02 | Exercise self-approval, delegated approval, cross-scope decisions, duplicate votes, and target account edits. Verify FR-03–04 and immutable approval history |
| T-03 | Verify allowed gateway-to-target path and denied direct SSH, unknown or changed host identity, wrong target account, and unapproved channels. Verify NFR-06 |
| T-04 | Race multiple uses of one launch and repeat after revocation or expiry. At most one session may start with a valid launch. Verify FR-05 |
| T-05 | Revoke a grant with multiple sessions. Partition one gateway and measure stop times, including when grant expiry is earlier than lease expiry. Verify NFR-01–02 |
| T-06 | Verify scoped certificate issuance and signer rotation. If testing a vault-backed target, confirm secret access scope, non-disclosure, rotation, and recovery. Verify FR-06 |
| T-07 | Interrupt recorder and recording storage during mandatory capture. Verify pause, timeout, evidence buffering or launch denial, and alerts. Verify NFR-03 |
| T-08 | Exercise unauthorized recording access, protected deletion, permitted export, and independent integrity verification. Verify NFR-07 |
| T-09 | Restore the system and evidence in an isolated lab. Drill emergency access with PAM and the IdP unavailable. Verify NFR-04 and FR-11 |
| T-10 | Check dependency and image scans, upgrade and rollback evidence, compatibility, performance, and operational alerts. Verify NFR-05 and NFR-08 |
| T-11 | Interrupt notification delivery after an approval. Verify the decision is retained, delivery retries are visible, and duplicate messages cannot repeat a state transition. Verify FR-10 |

| Functional coverage | Primary checks |
| --- | --- |
| FR-01 · Identity | T-01 |
| FR-02 · Inventory and scope | T-02, T-03 |
| FR-03 and FR-04 · Requests and approvals | T-02 |
| FR-05 and FR-06 · Grant, launch, and SSH | T-03, T-04, T-06 |
| FR-07 · Termination and revocation | T-01, T-05 |
| FR-08 and FR-09 · Evidence and review | T-07, T-08 |
| FR-10 · Notifications | T-11 |
| FR-11 · Emergency access | T-09 |

Capture environment, build, data fixtures, expected result, observed timing, outcome, reviewer, and evidence location for each execution. Use sanitized records in the repository. A pilot needs passing evidence for applicable checks and approval from security and infrastructure owners.

## Execution and result record

1. Prepare isolated environments, distinct synthetic roles, separate asset scopes, and known host identities. Use the environment's approved time source and record clock skew.
2. Run the corresponding positive and denied scenarios before injecting failures. Reset fixtures between runs and record any changed policy versions.
3. For concurrency or outage tests, record timestamps and shared identifiers at each affected component. Confirm observable system state from both the portal and gateway where applicable.
4. Use a row in the following format for each run. Mark skipped and blocked checks with their reason and owner. Record a separate run for each retry.

| Run ID | Test and requirements | Build and environment | Expected outcome | Observed outcome and timing | Result | Evidence and reviewer |
| --- | --- | --- | --- | --- | --- | --- |

The pilot catalog defines planned checks. Record implementation results below as each task lands.

## Lab implementation results

| Run ID | Scope | Environment | Observed result | Evidence |
| --- | --- | --- | --- | --- |
| LAB-P1-08 | Portal sign-in and scoped catalog under FR-01 and FR-02 | Python 3.14, SQLite, Playwright and Chromium, synthetic identities · 2026-11-22 | 23 tests passed, including both browser cases. Verified permitted inventory, loading, empty and denied states, sign-out, and expired-session handling | [API checks](../tests/test_portal.py), [browser checks](../tests/test_portal_browser.py) |
| LAB-P1-08-PACKAGE | Local installation and fixture smoke check | Package wheel and temporary SQLite database · 2026-11-22 | Wheel contains all three portal files. Applied the migration and ran the seed twice successfully | [Local setup](../README.md#start-the-lab-portal) |
| LAB-P2-01 | Reviewed policy publication, ordered approvals, and downstream authorization under FR-03, FR-04, and T-02 | Python 3.14, SQLite suite and disposable PostgreSQL 18 · 2026-11-22 | Full suite passed 28 tests. Six policy and workflow tests passed on PostgreSQL. Verified independent review, stale publication denial, invalid rules, distinct approvers, and superseded request and launch denial | [Policy tests](../tests/test_policies.py), [workflow test](../tests/test_workflow.py) |
| LAB-P2-01-MIGRATION | Policy schema upgrade and downgrade | Disposable PostgreSQL 18 with an existing baseline record · 2026-11-22 | Upgrade preserved the baseline record and created the policy table. Downgrade removed the policy table | [Policy migration](../alembic/versions/0002_access_policy_versions.py) |

These runs verify synthetic lab behavior. T-01 and T-10 still require the approved pilot identity provider, runtime, and pilot test evidence.

See [pilot targets](05-NON-FUNCTIONAL-REQUIREMENTS.md) and [security mapping](13-SECURITY-REQUIREMENTS.md).
