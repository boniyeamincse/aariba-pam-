"""Transactional audit outbox service supporting durable delivery, retry, and deduplication."""

from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.models import AuditOutbox
from ariba_pam.db.base import generate_id, utc_now


class AuditService:
    """Manages transactional outbox logging and resilient event delivery."""

    @staticmethod
    def record_event(
        db: Session,
        event_type: str,
        correlation_id: str,
        actor_id: Optional[str],
        payload: Dict[str, Any],
    ) -> AuditOutbox:
        """
        Record an audit event within the caller's active database transaction.
        If the caller's transaction rolls back, this event is rolled back atomically.
        """
        event = AuditOutbox(
            id=generate_id("aud"),
            event_type=event_type,
            correlation_id=correlation_id,
            actor_id=actor_id,
            payload=payload,
            occurred_at=utc_now(),
            delivery_state="pending",
            delivery_attempts=0,
        )
        db.add(event)
        # Flush to generate ID within the active transaction without committing
        db.flush()
        return event

    @staticmethod
    def get_pending_events(db: Session, limit: int = 100) -> List[AuditOutbox]:
        """Fetch pending events for dispatch to the independent evidence store."""
        stmt = (
            select(AuditOutbox)
            .where(AuditOutbox.delivery_state == "pending")
            .order_by(AuditOutbox.occurred_at.asc())
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @staticmethod
    def mark_delivered(db: Session, event_id: str) -> Optional[AuditOutbox]:
        """Mark an audit event as successfully delivered to independent storage."""
        event = db.get(AuditOutbox, event_id)
        if event:
            event.delivery_state = "delivered"
            event.delivered_at = utc_now()
            event.delivery_attempts += 1
            db.commit()
            db.refresh(event)
        return event

    @staticmethod
    def mark_failed(db: Session, event_id: str) -> Optional[AuditOutbox]:
        """Increment delivery attempts and mark failure for retry backoff."""
        event = db.get(AuditOutbox, event_id)
        if event:
            event.delivery_attempts += 1
            if event.delivery_attempts >= 5:
                event.delivery_state = "failed"
            db.commit()
            db.refresh(event)
        return event
