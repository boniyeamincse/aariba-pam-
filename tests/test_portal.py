"""Lab catalog routes and authentication boundary checks."""

from ariba_pam.config import settings


def test_portal_serves_same_origin_assets(client):
    page = client.get("/portal")
    assert page.status_code == 200
    assert "Lab sign-in" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in page.headers["content-security-policy"]
    assert client.get("/portal/catalog.css").headers["content-type"].startswith("text/css")
    assert client.get("/portal/catalog.js").headers["content-type"].startswith("application/javascript")
    assert client.get("/portal/catalog.html").status_code == 404


def test_synthetic_entry_points_unavailable_outside_lab(client, monkeypatch):
    monkeypatch.setattr(settings, "environment", "staging")
    assert client.get("/portal").status_code == 404
    assert client.get("/portal/catalog.js").status_code == 404
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "catalog-demo@example.test", "idp_subject": "catalog-demo"},
    )
    assert response.status_code == 404


def test_synthetic_login_cannot_rebind_existing_email(client, seeded_fixtures):
    user = seeded_fixtures["alice"]
    login = {"email": user.email, "idp_subject": user.idp_subject}

    changed_subject = client.post("/api/v1/auth/login", json={**login, "idp_subject": "unknown"})
    changed_issuer = client.post("/api/v1/auth/login", json={**login, "idp_issuer": "unknown"})
    assert changed_subject.status_code == changed_issuer.status_code == 401

    enrolled = client.post("/api/v1/auth/login", json=login)
    assert enrolled.status_code == 200
    assert enrolled.headers["cache-control"] == "no-store"
