"""
Dynamic Configuration Service
Provides runtime-configurable settings with database override capability.
"""

from typing import Any, Optional, Set

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services.config_management_service import ConfigurationService


class DynamicConfig:
    """
    Dynamic configuration service that reads from database first,
    falls back to environment variables.

    Usage:
        config = DynamicConfig()
        smtp_host = await config.get("smtp_host", db)
    """

    # Define which configurations can be dynamically modified
    # These settings can be overridden via database and take effect immediately
    DYNAMIC_CONFIGS: Set[str] = {
        # Email/SMTP Settings
        "smtp_host",
        "smtp_port",
        "smtp_user",
        "smtp_password",
        "email_from",
        "email_from_name",
        # OCR/Gemini API Settings
        "ocr_service_enabled",
        "gemini_api_key",
        "gemini_model",
        "ocr_timeout",
        # File Upload Settings
        "max_file_size",
        "allowed_file_types",
        "max_files_per_application",
        "max_document_image_width",
        "max_document_image_height",
        # Cache Settings
        "cache_ttl",
        # Token Expiry
        "access_token_expire_minutes",
        "refresh_token_expire_days",
    }

    # Static configurations that require app restart to change
    # These should NEVER be stored in database
    STATIC_CONFIGS: Set[str] = {
        "database_url",
        "database_url_sync",
        "secret_key",
        "algorithm",
        "cors_origins",
        "base_url",
        "host",
        "port",
        "environment",
        "debug",
        "reload",
        "app_name",
        "app_version",
        "api_v1_str",
        "upload_dir",
        "redis_url",
        "frontend_url",
        # MinIO Storage Settings (static - requires restart)
        "minio_endpoint",
        "minio_access_key",
        "minio_secret_key",
        "minio_bucket",
        "minio_secure",
        "roster_minio_bucket",
        # Virus Scanning Settings (static - requires restart)
        "enable_virus_scan",
        "virus_scan_api_url",
        "virus_scan_api_key",
        "virus_scan_timeout",
    }

    async def get(self, key: str, db: AsyncSession, default: Any = None) -> Any:
        """
        Get configuration value with database override.

        Args:
            key: Configuration key
            db: Database session
            default: Default value if not found (overrides env var default)

        Returns:
            Configuration value from database or environment variable

        Raises:
            AttributeError: If key doesn't exist in settings
        """
        # Check if this is a dynamic configuration
        if key in self.DYNAMIC_CONFIGS:
            # Try to get from database first
            config_service = ConfigurationService(db)
            setting = await config_service.get_configuration(key)

            if setting:
                # Found in database, return decrypted value
                return await config_service.get_decrypted_value(setting)

        # Check if key exists in settings
        if not hasattr(settings, key):
            if default is not None:
                return default
            raise AttributeError(f"Configuration key '{key}' not found in settings")

        # Fall back to environment variable
        return getattr(settings, key)

    async def get_bool(self, key: str, db: AsyncSession, default: Optional[bool] = None) -> bool:
        """Get boolean configuration value."""
        value = await self.get(key, db, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    async def get_int(self, key: str, db: AsyncSession, default: Optional[int] = None) -> int:
        """Get integer configuration value."""
        value = await self.get(key, db, default)
        return int(value)

    async def get_str(self, key: str, db: AsyncSession, default: Optional[str] = None) -> str:
        """Get string configuration value."""
        value = await self.get(key, db, default)
        return str(value)

    async def get_list(self, key: str, db: AsyncSession, separator: str = ",", default: Optional[list] = None) -> list:
        """Get list configuration value (comma-separated string)."""
        value = await self.get(key, db, default)
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            return [item.strip() for item in value.split(separator) if item.strip()]
        return []

    def is_dynamic(self, key: str) -> bool:
        """Check if a configuration key is dynamically modifiable."""
        return key in self.DYNAMIC_CONFIGS

    def is_static(self, key: str) -> bool:
        """Check if a configuration key is static (requires restart)."""
        return key in self.STATIC_CONFIGS


# Singleton instance
dynamic_config = DynamicConfig()
