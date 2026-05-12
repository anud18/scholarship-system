"""
Verify that reference-data endpoints return the standardized ApiResponse shape.

Wave 1 of the production-readiness rollout (audit found 10 endpoints in
``reference_data.py`` returning raw ``list[dict]`` / ``dict`` instead of
``{success, message, data}`` per CLAUDE.md §5). This test pins the contract so
a regression to a bare list/dict return would fail CI rather than silently
break the frontend's auto-detection in ``frontend/lib/api.ts``.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

pytestmark = pytest.mark.smoke


def _assert_api_response_shape(payload, expected_data_type=(list, dict)) -> None:
    """Assert payload matches {success: bool, message: str, data: <type>}."""
    assert isinstance(payload, dict), f"payload must be a dict, got {type(payload)}"
    assert "success" in payload, f"missing 'success' key in {payload!r}"
    assert "message" in payload, f"missing 'message' key in {payload!r}"
    assert "data" in payload, f"missing 'data' key in {payload!r}"
    assert isinstance(payload["success"], bool), "success must be bool"
    assert isinstance(payload["message"], str), "message must be str"
    assert isinstance(
        payload["data"], expected_data_type
    ), f"data must be {expected_data_type}, got {type(payload['data'])}"


def test_degrees_returns_api_response():
    """GET /api/v1/reference-data/degrees returns wrapped ApiResponse[list]."""
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/degrees")
    assert response.status_code == 200, response.text
    _assert_api_response_shape(response.json(), expected_data_type=list)


def test_identities_returns_api_response():
    """GET /api/v1/reference-data/identities returns wrapped ApiResponse[list]."""
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/identities")
    assert response.status_code == 200, response.text
    _assert_api_response_shape(response.json(), expected_data_type=list)


def test_studying_statuses_returns_api_response():
    """GET /api/v1/reference-data/studying-statuses returns wrapped ApiResponse[list]."""
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/studying-statuses")
    assert response.status_code == 200, response.text
    _assert_api_response_shape(response.json(), expected_data_type=list)


def test_genders_returns_api_response():
    """GET /api/v1/reference-data/genders returns wrapped ApiResponse[list]."""
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/genders")
    assert response.status_code == 200, response.text
    _assert_api_response_shape(response.json(), expected_data_type=list)


def test_semesters_returns_api_response():
    """GET /api/v1/reference-data/semesters returns wrapped ApiResponse[dict].

    This endpoint historically returned a bare dict (academic_years, semesters,
    current_*). Wave 1 wraps it in ApiResponse; verify the dict payload now sits
    under data and the standardized envelope is present.
    """
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/semesters")
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_api_response_shape(payload, expected_data_type=dict)
    # The original dict keys are now under .data
    data = payload["data"]
    assert "academic_years" in data
    assert "semesters" in data
    assert "current_academic_year" in data
