"""
Test configuration loading and validation
"""

import os

from app.core.config import Settings


def test_settings_with_defaults():
    """Test that the loaded settings instance has expected default field values."""
    # database_url, database_url_sync, and secret_key are REQUIRED (no defaults);
    # use env-supplied values via the module-level singleton instead of trying to
    # construct a bare Settings() with cleared env vars.
    from app.core.config import settings as _settings

    assert _settings.app_name == "Scholarship Management System"
    assert _settings.host == "0.0.0.0"
    assert _settings.port == 8000
    assert _settings.algorithm == "HS256"


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
