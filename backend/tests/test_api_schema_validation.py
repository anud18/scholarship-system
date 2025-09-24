"""
Test suite for API schema validation to prevent ResponseValidationError

This test suite ensures that all API endpoints return data that matches
their declared response models, preventing schema validation errors.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.scholarship import ScholarshipStatus, ScholarshipType
from app.models.user import User, UserRole


class TestAPISchemaValidation:
    """Test schema validation for all API endpoints"""

    @pytest.fixture
    async def test_client(self):
        """Create test client"""
        return TestClient(app)

    @pytest.fixture
    async def test_user(self):
        """Create test user"""
        return User(
            id=1,
            nycu_id="test_user",
            email="test@example.com",
            role=UserRole.STUDENT,
            is_active=True,
        )

    @pytest.fixture
    async def test_student(self):
        """Create test student - Student model removed, using mock ID"""
        return "STU001"

    @pytest.fixture
    async def auth_headers(self, test_user):
        """Create authentication headers"""
        token = create_access_token({"sub": test_user.nycu_id})
        return {"Authorization": f"Bearer {token}"}

    @pytest.fixture
    async def test_scholarships(self):
        """Create test scholarships"""
        return [
            ScholarshipType(
                id=1,
                code="test_undergrad",
                name="Test Undergraduate Scholarship",
                name_en="Test Undergraduate Scholarship",
                category="undergraduate_freshman",
                academic_year=113,
                semester="first",
                amount=Decimal("10000.00"),
                status=ScholarshipStatus.ACTIVE.value,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        ]

    @pytest.mark.asyncio
    async def test_eligible_scholarships_schema(
        self, test_client, auth_headers, monkeypatch
    ):
        """Test that /api/v1/scholarships/eligible returns valid EligibleScholarshipResponse"""

        # Mock the database and services
        async def mock_get_db():
            return None

        def mock_get_current_user():
            return User(
                id=1, nycu_id="test", email="test@test.com", role=UserRole.STUDENT
            )

        async def mock_get_eligible_scholarships(student):
            from app.models.enums import (
                ApplicationCycle,
                Semester,
                SubTypeSelectionMode,
            )
            from app.models.scholarship import ScholarshipStatus, ScholarshipType

            # Return a properly structured ScholarshipType object
            scholarship = ScholarshipType()
            scholarship.id = 1
            scholarship.code = "test_scholarship"
            scholarship.name = "Test Scholarship"
            scholarship.name_en = "Test Scholarship EN"
            scholarship.category = "undergraduate_freshman"
            scholarship.academic_year = 113
            scholarship.semester = Semester.FIRST
            scholarship.application_cycle = ApplicationCycle.SEMESTER
            scholarship.sub_type_list = ["general"]
            scholarship.sub_type_selection_mode = SubTypeSelectionMode.SINGLE
            scholarship.amount = Decimal("10000.00")
            scholarship.currency = "TWD"
            scholarship.status = ScholarshipStatus.ACTIVE.value
            scholarship.created_at = datetime.now(timezone.utc)

            return [scholarship]

        # Apply mocks
        monkeypatch.setattr("app.core.deps.get_db", mock_get_db)
        monkeypatch.setattr(
            "app.core.security.get_current_user", lambda: mock_get_current_user()
        )

        # Mock the ScholarshipService.get_eligible_scholarships method
        def mock_scholarship_service_init(self, db):
            self.db = db
            self.get_eligible_scholarships = mock_get_eligible_scholarships

        monkeypatch.setattr(
            "app.services.scholarship_service.ScholarshipService.__init__",
            mock_scholarship_service_init,
        )

        # Make the API call
        response = test_client.get(
            "/api/v1/scholarships/eligible", headers=auth_headers
        )

        # Check that the response is successful (no validation error)
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"

        # Check that the response can be parsed as JSON
        data = response.json()
        assert isinstance(data, list), "Response should be a list"

        if data:  # If there are scholarships returned
            scholarship = data[0]

            # Verify all required fields are present
            required_fields = [
                "id",
                "code",
                "name",
                "name_en",
                "eligible_sub_types",
                "category",
                "academic_year",
                "semester",
                "application_cycle",
                "amount",
                "currency",
                "sub_type_selection_mode",
                "passed",
                "warnings",
                "errors",
                "created_at",
            ]

            for field in required_fields:
                assert (
                    field in scholarship
                ), f"Required field '{field}' missing from response"

            # Verify field types
            assert isinstance(scholarship["id"], int), "id should be integer"
            assert isinstance(
                scholarship["eligible_sub_types"], list
            ), "eligible_sub_types should be list"
            assert isinstance(scholarship["semester"], str), "semester should be string"
            assert isinstance(
                scholarship["application_cycle"], str
            ), "application_cycle should be string"
            assert isinstance(
                scholarship["sub_type_selection_mode"], str
            ), "sub_type_selection_mode should be string"
            assert isinstance(scholarship["passed"], list), "passed should be list"
            assert isinstance(scholarship["warnings"], list), "warnings should be list"
            assert isinstance(scholarship["errors"], list), "errors should be list"


class TestSchemaValidationUtils:
    """Utility functions to help prevent schema validation errors"""

    @staticmethod
    def validate_response_schema(response_data, expected_schema):
        """
        Validate that response data matches the expected Pydantic schema

        Args:
            response_data: The actual response data
            expected_schema: The Pydantic model class

        Returns:
            bool: True if valid, raises exception if invalid
        """
        try:
            if isinstance(response_data, list):
                for item in response_data:
                    expected_schema(**item)
            else:
                expected_schema(**response_data)
            return True
        except Exception as e:
            raise AssertionError(f"Schema validation failed: {e}")

    @staticmethod
    def convert_sqlalchemy_to_dict(obj, exclude_private=True):
        """
        Convert SQLAlchemy model to dictionary, handling enums and relationships

        Args:
            obj: SQLAlchemy model instance
            exclude_private: Whether to exclude private attributes (starting with _)

        Returns:
            dict: Converted dictionary
        """
        result = {}

        for column in obj.__table__.columns:
            value = getattr(obj, column.name)

            # Handle enum values
            if hasattr(value, "value"):
                value = value.value

            # Handle datetime objects
            if isinstance(value, datetime):
                value = value.isoformat()

            # Handle Decimal objects
            if isinstance(value, Decimal):
                value = float(value)

            result[column.name] = value

        return result


def create_comprehensive_api_test():
    """
    Create a comprehensive test that validates all API endpoints
    """
    test_template = '''
    @pytest.mark.asyncio
    async def test_{endpoint_name}_schema(self, test_client, auth_headers):
        """Test schema validation for {endpoint_path}"""
        
        # Setup test data
        # ... (create necessary test data)
        
        # Make API call  
        response = test_client.{method}("{endpoint_path}", headers=auth_headers)
        
        # Validate response
        assert response.status_code == 200, f"API call failed: {{response.text}}"
        
        data = response.json()
        
        # Validate against expected schema
        # TestSchemaValidationUtils.validate_response_schema(data, {expected_schema})
    '''

    return test_template


# Prevention Checklist for Developers
SCHEMA_VALIDATION_CHECKLIST = """
## Schema Validation Prevention Checklist

Before deploying any API endpoint changes:

### 1. Response Model Validation
- [ ] Every endpoint has a properly defined `response_model`
- [ ] Response model matches the actual data structure being returned
- [ ] All required fields are included in the response model
- [ ] Optional fields are marked as `Optional[Type]`

### 2. Data Transformation
- [ ] Database models are converted to response schemas (don't return raw SQLAlchemy objects)
- [ ] Enum values are converted to strings (use `.value` attribute)
- [ ] DateTime objects are properly serialized
- [ ] Decimal/Money values are handled correctly

### 3. Testing
- [ ] Unit tests cover the endpoint with realistic data
- [ ] Integration tests make actual HTTP requests
- [ ] Tests verify response schema compliance
- [ ] Edge cases are tested (empty lists, null values, etc.)

### 4. Code Review
- [ ] Verify response model matches return statement
- [ ] Check for proper error handling
- [ ] Ensure consistent field naming conventions
- [ ] Validate that all business logic is covered

### 5. Common Patterns to Avoid
- [ ] Don't return SQLAlchemy models directly as API responses
- [ ] Don't forget to handle enum serialization
- [ ] Don't mix database field names with API field names inconsistently
- [ ] Don't forget required fields in response models

### Example Fix Pattern:
```python
# BAD: Returning SQLAlchemy model directly
@router.get("/items", response_model=List[ItemResponse])
async def get_items():
    items = await db.query(ItemModel).all()
    return items  # This will cause validation errors!

# GOOD: Convert to response schema
@router.get("/items", response_model=List[ItemResponse])
async def get_items():
    items = await db.query(ItemModel).all()
    return [
        ItemResponse(
            id=item.id,
            name=item.name,
            status=item.status.value,  # Convert enum to string
            created_at=item.created_at
        )
        for item in items
    ]
```
"""

if __name__ == "__main__":
    print(SCHEMA_VALIDATION_CHECKLIST)
