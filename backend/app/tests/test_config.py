"""
Test configuration loading and validation
"""

import os

from app.core.config import Settings


def test_settings_with_defaults():
    """Test that settings can be loaded with default values"""
    # Clear environment variables that might interfere
    env_vars_to_clear = ["DATABASE_URL", "DATABASE_URL_SYNC", "SECRET_KEY"]

    original_values = {}
    for var in env_vars_to_clear:
        original_values[var] = os.environ.get(var)
        if var in os.environ:
            del os.environ[var]

    try:
        # Create settings with defaults
        settings = Settings()

        # Verify basic settings
        assert settings.app_name == "Scholarship Management System"
        assert settings.host == "0.0.0.0"
        assert settings.port == 8000
        assert settings.algorithm == "HS256"

        # Verify database URLs have defaults
        assert settings.database_url.startswith("postgresql")
        assert settings.database_url_sync.startswith("postgresql")

        # Verify secret key has default
        assert len(settings.secret_key) >= 32

    finally:
        # Restore original environment variables
        for var, value in original_values.items():
            if value is not None:
                os.environ[var] = value


def test_settings_with_environment_variables():
    """Test that settings load from environment variables"""
    test_env = {
        "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test_db",
        "DATABASE_URL_SYNC": "postgresql://test:test@localhost:5432/test_db",
        "SECRET_KEY": "test-secret-key-for-testing-with-minimum-length",
        "APP_NAME": "Test App",
        "PORT": "9000",
    }

    # Set test environment variables
    for key, value in test_env.items():
        os.environ[key] = value

    try:
        settings = Settings()

        assert settings.database_url == test_env["DATABASE_URL"]
        assert settings.database_url_sync == test_env["DATABASE_URL_SYNC"]
        assert settings.secret_key == test_env["SECRET_KEY"]
        assert settings.app_name == test_env["APP_NAME"]
        assert settings.port == 9000

    finally:
        # Clean up test environment variables
        for key in test_env.keys():
            if key in os.environ:
                del os.environ[key]


def test_scholarship_constants():
    """Test that scholarship-related constants are defined"""
    from app.core.config import SCHOLARSHIP_CATEGORIES, SCHOLARSHIP_GPA_REQUIREMENTS

    assert len(SCHOLARSHIP_GPA_REQUIREMENTS) > 0
    assert len(SCHOLARSHIP_CATEGORIES) > 0
    assert "academic_excellence" in SCHOLARSHIP_GPA_REQUIREMENTS
    assert "academic_excellence" in SCHOLARSHIP_CATEGORIES
    assert SCHOLARSHIP_GPA_REQUIREMENTS["academic_excellence"] == 3.8
