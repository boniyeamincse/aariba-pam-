# 01 · Project Overview: Ariba PAM

> Architectural Baseline & Product Overview · 2026-11-22

## Executive Summary

**Ariba PAM** (Privileged Access Management) is an enterprise-grade privileged access management and zero-trust session gateway platform designed to eliminate static, standing administrative privileges across critical infrastructure. Through cryptographic verification, just-in-time (JIT) workflow authorization, ephemeral credential issuance, and non-bypassable protocol gateways, Ariba PAM guarantees that privileged access to servers, databases, and network equipment is strictly time-bounded, resource-scoped, independently approved, and immutably audited.

---

## The Problem Statement

Legacy enterprise access models rely on persistent credentials (static SSH keys, shared root/admin passwords, long-lived service accounts) and direct network-level access (VPNs, bastion hosts). This creates severe systemic risks:

1. **Standing Privilege & Credential Sprawl**: Reusable credentials leaked from developer workstations or stored in configuration files provide unmonitored lateral movement for attackers.
2. **Inconsistent Approval & Removal**: Access granted for urgent maintenance is rarely revoked promptly, resulting in lingering accounts long after tasks finish.
3. **Weak Separation of Duties (SoD)**: Engineers frequently approve their own access requests or grant unreviewed lateral permissions.
4. **Audit & Forensics Blind Spots**: Traditional audit logs only record connection start and end times, leaving forensic teams blind to keystrokes, interactive commands, file transfers, and privilege escalation during active sessions.
5. **Over-Privileged Administrators**: Traditional PAM systems grant superuser status to PAM administrators, allowing a single compromised administrative identity to extract credentials, manipulate audit trails, and bypass approval workflows.

---

## Core Product Vision & Value Proposition

Ariba PAM solves these challenges by implementing a **Zero Standing Privilege (ZSP)** architecture:

- **Ephemeral Access**: Credentials and certificates are dynamically generated on-demand, valid only for the duration of the approved task window, and automatically invalidated upon session conclusion or grant expiry.
- **Protocol-Mediated Gateways**: No user ever receives direct routable network access to target hosts. Interactive sessions (SSH, terminal) terminate at zone-isolated Ariba PAM Gateways that inspect host identity, inject target credentials, enforce active leases, and record bi-directional terminal traffic.
- **Hybrid Authorization (RBAC + ABAC + Resource Scope)**: Every privileged action evaluates user roles, environmental conditions (MFA assurance, IP, schedule), and hierarchical resource boundaries before authorization is granted.
- **Strict Custodian Boundary Isolation**: Administrative authority is partitioned across isolated boundaries. PAM Administrators cannot inspect vault secrets, alter audit evidence, or unilaterally initiate emergency access.

---

## Pilot Scope & Success Criteria

The initial implementation targets Linux infrastructure accessed via interactive SSH:

| Dimension | Pilot Baseline | Production Horizon |
| :--- | :--- | :--- |
| **Identities** | Workforce users federated via pilot OIDC IdP with FIDO2/WebAuthn MFA | Multi-IdP federation, SCIM directory synchronization |
| **Target Infrastructure** | Linux compute instances in isolated gateway zones | Multi-cloud, on-premises Linux, containers, Kubernetes |
| **Protocol** | Interactive SSH (terminal session forwarding, short-lived certificates) | SSH, SFTP, RDP, database native proxies |
| **Credential Model** | Short-lived SSH Certificates signed by isolated CA | Ephemeral CA signing + scoped HashiCorp Vault dynamic injection |
| **Evidence & Review** | Real-time asciinema/typescript session recording with SHA256 integrity digests | Multi-region independent storage, automated OCR/DLP anomaly detection |
| **Revocation Target** | Maximum 60-second end-to-end propagation from IdP disablement to session closure | Sub-5 second real-time WebSocket/gRPC control-plane push |

---

## Document Roadmap

Ariba PAM's complete architecture baseline is formalized across 18 numbered design documents:

1. [01 · Project Overview](01-PROJECT-OVERVIEW.md): Vision, problem space, pilot boundaries.
2. [02 · Product Requirements](02-PRODUCT-REQUIREMENTS.md): Business, functional, and non-functional requirements.
3. [03 · System Architecture](03-SYSTEM-ARCHITECTURE.md): Microservices, network topologies, and trust boundaries.
4. [04 · API Specification](04-API-SPECIFICATION.md): Complete OpenAPI REST contract and error models.
5. [05 · Database Schema](05-DATABASE-SCHEMA.md): Relational models, constraints, and migrations.
6. [06 · Identity & Access Management](06-IDENTITY-AND-ACCESS-MANAGEMENT.md): OIDC federation, MFA, and disablement signals.
7. [07 · User Roles & Permissions](07-USER-ROLES-AND-PERMISSIONS.md): Role matrix and custodian boundary separation.
8. [08 · Authorization Policy Engine](08-AUTHORIZATION-POLICY-ENGINE.md): Canonical permissions, ABAC rules, and decision pipeline.
9. [09 · Resource Scope Management](09-RESOURCE-SCOPE-MANAGEMENT.md): Hierarchical tree, inheritance rules, and scoping checks.
10. [10 · Separation of Duties](10-SEPARATION-OF-DUTIES.md): Conflict rules, four-eyes enforcement, and exception handling.
11. [11 · Approval & Delegation](11-APPROVAL-AND-DELEGATION.md): Workflow engine, delegation rules, and stale-decision handling.
12. [12 · Credential Vault Design](12-CREDENTIAL-VAULT-DESIGN.md): Ephemeral CA signing and dynamic secret custody.
13. [13 · Security Requirements](13-SECURITY-REQUIREMENTS.md): Threat modeling, core controls, and verification mapping.
14. [14 · Session Gateway Design](14-SESSION-GATEWAY-DESIGN.md): Go SSH proxy, lease renewals, and local expiry enforcement.
15. [15 · Audit & Evidence Management](15-AUDIT-AND-EVIDENCE-MANAGEMENT.md): Transactional outbox, session capture, and playback.
16. [16 · Integration Architecture](16-INTEGRATION-ARCHITECTURE.md): SIEM, SOC, ticketing, and external IdP adapters.
17. [17 · Workflow State Machine](17-WORKFLOW-STATE-MACHINE.md): Lifecycle state transitions and consistency invariants.
18. [18 · Development Roadmap](18-DEVELOPMENT-ROADMAP.md): Phases, task dependencies, and milestone exit criteria.
