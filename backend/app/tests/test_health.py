"""
Health check endpoint tests
"""

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from app.main import app


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


@pytest.mark.asyncio
async def test_health_endpoint_async():
    """Test health check endpoint async"""
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Service is healthy"
