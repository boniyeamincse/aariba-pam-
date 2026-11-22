"""Scoped Vault-Backed Credential Custody and Post-Session Rotation Service (P4-03, FR-06, SEC-05, T-06).

Implements JIT secret retrieval for authorized gateways, strictly non-disclosed credentials,
anti-superuser boundaries (Vault Custodian only), and automated post-session password rotation.
"""

import string
import secrets
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from ariba_pam.db.models import TargetAccount, VaultSecretStore, AccessGrant, AccessSession, Asset
from ariba_pam.db.base import utc_now, ensure_utc, generate_id
from ariba_pam.core.errors import (
    NotFoundException,
    ValidationException,
    ForbiddenException,
    ConflictException,
)
from ariba_pam.core.security import encrypt_vault_payload, decrypt_vault_payload
from ariba_pam.services.audit import AuditService


def generate_secure_password(length: int = 32) -> str:
    """Generate a high-entropy password suitable for privileged target accounts."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in "!@#$%^&*-_=+" for c in password)
        ):
            return password


class VaultCredentialService:
    """Manages vault-backed target credentials, JIT gateway retrieval, and rotation."""

    @staticmethod
    def store_target_credential(
        db: Session,
        account_id: str,
        secret_value: str,
        secret_type: str = "password",
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store or update an encrypted target secret in the vault store.
        Restricted to Vault Custodians. Never logs the plaintext secret.
        """
        account = db.scalar(select(TargetAccount).where(TargetAccount.id == account_id))
        if not account:
            raise NotFoundException(f"Target account {account_id} not found")

        encrypted_data = encrypt_vault_payload(secret_value)
        secret_record = db.scalar(
            select(VaultSecretStore).where(VaultSecretStore.account_id == account_id)
        )

        if secret_record:
            secret_record.encrypted_payload = encrypted_data
            secret_record.secret_type = secret_type
            secret_record.key_version += 1
            secret_record.updated_at = utc_now()
        else:
            secret_record = VaultSecretStore(
                id=generate_id("vsec"),
                account_id=account_id,
                secret_type=secret_type,
                encrypted_payload=encrypted_data,
                key_version=1,
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            db.add(secret_record)

        account.credential_type = "vault_secret"
        if not account.vault_secret_path:
            account.vault_secret_path = f"secret/targets/{account.asset_id}/{account.username}"
        account.rotation_status = "active"
        account.last_rotated_at = utc_now()

        AuditService.record_event(
            db=db,
            event_type="vault_secret.stored",
            correlation_id=account_id,
            actor_id=actor_id,
            payload={
                "account_id": account_id,
                "asset_id": account.asset_id,
                "username": account.username,
                "secret_type": secret_type,
                "key_version": secret_record.key_version,
            },
        )
        db.flush()

        return {
            "account_id": account_id,
            "credential_type": account.credential_type,
            "vault_secret_path": account.vault_secret_path,
            "key_version": secret_record.key_version,
            "last_rotated_at": account.last_rotated_at.isoformat() if account.last_rotated_at else None,
            "rotation_status": account.rotation_status,
        }

    @staticmethod
    def retrieve_secret_for_gateway(
        db: Session,
        grant_id: str,
        session_id: str,
        account_id: str,
    ) -> Dict[str, Any]:
        """
        Just-In-Time (JIT) retrieval of target credential for authorized Gateway.
        Enforces:
        - Grant is ACTIVE and NOT expired.
        - Session is ACTIVE or STARTING.
        - Account uses vault_secret credential type.
        - Audits retrieval immediately.
        """
        grant = db.scalar(select(AccessGrant).where(AccessGrant.id == grant_id))
        if not grant or grant.status != "active":
            raise ForbiddenException(
                "Access grant is not active or has been revoked",
                code="GRANT_NOT_ACTIVE",
            )

        if ensure_utc(grant.effective_end_at) <= utc_now():
            raise ForbiddenException(
                "Access grant has expired",
                code="GRANT_EXPIRED",
            )

        if grant.target_account_id != account_id:
            raise ForbiddenException(
                "Target account does not match access grant",
                code="GRANT_ACCOUNT_MISMATCH",
            )

        session = db.scalar(select(AccessSession).where(AccessSession.id == session_id))
        if not session or session.grant_id != grant_id:
            raise ForbiddenException(
                "Invalid or mismatched session",
                code="INVALID_SESSION",
            )

        if session.status in ("closed", "revoked", "failed"):
            raise ForbiddenException(
                f"Session is already {session.status}",
                code="SESSION_ENDED",
            )

        account = db.scalar(select(TargetAccount).where(TargetAccount.id == account_id))
        if not account or not account.is_active:
            raise NotFoundException(f"Target account {account_id} not found or inactive")

        if account.credential_type != "vault_secret":
            raise ValidationException(
                f"Target account uses {account.credential_type}, not vault_secret",
                code="NOT_VAULT_BACKED",
            )

        secret_record = db.scalar(
            select(VaultSecretStore).where(VaultSecretStore.account_id == account_id)
        )
        if not secret_record:
            raise NotFoundException(
                f"No vault secret found for target account {account_id}",
                code="VAULT_SECRET_NOT_FOUND",
            )

        try:
            decrypted_secret = decrypt_vault_payload(secret_record.encrypted_payload)
        except Exception as e:
            raise ValidationException(
                f"Failed to decrypt vault secret: {str(e)}",
                code="DECRYPTION_FAILED",
            )

        # Audit JIT secret retrieval
        AuditService.record_event(
            db=db,
            event_type="vault_secret.retrieved",
            correlation_id=session_id,
            actor_id=grant.requester_id,
            payload={
                "grant_id": grant_id,
                "session_id": session_id,
                "account_id": account_id,
                "asset_id": grant.asset_id,
                "secret_type": secret_record.secret_type,
                "key_version": secret_record.key_version,
            },
        )
        db.flush()

        return {
            "credential_type": secret_record.secret_type,
            "secret_value": decrypted_secret,
            "username": account.username,
        }

    @staticmethod
    def rotate_target_credential(
        db: Session,
        account_id: str,
        trigger_reason: str = "session_ended",
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Rotate target account credential.
        Invoked automatically when a session using vault credentials terminates,
        or manually by a Vault Custodian.
        """
        account = db.scalar(select(TargetAccount).where(TargetAccount.id == account_id))
        if not account:
            raise NotFoundException(f"Target account {account_id} not found")

        if account.credential_type != "vault_secret":
            raise ValidationException(
                f"Account {account_id} is not configured for vault secrets",
                code="NOT_VAULT_BACKED",
            )

        secret_record = db.scalar(
            select(VaultSecretStore).where(VaultSecretStore.account_id == account_id)
        )
        if not secret_record:
            raise NotFoundException(f"No vault record found for account {account_id}")

        new_password = generate_secure_password(32)
        encrypted_new = encrypt_vault_payload(new_password)

        secret_record.encrypted_payload = encrypted_new
        secret_record.key_version += 1
        secret_record.updated_at = utc_now()

        account.last_rotated_at = utc_now()
        account.rotation_status = "active"

        AuditService.record_event(
            db=db,
            event_type="vault_secret.rotated",
            correlation_id=account_id,
            actor_id=actor_id,
            payload={
                "account_id": account_id,
                "asset_id": account.asset_id,
                "username": account.username,
                "trigger_reason": trigger_reason,
                "new_key_version": secret_record.key_version,
            },
        )
        db.flush()

        return {
            "account_id": account_id,
            "rotation_status": account.rotation_status,
            "key_version": secret_record.key_version,
            "last_rotated_at": account.last_rotated_at.isoformat(),
            "trigger_reason": trigger_reason,
        }

    @staticmethod
    def get_credential_metadata(
        db: Session,
        account_id: str,
    ) -> Dict[str, Any]:
        """Retrieve target account vault credential metadata (no plaintext secret)."""
        account = db.scalar(select(TargetAccount).where(TargetAccount.id == account_id))
        if not account:
            raise NotFoundException(f"Target account {account_id} not found")

        secret_record = db.scalar(
            select(VaultSecretStore).where(VaultSecretStore.account_id == account_id)
        )

        return {
            "account_id": account.id,
            "username": account.username,
            "asset_id": account.asset_id,
            "credential_type": account.credential_type,
            "vault_secret_path": account.vault_secret_path,
            "auto_rotate_on_session_end": account.auto_rotate_on_session_end,
            "rotation_status": account.rotation_status,
            "key_version": secret_record.key_version if secret_record else None,
            "last_rotated_at": account.last_rotated_at.isoformat() if account.last_rotated_at else None,
        }
