# Ariba PAM --- Enterprise Privileged Access Management

## Software Idea & Product Foundation

> Product foundation carried forward into the numbered documentation set. The [README](../README.md) indexes the current requirements, architecture, pilot gates, and roadmap.

**Product name:** Ariba PAM\
**Product category:** Enterprise Privileged Access Management (PAM)\
**Document type:** Software Idea / Product Vision / Initial Scope\
**Status:** Initial planning baseline --- decisions remain open for
detailed project documentation\
**Development approach:** Build from scratch, incrementally, with an
extensible enterprise architecture

**Initial deployment assumption:** One organization with separate asset and
administrative scopes for its teams and environments. Confirm this assumption
in Phase 0. If shared hosting for multiple organizations is required, design
and test tenant isolation before onboarding a second organization.

------------------------------------------------------------------------

## 1. Product Overview

Ariba PAM is a custom-built, enterprise-grade Privileged Access
Management platform designed to control, monitor, record, and audit
privileged access to an organization's critical infrastructure.

The platform will provide a centralized and policy-driven way for
authorized employees, administrators, developers, and security engineers
to request and use privileged access to approved systems.

Ariba PAM will be developed as an independent software product. Its core
business logic, identity and authorization workflows, access-request
engine, approval engine, policy engine, session orchestration, audit
system, and administrative portal will be developed specifically for
Ariba PAM.

The project will **not** be a branded dashboard placed on top of an
existing PAM product. However, it may use mature, security-reviewed
libraries and standards-based implementations for cryptography, SSH/RDP
protocol handling, MFA, and other low-level security functions.
Security-critical primitives must not be invented or implemented from
scratch.

### Product vision

Provide one controlled access path to privileged infrastructure, with
verifiable identity, explicit authorization, limited access duration,
session accountability, and reliable audit evidence.

### Core principles

1.  **Zero Trust:** Never trust a user or connection solely because it
    originates from an internal network.
2.  **Least Privilege:** Grant only the permissions required for the
    approved task.
3.  **Just-in-Time Access:** Privileged access should be temporary and
    time-bound wherever practical.
4.  **Default Deny:** Access is denied unless an explicit policy permits
    it.
5.  **Separation of Duties:** Requesters, approvers, vault
    administrators, and auditors must have appropriately separated
    responsibilities.
6.  **Full Accountability:** Privileged actions must produce
    attributable audit events.
7.  **Secure by Design:** Threat modeling, secure coding, testing, and
    independent security review are part of development.
8.  **Extensibility:** New protocols, integrations, policies, and
    deployment models should be addable without redesigning the entire
    platform.

------------------------------------------------------------------------

## 2. Business Problems Ariba PAM Will Address

Organizations often face the following privileged-access risks:

-   Shared administrator accounts and passwords.
-   Direct SSH or RDP access without centralized control.
-   Permanent administrator privileges.
-   Access that remains enabled after a task is completed.
-   Weak or inconsistent approval processes.
-   Limited visibility into active privileged sessions.
-   Incomplete records of commands and administrative activities.
-   Credentials stored in spreadsheets, scripts, chat messages, or
    unprotected files.
-   Difficulty identifying who accessed a server, when, why, and under
    whose approval.
-   Inconsistent access practices across System Administration,
    Development, and Cybersecurity teams.

Ariba PAM will address these problems through centralized identity,
access requests, approvals, policy enforcement, controlled gateways,
credential protection, session oversight, and tamper-evident audit
records.

------------------------------------------------------------------------

## 3. Product Goals

### Primary goals

-   Centralize privileged access management.
-   Manage employees, departments, roles, permissions, and access
    policies.
-   Maintain an inventory of protected servers and infrastructure
    assets.
-   Provide request-and-approval workflows.
-   Grant time-limited privileged access.
-   Provide controlled SSH access to Linux systems.
-   Provide controlled RDP access to Windows systems.
-   Monitor and record privileged sessions.
-   Securely manage privileged credentials and keys.
-   Revoke access and terminate sessions when authorization expires or
    is withdrawn.
-   Maintain searchable audit trails and management reports.
-   Integrate security events with Wazuh and Ariba SOC.

### Long-term goals

-   Support multiple business units, sites, and infrastructure zones.
-   Support database and network-device access workflows.
-   Provide risk-based and policy-based approvals.
-   Support automated credential rotation.
-   Provide high availability and disaster recovery.
-   Support additional enterprise identity providers and directories beyond
    the initial pilot integration.
-   Provide a documented API and integration framework.
-   Support large-scale deployments and delegated administration.

### Non-goals for the first release

-   Replacing the organization's entire identity provider.
-   Building a new cryptographic algorithm.
-   Implementing SSH or RDP protocol cryptography independently.
-   Automatically granting unrestricted administrator access.
-   Supporting every infrastructure protocol in the initial MVP.
-   Deploying directly to production before security testing and pilot
    validation.

------------------------------------------------------------------------

## 4. Intended Users and Departments

Ariba PAM will initially support these organizational groups:

### System Administration Team

Typical use cases:

-   Linux and Windows server maintenance.
-   Service and application troubleshooting.
-   Operating-system configuration.
-   Approved patching and system administration.
-   Emergency infrastructure support.

### Software Development Team

Typical use cases:

-   Approved application deployment.
-   Application troubleshooting.
-   Access to designated development and staging systems.
-   Controlled production support when separately authorized.

Developer access must not automatically include unrestricted root or
local Administrator privileges.

### Cybersecurity Team

Typical use cases:

-   Authorized security investigations.
-   Incident response.
-   Security configuration verification.
-   Log and evidence collection.
-   Approved vulnerability remediation activities.
-   Privileged-access audit and review.

Cybersecurity access must also be governed by explicit authorization and
audit requirements.

### Management and Server Owners

Typical use cases:

-   Reviewing and approving access requests.
-   Reviewing access history for owned systems.
-   Defining access requirements for business services.

### Auditors

Typical use cases:

-   Read-only review of access approvals.
-   Audit-log review.
-   Session-recording review when authorized.
-   Compliance evidence collection.

------------------------------------------------------------------------

## 5. Product Modules

The product will be modular. Each module should have a clearly defined
responsibility and API boundary.

### 5.1 Identity and User Management

-   User lifecycle management.
-   User activation, suspension, and termination.
-   Department and team management.
-   Role and permission management.
-   MFA enrollment and recovery controls.
-   Login history and authentication events.
-   Integration with one enterprise identity provider for the production
    pilot. Additional providers and directory integrations can follow.

### 5.2 Server and Asset Inventory

-   Linux server inventory.
-   Windows server inventory.
-   Network-device inventory (future phase).
-   Database-server inventory (future phase).
-   Hostname, IP, operating system, environment, location, owner, and
    business service.
-   Server groups and tags.
-   Criticality and risk classification.
-   Connection configuration and gateway assignment.
-   Asset lifecycle and ownership history.

### 5.3 Access Request Management

A user should be able to request access to a specific target system with
a clear business reason.

Request fields may include:

-   Requester.
-   Target server or server group.
-   Requested protocol.
-   Requested account or privilege level.
-   Access start time and end time.
-   Requested duration.
-   Business justification.
-   Change or incident ticket reference.
-   Required task or command scope, where applicable.

Track request revisions, grants, and sessions as separate lifecycle records.
Request revisions can be Draft, Pending approval, Approved, Rejected,
Cancelled, or Expired. See the [user workflow](08-USER-WORKFLOW.md) for
grant and session states and transition rules.

### 5.4 Approval Workflow Engine

-   Manager approval.
-   Server-owner approval.
-   Department-specific approval rules.
-   Multi-stage approval.
-   Approval delegation with an audit trail.
-   Approval expiry.
-   Rejection reason.
-   Emergency-access approval workflow.
-   Separation-of-duties enforcement.

A requester must not approve their own request. High-risk access may
require more than one independent approver.

### 5.5 Access Policy Engine

The policy engine will evaluate access before a session is established.

Policy inputs may include:

-   User identity and status.
-   Department and role.
-   Target asset and asset criticality.
-   Requested protocol.
-   Approval state.
-   Access time window.
-   MFA status.
-   Source device or network context.
-   Request risk level.
-   Environment (development, staging, production).
-   Emergency-access status.

The engine should use explicit, testable policy rules and return an
explainable decision: allow, deny, or require additional approval.

### 5.6 SSH Gateway

The SSH gateway will provide controlled access to Linux and Unix-like
systems.

Planned capabilities:

-   Gateway-mediated SSH connections.
-   User-to-session identity mapping.
-   Per-session authorization.
-   Temporary credentials or short-lived certificates where supported.
-   Secure key handling.
-   Session start and end tracking.
-   Terminal input/output recording where legally and operationally
    approved.
-   Session termination on expiry or revocation.
-   Connection and security event logging.

The gateway must not expose target-server SSH credentials to the browser
or ordinary users.

### 5.7 RDP Gateway

The RDP gateway will provide controlled access to Windows systems.

Planned capabilities:

-   Browser-based or approved client-based RDP access.
-   Per-session authorization.
-   Session lifecycle tracking.
-   Screen recording where approved.
-   Session termination on expiry or revocation.
-   Secure credential handling.
-   Connection and security event logging.

RDP protocol handling should use mature, maintained protocol libraries
or implementations. Ariba PAM will own its authorization, orchestration,
policy, and audit logic.

### 5.8 Credential Management

-   Encrypted storage of privileged secrets.
-   Credential metadata and ownership.
-   Secret checkout and controlled use.
-   Access restrictions and audit events.
-   Credential rotation workflows.
-   SSH key and certificate lifecycle management.
-   Service-account secret management.
-   Emergency credential procedures.

Security requirements:

-   No plaintext credentials in application logs, API responses, browser
    storage, or ordinary database fields.
-   Use authenticated encryption and managed key-encryption practices.
-   Separate encryption keys from encrypted data.
-   Apply strict access control to secret decryption operations.
-   Plan key rotation, backup, recovery, and compromise response.
-   Never design custom cryptographic algorithms.

### 5.9 Session Management and Recording

-   Active-session dashboard.
-   Session owner and target asset.
-   Session start, end, and duration.
-   Session termination by authorized personnel.
-   Session recording metadata.
-   Recording access permissions.
-   Recording integrity verification.
-   Retention and deletion policies.
-   Recording access audit history.

Session recording must be protected against unauthorized modification
and deletion. Recording retention should follow company policy,
applicable law, and privacy requirements. Users should receive
appropriate notice where required.

### 5.10 Audit and Reporting

-   Authentication audit.
-   Access request and approval audit.
-   Policy decision audit.
-   Credential-access audit.
-   Session lifecycle audit.
-   Administrative configuration audit.
-   Recording access audit.
-   Exportable reports.
-   Search and filtering.
-   Tamper-evident audit design.
-   Time synchronization and reliable timestamps.

### 5.11 Notification Engine

Potential channels:

-   Email.
-   Telegram or other approved messaging integrations.
-   In-application notifications.
-   Wazuh and Ariba SOC event forwarding.

Notification examples:

-   Access request submitted.
-   Approval required.
-   Request approved or rejected.
-   Privileged session started.
-   Session approaching expiry.
-   Access revoked.
-   Emergency access activated.
-   Suspicious access event detected.

### 5.12 Administration and Configuration

-   Global system settings.
-   Authentication and MFA policy.
-   Access policy configuration.
-   Session and recording policy.
-   Notification configuration.
-   Audit retention configuration.
-   Integration settings.
-   Backup and recovery settings.
-   Health and service status.

------------------------------------------------------------------------

## 6. High-Level Architecture

The architecture should separate the web application, control plane,
access gateways, and protected infrastructure.

``` text
  Control paths
  Employees and admins --> Web portal --> Control plane <--> Enterprise IdP
  Control plane <--> PostgreSQL and Redis
  Control plane <--> Gateway (session authorization and revocation)

  Session paths
  Session client <--> SSH gateway <--> Linux target
  Session client <--> RDP gateway <--> Windows target (future)
  SSH gateway --> SSH signer or scoped credential vault

  Evidence paths
  Control plane and gateways --> Independent audit storage --> Wazuh / Ariba SOC
  Gateways --> Protected recording storage
```

### Architecture boundaries

**Control plane:** Identity, requests, approvals, policy evaluation,
administration, and session orchestration.

**Data plane:** Actual SSH/RDP traffic between the user and target
system through controlled gateways.

**Security data plane:** Audit events, recording metadata, protected
recordings, and security notifications.

The control plane should not need unrestricted access to every target
server. Gateway-to-target connectivity should be restricted by network
policy.

The session client carries terminal traffic through the gateway. The
control plane authorizes that connection and does not relay terminal traffic.
The Phase 0 architecture must show the client, identity provider, control
plane, gateway zones, targets, credential signer or vault, and independent
audit and recording stores. Label who authenticates to each component and
where credentials, grants, and evidence cross trust boundaries.

------------------------------------------------------------------------

## 7. Proposed Technology Stack

The following is an initial recommendation, not an irreversible
technology decision. Detailed technical design and proof-of-concept
testing will validate each selection.

  -----------------------------------------------------------------------
  Layer                   Proposed technology     Responsibility
  ----------------------- ----------------------- -----------------------
  Frontend                Next.js + TypeScript    User and admin portal

  UI                      Tailwind CSS            Enterprise interface

  Backend API             Python + FastAPI        Business logic and APIs

  SSH Gateway             Go                      Custom session proxy
                                                  and orchestration

  RDP Gateway             Go + maintained RDP     RDP session handling
                          implementation          

  Database                PostgreSQL              Transactional
                                                  application data

  Cache / Queue           Redis                   Short-lived state and
                                                  task coordination

  Background jobs         Celery or equivalent    Notifications and
                                                  scheduled jobs

  Recording storage       Encrypted object        Session recording files
                          storage                 

  Cryptography            Established, maintained Encryption and key
                          libraries               operations

  Containerization        Docker                  Packaging and
                                                  deployment

  Metrics                 Prometheus              Service and performance
                                                  metrics

  Dashboards              Grafana                 Operational monitoring

  SIEM                    Wazuh                   Security-event
                                                  monitoring

  SOC                     Ariba SOC               Alert and incident
                                                  workflow
  -----------------------------------------------------------------------

### Build-versus-use principle

Ariba PAM will own its product logic and user experience. It may use
trusted libraries for protocol and cryptographic functions. A library is
not the same as adopting an existing PAM product as the platform's core.

Before selecting any dependency, review its maintenance status, license,
security history, compatibility, and operational requirements.

------------------------------------------------------------------------

## 8. Initial Data Model

The following is a starting entity list. Detailed fields, constraints,
relationships, and migrations will be documented in the database design.

  Entity / Table       Purpose
  -------------------- ---------------------------------------------
  users                User accounts
  departments          Organization structure
  teams                Team membership
  roles                Role definitions
  permissions          Fine-grained permissions
  user_roles           User-role mapping
  role_permissions     Role-permission mapping
  mfa_methods          MFA enrollment metadata
  assets               Protected systems
  asset_groups         Logical asset grouping
  asset_owners         Ownership mapping
  access_requests      Access request records
  approval_steps       Approval workflow steps
  approval_decisions   Approval decisions
  access_grants        Revocable, time-bound authorizations for an approved target and account
  access_policies      Policy definitions
  policy_versions      Policy change history
  credentials          Secret metadata, not plaintext secrets
  secret_versions      Encrypted secret version metadata
  access_sessions      Session lifecycle records
  session_recordings   Recording metadata and integrity data
  audit_events         Security and administrative audit events
  notifications        Notification history
  integrations         External integration configuration metadata
  system_settings      Controlled application settings

The initial data model must scope access to owned assets, teams, and
environments as applicable. Apply those scopes to approval, credential use,
sessions, audit search, and recording export. If multi-tenant hosting enters
scope, define and verify organization isolation across the API, gateways,
vault, storage, background jobs, and exports before implementation for that
deployment. Sensitive fields need explicit classification and protection.

------------------------------------------------------------------------

## 9. Core Access Lifecycle

The standard access lifecycle should be:

1.  User signs in and completes MFA.
2.  User selects an authorized target asset.
3.  User submits an access request with justification and duration.
4.  Approval engine identifies the required approvers.
5.  Approvers approve or reject the request.
6.  Policy engine evaluates the final access conditions.
7.  Session orchestrator creates a limited session authorization.
8.  User connects through the appropriate Ariba PAM gateway.
9.  Gateway validates the authorization before connecting to the target.
10. Session activity and metadata are recorded.
11. Session is terminated at expiry, revocation, or policy violation.
12. Temporary authorization and credentials are invalidated.
13. Audit evidence is retained according to policy.

**Important:** Revoking a request must revoke gateway authorization and
terminate all associated active sessions. Expiring a credential alone
is not sufficient to terminate an established connection.

Track requests, grants, and sessions separately. Bind each grant to the
approved requester, target, target account, protocol, gateway, time window,
and policy version. A change to the approved scope requires a new approval.
At connection time, recheck the grant, current user status, and applicable
policy. Consume each session launch authorization once, including under
concurrent requests. Apply revocation idempotently and retain the access
request, grant, and session identifiers in audit events.

------------------------------------------------------------------------

## 10. Security Requirements

Security requirements are product requirements, not optional
enhancements.

### Identity and authentication

-   MFA for privileged users and administrators.
-   Secure password hashing using an established password-hashing
    algorithm.
-   Secure account recovery.
-   Rate limiting and brute-force protection.
-   Session security and device/browser protections.
-   One federated enterprise IdP for the production pilot. The IdP is the
    source of workforce identity status. Require phishing-resistant MFA for
    privileged access and PAM administration. Define the signal for account
    disablement and test that it blocks new access and revokes active grants.
-   Local test identities may be used in the lab. Any production emergency
    identity must follow the break-glass procedure.

### Authorization

-   Default-deny authorization.
-   Least privilege.
-   Role-based access control with resource-level checks.
-   Separation of duties.
-   Server ownership and environment restrictions.
-   No self-approval.
-   Explicit authorization for emergency access.

### Gateway security

-   Gateways must authenticate and validate every session authorization.
-   Short-lived, narrowly scoped session tokens.
-   Strong service-to-service authentication.
-   Restricted gateway-to-target network paths.
-   No public exposure of target SSH/RDP services unless explicitly
    required and separately protected.
-   Session termination on expiry and revocation.
-   Gateway hardening and independent security monitoring.
-   Restrict normal SSH to onboarded targets from approved gateway zones
    using network and host policy. Document and audit emergency exceptions.
-   Verify SSH host identity against provisioned host keys or an approved
    host CA. Reject unknown or changed identities until an authorized
    inventory update accepts them.
-   Default to interactive SSH only during the pilot. Gate forwarding,
    non-interactive execution, and file transfer behind separately defined
    policies and tests before enabling them. Enforce the target account's
    privileges on the host.
-   Use unique gateway identities with mutual authentication. Deny a
    gateway access to targets outside its assigned zone.

### Credential and key security

-   Authenticated encryption.
-   Key separation and key rotation.
-   No plaintext secrets in logs or browser code.
-   Restricted secret decryption.
-   Secure backup and recovery.
-   Credential rotation and compromise procedures.
-   Use short-lived SSH user certificates for initial targets that support
    them. Scope certificate issuance to the approved account and bound its
    validity to the remaining grant. Keep the CA signing key in an isolated
    signing service or protected custody and define CA rollover, revocation,
    and target trust recovery before pilot access.
-   If a pilot target requires a stored credential, onboard it only after
    scoped gateway use, key custody, credential rotation, and recovery have
    been verified. Never expose target credentials to users or browsers.

### Audit and recording

-   Reliable time synchronization.
-   Append-oriented and tamper-evident audit records.
-   Restricted access to recordings.
-   Integrity verification.
-   Retention and legal/privacy controls.
-   Auditing of audit and recording access.
-   Store evidence under retention controls administered separately from
    routine PAM administration. Restrict evidence reads and exports by
    role and asset scope. Audit those operations and verify evidence
    integrity independently of the PAM application.
-   Assign an owner to approve retention periods for audit events and raw
    recordings, along with capture notice, handling of sensitive material,
    deletion, and legal holds where applicable.
-   For mandatory recording, require a healthy recorder before opening a
    session. Pause forwarding if the recorder can no longer safely capture
    the session. Terminate if capture cannot resume within the approved
    interruption limit. Preserve the recording failure and termination
    events in a protected local buffer if remote audit storage is
    unavailable. Forward them once delivery resumes and alert on evidence
    gaps. Deny new privileged sessions if required audit events cannot be
    retained durably.

### Resilience

-   Tested backup and restore.
-   Disaster recovery plan.
-   Gateway health checks.
-   High-availability design for later phases.
-   Safe behavior during database, queue, or gateway outages.
-   Fail-closed behavior for new privileged sessions when authorization
    cannot be verified.
-   Enforce session expiry locally at the gateway. Require periodic renewal
    of the gateway's permission to keep an active session open. Terminate
    when renewal expires if the gateway loses authoritative access to
    revocation information.
-   Define a break-glass procedure that works during a PAM or IdP outage.
    Assign named custodians, restrict emergency access to specific targets,
    require time-bounded use and independent evidence, and notify the SOC
    through an available channel. Review each use and rotate or revoke
    emergency credentials after use as applicable. Test the procedure with
    the primary access path unavailable.

------------------------------------------------------------------------

## 11. Integrations

### Wazuh

Ariba PAM should send security-relevant events to Wazuh, including:

-   Authentication failures.
-   MFA failures.
-   Privileged access approvals.
-   Access outside permitted time windows.
-   Session starts and terminations.
-   Emergency access activation.
-   Policy violations.
-   Recording integrity failures.
-   Administrative configuration changes.

### Ariba SOC

Potential integration workflows:

-   Critical PAM event creates an SOC alert or ticket.
-   Suspicious privileged activity triggers investigation.
-   Emergency access generates a high-priority notification.
-   Repeated authentication failures are correlated with other security
    events.
-   Incident references can be linked to PAM access requests.

Integration must use authenticated APIs or a secure event transport
mechanism. Events should contain useful metadata without exposing
passwords, private keys, session tokens, or other secrets.

### Future integrations

-   Active Directory / LDAP.
-   Additional enterprise identity providers.
-   Email systems.
-   IT service management and ticketing platforms.
-   Endpoint detection and response.
-   Vulnerability management.
-   Network-device management.
-   SIEM and SOAR platforms.

------------------------------------------------------------------------

## 12. Product User Interface

### User Portal

-   My Dashboard.
-   Request Server Access.
-   My Access Requests.
-   My Active Sessions.
-   Session History.
-   Notifications.
-   My Account and MFA.

### Approver Portal

-   Pending Approvals.
-   Request Details.
-   Asset and Risk Context.
-   Approval History.
-   Delegated Approvals.

### Administrator Portal

-   Overview Dashboard.
-   User and Department Management.
-   Roles and Permissions.
-   Asset Inventory.
-   Access Policies.
-   Approval Workflows.
-   SSH and RDP Gateway Status.
-   Credential Management.
-   Active Sessions.
-   Session Recordings.
-   Audit and Reports.
-   Integrations.
-   System Configuration.

### Auditor Portal

-   Read-only access records.
-   Approval evidence.
-   Session metadata.
-   Authorized recording review.
-   Policy-change history.
-   Audit exports.

The interface should be simple for ordinary employees and provide
detailed controls for authorized administrators.

------------------------------------------------------------------------

## 13. Development Roadmap

Development should proceed in independently testable phases. Each phase
must have requirements, implementation tasks, tests, security review,
and documentation before moving to the next phase.

### Phase 0 --- Product Discovery and Architecture

Deliverables:

-   Product vision and scope.
-   Stakeholder and user-role definitions.
-   Threat model.
-   Deployment scope and trust boundaries, including the production pilot
    IdP, SSH credential model, and ownership of signing keys and evidence.
-   Functional requirements.
-   Non-functional requirements.
-   Architecture decision records.
-   Initial data model.
-   Development standards.
-   Test strategy.
-   Pilot acceptance tests, target values, and accountable owners.

### Phase 1 --- Core Platform

Deliverables:

-   Project repository and development environment.
-   Frontend and backend foundation.
-   Authentication and MFA.
-   Integration with the selected pilot IdP, including account-disable
    propagation and privileged MFA enforcement before the production pilot.
-   User and department management.
-   RBAC and permission checks.
-   Asset inventory.
-   Audit-event foundation.
-   Initial administrator dashboard.

### Phase 2 --- Request and Approval Engine

Deliverables:

-   Access request creation.
-   Request lifecycle and status handling.
-   Approval workflow.
-   Separation-of-duties rules.
-   Access policy evaluation.
-   Notifications.
-   Approval audit history.

### Phase 3 --- Custom SSH Gateway

Deliverables:

-   Gateway service foundation.
-   Gateway registration and authentication.
-   Linux target inventory integration.
-   Session authorization.
-   Controlled SSH proxying.
-   Session start and end events.
-   Session expiry and termination.
-   Terminal recording proof of concept.
-   Security and performance testing.

Phase 3 begins in an isolated lab. Before using any production target,
validate the Phase 0 credential design, target access restrictions, and the
production pilot acceptance criteria. A target that requires a vault-backed
credential depends on the relevant Phase 4 controls.

### Phase 4 --- Credential Management

Deliverables:

-   Encrypted secret storage.
-   Key-management design.
-   Secret access authorization.
-   Secret versioning.
-   Credential checkout and audit.
-   Rotation workflow.
-   Backup and recovery tests.

### Phase 5 --- Session Management and Recording

Deliverables:

-   Active-session dashboard.
-   Session termination controls.
-   Recording metadata.
-   Protected recording storage.
-   Recording integrity verification.
-   Retention policy.
-   Recording access audit.

The first production pilot follows this phase after the applicable
security, recovery, and release checks pass. The
[development roadmap](17-DEVELOPMENT-ROADMAP.md) owns phase exit criteria.

### Phase 6 --- RDP Gateway

Deliverables:

-   Windows target support.
-   RDP session authorization.
-   Session lifecycle management.
-   Screen recording proof of concept.
-   Session termination.
-   Security and compatibility testing.

### Phase 7 --- Enterprise Integrations

Deliverables:

-   Wazuh integration.
-   Ariba SOC integration.
-   Email notifications.
-   Additional enterprise directory and IdP integrations.
-   External ticket-reference support.
-   Integration health monitoring.

### Phase 8 --- Enterprise Readiness

Deliverables:

-   High availability.
-   Disaster recovery.
-   Backup and restore validation.
-   Performance and load testing.
-   Security assessment and penetration testing.
-   Deployment and upgrade automation.
-   Operational runbooks.
-   Release and support process.

------------------------------------------------------------------------

## 14. MVP Scope

The first usable release should be intentionally limited.

### MVP includes

-   Admin and employee authentication.
-   MFA.
-   User, department, role, and permission management.
-   Linux server inventory.
-   Access request and approval.
-   Access policy validation.
-   Custom SSH gateway.
-   Time-limited SSH sessions.
-   Short-lived SSH user certificates for compatible pilot targets.
-   Session monitoring.
-   Basic terminal recording.
-   Session expiry and termination.
-   Audit logs.
-   Basic email or in-app notifications.

### MVP excludes

-   Production RDP gateway.
-   Full credential rotation automation.
-   Network-device access.
-   Database privileged access.
-   Advanced analytics.
-   Multi-region deployment.
-   Shared hosting for multiple organizations, under the initial deployment
    assumption.
-   Complex risk-scoring automation.

These are planned extensions, not forgotten requirements.

------------------------------------------------------------------------

## 15. Non-Functional Requirements

Detailed targets will be finalized after infrastructure sizing and load
testing.

  Area              Requirement
  ----------------- ------------------------------------------------------
  Security          Secure development lifecycle and threat modeling
  Availability      Resilient service design and documented recovery
  Scalability       Horizontally extensible API and gateway architecture
  Performance       Measured API and session-establishment latency
  Auditability      Traceable access and administrative events
  Maintainability   Modular code, tests, and documented APIs
  Extensibility     Versioned APIs and replaceable integration adapters
  Compatibility     Documented supported operating systems and clients
  Observability     Structured logs, metrics, health checks
  Recovery          Tested backup, restore, and key recovery procedures

In Phase 0, record the expected number of assets and concurrent sessions,
supported SSH client and server versions, API and session-start latency
targets, and alert thresholds. Verify these at representative load before
committing to production capacity or service levels.

### Production pilot acceptance criteria

The values below summarize the proposed
[pilot acceptance baseline](05-NON-FUNCTIONAL-REQUIREMENTS.md). The named
control owners and pilot sponsor must confirm the applicable targets in
Phase 0. Keep test evidence with the release decision.

| Control | Proposed pilot acceptance check | Owner |
| --- | --- | --- |
| Target access | A workstation on a normal user network cannot connect directly to a pilot host over SSH. The approved gateway can connect to the assigned host and rejects an untrusted host key. Test that an unapproved target, wrong account, or replayed session launch is denied. | Infrastructure and PAM engineering |
| Identity and revocation | With the pilot IdP connected, privileged access requires phishing-resistant MFA. Starting from grant revocation or IdP account disablement, block new access and terminate associated sessions within 60 seconds. Record timestamps from the initiating system and gateway. | IAM and PAM engineering |
| Gateway isolation | With the control plane unreachable, deny new sessions as soon as authorization cannot be verified. During a network partition, terminate active sessions within 60 seconds of the last successful authorization renewal and enforce grant expiry locally. | PAM engineering |
| Evidence and recording | A normal PAM admin cannot modify or delete protected evidence. When mandatory recording fails, pause forwarding immediately and terminate within 60 seconds if capture remains unavailable. Alert the SOC and verify that the failure and session termination can be correlated, including after an evidence service outage. | Security operations and PAM engineering |
| Recovery and emergency access | Restore service, signing or vault access, and accessible audit evidence from backups in an isolated environment. Proposed recovery targets are 4 hours to restore service (RTO) and at most 15 minutes of recoverable state loss (RPO). Revalidate grants against current identity and policy before reopening access. Drill break-glass with PAM and the IdP unavailable. | Platform operations and security operations |

Resolve failed pilot checks before enabling production access. Record the
validated asset list, control owners, test evidence, and approval from
security and infrastructure owners.

------------------------------------------------------------------------

## 16. Extensibility and Future Development

Ariba PAM must be designed so new features can be added without
rewriting its core.

Potential future capabilities:

-   Database access gateway.
-   Network-device SSH access.
-   Kubernetes privileged access.
-   Cloud console and cloud-role access workflows.
-   Just-in-time privilege elevation.
-   Command allowlists and restricted command policies.
-   Risk-based approval.
-   Device posture checks.
-   Service-account governance.
-   Automated credential rotation.
-   Privileged task workflows.
-   Multi-business-unit administration.
-   Delegated asset ownership.
-   Advanced session search and analytics.
-   SIEM correlation and SOAR actions.
-   Compliance evidence and scheduled reports.
-   High availability and multi-site gateways.

### Extensibility rules

1.  Keep protocol gateways separate from the core API.
2.  Define stable internal service interfaces.
3.  Use versioned public APIs.
4.  Keep external integrations behind adapters.
5.  Use database migrations for schema evolution.
6.  Make background jobs idempotent where practical.
7.  Record security-relevant configuration changes.
8.  Maintain backward-compatible upgrade paths where possible.
9.  Document architecture decisions and rejected alternatives.
10. Do not add a feature without requirements, tests, permissions, and
    audit coverage.

------------------------------------------------------------------------

## 17. Repository Structure

The [repository index](../README.md) describes the current documentation
tree. Create application and infrastructure directories when the roadmap
reaches those implementation stages.

## 18. Documentation Plan

Read the numbered documents in the [repository index](../README.md).
Detailed requirements and acceptance criteria live in their designated
documents. Record proposed and approved choices in the
[architecture decision log](../decisions/architecture-decisions.md).

---

## 19. Development Workflow

Use a repeatable, step-by-step workflow.

For each feature:

1.  Write or update the requirement.
2.  Create a GitHub issue with acceptance criteria.
3.  Review architecture and security impact.
4.  Implement in a feature branch.
5.  Add unit and integration tests.
6.  Run linting, type checks, dependency and secret scans.
7.  Perform security review for privileged-access changes.
8.  Open a pull request.
9.  Review and merge into the protected main branch.
10. Update documentation and changelog.
11. Deploy to development or staging.
12. Verify behavior and retain test evidence.

### Branching suggestion

-   `main` --- protected, release-ready code.
-   `develop` --- integration branch, if the team needs one.
-   `feature/<issue-id>-<short-name>` --- feature work.
-   `fix/<issue-id>-<short-name>` --- bug fixes.
-   `hotfix/<issue-id>-<short-name>` --- urgent production fixes.

Never commit real credentials, private keys, production recordings,
tokens, or sensitive infrastructure data to Git.

------------------------------------------------------------------------

## 20. Definition of Done

A feature is not complete merely because its screen or API works.

A feature is complete only when:

-   Requirements are documented.
-   Authorization is enforced on the backend.
-   Input validation and error handling exist.
-   Relevant audit events are generated.
-   Unit and integration tests pass.
-   Security tests are completed where relevant.
-   No secrets are exposed.
-   API and user documentation are updated.
-   Database migrations are included when needed.
-   Deployment and rollback implications are understood.
-   Acceptance criteria are verified.

------------------------------------------------------------------------

## 21. Key Risks and Mitigations

  -----------------------------------------------------------------------
  Risk                                Mitigation
  ----------------------------------- -----------------------------------
  PAM gateway compromise              Isolate gateways, minimize
                                      privileges, harden and monitor them

  Credential exposure                 Authenticated encryption, key
                                      separation, secret redaction

  Unauthorized approval               Separation of duties and immutable
                                      approval history

  Session survives expiry             Gateway-enforced session
                                      termination

  Recording tampering                 Integrity verification and
                                      protected storage

  Database outage                     Fail closed for new privileged
                                      sessions

  Lost encryption keys                Secure key backup and tested
                                      recovery

  Excessive permissions               Default deny, least privilege,
                                      periodic access review

  Malicious administrator             Independent audit, dual control,
                                      protected evidence

  Dependency vulnerability            Dependency inventory, scanning,
                                      patching and review
  -----------------------------------------------------------------------

------------------------------------------------------------------------

## 22. Initial Project Success Metrics

The following metrics can be introduced after the MVP is operational:

-   Percentage of privileged access routed through Ariba PAM.
-   Percentage of privileged accounts assigned to named identities.
-   Percentage of sessions linked to approved requests.
-   Percentage of temporary access automatically revoked on time.
-   Number of unapproved or denied access attempts.
-   Percentage of privileged sessions with required audit evidence.
-   Time required to approve and establish authorized access.
-   Number of overdue access reviews.
-   Gateway availability and session-establishment success rate.
-   Backup and recovery test success rate.

Metrics must be based on actual system evidence, not manually estimated
figures.

------------------------------------------------------------------------

## 23. Immediate Next Steps

Do not begin with all modules at once. Start with product discovery and
the core security model.

Recommended first tasks:

1.  Confirm the product vision and initial user groups.
2.  Define the role and permission matrix.
3.  Create the first threat model and trust-boundary diagram.
4.  Write the initial SRS.
5.  Define the asset and access-request data model.
6.  Decide the development, staging, and lab deployment topology.
7.  Create the repository and development standards.
8.  Build authentication, MFA, RBAC, and audit foundations.
9.  Implement access requests and approval workflows.
10. Begin SSH gateway proof-of-concept only after the authorization
    model is reviewed.

### First milestone

**Milestone 1: Secure Core Platform**

The first milestone is complete when an authorized employee can
authenticate with MFA, view only permitted assets, submit an access
request, receive an approval decision, and have all relevant actions
recorded in the audit system.

Validate the production pilot acceptance criteria in an isolated lab before
enabling pilot SSH access. Future RDP rollout requires protocol-specific
authorization, session termination, recording, and security validation.

------------------------------------------------------------------------

## 24. Product Definition

**Ariba PAM is a custom-built enterprise Privileged Access Management
platform that centralizes privileged identity, access requests, approval
workflows, policy enforcement, controlled infrastructure gateways,
credential protection, session monitoring, session recording, and
security auditing.**

The platform will be developed incrementally, with a secure core and
modular architecture that can support additional protocols,
integrations, infrastructure environments, and enterprise capabilities
over time.

**Guiding development rule:** Build a secure, testable, documented
foundation first. Add enterprise capabilities in controlled phases
without compromising the integrity of the access-control system.
