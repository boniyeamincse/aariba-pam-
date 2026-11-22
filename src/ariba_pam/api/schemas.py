"""Pydantic schemas for Ariba PAM API."""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import AwareDatetime, BaseModel, Field, field_validator


class UserProfileResponse(BaseModel):
    """GET /api/v1/me response."""

    id: str
    email: str
    full_name: str
    is_active: bool
    roles: List[Dict[str, Any]]
    permitted_scopes: List[Dict[str, str]]


class TargetAccountResponse(BaseModel):
    """Target account details."""

    id: str
    username: str
    is_active: bool
    requires_ticket: bool
    max_duration_seconds: int


class AssetResponse(BaseModel):
    """Asset with available target accounts."""

    id: str
    name: str
    environment: str
    team: str
    zone_id: str
    host: str
    port: int
    is_active: bool
    accounts: List[TargetAccountResponse]


class CreateRequestInput(BaseModel):
    """POST /api/v1/requests payload."""

    asset_id: str
    target_account_id: str
    requested_start_at: AwareDatetime
    requested_end_at: AwareDatetime
    justification: str = Field(min_length=5)
    ticket_ref: Optional[str] = None

    @field_validator("requested_start_at", "requested_end_at")
    @classmethod
    def normalize_window_to_utc(cls, value: datetime) -> datetime:
        return value.astimezone(timezone.utc)


class DecisionInput(BaseModel):
    """POST /api/v1/approval-steps/{step_id}/decisions payload."""

    expected_revision_id: str
    decision: str = Field(pattern="^(approved|rejected)$")
    reason: Optional[str] = None


class RevokeGrantInput(BaseModel):
    """POST /api/v1/grants/{grant_id}/revoke payload."""

    reason: str = Field(min_length=3)


class AdminProposalInput(BaseModel):
    """POST /api/v1/admin/change-proposals payload."""

    resource_type: str = Field(pattern="^(asset|role|policy)$")
    resource_id: Optional[str] = None
    change_payload: Dict[str, Any]
    expected_version: int = Field(default=1, ge=0, strict=True)
    reason: str = Field(min_length=5)


class AdminProposalDecisionInput(BaseModel):
    """POST /api/v1/admin/change-proposals/{proposal_id}/decisions payload."""

    decision: str = Field(pattern="^(applied|rejected)$")
    reason: Optional[str] = None


class LaunchConsumeInput(BaseModel):
    """Internal gateway POST /internal/v1/launches/consume payload."""

    launch_token: str
    gateway_id: str


class ReplaceRevisionInput(BaseModel):
    """POST /api/v1/requests/{request_id}/revisions payload."""

    expected_revision_id: str
    target_account_id: Optional[str] = None
    requested_start_at: Optional[AwareDatetime] = None
    requested_end_at: Optional[AwareDatetime] = None
    justification: Optional[str] = Field(default=None, min_length=5)
    ticket_ref: Optional[str] = None

    @field_validator("requested_start_at", "requested_end_at")
    @classmethod
    def normalize_window_to_utc(cls, value: Optional[datetime]) -> Optional[datetime]:
        return value.astimezone(timezone.utc) if value else None


class CertificateSignInput(BaseModel):
    """Internal gateway POST /internal/v1/sessions/{session_id}/sign-certificate payload."""

    client_public_key: str = Field(min_length=10)


class CertificateSignOutput(BaseModel):
    """Signed certificate response for gateway."""

    certificate: str
    expires_at: AwareDatetime
    principal: str
    serial: int
    ca_fingerprint: str


class CreateAuditExportInput(BaseModel):
    """POST /api/v1/audit-events/exports payload."""

    justification: str = Field(min_length=5)
    scope_filter: Optional[str] = None
    limit: int = Field(default=200, ge=1, le=1000)


class AuditExportResponse(BaseModel):
    """Audit export bundle response."""

    export_id: str
    export_type: str
    status: str
    record_count: int
    manifest_sha256: str
    storage_uri: str
    download_url: str
    justification: str
    expires_at: AwareDatetime
    created_at: AwareDatetime
    requester_id: str


class VerifyIntegrityInput(BaseModel):
    """POST /api/v1/audit-events/verify-integrity payload."""

    batch_limit: int = Field(default=100, ge=1, le=1000)


class VerifyIntegrityResponse(BaseModel):
    """POST /api/v1/audit-events/verify-integrity response."""

    verified: bool
    events_checked: int
    tampered_event_ids: List[str]
    hash_algorithm: str
    verified_at: AwareDatetime
    message: str


class RecordingResponse(BaseModel):
    """GET /api/v1/recordings/{recording_id} response."""

    recording_id: str
    session_id: str
    asset_id: str
    asset_name: str
    target_account: str
    duration_seconds: int
    size_bytes: int
    coverage_status: str
    digest_sha256: str
    storage_uri: str
    created_at: AwareDatetime


class PlaybackSessionResponse(BaseModel):
    """POST /api/v1/recordings/{recording_id}/playback-sessions response."""

    recording_id: str
    playback_url: str
    token: str
    expires_at: AwareDatetime


class CreateRecordingExportInput(BaseModel):
    """POST /api/v1/recordings/{recording_id}/exports payload."""

    justification: str = Field(min_length=5)


class RecordingExportResponse(BaseModel):
    """Recording export job response."""

    export_id: str
    recording_id: str
    status: str
    manifest_sha256: str
    storage_uri: str
    download_url: str
    justification: str
    expires_at: AwareDatetime
    created_at: AwareDatetime
    requester_id: str

class GatewayHeartbeatInput(BaseModel):
    """POST /internal/v1/gateways/{gateway_id}/heartbeat payload."""

    zone_id: str
    status: str = "healthy"
    active_sessions_count: int = 0
    capture_status: str = "healthy"


class SOCAlertResponse(BaseModel):
    """GET /api/v1/alerts response."""

    id: str
    alert_type: str
    severity: str
    title: str
    description: str
    correlation_id: str
    session_id: Optional[str] = None
    gateway_id: Optional[str] = None
    asset_id: Optional[str] = None
    details: Dict[str, Any] = {}
    status: str
    acknowledged_by_id: Optional[str] = None
    acknowledged_at: Optional[AwareDatetime] = None
    created_at: AwareDatetime
