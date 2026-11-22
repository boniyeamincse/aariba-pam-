"""Notification dispatcher processing transactional audit outbox events (FR-10, T-11)."""

from typing import Dict, Any, List, Optional, Callable
from sqlalchemy.orm import Session
from sqlalchemy import select
from ariba_pam.db.models import AuditOutbox, User, AccessRequest, AccessGrant
from ariba_pam.services.audit import AuditService


class NotificationDispatcher:
    """Dispatches notifications from the audit outbox with resilient retry and deduplication."""

    def __init__(self, delivery_sink: Optional[Callable[[Dict[str, Any]], bool]] = None):
        # Optional mockable sink for tests/lab
        self.delivery_sink = delivery_sink or (lambda msg: True)
        self.delivered_message_ids: set[str] = set()

    def process_outbox_event(self, db: Session, event: AuditOutbox) -> bool:
        """
        Process a single outbox event.
        Returns True on successful delivery, False on failure.
        Deduplicates previously delivered events.
        """
        if event.delivery_state == "delivered":
            # Already delivered; do not duplicate
            return True

        # Idempotency deduplication check on message key
        message_key = f"{event.id}_{event.event_type}"
        if message_key in self.delivered_message_ids:
            AuditService.mark_delivered(db, event.id)
            return True

        message = {
            "event_id": event.id,
            "event_type": event.event_type,
            "correlation_id": event.correlation_id,
            "actor_id": event.actor_id,
            "payload": event.payload,
            "occurred_at": event.occurred_at.isoformat(),
            "attempt": event.delivery_attempts + 1,
        }

        try:
            # Deliver to channel/sink
            success = self.delivery_sink(message)
            if success:
                self.delivered_message_ids.add(message_key)
                AuditService.mark_delivered(db, event.id)
                return True
            else:
                AuditService.mark_failed(db, event.id)
                return False
        except Exception:
            # A delivery outage preserves the authoritative decision and records retry visibility
            AuditService.mark_failed(db, event.id)
            return False

    def dispatch_pending(self, db: Session, limit: int = 50) -> Dict[str, int]:
        """Dispatch a batch of pending events from the outbox."""
        pending_events = AuditService.get_pending_events(db, limit=limit)
        successful = 0
        failed = 0

        for event in pending_events:
            if self.process_outbox_event(db, event):
                successful += 1
            else:
                failed += 1

        return {"processed": len(pending_events), "successful": successful, "failed": failed}
