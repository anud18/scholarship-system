"""
Test file to verify type checking fixes for the live model layer.

Stale skip-marked tests that referenced removed code (Student model,
password-auth functions, drifted ApplicationResponse schema) were deleted
in the dead-test sweep — only tests covering the surviving live models
remain.
"""

from app.models.application import Application, ApplicationStatus
from app.models.user import User, UserRole


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


def test_application_model_properties():
    """Test Application model has required properties"""
    from app.models.enums import Semester
    from app.models.scholarship import SubTypeSelectionMode

    app = Application(
        app_id="APP-2025-123456",
        user_id=1,
        scholarship_name="Academic Excellence",
        status=ApplicationStatus.draft,
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
    app.status = ApplicationStatus.submitted
    assert app.is_editable is False
    assert app.is_submitted is True
    assert app.can_be_reviewed is True
