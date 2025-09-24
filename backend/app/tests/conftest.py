"""
Pytest configuration and fixtures for all tests
"""
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Override settings BEFORE importing models (models use settings to determine JSON type)
os.environ["TESTING"] = "true"
os.environ["PYTEST_CURRENT_TEST"] = "true"

# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite:///:memory:"
TEST_DATABASE_URL_ASYNC = "sqlite+aiosqlite:///:memory:"

from app.core.config import settings

settings.database_url_sync = TEST_DATABASE_URL
settings.database_url = TEST_DATABASE_URL_ASYNC  # Set async URL early too

# Now import models (they will use SQLite-compatible JSON type)
# Note: Password functions removed since system uses SSO authentication
# from app.core.security import get_password_hash
from app.db.base_class import Base  # Use the correct Base class that models use
from app.db.deps import get_db
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType

# Create test engines - use sync only for service tests
test_engine_sync = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# For async tests (if aiosqlite is available)
try:
    test_engine = create_async_engine(
        TEST_DATABASE_URL_ASYNC,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    settings.database_url = TEST_DATABASE_URL_ASYNC
except ImportError:
    # Fallback if aiosqlite is not available
    test_engine = None
    settings.database_url = TEST_DATABASE_URL

# Create session factories
TestingSessionLocalSync = sessionmaker(test_engine_sync, class_=Session, expire_on_commit=False)

# Only create async session if async engine is available
if test_engine:
    TestingSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
else:
    TestingSessionLocal = None


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for a test."""
    if not test_engine or not TestingSessionLocal:
        pytest.skip("Async database tests require aiosqlite")

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestingSessionLocal() as session:
        yield session

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(scope="function")
def db_sync() -> Generator[Session, None, None]:
    """Create a new sync database session for a test."""
    Base.metadata.create_all(bind=test_engine_sync)

    with TestingSessionLocalSync() as session:
        yield session

    Base.metadata.drop_all(bind=test_engine_sync)


@pytest_asyncio.fixture(scope="function")
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create a test client."""

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        nycu_id="testuser",
        name="Test User",
        email="test@university.edu",
        user_type=UserType.STUDENT,
        role=UserRole.STUDENT,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db: AsyncSession) -> User:
    """Create a test admin user."""
    admin = User(
        nycu_id="adminuser",
        name="Admin User",
        email="admin@university.edu",
        user_type=UserType.EMPLOYEE,
        role=UserRole.ADMIN,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def test_professor(db: AsyncSession) -> User:
    """Create a test professor user."""
    professor = User(
        nycu_id="profuser",
        name="Professor User",
        email="professor@university.edu",
        user_type=UserType.EMPLOYEE,
        role=UserRole.PROFESSOR,
    )
    db.add(professor)
    await db.commit()
    await db.refresh(professor)
    return professor


@pytest_asyncio.fixture
async def test_scholarship(db: AsyncSession) -> ScholarshipType:
    """Create a test scholarship type."""
    scholarship = ScholarshipType(
        code="test_scholarship",
        name="Test Academic Excellence Scholarship",
        description="Test scholarship for academic excellence",
        is_active=True,
        is_application_period=True,
        category="undergraduate_freshman",
        eligible_student_types=["undergraduate"],
        max_ranking_percent=10.0,
        gpa_requirement=3.8,
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def test_application(db: AsyncSession, test_user: User, test_scholarship: ScholarshipType) -> Application:
    """Create a test application."""
    application = Application(
        user_id=test_user.id,
        scholarship_type_id=test_scholarship.id,
        status=ApplicationStatus.DRAFT.value,
        app_id="TEST-2024-123456",
        academic_year=2024,
        semester="first",
        student_data={"name": "Test Student"},
        submitted_form_data={"personal_statement": "This is my test personal statement."},
        agree_terms=True,
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)
    return application


@pytest_asyncio.fixture
async def authenticated_client(client: AsyncClient, test_user: User) -> AsyncClient:
    """Create an authenticated test client."""
    login_data = {
        "username": test_user.email,
        "password": "testpassword123",
    }
    response = await client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]

    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, test_admin: User) -> AsyncClient:
    """Create an authenticated admin client."""
    login_data = {
        "username": test_admin.email,
        "password": "adminpassword123",
    }
    response = await client.post("/api/v1/auth/login", data=login_data)
    assert response.status_code == 200
    token = response.json()["access_token"]

    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# Fixture aliases for test_admin_endpoints.py compatibility
# Use Mock objects since tests mock everything anyway
@pytest.fixture
def admin_user():
    """Create mock admin user."""
    from unittest.mock import Mock

    user = Mock(spec=User)
    user.id = 1
    user.nycu_id = "adminuser"
    user.name = "Admin User"
    user.email = "admin@university.edu"
    user.user_type = UserType.EMPLOYEE
    user.role = UserRole.ADMIN
    return user


@pytest.fixture
def regular_user():
    """Create mock regular user."""
    from unittest.mock import Mock

    user = Mock(spec=User)
    user.id = 2
    user.nycu_id = "testuser"
    user.name = "Test User"
    user.email = "test@university.edu"
    user.user_type = UserType.STUDENT
    user.role = UserRole.STUDENT
    return user


@pytest.fixture
def student_user():
    """Create mock student user."""
    from unittest.mock import Mock

    user = Mock(spec=User)
    user.id = 3
    user.nycu_id = "student123"
    user.name = "Student User"
    user.email = "student@university.edu"
    user.user_type = UserType.STUDENT
    user.role = UserRole.STUDENT
    return user


@pytest.fixture
def scholarship_type():
    """Create mock scholarship type."""
    from unittest.mock import Mock

    scholarship = Mock(spec=ScholarshipType)
    scholarship.id = 1
    scholarship.code = "test_scholarship"
    scholarship.name = "Test Academic Excellence Scholarship"
    scholarship.description = "Test scholarship for academic excellence"
    return scholarship


@pytest.fixture
def mock_email_service():
    """Mock email service."""
    mock = AsyncMock()
    mock.send_email = AsyncMock(return_value=True)
    mock.send_application_confirmation = AsyncMock(return_value=True)
    mock.send_status_update = AsyncMock(return_value=True)
    return mock


@pytest.fixture
def mock_ocr_service():
    """Mock OCR service."""
    mock = AsyncMock()
    mock.process_document = AsyncMock(
        return_value={
            "text": "Sample extracted text",
            "confidence": 0.95,
        }
    )
    return mock


@pytest.fixture
def mock_storage_service():
    """Mock storage service."""
    mock = AsyncMock()
    mock.upload_file = AsyncMock(return_value="https://storage.example.com/file.pdf")
    mock.delete_file = AsyncMock(return_value=True)
    mock.get_file_url = AsyncMock(return_value="https://storage.example.com/file.pdf")
    return mock


# Test data fixtures
@pytest.fixture
def sample_application_data():
    """Sample application data for testing."""
    return {
        "scholarship_id": "test-scholarship-id",
        "personal_statement": "This is a test personal statement with more than 100 characters to meet validation requirements.",
        "gpa": 3.85,
        "expected_graduation": "2025-06-15",
        "references": [
            {
                "name": "Dr. John Smith",
                "email": "john.smith@university.edu",
                "relationship": "Professor",
            }
        ],
    }


@pytest.fixture
def sample_scholarship_data():
    """Sample scholarship data for testing."""
    return {
        "name": "Merit Scholarship",
        "description": "Scholarship for outstanding students",
        "type": "merit",
        "amount": 10000.00,
        "currency": "USD",
        "gpa_requirement": 3.5,
        "deadline": "2025-12-31T23:59:59",
        "max_recipients": 5,
        "requirements": ["Transcript", "Letter of Recommendation"],
    }


# Performance testing fixtures
@pytest.fixture
def performance_monitor():
    """Monitor performance metrics during tests."""
    import time

    class PerformanceMonitor:
        def __init__(self):
            self.start_time = None
            self.end_time = None
            self.memory_start = None
            self.memory_end = None

        def start(self):
            self.start_time = time.time()
            # Could add memory tracking here

        def stop(self):
            self.end_time = time.time()

        @property
        def duration(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

        def assert_performance(self, max_duration: float):
            """Assert that operation completed within max_duration seconds."""
            assert self.duration is not None, "Performance monitoring not started/stopped"
            assert self.duration < max_duration, f"Operation took {self.duration:.2f}s, expected < {max_duration}s"

    return PerformanceMonitor()


# Markers for different test types
pytest.mark.unit = pytest.mark.mark(name="unit")
pytest.mark.integration = pytest.mark.mark(name="integration")
pytest.mark.smoke = pytest.mark.mark(name="smoke")
pytest.mark.slow = pytest.mark.mark(name="slow")
pytest.mark.security = pytest.mark.mark(name="security")
pytest.mark.performance = pytest.mark.mark(name="performance")
