"""
Health check endpoint tests
"""

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.smoke


def test_health_endpoint():
    """Test health check endpoint"""
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "app_name" in data
    assert "version" in data


def test_root_endpoint():
    """Test root endpoint"""
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "version" in data


def test_root_endpoint_never_advertises_disabled_docs():
    """Root must not link to docs that are turned off.

    `_expose_api_docs` in app.main drops docs_url/redoc_url in production, so a
    hardcoded link there would point at a 404. Assert the payload tracks whatever
    the app actually routes, in either direction.
    """
    client = TestClient(app)
    data = client.get("/").json()

    for key, url in (("docs_url", app.docs_url), ("redoc_url", app.redoc_url)):
        if url is None:
            assert key not in data, f"{key} advertised while the docs route is disabled"
        else:
            assert data[key] == url
            assert client.get(url).status_code == 200


@pytest.mark.asyncio
async def test_health_endpoint_async():
    """Test health check endpoint async"""
    # httpx >=0.28 deprecated `AsyncClient(app=...)` in favor of explicit
    # ASGITransport. Update for forward compatibility.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Service is healthy"
