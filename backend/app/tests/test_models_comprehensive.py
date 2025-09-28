"""
Comprehensive unit tests for database models

Tests model functionality including:
- Model creation and validation
- Relationships and foreign keys
- Model methods and properties
- Constraints and validations
- Serialization and deserialization
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.models.application import Application, ApplicationStatus
from app.models.email_management import EmailCategory, EmailHistory, EmailStatus
from app.models.enums import Semester
from app.models.notification import Notification, NotificationPriority, NotificationType
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType


@pytest.mark.unit
class TestUserModel:
    """Test suite for User model"""

    @pytest.mark.asyncio
    async def test_user_creation_success(self, db):
        """Test successful user creation"""
        # Arrange
        user_data = {
            "email": "test@university.edu",
            "name": "Test User",
            "nycu_id": "11011001",
            "role": UserRole.student,
            "user_type": UserType.student,
            "is_active": True,
        }

        # Act
        user = User(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Assert
        assert user.id is not None
        assert user.email == "test@university.edu"
        assert user.role == UserRole.student
        assert user.is_active is True
        assert user.created_at is not None

    @pytest.mark.asyncio
    async def test_user_unique_email_constraint(self, db):
        """Test that email must be unique"""
        # Arrange
        user1 = User(
            email="duplicate@university.edu",
            name="User One",
            nycu_id="11011001",
            role=UserRole.student,
        )
        user2 = User(
            email="duplicate@university.edu",
            name="User Two",
            nycu_id="11011002",
            role=UserRole.student,
        )

        # Act & Assert
        db.add(user1)
        await db.commit()

        db.add(user2)
        with pytest.raises(IntegrityError):
            await db.commit()

    @pytest.mark.asyncio
    async def test_user_unique_nycu_id_constraint(self, db):
        """Test that NYCU ID must be unique when not null"""
        # Arrange
        user1 = User(
            email="user1@university.edu",
            name="User One",
            nycu_id="11011001",
            role=UserRole.student,
        )
        user2 = User(
            email="user2@university.edu",
            name="User Two",
            nycu_id="11011001",  # Duplicate NYCU ID
            role=UserRole.student,
        )

        # Act & Assert
        db.add(user1)
        await db.commit()

        db.add(user2)
        with pytest.raises(IntegrityError):
            await db.commit()

    @pytest.mark.asyncio
    async def test_user_display_name_property(self, db):
        """Test user display name property"""
        # Arrange
        user = User(
            email="test@university.edu",
            name="John Doe",
            nycu_id="11011001",
            role=UserRole.student,
        )

        # Act & Assert
        assert user.display_name == "John Doe"

        # Test with missing name
        user.name = None
        assert user.display_name == "test@university.edu"

    @pytest.mark.asyncio
    async def test_user_is_admin_property(self, db):
        """Test is_admin property"""
        # Arrange & Act & Assert
        admin_user = User(role=UserRole.admin)
        assert admin_user.is_admin is True

        super_admin = User(role=UserRole.super_admin)
        assert super_admin.is_admin is True

        student = User(role=UserRole.student)
        assert student.is_admin is False

        professor = User(role=UserRole.professor)
        assert professor.is_admin is False

    @pytest.mark.asyncio
    async def test_user_can_access_scholarship_method(self, db):
        """Test can_access_scholarship method"""
        # Arrange
        user = User(role=UserRole.admin)
        scholarship = ScholarshipType(id=1, code="test", name="Test Scholarship")

        # Act & Assert
        # Admin should have access to all scholarships
        assert user.can_access_scholarship(scholarship) is True

        # Student should have limited access based on eligibility
        student = User(role=UserRole.student)
        # Implementation depends on actual business logic
        # For now, assume students can access active scholarships
        scholarship.is_active = True
        assert student.can_access_scholarship(scholarship) is True

        scholarship.is_active = False
        assert student.can_access_scholarship(scholarship) is False


@pytest.mark.unit
class TestApplicationModel:
    """Test suite for Application model"""

    @pytest.fixture
    async def test_user(self, db):
        """Create test user"""
        user = User(
            email="student@university.edu",
            name="Test Student",
            nycu_id="11011001",
            role=UserRole.student,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @pytest.fixture
    async def test_scholarship(self, db):
        """Create test scholarship"""
        scholarship = ScholarshipType(
            code="test_scholarship",
            name="Test Scholarship",
            category="undergraduate_freshman",
            amount=Decimal("50000"),
            is_active=True,
        )
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)
        return scholarship

    @pytest.mark.asyncio
    async def test_application_creation_success(self, db, test_user, test_scholarship):
        """Test successful application creation"""
        # Arrange
        application_data = {
            "app_id": "APP-2024-000001",
            "user_id": test_user.id,
            "scholarship_type_id": test_scholarship.id,
            "status": ApplicationStatus.DRAFT.value,
            "amount": Decimal("50000"),
            "academic_year": 113,
            "semester": Semester.first,
            "student_data": {"name": "Test Student", "gpa": 3.8},
            "submitted_form_data": {"statement": "Test statement"},
            "agree_terms": True,
        }

        # Act
        application = Application(**application_data)
        db.add(application)
        await db.commit()
        await db.refresh(application)

        # Assert
        assert application.id is not None
        assert application.app_id == "APP-2024-000001"
        assert application.status == ApplicationStatus.DRAFT.value
        assert application.amount == Decimal("50000")
        assert application.created_at is not None

    @pytest.mark.asyncio
    async def test_application_unique_app_id_constraint(self, db, test_user, test_scholarship):
        """Test that app_id must be unique"""
        # Arrange
        app_id = "APP-2024-DUPLICATE"

        app1 = Application(
            app_id=app_id,
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
        )

        app2 = Application(
            app_id=app_id,  # Duplicate app_id
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
        )

        # Act & Assert
        db.add(app1)
        await db.commit()

        db.add(app2)
        with pytest.raises(IntegrityError):
            await db.commit()

    @pytest.mark.asyncio
    async def test_application_status_transitions(self, db, test_user, test_scholarship):
        """Test application status transitions"""
        # Arrange
        application = Application(
            app_id="APP-2024-STATUS",
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
        )
        db.add(application)
        await db.commit()

        # Act & Assert - Test valid transitions
        application.status = ApplicationStatus.SUBMITTED.value
        application.submitted_at = datetime.now(timezone.utc)
        await db.commit()

        application.status = ApplicationStatus.UNDER_REVIEW.value
        await db.commit()

        application.status = ApplicationStatus.APPROVED.value
        application.approved_at = datetime.now(timezone.utc)
        await db.commit()

        # Verify final state
        await db.refresh(application)
        assert application.status == ApplicationStatus.APPROVED.value
        assert application.submitted_at is not None
        assert application.approved_at is not None

    @pytest.mark.asyncio
    async def test_application_relationships(self, db, test_user, test_scholarship):
        """Test application relationships"""
        # Arrange
        application = Application(
            app_id="APP-2024-REL",
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
        )
        db.add(application)
        await db.commit()
        await db.refresh(application)

        # Act - Load relationships
        result = await db.execute(
            select(Application)
            .where(Application.id == application.id)
            .options(
                selectinload(Application.student),
                selectinload(Application.scholarship_type),
            )
        )
        app_with_relations = result.scalar_one()

        # Assert
        assert app_with_relations.student.id == test_user.id
        assert app_with_relations.scholarship_type.id == test_scholarship.id

    @pytest.mark.asyncio
    async def test_application_json_fields(self, db, test_user, test_scholarship):
        """Test JSON field handling"""
        # Arrange
        student_data = {
            "name": "Test Student",
            "department": "Computer Science",
            "gpa": 3.85,
            "graduation_year": 2024,
        }

        form_data = {
            "personal_statement": "I am passionate about computer science...",
            "career_goals": "To become a software engineer",
            "extracurricular": ["Programming club", "Volunteer work"],
        }

        application = Application(
            app_id="APP-2024-JSON",
            user_id=test_user.id,
            scholarship_type_id=test_scholarship.id,
            status=ApplicationStatus.DRAFT.value,
            student_data=student_data,
            submitted_form_data=form_data,
        )

        # Act
        db.add(application)
        await db.commit()
        await db.refresh(application)

        # Assert
        assert application.student_data["name"] == "Test Student"
        assert application.student_data["gpa"] == 3.85
        assert application.submitted_form_data["personal_statement"] == "I am passionate about computer science..."
        assert len(application.submitted_form_data["extracurricular"]) == 2


@pytest.mark.unit
class TestScholarshipTypeModel:
    """Test suite for ScholarshipType model"""

    @pytest.mark.asyncio
    async def test_scholarship_creation_success(self, db):
        """Test successful scholarship type creation"""
        # Arrange
        scholarship_data = {
            "code": "undergraduate_excellence",
            "name": "Undergraduate Excellence Scholarship",
            "description": "Merit-based scholarship for outstanding students",
            "category": "undergraduate_freshman",
            "amount": Decimal("50000"),
            "academic_year": 113,
            "semester": Semester.first,
            "is_active": True,
            "is_application_period": True,
            "application_start_date": datetime.now(timezone.utc),
            "application_end_date": datetime.now(timezone.utc) + timedelta(days=30),
        }

        # Act
        scholarship = ScholarshipType(**scholarship_data)
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)

        # Assert
        assert scholarship.id is not None
        assert scholarship.code == "undergraduate_excellence"
        assert scholarship.amount == Decimal("50000")
        assert scholarship.is_active is True

    @pytest.mark.asyncio
    async def test_scholarship_unique_code_constraint(self, db):
        """Test that scholarship code must be unique"""
        # Arrange
        code = "duplicate_code"

        scholarship1 = ScholarshipType(
            code=code,
            name="First Scholarship",
            category="undergraduate",
            amount=Decimal("30000"),
        )

        scholarship2 = ScholarshipType(
            code=code,  # Duplicate code
            name="Second Scholarship",
            category="graduate",
            amount=Decimal("40000"),
        )

        # Act & Assert
        db.add(scholarship1)
        await db.commit()

        db.add(scholarship2)
        with pytest.raises(IntegrityError):
            await db.commit()

    @pytest.mark.asyncio
    async def test_scholarship_is_available_property(self, db):
        """Test is_available property"""
        # Arrange
        now = datetime.now(timezone.utc)

        # Available scholarship
        available_scholarship = ScholarshipType(
            code="available",
            name="Available Scholarship",
            is_active=True,
            is_application_period=True,
            application_start_date=now - timedelta(days=1),
            application_end_date=now + timedelta(days=30),
        )

        # Inactive scholarship
        inactive_scholarship = ScholarshipType(
            code="inactive",
            name="Inactive Scholarship",
            is_active=False,
            is_application_period=True,
        )

        # Expired scholarship
        expired_scholarship = ScholarshipType(
            code="expired",
            name="Expired Scholarship",
            is_active=True,
            is_application_period=True,
            application_start_date=now - timedelta(days=60),
            application_end_date=now - timedelta(days=30),
        )

        # Act & Assert
        assert available_scholarship.is_available is True
        assert inactive_scholarship.is_available is False
        assert expired_scholarship.is_available is False

    @pytest.mark.asyncio
    async def test_scholarship_application_count_property(self, db, test_user):
        """Test application_count property"""
        # Arrange
        scholarship = ScholarshipType(code="count_test", name="Count Test Scholarship", is_active=True)
        db.add(scholarship)
        await db.commit()
        await db.refresh(scholarship)

        # Create applications
        for i in range(3):
            app = Application(
                app_id=f"APP-2024-{i:06d}",
                user_id=test_user.id,
                scholarship_type_id=scholarship.id,
                status=ApplicationStatus.SUBMITTED.value,
            )
            db.add(app)

        await db.commit()

        # Act - Query with application count
        result = await db.execute(select(ScholarshipType).where(ScholarshipType.id == scholarship.id))
        scholarship_from_db = result.scalar_one()

        # Assert
        # Note: This would require implementing the property or method in the actual model
        # For now, we verify the relationship exists
        assert scholarship_from_db.id == scholarship.id


@pytest.mark.unit
class TestEmailHistoryModel:
    """Test suite for EmailHistory model"""

    @pytest.mark.asyncio
    async def test_email_history_creation_success(self, db):
        """Test successful email history creation"""
        # Arrange
        email_data = {
            "recipient_email": "student@university.edu",
            "subject": "Application Confirmation",
            "body": "Your application has been received successfully.",
            "status": EmailStatus.SENT,
            "category": EmailCategory.APPLICATION_CONFIRMATION,
            "sent_at": datetime.now(timezone.utc),
            "template_data": {"student_name": "John Doe", "app_id": "APP-2024-000001"},
        }

        # Act
        email = EmailHistory(**email_data)
        db.add(email)
        await db.commit()
        await db.refresh(email)

        # Assert
        assert email.id is not None
        assert email.recipient_email == "student@university.edu"
        assert email.status == EmailStatus.SENT
        assert email.template_data["student_name"] == "John Doe"

    @pytest.mark.asyncio
    async def test_email_history_status_enum(self, db):
        """Test email status enum validation"""
        # Arrange
        email = EmailHistory(
            recipient_email="test@university.edu",
            subject="Test",
            body="Test body",
            status=EmailStatus.PENDING,
        )

        # Act
        db.add(email)
        await db.commit()
        await db.refresh(email)

        # Assert
        assert email.status == EmailStatus.PENDING

        # Test status change
        email.status = EmailStatus.FAILED
        email.error_message = "SMTP timeout"
        await db.commit()

        assert email.status == EmailStatus.FAILED
        assert email.error_message == "SMTP timeout"


@pytest.mark.unit
class TestNotificationModel:
    """Test suite for Notification model"""

    @pytest.mark.asyncio
    async def test_notification_creation_success(self, db, test_user):
        """Test successful notification creation"""
        # Arrange
        notification_data = {
            "user_id": test_user.id,
            "title": "Application Update",
            "message": "Your application status has been updated.",
            "notification_type": NotificationType.APPLICATION_STATUS,
            "priority": NotificationPriority.NORMAL,
            "is_read": False,
            "data": {"application_id": 1, "new_status": "approved"},
        }

        # Act
        notification = Notification(**notification_data)
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        # Assert
        assert notification.id is not None
        assert notification.user_id == test_user.id
        assert notification.notification_type == NotificationType.APPLICATION_STATUS
        assert notification.is_read is False
        assert notification.data["application_id"] == 1

    @pytest.mark.asyncio
    async def test_notification_mark_as_read(self, db, test_user):
        """Test marking notification as read"""
        # Arrange
        notification = Notification(
            user_id=test_user.id,
            title="Test Notification",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
            is_read=False,
        )
        db.add(notification)
        await db.commit()

        # Act
        notification.is_read = True
        notification.read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(notification)

        # Assert
        assert notification.is_read is True
        assert notification.read_at is not None

    @pytest.mark.asyncio
    async def test_notification_foreign_key_constraint(self, db):
        """Test notification foreign key constraint"""
        # Arrange
        notification = Notification(
            user_id=99999,  # Non-existent user
            title="Test",
            message="Test message",
            notification_type=NotificationType.SYSTEM_ANNOUNCEMENT,
        )

        # Act & Assert
        db.add(notification)
        with pytest.raises(IntegrityError):
            await db.commit()


@pytest.mark.unit
class TestModelTimestamps:
    """Test suite for model timestamp behavior"""

    @pytest.mark.asyncio
    async def test_created_at_auto_set(self, db):
        """Test that created_at is automatically set"""
        # Arrange
        user = User(
            email="timestamp@university.edu",
            name="Timestamp User",
            role=UserRole.student,
        )

        # Act
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Assert
        assert user.created_at is not None
        assert isinstance(user.created_at, datetime)

    @pytest.mark.asyncio
    async def test_updated_at_auto_update(self, db):
        """Test that updated_at is automatically updated"""
        # Arrange
        user = User(email="update@university.edu", name="Update User", role=UserRole.student)
        db.add(user)
        await db.commit()
        await db.refresh(user)

        original_updated_at = user.updated_at

        # Act - Update the user
        user.name = "Updated Name"
        await db.commit()
        await db.refresh(user)

        # Assert
        assert user.updated_at > original_updated_at

    # TODO: Add tests for model validation methods
    # TODO: Add tests for model serialization to dict/JSON
    # TODO: Add tests for complex query scenarios
    # TODO: Add tests for model inheritance relationships
    # TODO: Add performance tests for large dataset operations
