"""Test fixtures, database setup, and synthetic identities."""

import pytest
from typing import Generator
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

from ariba_pam.main import app
from ariba_pam.config import settings
from ariba_pam.db.base import Base
from ariba_pam.db.session import get_db
from ariba_pam.db.models import (
    User,
    Role,
    RoleAssignment,
    GatewayZone,
    Asset,
    TargetAccount,
)
from ariba_pam.core.security import create_session_token

# In-memory SQLite engine for tests with static pool
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def init_db():
    """Create fresh schema tables for each test."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Provide a database session for the test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    """Test client overriding the get_db dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            db_session.rollback()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded_fixtures(db_session: Session):
    """Seed synthetic identities, roles, zones, and assets for tests."""
    # 1. Roles
    role_requester = Role(id="rol_requester", name="requester", description="Access requester")
    role_approver = Role(id="rol_approver", name="approver", description="Access approver")
    role_operator = Role(id="rol_operator", name="operator", description="Security operator")
    role_admin = Role(id="rol_admin", name="admin", description="Platform administrator")
    role_auditor = Role(id="rol_auditor", name="auditor", description="Audit reviewer")
    db_session.add_all([role_requester, role_approver, role_operator, role_admin, role_auditor])

    # 2. Users
    user_alice = User(
        id="usr_alice",
        email="alice@example.com",
        full_name="Alice Requester (Payments)",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_alice_123",
        is_active=True,
    )
    user_bob = User(
        id="usr_bob",
        email="bob@example.com",
        full_name="Bob Approver (Payments)",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_bob_456",
        is_active=True,
    )
    user_charlie = User(
        id="usr_charlie",
        email="charlie@example.com",
        full_name="Charlie Approver (Analytics)",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_charlie_789",
        is_active=True,
    )
    user_dave = User(
        id="usr_dave",
        email="dave@example.com",
        full_name="Dave Admin",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_dave_001",
        is_active=True,
    )
    user_disabled = User(
        id="usr_disabled",
        email="disabled@example.com",
        full_name="Disabled User",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_disabled_999",
        is_active=False,
    )
    user_eva = User(
        id="usr_eva",
        email="eva@example.com",
        full_name="Eva Auditor & Custodian",
        idp_issuer=settings.idp_issuer,
        idp_subject="sub_eva_555",
        is_active=True,
    )
    role_custodian = Role(id="rol_custodian", name="evidence_custodian", description="Evidence Custodian")
    db_session.add(role_custodian)
    db_session.add_all([user_alice, user_bob, user_charlie, user_dave, user_disabled, user_eva])

    # 3. Role Assignments
    # Alice is requester for team 'payments'
    ra_alice = RoleAssignment(
        id="ras_alice",
        user_id=user_alice.id,
        role_id=role_requester.id,
        scope_type="team",
        scope_value="payments",
    )
    # Bob is approver for team 'payments'
    ra_bob = RoleAssignment(
        id="ras_bob",
        user_id=user_bob.id,
        role_id=role_approver.id,
        scope_type="team",
        scope_value="payments",
    )
    # Charlie is approver only for team 'analytics'
    ra_charlie = RoleAssignment(
        id="ras_charlie",
        user_id=user_charlie.id,
        role_id=role_approver.id,
        scope_type="team",
        scope_value="analytics",
    )
    # Dave has global admin & operator
    ra_dave_admin = RoleAssignment(
        id="ras_dave_admin",
        user_id=user_dave.id,
        role_id=role_admin.id,
        scope_type="global",
        scope_value="*",
    )
    ra_dave_op = RoleAssignment(
        id="ras_dave_op",
        user_id=user_dave.id,
        role_id=role_operator.id,
        scope_type="global",
        scope_value="*",
    )
    # Eva is Evidence Custodian and Auditor
    ra_eva_custodian = RoleAssignment(
        id="ras_eva_custodian",
        user_id=user_eva.id,
        role_id=role_custodian.id,
        scope_type="global",
        scope_value="*",
    )
    ra_eva_auditor = RoleAssignment(
        id="ras_eva_auditor",
        user_id=user_eva.id,
        role_id=role_auditor.id,
        scope_type="global",
        scope_value="*",
    )
    db_session.add_all([ra_alice, ra_bob, ra_charlie, ra_dave_admin, ra_dave_op, ra_eva_custodian, ra_eva_auditor])

    # 4. Gateway Zone
    zone_lab = GatewayZone(id="zon_lab_01", name="lab-zone-primary", description="Primary Lab Zone")
    db_session.add(zone_lab)

    # 5. Assets
    # Asset 1: Payment backend (team: payments)
    asset_payment = Asset(
        id="ast_payment_db",
        name="payment-db-01.lab",
        environment="lab",
        team="payments",
        zone_id=zone_lab.id,
        host="10.0.1.50",
        port=22,
        is_active=True,
    )
    # Asset 2: Analytics backend (team: analytics)
    asset_analytics = Asset(
        id="ast_analytics_db",
        name="analytics-db-01.lab",
        environment="lab",
        team="analytics",
        zone_id=zone_lab.id,
        host="10.0.2.50",
        port=22,
        is_active=True,
    )
    db_session.add_all([asset_payment, asset_analytics])
    db_session.flush()

    # 6. Target Accounts
    acc_pay_admin = TargetAccount(
        id="act_pay_admin",
        asset_id=asset_payment.id,
        username="dbadmin",
        is_active=True,
        requires_ticket=False,
        max_duration_seconds=3600,
    )
    acc_pay_root = TargetAccount(
        id="act_pay_root",
        asset_id=asset_payment.id,
        username="root",
        is_active=True,
        requires_ticket=True,
        max_duration_seconds=1800,
    )
    acc_ana_readonly = TargetAccount(
        id="act_ana_readonly",
        asset_id=asset_analytics.id,
        username="readonly",
        is_active=True,
        requires_ticket=False,
        max_duration_seconds=7200,
    )
    db_session.add_all([acc_pay_admin, acc_pay_root, acc_ana_readonly])
    db_session.commit()

    return {
        "alice": user_alice,
        "bob": user_bob,
        "charlie": user_charlie,
        "dave": user_dave,
        "eva": user_eva,
        "disabled": user_disabled,
        "asset_payment": asset_payment,
        "asset_analytics": asset_analytics,
        "acc_pay_admin": acc_pay_admin,
        "acc_pay_root": acc_pay_root,
        "acc_ana_readonly": acc_ana_readonly,
        "zone_lab": zone_lab,
    }


def auth_headers(user_id: str, email: str, amr: list = None) -> dict:
    """Helper generating authorization header with synthetic session token."""
    token = create_session_token(user_id=user_id, email=email, auth_methods=amr)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def policy_admin(client, seeded_fixtures, db_session):
    """Provide a policy author and distinct reviewers in separate asset scopes."""
    from types import SimpleNamespace

    author = seeded_fixtures["dave"]
    reviewer = seeded_fixtures["bob"]
    outside = seeded_fixtures["charlie"]
    asset = seeded_fixtures["asset_payment"]
    account = seeded_fixtures["acc_pay_admin"]
    role = Role(name="reviewer", description="Reviews administrative proposals")
    db_session.add(role)
    db_session.flush()
    db_session.add_all([
        RoleAssignment(user_id=reviewer.id, role_id=role.id, scope_type="team", scope_value="payments"),
        RoleAssignment(user_id=outside.id, role_id=role.id, scope_type="team", scope_value="analytics"),
    ])
    db_session.commit()

    path = "/api/v1/admin/change-proposals"

    def propose(version=0, **rules):
        return client.post(
            path,
            headers=auth_headers(author.id, author.email),
            json={
                "resource_type": "policy",
                "resource_id": asset.id,
                "expected_version": version,
                "reason": "Review lab access policy",
                "change_payload": {
                    "allowed_target_account_ids": [account.id],
                    "max_duration_seconds": 3600,
                    "required_approvals": 1,
                    **rules,
                },
            },
        )

    def publish(proposal, actor=reviewer, decision="applied"):
        assert proposal.status_code == 201, proposal.text
        proposal_id = proposal.json()["proposal_id"]
        return client.post(
            f"{path}/{proposal_id}/decisions",
            headers=auth_headers(actor.id, actor.email),
            json={"decision": decision},
        )

    return SimpleNamespace(propose=propose, publish=publish, path=path)
