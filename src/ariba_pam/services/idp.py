"""Multi-Provider Enterprise Identity Federation and Assurance Normalization Service (P7-03, ADR-015).

Provides:
1. Multi-IdP Directory Federation: Binds identities to (idp_issuer, idp_subject) across primary and secondary IdPs.
2. NIST SP 800-63B Authentication Assurance Normalization: Translates provider-specific AMR claims
   (e.g. Entra ID, Okta, and standard OIDC) to canonical AAL levels (AAL3 Phishing-Resistant vs AAL2 vs AAL1).
3. Provider-Neutral Disablement & Deprovisioning: Normalizes native webhooks, Microsoft Graph notifications,
   and SCIM 2.0 signals to execute rapid grant revocation and session termination within ≤ 60s NFR-01 SLA.
"""

from typing import Dict, Any, Optional, List, Tuple
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ariba_pam.config import settings
from ariba_pam.db.base import utc_now, ensure_utc
from ariba_pam.db.models import User, AccessGrant, AccessSession
from ariba_pam.services.audit import AuditService
from ariba_pam.core.errors import UnauthorizedException, NotFoundException


# Canonical Assurance Levels
AAL3_PHISHING_RESISTANT = "AAL3_PHISHING_RESISTANT"
AAL2_MULTI_FACTOR = "AAL2_MULTI_FACTOR"
AAL1_SINGLE_FACTOR = "AAL1_SINGLE_FACTOR"
REJECTED_INSECURE = "REJECTED_INSECURE"

# Provider-Specific AMR Claim Classifications
AMR_CLASSIFICATIONS: Dict[str, Dict[str, set]] = {
    "pilot_oidc": {
        AAL3_PHISHING_RESISTANT: {"fido2", "webauthn", "hwk", "x509"},
        AAL2_MULTI_FACTOR: {"otp", "totp", "mfa"},
        AAL1_SINGLE_FACTOR: {"pwd", "password"},
        REJECTED_INSECURE: {"sms", "tel", "voice"},
    },
    "microsoft_entra": {
        AAL3_PHISHING_RESISTANT: {"fido", "x509", "ngcmfa"},  # FIDO2 / Windows Hello / Smartcard
        AAL2_MULTI_FACTOR: {"mfa", "pin", "rsa", "push"},
        AAL1_SINGLE_FACTOR: {"pwd", "password"},
        REJECTED_INSECURE: {"sms", "voice"},
    },
    "okta": {
        AAL3_PHISHING_RESISTANT: {"fido2", "hwk", "webauthn"},
        AAL2_MULTI_FACTOR: {"otp", "totp", "push", "duo"},
        AAL1_SINGLE_FACTOR: {"pwd", "password"},
        REJECTED_INSECURE: {"sms", "tel"},
    },
}


class NormalizedIdPLifecycleEvent(BaseModel):
    """Standardized representation of inbound IdP account lifecycle events."""
    event_id: str
    event_type: str  # "user.disabled", "user.deprovisioned"
    idp_issuer: str
    idp_subject: Optional[str] = None
    email: Optional[str] = None
    source_provider: str = "pilot_oidc"
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: utc_now().isoformat())


class MultiIdPService:
    """Manages multi-provider federation, assurance evaluation, and lifecycle normalization."""

    @classmethod
    def get_trusted_providers(cls) -> Dict[str, Dict[str, Any]]:
        """Return catalog of currently configured and trusted enterprise IdPs."""
        providers = {
            "pilot_oidc": {
                "name": "Pilot Workforce OIDC",
                "issuer": settings.idp_issuer,
                "audience": settings.idp_audience,
                "subject_claim": "sub",
                "assurance_mode": "phishing_resistant",
                "is_primary": True,
                "is_enabled": True,
            }
        }
        if settings.secondary_idp_enabled:
            providers[settings.secondary_idp_name] = {
                "name": "Microsoft Entra ID (Enterprise Evaluation)",
                "issuer": settings.secondary_idp_issuer,
                "audience": settings.secondary_idp_audience,
                "subject_claim": "oid",
                "assurance_mode": settings.secondary_idp_assurance_mode,
                "is_primary": False,
                "is_enabled": True,
            }
        return providers

    @classmethod
    def resolve_provider_by_issuer(cls, issuer: str) -> Optional[str]:
        """Map issuer URL to registered provider identifier."""
        if not issuer:
            return None
        clean_issuer = issuer.rstrip("/")
        for provider_key, info in cls.get_trusted_providers().items():
            if info["issuer"].rstrip("/") == clean_issuer:
                return provider_key
        return None

    @classmethod
    def is_issuer_trusted(cls, issuer: str) -> bool:
        """Check whether the given OIDC issuer is registered and trusted."""
        return cls.resolve_provider_by_issuer(issuer) is not None

    @classmethod
    def normalize_amr(cls, provider: str, raw_amr: List[str]) -> Dict[str, Any]:
        """
        Normalize raw AMR claims against NIST SP 800-63B assurance tiers.
        Determines whether the token satisfies phishing-resistant privileged requirements.
        """
        provider_catalog = AMR_CLASSIFICATIONS.get(provider, AMR_CLASSIFICATIONS["pilot_oidc"])
        amr_set = {str(item).lower() for item in (raw_amr or [])}

        has_insecure = bool(amr_set & provider_catalog[REJECTED_INSECURE])
        has_phishing_resistant = bool(amr_set & provider_catalog[AAL3_PHISHING_RESISTANT])
        has_mfa = bool(amr_set & provider_catalog[AAL2_MULTI_FACTOR])
        has_single_factor = bool(amr_set & provider_catalog[AAL1_SINGLE_FACTOR])

        if has_insecure:
            level = REJECTED_INSECURE
        elif has_phishing_resistant:
            level = AAL3_PHISHING_RESISTANT
        elif has_mfa:
            level = AAL2_MULTI_FACTOR
        elif has_single_factor:
            level = AAL1_SINGLE_FACTOR
        else:
            level = REJECTED_INSECURE

        is_phishing_resistant = (level == AAL3_PHISHING_RESISTANT)
        is_acceptable = is_phishing_resistant  # privileged invariant: SEC-01 requires phishing-resistant

        return {
            "provider": provider,
            "raw_amr": list(raw_amr or []),
            "assurance_level": level,
            "is_phishing_resistant": is_phishing_resistant,
            "is_multi_factor": has_mfa or is_phishing_resistant,
            "is_acceptable_for_privileged": is_acceptable,
        }

    @classmethod
    def validate_assurance(
        cls,
        provider: str,
        raw_amr: List[str],
        require_phishing_resistant: bool = True,
    ) -> Tuple[bool, str]:
        """
        Verify that identity claims satisfy the configured authentication assurance policy.
        Returns (is_valid, reason).
        """
        norm = cls.normalize_amr(provider, raw_amr)
        if norm["assurance_level"] == REJECTED_INSECURE:
            return False, "Insecure or telephony-based authentication methods (SMS/voice) are forbidden for privileged access"

        if require_phishing_resistant and not norm["is_phishing_resistant"]:
            return False, f"Authentication assurance ({norm['assurance_level']}) does not satisfy mandatory phishing-resistant MFA requirement (NIST AAL3 / FIDO2)"

        return True, "Assurance verified"

    @classmethod
    def normalize_lifecycle_event(cls, payload: Dict[str, Any]) -> NormalizedIdPLifecycleEvent:
        """
        Normalize heterogeneous IdP lifecycle events (standard OIDC, Microsoft Graph, or SCIM 2.0).
        """
        # Case 1: Microsoft Graph Change Notification format
        if payload.get("subscriptionId") and payload.get("resourceData"):
            res_data = payload.get("resourceData") or {}
            event_id = payload.get("id") or payload.get("subscriptionId")
            account_enabled = res_data.get("accountEnabled")
            event_type = "user.disabled" if account_enabled is False else "user.updated"
            issuer = settings.secondary_idp_issuer
            subject = res_data.get("id")  # Entra object ID
            email = res_data.get("userPrincipalName") or res_data.get("mail")
            return NormalizedIdPLifecycleEvent(
                event_id=str(event_id),
                event_type=event_type,
                idp_issuer=issuer,
                idp_subject=subject,
                email=email,
                source_provider="microsoft_entra",
                raw_payload=payload,
            )

        # Case 2: SCIM 2.0 Patch / Deprovision format
        schemas = payload.get("schemas") or []
        if schemas and any("scim" in s.lower() for s in schemas):
            ops = payload.get("Operations") or []
            is_deactivated = False
            for op in ops:
                if op.get("op", "").lower() == "replace" and op.get("path") == "active" and op.get("value") is False:
                    is_deactivated = True
                    break
            event_type = "user.disabled" if is_deactivated else "user.updated"
            event_id = payload.get("id") or f"scim_{utc_now().timestamp()}"
            issuer = payload.get("idp_issuer") or settings.idp_issuer
            subject = payload.get("externalId") or payload.get("userName")
            email = payload.get("email") or payload.get("userName")
            return NormalizedIdPLifecycleEvent(
                event_id=str(event_id),
                event_type=event_type,
                idp_issuer=issuer,
                idp_subject=subject,
                email=email,
                source_provider="scim",
                raw_payload=payload,
            )

        # Case 3: Standard Ariba PAM / OIDC event format
        issuer = payload.get("idp_issuer") or settings.idp_issuer
        provider = cls.resolve_provider_by_issuer(issuer) or "pilot_oidc"
        return NormalizedIdPLifecycleEvent(
            event_id=str(payload.get("event_id") or f"evt_{utc_now().timestamp()}"),
            event_type=str(payload.get("event_type") or "user.disabled"),
            idp_issuer=issuer,
            idp_subject=payload.get("idp_subject"),
            email=payload.get("email"),
            source_provider=provider,
            raw_payload=payload,
            timestamp=payload.get("timestamp") or utc_now().isoformat(),
        )

    @classmethod
    def execute_disablement(
        cls,
        db: Session,
        event: NormalizedIdPLifecycleEvent,
        correlation_id: str,
    ) -> Dict[str, Any]:
        """
        Execute instantaneous user account deactivation, grant revocation, and session termination.
        Enforces the ≤ 60s NFR-01 SLA across all federated IdPs.
        """
        user = None
        if event.idp_subject:
            user = (
                db.query(User)
                .filter(User.idp_issuer == event.idp_issuer, User.idp_subject == event.idp_subject)
                .first()
            )
        if not user and event.email:
            user = db.query(User).filter(User.email == event.email).first()

        if not user:
            raise NotFoundException(
                f"User not found for IdP event from issuer {event.idp_issuer}",
                code="UNKNOWN_IDENTITY",
            )

        now = utc_now()
        revoked_count = 0
        terminating_count = 0

        if event.event_type in ("user.disabled", "user.deprovisioned"):
            user.is_active = False

            # Revoke active and scheduled grants
            active_grants = (
                db.query(AccessGrant)
                .filter(AccessGrant.requester_id == user.id, AccessGrant.status.in_(["active", "scheduled"]))
                .all()
            )
            revoked_count = len(active_grants)
            for grant in active_grants:
                grant.status = "revoked"
                grant.revocation_reason = f"IdP disablement from {event.source_provider} ({event.event_type})"
                grant.revoked_at = now

                # Mark active sessions under these grants as terminating
                active_sessions = (
                    db.query(AccessSession)
                    .filter(AccessSession.grant_id == grant.id, AccessSession.status.in_(["starting", "active"]))
                    .all()
                )
                for s in active_sessions:
                    s.status = "terminating"
                    s.termination_reason = f"IdP disablement from {event.source_provider} ({event.event_type})"
                    terminating_count += 1

            AuditService.record_event(
                db=db,
                event_type="IDP_USER_DISABLED",
                correlation_id=correlation_id,
                actor_id=user.id,
                payload={
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "source_provider": event.source_provider,
                    "idp_issuer": event.idp_issuer,
                    "idp_subject": event.idp_subject,
                    "user_id": user.id,
                    "email": user.email,
                    "revoked_grants_count": revoked_count,
                    "terminating_sessions_count": terminating_count,
                    "source_timestamp": event.timestamp,
                },
            )

        return {
            "status": "processed",
            "event_id": event.event_id,
            "event_type": event.event_type,
            "source_provider": event.source_provider,
            "idp_issuer": event.idp_issuer,
            "user_id": user.id,
            "is_active": user.is_active,
            "revoked_grants_count": revoked_count,
            "terminating_sessions_count": terminating_count,
        }
