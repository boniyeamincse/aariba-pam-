"""Transactional audit outbox atomicity and resilient delivery tests (Task P1-05 / FR-08 / T-07)."""

from sqlalchemy import select, func
from ariba_pam.services.audit import AuditService
from ariba_pam.db.models import AuditOutbox, User


def test_audit_outbox_transaction_atomicity_on_rollback(db_session, seeded_fixtures):
    """
    Verify that if a database transaction fails and rolls back,
    no dangling audit event persists in the audit outbox.
    """
    alice = seeded_fixtures["alice"]

    initial_count = db_session.scalar(select(func.count()).select_from(AuditOutbox)) or 0

    try:
        # Start a nested savepoint / transaction
        with db_session.begin_nested():
            AuditService.record_event(
                db=db_session,
                event_type="TEST_FAILED_TRANSACTION",
                correlation_id="corr_tx_fail_01",
                actor_id=alice.id,
                payload={"sensitive": "state"},
            )
            # Simulate a database failure or integrity violation
            raise ValueError("Simulated database failure during business operation")
    except ValueError:
        pass

    # The outer session verifies that the uncommitted event was completely rolled back
    final_count = db_session.scalar(select(func.count()).select_from(AuditOutbox)) or 0
    assert final_count == initial_count


def test_audit_outbox_delivery_and_retry_lifecycle(db_session, seeded_fixtures):
    """
    Verify that committed audit events are retrieved, marked as delivered,
    and retry attempts increment correctly.
    """
    alice = seeded_fixtures["alice"]

    event = AuditService.record_event(
        db=db_session,
        event_type="TEST_SUCCESSFUL_EVENT",
        correlation_id="corr_tx_success_01",
        actor_id=alice.id,
        payload={"action": "test_delivery"},
    )
    db_session.commit()

    # Retrieve pending events
    pending = AuditService.get_pending_events(db_session)
    event_ids = [e.id for e in pending]
    assert event.id in event_ids

    # Simulate delivery retry
    failed_event = AuditService.mark_failed(db_session, event.id)
    assert failed_event.delivery_attempts == 1
    assert failed_event.delivery_state == "pending"

    # Simulate successful delivery
    delivered_event = AuditService.mark_delivered(db_session, event.id)
    assert delivered_event.delivery_state == "delivered"
    assert delivered_event.delivery_attempts == 2
    assert delivered_event.delivered_at is not None

    # Delivered events no longer show up in pending list
    pending_after = AuditService.get_pending_events(db_session)
    assert event.id not in [e.id for e in pending_after]
