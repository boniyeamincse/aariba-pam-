"""Database models for Ariba PAM matching the baseline schema."""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import (
    String,
    Boolean,
    Integer,
    Float,
    ForeignKey,
    DateTime,
    Text,
    JSON,
    UniqueConstraint,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from ariba_pam.db.base import Base, generate_id, utc_now


class User(Base):
    """Workforce identity bound to an enterprise IdP."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("usr"))
    idp_issuer: Mapped[str] = mapped_column(String(255), nullable=False)
    idp_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    security_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    role_assignments: Mapped[List["RoleAssignment"]] = relationship("RoleAssignment", back_populates="user", cascade="all, delete-orphan")
    requests: Mapped[List["AccessRequest"]] = relationship("AccessRequest", back_populates="requester")

    __table_args__ = (
        UniqueConstraint("idp_issuer", "idp_subject", name="uq_user_idp_identity"),
        Index("ix_users_email", "email"),
    )


class Role(Base):
    """Roles defining authority levels (e.g., requester, approver, security_operator, admin)."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("rol"))
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class RoleAssignment(Base):
    """Resource-scoped role assignment relating a user to a role within an explicit scope."""

    __tablename__ = "role_assignments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("ras"))
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[str] = mapped_column(String(64), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)  # global, team, asset, environment
    scope_value: Mapped[str] = mapped_column(String(128), nullable=False)  # '*' or specific team/asset/env id
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    user: Mapped["User"] = relationship("User", back_populates="role_assignments")
    role: Mapped["Role"] = relationship("Role")

    __table_args__ = (
        Index("ix_role_assignments_user_scope", "user_id", "scope_type", "scope_value"),
    )


class GatewayZone(Base):
    """Network zones serviced by specific gateways."""

    __tablename__ = "gateway_zones"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("zon"))
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")


class Asset(Base):
    """Target system or server managed by Ariba PAM."""

    __tablename__ = "assets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("ast"))
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)  # lab, staging, prod
    team: Mapped[str] = mapped_column(String(64), nullable=False)
    zone_id: Mapped[str] = mapped_column(String(64), ForeignKey("gateway_zones.id"), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    protocol: Mapped[str] = mapped_column(String(16), default="ssh", nullable=False)  # ssh, rdp
    host_trust_ref: Mapped[str] = mapped_column(String(255), default="")  # pinned host key fingerprint
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    zone: Mapped["GatewayZone"] = relationship("GatewayZone")
    accounts: Mapped[List["TargetAccount"]] = relationship("TargetAccount", back_populates="asset", cascade="all, delete-orphan")


class TargetAccount(Base):
    """Privileged accounts available on an asset."""

    __tablename__ = "target_accounts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("act"))
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id", ondelete="CASCADE"), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    requires_ticket: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, default=3600, nullable=False)
    credential_type: Mapped[str] = mapped_column(String(32), default="ssh_certificate", nullable=False)  # ssh_certificate, vault_secret
    vault_secret_path: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    auto_rotate_on_session_end: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rotation_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # active, rotating, failed

    asset: Mapped["Asset"] = relationship("Asset", back_populates="accounts")

    __table_args__ = (
        UniqueConstraint("asset_id", "username", name="uq_asset_account"),
    )


class VaultSecretStore(Base):
    """Encrypted vault-backed credential store for targets requiring static secrets."""

    __tablename__ = "vault_secret_store"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("vsec"))
    account_id: Mapped[str] = mapped_column(String(64), ForeignKey("target_accounts.id", ondelete="CASCADE"), unique=True, nullable=False)
    secret_type: Mapped[str] = mapped_column(String(32), default="password", nullable=False)  # password, private_key
    encrypted_payload: Mapped[str] = mapped_column(Text, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    account: Mapped["TargetAccount"] = relationship("TargetAccount")


class AdminChangeProposal(Base):
    """Independently reviewed administrative changes to inventory, roles, or policies."""

    __tablename__ = "admin_change_proposals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("prp"))
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)  # asset, role, policy
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    change_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    expected_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    author_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, applied, rejected
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    author: Mapped["User"] = relationship("User", foreign_keys=[author_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewer_id])


class AccessPolicyVersion(Base):
    """Immutable rules published by independent review for one asset."""

    __tablename__ = "access_policy_versions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("pol"))
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    rules: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    proposal_id: Mapped[str] = mapped_column(String(64), ForeignKey("admin_change_proposals.id"), nullable=False, unique=True)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (UniqueConstraint("asset_id", "version", name="uq_policy_asset_version"),)


class AccessRequest(Base):
    """Access request submitted by a workforce user."""

    __tablename__ = "access_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("req"))
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, approved, rejected, cancelled, expired
    current_revision_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    requester: Mapped["User"] = relationship("User", back_populates="requests")
    revisions: Mapped[List["RequestRevision"]] = relationship("RequestRevision", back_populates="request", cascade="all, delete-orphan")


class RequestRevision(Base):
    """Immutable revision of an access request."""

    __tablename__ = "request_revisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("rev"))
    request_id: Mapped[str] = mapped_column(String(64), ForeignKey("access_requests.id", ondelete="CASCADE"), nullable=False)
    revision_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    target_account_id: Mapped[str] = mapped_column(String(64), ForeignKey("target_accounts.id"), nullable=False)
    requested_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    ticket_ref: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    policy_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    is_frozen: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    request: Mapped["AccessRequest"] = relationship("AccessRequest", back_populates="revisions")
    asset: Mapped["Asset"] = relationship("Asset")
    target_account: Mapped["TargetAccount"] = relationship("TargetAccount")
    steps: Mapped[List["ApprovalStep"]] = relationship("ApprovalStep", back_populates="revision", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("request_id", "revision_number", name="uq_request_revision"),
    )


class ApprovalStep(Base):
    """Required approval step for an access revision."""

    __tablename__ = "approval_steps"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("stp"))
    revision_id: Mapped[str] = mapped_column(String(64), ForeignKey("request_revisions.id", ondelete="CASCADE"), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # waiting, pending, approved, rejected, cancelled
    required_role: Mapped[str] = mapped_column(String(64), default="approver", nullable=False)

    revision: Mapped["RequestRevision"] = relationship("RequestRevision", back_populates="steps")
    decisions: Mapped[List["ApprovalDecision"]] = relationship("ApprovalDecision", back_populates="step", cascade="all, delete-orphan")


class ApprovalDecision(Base):
    """Durable decision record by an authorized reviewer."""

    __tablename__ = "approval_decisions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("dcs"))
    step_id: Mapped[str] = mapped_column(String(64), ForeignKey("approval_steps.id", ondelete="CASCADE"), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # approved, rejected
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    step: Mapped["ApprovalStep"] = relationship("ApprovalStep", back_populates="decisions")
    approver: Mapped["User"] = relationship("User")

    __table_args__ = (
        UniqueConstraint("step_id", "approver_id", name="uq_step_approver"),
    )


class AccessGrant(Base):
    """Authorized grant issued upon final approval."""

    __tablename__ = "access_grants"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("grn"))
    revision_id: Mapped[str] = mapped_column(String(64), ForeignKey("request_revisions.id"), nullable=False, unique=True)
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    target_account_id: Mapped[str] = mapped_column(String(64), ForeignKey("target_accounts.id"), nullable=False)
    effective_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # active, revoked, expired
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)

    revision: Mapped["RequestRevision"] = relationship("RequestRevision")
    requester: Mapped["User"] = relationship("User", foreign_keys=[requester_id])
    asset: Mapped["Asset"] = relationship("Asset")
    target_account: Mapped["TargetAccount"] = relationship("TargetAccount")
    revoked_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[revoked_by_id])
    launches: Mapped[List["SessionLaunch"]] = relationship("SessionLaunch", back_populates="grant")


class SessionLaunch(Base):
    """Single-use launch authorization issued to the grant owner."""

    __tablename__ = "session_launches"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("lnc"))
    grant_id: Mapped[str] = mapped_column(String(64), ForeignKey("access_grants.id"), nullable=False)
    launch_token_digest: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_consumed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_gateway_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    grant: Mapped["AccessGrant"] = relationship("AccessGrant", back_populates="launches")


class AccessSession(Base):
    """Active or historical connection session through a gateway."""

    __tablename__ = "access_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("ses"))
    grant_id: Mapped[str] = mapped_column(String(64), ForeignKey("access_grants.id"), nullable=False)
    launch_id: Mapped[str] = mapped_column(String(64), ForeignKey("session_launches.id"), unique=True, nullable=False)
    gateway_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)  # active, terminating, ended
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    termination_reason: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    grant: Mapped["AccessGrant"] = relationship("AccessGrant")
    launch: Mapped["SessionLaunch"] = relationship("SessionLaunch")
    recording: Mapped[Optional["SessionRecording"]] = relationship("SessionRecording", back_populates="session", uselist=False)


class SessionRecording(Base):
    """Immutable terminal session recording with cryptographic integrity digest."""

    __tablename__ = "session_recordings"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("rec"))
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("access_sessions.id"), unique=True, nullable=False)
    digest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coverage_status: Mapped[str] = mapped_column(String(32), default="complete", nullable=False)  # complete, partial, gap
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    session: Mapped["AccessSession"] = relationship("AccessSession", back_populates="recording")


class EvidenceExport(Base):
    """Auditable evidence export package with cryptographic manifest and TTL."""

    __tablename__ = "evidence_exports"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("exp"))
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    export_type: Mapped[str] = mapped_column(String(32), nullable=False)  # audit_trail, session_recording
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # session_id or recording_id if specific
    scope_filter: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    record_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manifest_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)  # pending, completed, failed
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    requester: Mapped["User"] = relationship("User")


class AuditOutbox(Base):
    """Transactional audit outbox guaranteeing at-least-once event delivery."""

    __tablename__ = "audit_outbox"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("aud"))
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    payload_digest: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    delivery_state: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, delivered, failed
    delivery_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_audit_outbox_delivery", "delivery_state", "occurred_at"),
    )


class IdempotencyRecord(Base):
    """Deduplication and idempotency cache for state-changing operations."""

    __tablename__ = "idempotency_records"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("idm"))
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    response_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_payload: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    __table_args__ = (
        UniqueConstraint("actor_id", "operation", "idempotency_key", name="uq_actor_op_idempotency"),
    )


class SOCAlert(Base):
    """High-priority security alert dispatched to enterprise SOC/SIEM."""

    __tablename__ = "soc_alerts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("alt"))
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)  # CAPTURE_FAILURE, EVIDENCE_DELIVERY_FAILURE, LEASE_RENEWAL_FAILURE, SIGNING_FAILURE, SOD_VIOLATION, UNSAFE_LAUNCH_BLOCKED
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # CRITICAL, HIGH, WARNING
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    gateway_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    asset_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    details: Mapped[Dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)  # open, acknowledged, resolved
    acknowledged_by_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    acknowledged_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[acknowledged_by_id])


class BackupRehearsalRecord(Base):
    """Tracks disaster recovery exercises, RTO/RPO measurements, and restored evidence audits (P5-07, NFR-04, T-09)."""

    __tablename__ = "backup_rehearsals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("reh"))
    exercise_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    snapshot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rto_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    rpo_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    target_rto_seconds: Mapped[float] = mapped_column(Float, default=900.0, nullable=False)  # 15 minutes (NFR-04)
    target_rpo_seconds: Mapped[float] = mapped_column(Float, default=60.0, nullable=False)   # 1 minute (NFR-04)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)     # completed, failed
    restored_counts: Mapped[Dict[str, int]] = mapped_column(JSON, nullable=False)
    reconciled_grants_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reconciled_sessions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    worm_verified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    discrepancies: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    operator: Mapped["User"] = relationship("User", foreign_keys=[operator_id])


class EmergencyRequest(Base):
    """Multi-custodian emergency break-glass access request (FR-11, SOD-04, T-09)."""

    __tablename__ = "emergency_requests"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("emg"))
    asset_id: Mapped[str] = mapped_column(String(64), ForeignKey("assets.id"), nullable=False)
    target_account_id: Mapped[str] = mapped_column(String(64), ForeignKey("target_accounts.id"), nullable=False)
    requester_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)  # pending, approved, active, revoked, reviewed, rejected
    required_approvals: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    approval_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    requested_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revocation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("users.id"), nullable=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    grant_id: Mapped[Optional[str]] = mapped_column(String(64), ForeignKey("access_grants.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    asset: Mapped["Asset"] = relationship("Asset")
    target_account: Mapped["TargetAccount"] = relationship("TargetAccount")
    requester: Mapped["User"] = relationship("User", foreign_keys=[requester_id])
    reviewer: Mapped[Optional["User"]] = relationship("User", foreign_keys=[reviewer_id])
    grant: Mapped[Optional["AccessGrant"]] = relationship("AccessGrant")
    approvals: Mapped[List["EmergencyApproval"]] = relationship("EmergencyApproval", back_populates="emergency_request", cascade="all, delete-orphan")


class EmergencyApproval(Base):
    """Independent custodian approval or rejection for break-glass emergency access (SOD-04)."""

    __tablename__ = "emergency_approvals"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: generate_id("ema"))
    emergency_request_id: Mapped[str] = mapped_column(String(64), ForeignKey("emergency_requests.id"), nullable=False)
    custodian_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(32), nullable=False)  # approve, reject
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)

    emergency_request: Mapped["EmergencyRequest"] = relationship("EmergencyRequest", back_populates="approvals")
    custodian: Mapped["User"] = relationship("User", foreign_keys=[custodian_id])

    __table_args__ = (
        UniqueConstraint("emergency_request_id", "custodian_id", name="uq_emg_custodian_vote"),
    )



