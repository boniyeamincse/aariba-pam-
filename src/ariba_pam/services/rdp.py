"""RDP Gateway Policy and Windows Infrastructure Management Service (P6-01, P6-02, ADR-012).

Defines the RDP proxy configuration, client compatibility matrix,
clipboard restriction, drive redirection blocking, and graphics recording policies.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import select

from ariba_pam.db.models import Asset, TargetAccount, AccessGrant, AccessSession, AccessPolicyVersion
from ariba_pam.core.errors import ValidationException, ForbiddenException, NotFoundException
from ariba_pam.db.base import utc_now, ensure_utc
from ariba_pam.services.vault import VaultCredentialService


class RDPSecurityPolicy(BaseModel):
    """Enforceable security constraints for RDP Windows infrastructure sessions."""

    disable_clipboard: bool = Field(default=True, description="Strictly block bi-directional clipboard copy/paste")
    disable_drive_redirection: bool = Field(default=True, description="Prevent client local disk or USB folder mounting")
    disable_audio: bool = Field(default=True, description="Disable remote audio redirection")
    disable_printing: bool = Field(default=True, description="Disable local printer mapping")
    enable_recording: bool = Field(default=True, description="Capture graphical session frames for WORM custody")
    security_mode: str = Field(default="nla", description="Network Level Authentication (NLA) / TLS")
    color_depth: int = Field(default=24, description="Color depth (16, 24, 32)")
    resize_method: str = Field(default="display-update", description="Dynamic display update")


class RDPGatewayService:
    """Evaluates RDP authorization, compiles secure tunnel parameters, and enforces restrictions."""

    @staticmethod
    def get_effective_policy(
        db: Session,
        asset: Asset,
    ) -> RDPSecurityPolicy:
        """
        Derive effective RDP security policy for an asset.
        Defaults to strict Zero Standing Privilege (clipboard disabled, drive redirection blocked).
        """
        if getattr(asset, "protocol", "ssh") != "rdp":
            raise ValidationException(
                f"Asset {asset.name} is configured for protocol {getattr(asset, 'protocol', 'ssh')}, not rdp",
                code="PROTOCOL_MISMATCH",
            )

        policy = RDPSecurityPolicy()

        # Check latest published policy version for custom asset overrides
        latest_policy = (
            db.scalar(
                select(AccessPolicyVersion)
                .where(AccessPolicyVersion.asset_id == asset.id)
                .order_by(AccessPolicyVersion.version.desc())
            )
        )
        if latest_policy and "rdp" in latest_policy.rules:
            rdp_rules = latest_policy.rules["rdp"]
            if "disable_clipboard" in rdp_rules:
                policy.disable_clipboard = bool(rdp_rules["disable_clipboard"])
            if "disable_drive_redirection" in rdp_rules:
                policy.disable_drive_redirection = bool(rdp_rules["disable_drive_redirection"])
            if "disable_audio" in rdp_rules:
                policy.disable_audio = bool(rdp_rules["disable_audio"])
            if "enable_recording" in rdp_rules:
                policy.enable_recording = bool(rdp_rules["enable_recording"])

        return policy

    @staticmethod
    def compile_rdp_connection_parameters(
        db: Session,
        grant_id: str,
        session_id: str,
    ) -> Dict[str, Any]:
        """
        Compile RDP proxy parameters for the gateway tunnel (e.g. Guacamole/FreeRDP bridge).
        Injects vault-stored credentials, verifies active grant, and enforces security constraints.
        """
        grant = db.scalar(select(AccessGrant).where(AccessGrant.id == grant_id))
        if not grant or grant.status != "active":
            raise ForbiddenException("Access grant is not active", code="GRANT_NOT_ACTIVE")

        if ensure_utc(grant.effective_end_at) <= utc_now():
            raise ForbiddenException("Access grant has expired", code="GRANT_EXPIRED")

        session = db.scalar(select(AccessSession).where(AccessSession.id == session_id))
        if not session or session.grant_id != grant_id:
            raise ForbiddenException("Session does not match access grant", code="INVALID_SESSION")

        if session.status in ("closed", "revoked", "failed"):
            raise ForbiddenException(f"Session is {session.status}", code="SESSION_ENDED")

        asset = grant.asset
        if not asset or getattr(asset, "protocol", "ssh") != "rdp":
            raise ValidationException("Target asset is not an RDP destination", code="NOT_RDP_ASSET")

        account = grant.target_account
        if not account:
            raise NotFoundException("Target account not found", code="ACCOUNT_NOT_FOUND")

        # Derive effective policy constraints
        policy = RDPGatewayService.get_effective_policy(db, asset)

        # Retrieve target credential (password) securely from Vault
        secret_info = VaultCredentialService.retrieve_secret_for_gateway(
            db=db,
            grant_id=grant.id,
            session_id=session.id,
            account_id=account.id,
        )

        return {
            "session_id": session.id,
            "grant_id": grant.id,
            "protocol": "rdp",
            "hostname": asset.host,
            "port": asset.port or 3389,
            "username": account.username,
            "password": secret_info["secret_value"],
            "security": policy.security_mode,
            "disable_clipboard": policy.disable_clipboard,
            "disable_drive_redirection": policy.disable_drive_redirection,
            "disable_audio": policy.disable_audio,
            "disable_printing": policy.disable_printing,
            "enable_recording": policy.enable_recording,
            "recording_name": f"rdp_{session.id}",
            "color_depth": policy.color_depth,
            "lease_deadline": grant.effective_end_at.isoformat(),
        }
