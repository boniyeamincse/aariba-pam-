"""Resource-scoped permissions and default-deny validation (Task P1-04 / FR-02 / T-02)."""

from tests.conftest import auth_headers
from ariba_pam.core.scoping import ScopeChecker


def test_scoping_default_deny(seeded_fixtures):
    """Principals with no matching scope assignments are denied by default."""
    alice = seeded_fixtures["alice"]
    asset_analytics = seeded_fixtures["asset_analytics"]

    # Alice is scoped only to team 'payments'
    assert not ScopeChecker.is_asset_in_scope(alice, asset_analytics)


def test_scoping_team_scope_matching(seeded_fixtures):
    """Team-scoped roles permit assets belonging to the team."""
    alice = seeded_fixtures["alice"]
    charlie = seeded_fixtures["charlie"]
    asset_payment = seeded_fixtures["asset_payment"]
    asset_analytics = seeded_fixtures["asset_analytics"]

    # Alice matches payment asset
    assert ScopeChecker.is_asset_in_scope(alice, asset_payment, "requester")
    # Alice is not an approver on payment asset
    assert not ScopeChecker.is_asset_in_scope(alice, asset_payment, "approver")

    # Charlie matches analytics asset as approver
    assert ScopeChecker.is_asset_in_scope(charlie, asset_analytics, "approver")
    # Charlie cannot access payment asset
    assert not ScopeChecker.is_asset_in_scope(charlie, asset_payment, "approver")


def test_scoping_global_scope(seeded_fixtures):
    """Global scope ('*') covers all assets across teams."""
    dave = seeded_fixtures["dave"]
    asset_payment = seeded_fixtures["asset_payment"]
    asset_analytics = seeded_fixtures["asset_analytics"]

    assert ScopeChecker.is_asset_in_scope(dave, asset_payment, "admin")
    assert ScopeChecker.is_asset_in_scope(dave, asset_analytics, "admin")
    assert ScopeChecker.is_asset_in_scope(dave, asset_payment, "operator")
