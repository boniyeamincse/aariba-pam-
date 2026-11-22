"""Scoped asset and inventory read tests with identifier concealment (Task P1-06 / FR-02 / T-02)."""

from tests.conftest import auth_headers


def test_list_assets_filtered_by_scope(client, seeded_fixtures):
    """Alice (payments team) only sees payments asset; Charlie sees analytics asset."""
    alice = seeded_fixtures["alice"]
    charlie = seeded_fixtures["charlie"]
    dave = seeded_fixtures["dave"]

    # 1. Alice's view
    resp_alice = client.get("/api/v1/assets", headers=auth_headers(alice.id, alice.email))
    assert resp_alice.status_code == 200
    alice_assets = resp_alice.json()
    assert len(alice_assets) == 1
    assert alice_assets[0]["name"] == "payment-db-01.lab"
    assert len(alice_assets[0]["accounts"]) == 2  # dbadmin and root

    # 2. Charlie's view
    resp_charlie = client.get("/api/v1/assets", headers=auth_headers(charlie.id, charlie.email))
    assert resp_charlie.status_code == 200
    charlie_assets = resp_charlie.json()
    assert len(charlie_assets) == 1
    assert charlie_assets[0]["name"] == "analytics-db-01.lab"

    # 3. Dave (admin)'s view
    resp_dave = client.get("/api/v1/assets", headers=auth_headers(dave.id, dave.email))
    assert resp_dave.status_code == 200
    assert len(resp_dave.json()) == 2


def test_get_asset_concealment_on_out_of_scope_or_guessed_id(client, seeded_fixtures):
    """
    Attempting to access an asset outside caller's scope returns 404 (concealment),
    preventing disclosure of valid asset IDs or unauthorized infrastructure.
    """
    alice = seeded_fixtures["alice"]
    asset_analytics = seeded_fixtures["asset_analytics"]

    # Alice queries valid asset_analytics (which is out of her scope)
    resp_out_of_scope = client.get(
        f"/api/v1/assets/{asset_analytics.id}",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_out_of_scope.status_code == 404
    assert resp_out_of_scope.json()["code"] == "ASSET_NOT_FOUND"

    # Alice queries non-existent random ID
    resp_nonexistent = client.get(
        "/api/v1/assets/ast_guessed_random_id",
        headers=auth_headers(alice.id, alice.email),
    )
    assert resp_nonexistent.status_code == 404
    assert resp_nonexistent.json()["code"] == "ASSET_NOT_FOUND"

    # Both responses are identical 404 NOT_FOUND errors
    assert resp_out_of_scope.json()["code"] == resp_nonexistent.json()["code"] == "ASSET_NOT_FOUND"
    assert resp_out_of_scope.json()["message"] == resp_nonexistent.json()["message"] == "Resource not found"
