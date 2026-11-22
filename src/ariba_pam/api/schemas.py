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


