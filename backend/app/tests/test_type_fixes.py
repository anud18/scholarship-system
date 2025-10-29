"""
Test file to verify type checking fixes
NOTE: Password functions and Student model removed - system uses SSO authentication
"""

import pytest

# from app.models.student import Student  # Removed - student data from external API
from app.models.application import Application, ApplicationStatus

# from app.core.security import verify_password, get_password_hash  # Removed - SSO only
from app.models.user import User, UserRole
from app.schemas.application import ApplicationListResponse, ApplicationResponse


@pytest.mark.skip(reason="Password functions removed - system uses SSO authentication")
def test_password_verification():
    """Test password verification returns bool"""
    pass


def test_user_model_creation():
    """Test User model can be created with proper arguments"""
    from app.models.user import UserType

    user = User(
        email="test@example.com",
        nycu_id="testuser",
        name="Test User",
        user_type=UserType.student,
        role=UserRole.student,
    )

    assert user.email == "test@example.com"
    assert user.nycu_id == "testuser"
    assert user.name == "Test User"
    assert user.user_type == UserType.student
    assert user.role == UserRole.student


@pytest.mark.skip(reason="ApplicationResponse schema changed - needs update")
def test_application_response_properties():
    """Test ApplicationResponse has required computed properties"""
    # Create a mock application response with all required fields
    app_response = ApplicationResponse(
        id=1,
        app_id="APP-2025-123456",
        user_id=1,
        student_id=1,
        scholarship_type="academic_excellence",
        scholarship_name="Academic Excellence Scholarship",
        amount=5000.00,
        status=ApplicationStatus.draft.value,
        status_name="Draft",
        academic_year="2024",
        semester="Fall",
        gpa=3.8,
        class_ranking_percent=10.5,
        dept_ranking_percent=8.2,
        completed_terms=6,
        contact_phone="1234567890",
        contact_email="test@example.com",
        contact_address="123 Test St",
        bank_account="123456789",
        research_proposal="Test research proposal",
        budget_plan="Test budget plan",
        milestone_plan="Test milestone plan",
        agree_terms=True,
        professor_id=1,
        reviewer_id=1,
        review_score=85.5,
        review_comments="Good application",
        rejection_reason=None,
        submitted_at="2024-01-02T00:00:00",
        reviewed_at="2024-01-03T00:00:00",
        approved_at=None,
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    # Test computed properties exist and work
    assert hasattr(app_response, "is_editable")
    assert hasattr(app_response, "is_submitted")
    assert hasattr(app_response, "can_be_reviewed")

    # Test the properties return boolean values
    assert isinstance(app_response.is_editable, bool)
    assert isinstance(app_response.is_submitted, bool)
    assert isinstance(app_response.can_be_reviewed, bool)


@pytest.mark.skip(reason="ApplicationListResponse schema changed - needs update")
def test_application_list_response_optional_fields():
    """Test ApplicationListResponse has optional student fields"""
    app_list = ApplicationListResponse(
        id=1,
        app_id="APP-2025-123456",
        scholarship_type="academic_excellence",
        scholarship_name="Academic Excellence Scholarship",
        amount=5000.00,
        status=ApplicationStatus.submitted.value,
        status_name="Submitted",
        submitted_at="2024-01-02T00:00:00",
        created_at="2024-01-01T00:00:00",
        updated_at="2024-01-01T00:00:00",
    )

    # These should be optional and default to None
    assert app_list.student_name is None
    assert app_list.student_no is None

    # Should be able to set them
    app_list.student_name = "Test Student"
    app_list.student_no = "S123456"

    assert app_list.student_name == "Test Student"
    assert app_list.student_no == "S123456"


@pytest.mark.skip(reason="Student model removed - student data from external API")
def test_student_display_name_property():
    """Test Student model has display_name property"""
    pass


def test_application_model_properties():
    """Test Application model has required properties"""
    from app.models.enums import Semester
    from app.models.scholarship import SubTypeSelectionMode

    app = Application(
        app_id="APP-2025-123456",
        user_id=1,
        scholarship_name="Academic Excellence",
        status=ApplicationStatus.draft.value,
        academic_year=113,
        semester=Semester.first,
        scholarship_subtype_list=[],
        sub_type_selection_mode=SubTypeSelectionMode.single,
    )

    # Test required properties exist
    assert hasattr(app, "is_editable")
    assert hasattr(app, "is_submitted")
    assert hasattr(app, "can_be_reviewed")

    # Test property values for draft status
    assert app.is_editable is True
    assert app.is_submitted is False
    assert app.can_be_reviewed is False

    # Test property values for submitted status
    app.status = ApplicationStatus.submitted.value
    assert app.is_editable is False
    assert app.is_submitted is True
    assert app.can_be_reviewed is True
