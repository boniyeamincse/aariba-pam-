"""Idempotency engine enforcing non-duplication and payload conflict detection."""

import hashlib
import json
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.models import IdempotencyRecord
from ariba_pam.core.errors import ConflictException
from ariba_pam.db.base import generate_id, utc_now


class IdempotencyService:
    """Manages transactional idempotency records."""

    @staticmethod
    def compute_fingerprint(payload: Any) -> str:
        """Deterministic SHA256 digest of request payload."""
        if isinstance(payload, dict):
            serialized = json.dumps(payload, sort_keys=True, default=str)
        else:
            serialized = str(payload)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @staticmethod
    def check_idempotency(
        db: Session,
        actor_id: str,
        operation: str,
        idempotency_key: Optional[str],
        payload: Any,
    ) -> Optional[Tuple[int, Dict[str, Any]]]:
        """
        Check if operation has already been executed under this idempotency key.
        Returns cached (status_code, response_payload) if duplicate matches fingerprint.
        Raises 409 Conflict if same key is reused with a different payload.
        Returns None if this is a fresh invocation.
        """
        if not idempotency_key:
            return None

        fingerprint = IdempotencyService.compute_fingerprint(payload)
        stmt = select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.idempotency_key == idempotency_key,
        )
        record = db.scalar(stmt)

        if record:
            if record.request_fingerprint != fingerprint:
                raise ConflictException(
                    "Idempotency key reused with different request payload",
                    code="IDEMPOTENCY_CONFLICT",
                )
            return record.response_code, record.response_payload

        return None

    @staticmethod
    def save_idempotency(
        db: Session,
        actor_id: str,
        operation: str,
        idempotency_key: Optional[str],
        payload: Any,
        response_code: int,
        response_payload: Dict[str, Any],
    ) -> None:
        """Persist idempotency record within the active database transaction."""
        if not idempotency_key:
            return

        fingerprint = IdempotencyService.compute_fingerprint(payload)
        record = IdempotencyRecord(
            id=generate_id("idm"),
            actor_id=actor_id,
            operation=operation,
            idempotency_key=idempotency_key,
            request_fingerprint=fingerprint,
            response_code=response_code,
            response_payload=response_payload,
            created_at=utc_now(),
        )
        db.add(record)
