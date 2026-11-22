# User workflow

> Proposed lifecycle baseline · 2026-11-22

## Standard SSH access

1. The user signs in through the IdP, selects a permitted asset and target account, and submits the access window and justification.
2. Policy assigns the approval steps. Approvers review the same request revision and record decisions. A rejection or expired approval prevents grant issuance.
3. The control plane rechecks current policy and creates a scoped grant. When the window opens, the user requests a single-use launch authorization.
4. The assigned gateway atomically consumes the launch authorization, verifies target identity and recording readiness, and connects using scoped credentials.
5. The gateway renews authorization while the session runs. User disconnect, operator termination, grant expiry, revocation, identity disablement, or a policy violation ends the session. A lease expiry ends it during a partition.
6. The gateway supplies the end status and evidence. The user sees the final reason and authorized reviewers can correlate the session with the request.

## State ownership

| Object | States | Transition rules |
| --- | --- | --- |
| Request revision | Draft, Pending approval, Approved, Rejected, Cancelled, Expired | Drafts exist before API submission. Submission freezes the revision. Replacing a pending revision cancels that revision and creates a new approval flow. Changes after approval require a new request. The approved revision remains historical after grant expiry or revocation. |
| Grant | Scheduled, Active, Expired, Revoked | The gateway checks the effective window at launch and during the session. Expired and revoked grants are terminal. |
| Session | Starting, Active, Terminating, Ended, Failed | A gateway confirmation records the end. A failure before target connection produces a failed session. A disconnected gateway remains unconfirmed until reconciliation supplies evidence. |

## Emergency access

When PAM or the IdP is unavailable, a named custodian uses the approved out-of-band procedure, documents scope and reason independently, notifies SOC through an available channel, and closes access after the approved window. The security owner reviews the record and verifies any required credential rotation or revocation.

See [functional requirements](04-FUNCTIONAL-REQUIREMENTS.md) and [API routes](11-API-SPECIFICATION.md).
