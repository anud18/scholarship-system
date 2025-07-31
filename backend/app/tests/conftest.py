"""
Pytest configuration and fixtures for all tests
"""
import asyncio
import os
from typing import AsyncGenerator, Generator
from unittest.mock import Mock, AsyncMock

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
# Note: Password functions removed since system uses SSO authentication
# from app.core.security import get_password_hash
from app.db.base import Base
from app.db.deps import get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.scholarship import ScholarshipType
from app.models.application import Application, ApplicationStatus

# Override settings for testing
settings.TESTING = True
settings.DATABASE_URL = "sqlite+aiosqlite:///:memory:"
settings.DATABASE_URL_SYNC = "sqlite:///:memory:"

# Create test engines
test_engine = create_async_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

test_engine_sync = create_engine(
    settings.DATABASE_URL_SYNC,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

# Create session factories
TestingSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False
)

TestingSessionLocalSync = sessionmaker(
    test_engine_sync, class_=Session, expire_on_commit=False
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="function")
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Create a new database session for a test."""
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
        email="test@university.edu",
        username="testuser",
        full_name="Test User",
        role=UserRole.STUDENT,
        # No password needed for SSO authentication
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db: AsyncSession) -> User:
    """Create a test admin user."""
    admin = User(
        email="admin@university.edu",
        username="adminuser",
        full_name="Admin User",
        role=UserRole.ADMIN,
        # No password needed for SSO authentication
        is_active=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@pytest_asyncio.fixture
async def test_professor(db: AsyncSession) -> User:
    """Create a test professor user."""
    professor = User(
        email="professor@university.edu",
        username="profuser",
        full_name="Professor User",
        role=UserRole.PROFESSOR,
        # No password needed for SSO authentication
        is_active=True,
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
        gpa_requirement=3.8
    )
    db.add(scholarship)
    await db.commit()
    await db.refresh(scholarship)
    return scholarship


@pytest_asyncio.fixture
async def test_application(
    db: AsyncSession, test_user: User, test_scholarship: ScholarshipType
) -> Application:
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
        agree_terms=True
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
    mock.process_document = AsyncMock(return_value={
        "text": "Sample extracted text",
        "confidence": 0.95,
    })
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