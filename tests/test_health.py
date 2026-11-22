"""Smoke tests verifying API health and readiness probes (Task P1-01 / T-10)."""

def test_health_check(client):
    """Verify /health returns 200 with service identification and environment."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "ariba-pam-control-plane"
    assert "version" in data
    assert "environment" in data


def test_readiness_check(client):
    """Verify /ready verifies live database connectivity."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_request_id_middleware(client):
    """Verify X-Request-ID header is propagated or generated."""
    # Auto-generated
    resp1 = client.get("/health")
    assert "X-Request-ID" in resp1.headers
    assert resp1.headers["X-Request-ID"].startswith("req_")

    # Caller supplied
    custom_id = "test-custom-trace-id-123"
    resp2 = client.get("/health", headers={"X-Request-ID": custom_id})
    assert resp2.headers["X-Request-ID"] == custom_id
