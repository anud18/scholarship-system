#!/usr/bin/env python3
"""
Simple test runner for unit tests that don't require database fixtures
"""

import sys
import traceback

from app.core.exceptions import AuthenticationError, NotFoundError, ScholarshipException, ValidationError


def test_basic_exceptions():
    """Test basic exception functionality"""
    print("Testing basic exceptions...")

    # Test ScholarshipException
    exc = ScholarshipException("Test message", status_code=422, error_code="TEST_ERROR")
    assert exc.message == "Test message"
    assert exc.status_code == 422
    assert exc.error_code == "TEST_ERROR"
    print("✓ ScholarshipException works")

    # Test ValidationError
    val_exc = ValidationError("Invalid field", field="email")
    assert val_exc.message == "Invalid field"
    assert val_exc.status_code == 422
    assert val_exc.field == "email"
    print("✓ ValidationError works")

    # Test AuthenticationError
    auth_exc = AuthenticationError("Login failed")
    assert auth_exc.message == "Login failed"
    assert auth_exc.status_code == 401
    print("✓ AuthenticationError works")

    # Test NotFoundError
    not_found_exc = NotFoundError("User", "123")
    assert not_found_exc.message == "User not found: 123"
    assert not_found_exc.status_code == 404
    print("✓ NotFoundError works")


def test_token_operations():
    """Test JWT token operations"""
    print("\nTesting JWT token operations...")

    from unittest.mock import patch

    from app.core.security import create_access_token, verify_token

    with patch("app.core.security.settings") as mock_settings:
        mock_settings.secret_key = "test_secret_key"
        mock_settings.algorithm = "HS256"
        mock_settings.access_token_expire_minutes = 30

        # Test token creation
        data = {"sub": "123", "role": "student"}
        token = create_access_token(data)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT has 3 parts
        print("✓ Token creation works")

        # Test token verification
        payload = verify_token(token)
        assert payload["sub"] == "123"
        assert payload["role"] == "student"
        print("✓ Token verification works")


def test_sso_authentication():
    """Test SSO authentication structure"""
    print("\nTesting SSO authentication structure...")

    from unittest.mock import AsyncMock

    from app.services.mock_sso_service import MockSSOService

    # Mock database session
    mock_db = AsyncMock()

    # Test MockSSOService instantiation
    sso_service = MockSSOService(mock_db)
    assert sso_service.db == mock_db
    assert hasattr(sso_service, "auth_service")

    print("✓ SSO authentication service structure works")


def test_service_structure():
    """Test that services can be imported and instantiated"""
    print("\nTesting service structure...")

    from unittest.mock import Mock

    from app.services.auth_service import AuthService
    from app.services.notification_service import NotificationService
    from app.services.student_service import StudentService

    # Mock database session
    mock_db = Mock()

    # Test service instantiation
    auth_service = AuthService(mock_db)
    student_service = StudentService(mock_db)
    notification_service = NotificationService(mock_db)

    assert auth_service.db == mock_db
    assert student_service.db == mock_db
    assert notification_service.db == mock_db

    print("✓ Service instantiation works")


def run_all_tests():
    """Run all unit tests"""
    print("=" * 50)
    print("Running Unit Tests for Scholarship Backend")
    print("=" * 50)

    tests = [
        test_basic_exceptions,
        test_token_operations,
        test_sso_authentication,
        test_service_structure,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            traceback.print_exc()
            failed += 1

    print("\n" + "=" * 50)
    print(f"Test Results: {passed} passed, {failed} failed")
    print("=" * 50)

    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
