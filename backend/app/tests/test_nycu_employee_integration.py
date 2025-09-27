"""
Tests for NYCU Employee API integration.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.integrations.nycu_emp import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpItem,
    NYCUEmpPage,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
    create_nycu_emp_client,
    create_nycu_emp_client_from_env,
)
from app.integrations.nycu_emp.client_http import NYCUEmpHttpClient
from app.integrations.nycu_emp.client_mock import NYCUEmpMockClient


class TestNYCUEmpFactory:
    """Test NYCU Employee API client factory."""

    def test_create_mock_client(self):
        """Test creating mock client."""
        client = create_nycu_emp_client(mode="mock")
        assert isinstance(client, NYCUEmpMockClient)

    def test_create_http_client(self):
        """Test creating HTTP client with valid parameters."""
        client = create_nycu_emp_client(
            mode="http",
            account="test_account",
            key_hex="abcdef123456",
            endpoint="https://test.api.com",
        )
        assert isinstance(client, NYCUEmpHttpClient)

    def test_create_http_client_missing_account(self):
        """Test creating HTTP client without account raises error."""
        with pytest.raises(ValueError, match="account is required"):
            create_nycu_emp_client(
                mode="http",
                key_hex="abcdef123456",
                endpoint="https://test.api.com",
            )

    def test_create_http_client_missing_endpoint(self):
        """Test creating HTTP client without endpoint raises error."""
        with pytest.raises(ValueError, match="endpoint is required"):
            create_nycu_emp_client(
                mode="http",
                account="test_account",
                key_hex="abcdef123456",
            )

    def test_create_http_client_missing_keys(self):
        """Test creating HTTP client without any key raises error."""
        with pytest.raises(ValueError, match="Either key_hex or key_raw is required"):
            create_nycu_emp_client(
                mode="http",
                account="test_account",
                endpoint="https://test.api.com",
            )

    def test_invalid_mode(self):
        """Test creating client with invalid mode raises error."""
        with pytest.raises(ValueError, match="Invalid NYCU_EMP_MODE"):
            create_nycu_emp_client(mode="invalid")

    @patch.dict("os.environ", {"NYCU_EMP_MODE": "mock"})
    def test_create_from_env_mock(self):
        """Test creating mock client from environment variables."""
        client = create_nycu_emp_client_from_env()
        assert isinstance(client, NYCUEmpMockClient)

    @patch.dict(
        "os.environ",
        {
            "NYCU_EMP_MODE": "http",
            "NYCU_EMP_ACCOUNT": "test_account",
            "NYCU_EMP_KEY_HEX": "abcdef123456",
            "NYCU_EMP_ENDPOINT": "https://test.api.com",
        },
    )
    def test_create_from_env_http(self):
        """Test creating HTTP client from environment variables."""
        client = create_nycu_emp_client_from_env()
        assert isinstance(client, NYCUEmpHttpClient)


class TestNYCUEmpMockClient:
    """Test NYCU Employee mock client."""

    @pytest.fixture
    def mock_client(self):
        """Create mock client for testing."""
        return NYCUEmpMockClient()

    @pytest.mark.asyncio
    async def test_get_employee_page_default(self, mock_client):
        """Test getting employee page with default parameters."""
        result = await mock_client.get_employee_page()

        assert isinstance(result, NYCUEmpPage)
        assert result.status == "0000"
        assert result.message == ""
        assert result.total_page > 0
        assert result.total_count > 0
        assert len(result.empDataList) <= 2  # Mock uses 2 per page
        assert all(isinstance(emp, NYCUEmpItem) for emp in result.empDataList)

    @pytest.mark.asyncio
    async def test_get_employee_page_active_employees(self, mock_client):
        """Test getting active employees only."""
        result = await mock_client.get_employee_page(status="01")

        # All employees should have status "01"
        for employee in result.empDataList:
            assert employee.employee_status == "01"

    @pytest.mark.asyncio
    async def test_get_employee_page_inactive_employees(self, mock_client):
        """Test getting inactive employees only."""
        result = await mock_client.get_employee_page(status="02")

        # All employees should have status "02"
        for employee in result.empDataList:
            assert employee.employee_status == "02"

    @pytest.mark.asyncio
    async def test_get_employee_page_pagination(self, mock_client):
        """Test pagination functionality."""
        page1 = await mock_client.get_employee_page(page_row="1")
        page2 = await mock_client.get_employee_page(page_row="2")

        # Both pages should have same total_count but different employees
        assert page1.total_count == page2.total_count
        assert page1.total_page == page2.total_page

        # Employee IDs should be different (if there are enough employees)
        if len(page1.empDataList) > 0 and len(page2.empDataList) > 0:
            page1_ids = {emp.employee_no for emp in page1.empDataList}
            page2_ids = {emp.employee_no for emp in page2.empDataList}
            assert page1_ids != page2_ids

    @pytest.mark.asyncio
    async def test_get_all_employees(self, mock_client):
        """Test getting all employees across multiple pages."""
        all_pages = await mock_client.get_all_employees(status="01")

        assert len(all_pages) > 0
        assert all(isinstance(page, NYCUEmpPage) for page in all_pages)

        # Total count should be consistent across pages
        total_counts = {page.total_count for page in all_pages}
        assert len(total_counts) == 1  # All should be the same

        # Combine all employees
        all_employees = []
        for page in all_pages:
            all_employees.extend(page.empDataList)

        # Should have expected number of employees
        expected_count = all_pages[0].total_count if all_pages else 0
        assert len(all_employees) == expected_count

    @pytest.mark.asyncio
    async def test_employee_data_structure(self, mock_client):
        """Test that employee data has correct structure."""
        result = await mock_client.get_employee_page()

        if result.empDataList:
            employee = result.empDataList[0]

            # Check required fields exist
            assert hasattr(employee, "employee_no")
            assert hasattr(employee, "employee_name")
            assert hasattr(employee, "dept_name")
            assert hasattr(employee, "position_name")
            assert hasattr(employee, "email")
            assert hasattr(employee, "employee_status")

            # Check field types
            assert isinstance(employee.employee_no, str)
            assert isinstance(employee.employee_name, str)
            assert isinstance(employee.dept_name, str)
            assert isinstance(employee.position_name, str)
            assert isinstance(employee.email, str)
            assert isinstance(employee.employee_status, str)


class TestNYCUEmpHttpClient:
    """Test NYCU Employee HTTP client."""

    def test_client_initialization(self):
        """Test HTTP client initialization."""
        client = NYCUEmpHttpClient(
            account="test_account",
            key_hex="abcdef123456",
            endpoint="https://test.api.com",
        )

        assert client.account == "test_account"
        assert client.endpoint == "https://test.api.com"
        assert client.hmac_key == bytes.fromhex("abcdef123456")

    def test_client_initialization_with_raw_key(self):
        """Test HTTP client initialization with raw key."""
        client = NYCUEmpHttpClient(
            account="test_account",
            key_raw="test_key",
            endpoint="https://test.api.com",
        )

        assert client.hmac_key == b"test_key"

    def test_client_initialization_missing_key(self):
        """Test HTTP client initialization without any key raises error."""
        with pytest.raises(ValueError, match="Either key_hex or key_raw must be provided"):
            NYCUEmpHttpClient(
                account="test_account",
                endpoint="https://test.api.com",
            )

    def test_create_request_body(self):
        """Test request body creation."""
        client = NYCUEmpHttpClient(
            account="test_account",
            key_hex="abcdef123456",
            endpoint="https://test.api.com",
        )

        body = client._create_request_body("1", "01")

        # Should be compact JSON
        expected = '{"page_row":"1","status":"01"}'
        assert body == expected

    def test_generate_hmac_signature(self):
        """Test HMAC signature generation."""
        client = NYCUEmpHttpClient(
            account="test_account",
            key_hex="deadbeef",
            endpoint="https://test.api.com",
        )

        exe_time = "20251226120000"
        body = '{"page_row":"1","status":"01"}'

        signature = client._generate_hmac_signature(exe_time, body)

        # Should return a hex string
        assert isinstance(signature, str)
        assert len(signature) == 64  # SHA256 hex = 64 chars
        assert all(c in "0123456789abcdef" for c in signature)

    def test_get_taipei_time_format(self):
        """Test Taipei time format."""
        client = NYCUEmpHttpClient(
            account="test_account",
            key_hex="abcdef123456",
            endpoint="https://test.api.com",
        )

        time_str = client._get_taipei_time()

        # Should be YYYYMMDDHHMMSS format (14 digits)
        assert len(time_str) == 14
        assert time_str.isdigit()


class TestNYCUEmpModels:
    """Test NYCU Employee API models."""

    def test_nycu_emp_item_creation(self):
        """Test creating NYCUEmpItem."""
        data = {
            "employee_no": "A00001",
            "employee_type": "E",
            "employee_name": "測試員工",
            "employee_ename": "TEST,EMPLOYEE",
            "zone_no": "H01",
            "zone_name": "光復校區",
            "dept_no": "A307",
            "dept_name": "光電工程學系",
            "service_dept_no": "A307",
            "service_dept_name": "光電工程學系",
            "class_no": "A",
            "identity_no": "A01",
            "position_no": "A01004",
            "position_name": "助理教授",
            "onboard_date": "2021-02-01",
            "leave_date": "1900-01-01",
            "email": "test@nycu.edu.tw",
            "school_email": "test@nycu.edu.tw",
            "mobile_phone": "0912345678",
            "employee_status": "01",
            "update_time": "2025-09-17 10:23:28.360",
        }

        item = NYCUEmpItem(**data)

        assert item.employee_no == "A00001"
        assert item.employee_name == "測試員工"
        assert item.dept_name == "光電工程學系"
        assert item.position_name == "助理教授"
        assert item.employee_status == "01"

    def test_nycu_emp_page_creation(self):
        """Test creating NYCUEmpPage."""
        employee_data = {
            "employee_no": "A00001",
            "employee_type": "E",
            "employee_name": "測試員工",
            "employee_ename": "TEST,EMPLOYEE",
            "zone_no": "H01",
            "zone_name": "光復校區",
            "dept_no": "A307",
            "dept_name": "光電工程學系",
            "service_dept_no": "A307",
            "service_dept_name": "光電工程學系",
            "class_no": "A",
            "identity_no": "A01",
            "position_no": "A01004",
            "position_name": "助理教授",
            "onboard_date": "2021-02-01",
            "leave_date": "1900-01-01",
            "email": "test@nycu.edu.tw",
            "school_email": "test@nycu.edu.tw",
            "mobile_phone": "0912345678",
            "employee_status": "01",
            "update_time": "2025-09-17 10:23:28.360",
        }

        page_data = {
            "status": "0000",
            "message": "",
            "total_page": 2,
            "total_count": 3,
            "empDataList": [employee_data],
        }

        page = NYCUEmpPage(**page_data)

        assert page.status == "0000"
        assert page.total_page == 2
        assert page.total_count == 3
        assert len(page.empDataList) == 1
        assert page.is_success is True
        assert isinstance(page.empDataList[0], NYCUEmpItem)

    def test_nycu_emp_page_is_success(self):
        """Test NYCUEmpPage.is_success property."""
        success_page = NYCUEmpPage(
            status="0000",
            message="",
            total_page=1,
            total_count=0,
            empDataList=[],
        )
        assert success_page.is_success is True

        error_page = NYCUEmpPage(
            status="9999",
            message="Error occurred",
            total_page=0,
            total_count=0,
            empDataList=[],
        )
        assert error_page.is_success is False


class TestNYCUEmpExceptions:
    """Test NYCU Employee API exceptions."""

    def test_nycu_emp_error_basic(self):
        """Test basic NYCUEmpError."""
        error = NYCUEmpError("Test error message")

        assert str(error) == "NYCUEmpError: Test error message (status=None, http_status=None)"
        assert error.message == "Test error message"
        assert error.status is None
        assert error.http_status is None

    def test_nycu_emp_error_with_details(self):
        """Test NYCUEmpError with status and HTTP status."""
        error = NYCUEmpError("Test error", status="9999", http_status=500)

        assert error.status == "9999"
        assert error.http_status == 500

    def test_nycu_emp_connection_error(self):
        """Test NYCUEmpConnectionError."""
        error = NYCUEmpConnectionError("Connection failed")

        assert isinstance(error, NYCUEmpError)
        assert error.message == "Connection failed"

    def test_nycu_emp_authentication_error(self):
        """Test NYCUEmpAuthenticationError."""
        error = NYCUEmpAuthenticationError("Auth failed")

        assert isinstance(error, NYCUEmpError)
        assert error.message == "Auth failed"
        assert error.http_status == 401

    def test_nycu_emp_timeout_error(self):
        """Test NYCUEmpTimeoutError."""
        error = NYCUEmpTimeoutError("Timeout occurred")

        assert isinstance(error, NYCUEmpError)
        assert error.message == "Timeout occurred"

    def test_nycu_emp_validation_error(self):
        """Test NYCUEmpValidationError."""
        error = NYCUEmpValidationError("Validation failed")

        assert isinstance(error, NYCUEmpError)
        assert error.message == "Validation failed"
        assert error.http_status == 400
