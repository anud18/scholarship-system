"""
Verify that reference-data endpoints return the standardized ApiResponse shape.

Wave 1 of the production-readiness rollout (audit found 10 endpoints in
``reference_data.py`` returning raw ``list[dict]`` / ``dict`` instead of
``{success, message, data}`` per CLAUDE.md §5). This test pins the contract so
a regression to a bare list/dict return would fail CI rather than silently
break the frontend's auto-detection in ``frontend/lib/api.ts``.

NOTE: These tests construct a TestClient against the real FastAPI app and
hit endpoints that SELECT from reference-data tables (genders, degrees,
identities, studying_statuses). They require a populated DB and are NOT
suitable for the lightweight ``smoke`` marker — running them under the
smoke harness (no DB seed) yields ``no such table: genders``. The
``smoke`` marker has been removed; the tests still run under the full
integration suite where the DB is seeded.

A future PR can re-add ``smoke`` once the DB plumbing is fixed (the two
``get_db`` import paths — ``app.core.deps.get_db`` and
``app.db.deps.get_db`` — must be consolidated so test ``dependency_overrides``
applies to both, and all reference-data models must be registered with
``Base.metadata`` before the test fixture's ``create_all`` runs).
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


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


@pytest.mark.smoke
def test_semesters_returns_api_response():
    """GET /api/v1/reference-data/semesters returns wrapped ApiResponse[dict].

    This endpoint historically returned a bare dict (academic_years, semesters,
    current_*). Wave 1 wraps it in ApiResponse; verify the dict payload now sits
    under data and the standardized envelope is present.

    Kept under smoke because this endpoint doesn't touch the DB.
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


def test_all_reference_data_returns_api_response():
    """GET /api/v1/reference-data/all returns wrapped ApiResponse[dict].

    Wave-1 closeout: this aggregate endpoint historically returned a bare dict
    (degrees, identities, academies, departments, ...). It is now wrapped in
    ApiResponse so frontend auto-detection in ``frontend/lib/api.ts`` continues
    to work uniformly.
    """
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/all")
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_api_response_shape(payload, expected_data_type=dict)
    # Original dict keys are now under .data
    data = payload["data"]
    for key in ("degrees", "identities", "academies", "departments", "genders"):
        assert key in data, f"missing '{key}' in /reference-data/all .data payload"


def test_scholarship_types_with_cycles_returns_api_response():
    """GET /api/v1/reference-data/scholarship-types-with-cycles returns wrapped ApiResponse[dict].

    Wave-1 closeout: this endpoint historically returned a bare dict
    (scholarships, cycle_counts, total_scholarships). It is now wrapped in
    ApiResponse for parity with the rest of the reference-data module.
    """
    client = TestClient(app)
    response = client.get("/api/v1/reference-data/scholarship-types-with-cycles")
    assert response.status_code == 200, response.text
    payload = response.json()
    _assert_api_response_shape(payload, expected_data_type=dict)
    data = payload["data"]
    assert "scholarships" in data
    assert "cycle_counts" in data
    assert "total_scholarships" in data
