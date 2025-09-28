"""
Tests for NYCU Employee API endpoints.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.integrations.nycu_emp import NYCUEmpItem, NYCUEmpPage
from app.integrations.nycu_emp.exceptions import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
)
from app.main import app


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def sample_employee():
    """Create sample employee data."""
    return NYCUEmpItem(
        employee_no="A00001",
        employee_type="E",
        employee_name="測試教授",
        employee_ename="TEST,PROFESSOR",
        zone_no="H01",
        zone_name="光復校區",
        dept_no="A307",
        dept_name="光電工程學系",
        service_dept_no="A307",
        service_dept_name="光電工程學系",
        class_no="A",
        identity_no="A01",
        position_no="A01004",
        position_name="助理教授",
        onboard_date="2021-02-01",
        leave_date="1900-01-01",
        email="test@nycu.edu.tw",
        school_email="test@nycu.edu.tw",
        mobile_phone="0912345678",
        employee_status="01",
        update_time="2025-09-17 10:23:28.360",
    )


@pytest.fixture
def sample_page(sample_employee):
    """Create sample employee page."""
    return NYCUEmpPage(
        status="0000",
        message="",
        total_page=2,
        total_count=3,
        empDataList=[sample_employee],
    )


class TestNYCUEmployeeEndpoints:
    """Test NYCU Employee API endpoints."""

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_success(self, mock_factory, client, sample_page):
        """Test successful employee list retrieval."""
        # Mock client
        mock_client = AsyncMock()
        mock_client.get_employee_page.return_value = sample_page
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "0000"
        assert data["total_page"] == 2
        assert data["total_count"] == 3
        assert data["page"] == 1
        assert len(data["employees"]) == 1
        assert data["employees"][0]["employee_no"] == "A00001"

        # Verify client was called with correct parameters
        mock_client.get_employee_page.assert_called_once_with(page_row="1", status="01")

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_with_parameters(self, mock_factory, client, sample_page):
        """Test employee list with custom parameters."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.return_value = sample_page
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees?page=2&status=02")

        assert response.status_code == 200

        # Verify client was called with correct parameters
        mock_client.get_employee_page.assert_called_once_with(page_row="2", status="02")

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_with_context_manager(self, mock_factory, client, sample_page):
        """Test employee list with HTTP client that uses context manager."""
        # Mock client with context manager support
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.get_employee_page.return_value = sample_page
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 200

        # Verify context manager was used
        mock_client.__aenter__.assert_called_once()
        mock_client.__aexit__.assert_called_once()

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_authentication_error(self, mock_factory, client):
        """Test authentication error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = NYCUEmpAuthenticationError("Auth failed")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 401
        assert "Authentication failed" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_validation_error(self, mock_factory, client):
        """Test validation error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = NYCUEmpValidationError("Invalid request")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 400
        assert "Invalid request" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_connection_error(self, mock_factory, client):
        """Test connection error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = NYCUEmpConnectionError("Connection failed")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 503
        assert "Service unavailable" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_timeout_error(self, mock_factory, client):
        """Test timeout error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = NYCUEmpTimeoutError("Timeout")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 504
        assert "Request timeout" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_generic_error(self, mock_factory, client):
        """Test generic API error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = NYCUEmpError("Generic error")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 500
        assert "API error" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employees_unexpected_error(self, mock_factory, client):
        """Test unexpected error handling."""
        mock_client = AsyncMock()
        mock_client.get_employee_page.side_effect = Exception("Unexpected error")
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees")

        assert response.status_code == 500
        assert "Unexpected error" in response.json()["detail"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_all_employees_success(self, mock_factory, client, sample_page, sample_employee):
        """Test successful retrieval of all employees."""
        # Create second page
        page2 = NYCUEmpPage(
            status="0000",
            message="",
            total_page=2,
            total_count=3,
            empDataList=[sample_employee],
        )

        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page, page2]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/all")

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert data[0]["page"] == 1
        assert data[1]["page"] == 2
        assert all(page["total_count"] == 3 for page in data)

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_search_employees_success(self, mock_factory, client, sample_page):
        """Test successful employee search."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/search?query=測試")

        assert response.status_code == 200
        data = response.json()

        assert "employees" in data
        assert "total_count" in data
        assert "filtered_count" in data
        assert data["total_count"] == 3
        assert data["filtered_count"] == 1  # Should match one employee

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_search_employees_no_matches(self, mock_factory, client, sample_page):
        """Test employee search with no matches."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/search?query=不存在的員工")

        assert response.status_code == 200
        data = response.json()

        assert data["total_count"] == 3
        assert data["filtered_count"] == 0
        assert len(data["employees"]) == 0

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_search_employees_department_filter(self, mock_factory, client, sample_page):
        """Test employee search with department filter."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/search?dept_name=光電")

        assert response.status_code == 200
        data = response.json()

        assert data["filtered_count"] == 1
        assert len(data["employees"]) == 1
        assert "光電" in data["employees"][0]["dept_name"]

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_search_employees_position_filter(self, mock_factory, client, sample_page):
        """Test employee search with position filter."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/search?position_name=助理教授")

        assert response.status_code == 200
        data = response.json()

        assert data["filtered_count"] == 1
        assert data["employees"][0]["position_name"] == "助理教授"

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employee_by_no_success(self, mock_factory, client, sample_page):
        """Test successful employee retrieval by number."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/A00001")

        assert response.status_code == 200
        data = response.json()

        assert data["employee_no"] == "A00001"
        assert data["employee_name"] == "測試教授"

    @patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env")
    def test_get_employee_by_no_not_found(self, mock_factory, client, sample_page):
        """Test employee not found by number."""
        mock_client = AsyncMock()
        mock_client.get_all_employees.return_value = [sample_page]
        mock_factory.return_value = mock_client

        response = client.get("/api/v1/nycu-employee/employees/NOT_FOUND")

        assert response.status_code == 404
        assert "Employee NOT_FOUND not found" in response.json()["detail"]

    def test_get_employees_invalid_page(self, client):
        """Test invalid page parameter."""
        response = client.get("/api/v1/nycu-employee/employees?page=0")

        assert response.status_code == 422  # Validation error

    def test_get_employees_parameter_validation(self, client):
        """Test parameter validation."""
        # Valid request
        with patch("app.api.v1.endpoints.nycu_employee.create_nycu_emp_client_from_env") as mock_factory:
            mock_client = AsyncMock()
            mock_client.get_employee_page.return_value = NYCUEmpPage(
                status="0000", message="", total_page=1, total_count=0, empDataList=[]
            )
            mock_factory.return_value = mock_client

            response = client.get("/api/v1/nycu-employee/employees?page=1&status=01")
            assert response.status_code == 200
