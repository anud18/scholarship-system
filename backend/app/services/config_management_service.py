"""
Secure Configuration Management Service
Handles system configuration with encryption for sensitive values
"""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_setting import ConfigCategory, ConfigDataType, ConfigurationAuditLog, SystemSetting


class ConfigEncryption:
    """Handle encryption/decryption of sensitive configuration values"""

    def __init__(self):
        # Use a key derived from SECRET_KEY for configuration encryption
        key_material = settings.secret_key.encode()[:32].ljust(32, b"0")  # Ensure 32 bytes
        import base64
        import hashlib

        key = base64.urlsafe_b64encode(hashlib.sha256(key_material).digest())
        self.fernet = Fernet(key)

    def encrypt_value(self, value: str) -> str:
        """Encrypt a sensitive value"""
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt_value(self, encrypted_value: str) -> str:
        """Decrypt a sensitive value"""
        return self.fernet.decrypt(encrypted_value.encode()).decode()


class ConfigurationService:
    """Service for managing system configurations"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.encryption = ConfigEncryption()

    async def get_configuration(self, key: str) -> Optional[SystemSetting]:
        """Get a single configuration by key"""
        stmt = select(SystemSetting).where(SystemSetting.key == key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_configurations_by_category(self, category: ConfigCategory) -> List[SystemSetting]:
        """Get all configurations in a category"""
        stmt = select(SystemSetting).where(SystemSetting.category == category)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_all_configurations(self) -> List[SystemSetting]:
        """Get all configurations"""
        stmt = select(SystemSetting)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_decrypted_value(self, setting: SystemSetting) -> Any:
        """Get the decrypted value of a configuration setting"""
        value = setting.value

        # Decrypt if sensitive AND not empty (empty values are stored unencrypted)
        if setting.is_sensitive and value:  # Only decrypt non-empty sensitive values
            try:
                value = self.encryption.decrypt_value(value)
            except Exception:
                # If decryption fails, return as-is (might be unencrypted legacy value or empty)
                pass

        # Convert to appropriate type
        if setting.data_type == ConfigDataType.boolean:
            return value.lower() in ("true", "1", "yes", "on")
        elif setting.data_type == ConfigDataType.integer:
            return int(value)
        elif setting.data_type == ConfigDataType.float:
            return float(value)
        elif setting.data_type == ConfigDataType.json:
            return json.loads(value)
        else:
            return value

    async def set_configuration(
        self,
        key: str,
        value: Any,
        user_id: int,
        category: ConfigCategory = ConfigCategory.features,
        data_type: ConfigDataType = ConfigDataType.string,
        is_sensitive: bool = False,
        is_readonly: bool = False,
        allow_empty: bool = False,
        description: str = None,
        validation_regex: str = None,
        default_value: str = None,
        change_reason: str = None,
    ) -> SystemSetting:
        """Set or update a configuration value"""

        # Convert value to string
        if data_type == ConfigDataType.json:
            string_value = json.dumps(value) if value else ""
        elif data_type == ConfigDataType.boolean:
            string_value = str(bool(value)).lower() if value else ""
        else:
            string_value = str(value) if value is not None else ""

        # Check if empty value is allowed
        if not string_value:  # Empty string
            if not allow_empty:
                raise ValueError("This configuration does not allow empty values. Set allow_empty=True to enable.")
            # For empty values, skip validation and type conversion
        else:
            # Validate if regex provided (only for non-empty values)
            if validation_regex and not re.match(validation_regex, string_value):
                raise ValueError(f"Value does not match validation pattern: {validation_regex}")

        # Encrypt if sensitive (but NOT if empty when allow_empty=True)
        stored_value = string_value
        if is_sensitive and string_value:  # Only encrypt non-empty sensitive values
            stored_value = self.encryption.encrypt_value(string_value)
        # If empty string and allow_empty=True, store as-is (don't encrypt empty values)

        # Get existing setting
        existing = await self.get_configuration(key)
        old_value = existing.value if existing else None

        if existing:
            # Check if readonly
            if existing.is_readonly:
                raise ValueError(f"Configuration '{key}' is readonly and cannot be modified")

            # Update existing
            existing.value = stored_value
            existing.allow_empty = allow_empty
            existing.last_modified_by = user_id
            existing.updated_at = datetime.utcnow()
            setting = existing
            action = "UPDATE"
        else:
            # Create new
            setting = SystemSetting(
                key=key,
                value=stored_value,
                category=category,
                data_type=data_type,
                is_sensitive=is_sensitive,
                is_readonly=is_readonly,
                allow_empty=allow_empty,
                description=description,
                validation_regex=validation_regex,
                default_value=default_value,
                last_modified_by=user_id,
            )
            self.db.add(setting)
            action = "CREATE"

        # Create audit log
        audit_log = ConfigurationAuditLog(
            setting_key=key,
            old_value=old_value,
            new_value=stored_value,
            action=action,
            changed_by=user_id,
            change_reason=change_reason,
        )
        self.db.add(audit_log)

        await self.db.commit()
        await self.db.refresh(setting)
        return setting

    async def delete_configuration(self, key: str, user_id: int, change_reason: str = None) -> bool:
        """Delete a configuration"""
        setting = await self.get_configuration(key)
        if not setting:
            return False

        if setting.is_readonly:
            raise ValueError(f"Configuration '{key}' is readonly and cannot be deleted")

        # Create audit log
        audit_log = ConfigurationAuditLog(
            setting_key=key,
            old_value=setting.value,
            new_value="",
            action="DELETE",
            changed_by=user_id,
            change_reason=change_reason,
        )
        self.db.add(audit_log)

        await self.db.delete(setting)
        await self.db.commit()
        return True

    async def bulk_update_configurations(
        self, updates: List[Dict[str, Any]], user_id: int, change_reason: str = None
    ) -> List[SystemSetting]:
        """Update multiple configurations in a transaction"""
        updated_settings = []

        try:
            for update in updates:
                setting = await self.set_configuration(
                    key=update["key"],
                    value=update["value"],
                    user_id=user_id,
                    category=update.get("category", ConfigCategory.features),
                    data_type=update.get("data_type", ConfigDataType.string),
                    is_sensitive=update.get("is_sensitive", False),
                    is_readonly=update.get("is_readonly", False),
                    description=update.get("description"),
                    validation_regex=update.get("validation_regex"),
                    default_value=update.get("default_value"),
                    change_reason=change_reason,
                )
                updated_settings.append(setting)

            return updated_settings
        except Exception as e:
            await self.db.rollback()
            raise e

    async def validate_configuration(self, key: str, value: Any, data_type: ConfigDataType) -> Tuple[bool, str]:
        """Validate a configuration value"""
        try:
            if data_type == ConfigDataType.integer:
                int(value)
            elif data_type == ConfigDataType.float:
                float(value)
            elif data_type == ConfigDataType.boolean:
                if str(value).lower() not in ("true", "false", "1", "0", "yes", "no", "on", "off"):
                    return False, "Boolean value must be true/false, 1/0, yes/no, or on/off"
            elif data_type == ConfigDataType.json:
                json.loads(str(value))

            return True, "Valid"
        except Exception as e:
            return False, f"Validation error: {str(e)}"

    async def get_audit_logs(
        self, setting_key: str = None, user_id: int = None, limit: int = 100
    ) -> List[ConfigurationAuditLog]:
        """Get audit logs for configuration changes"""
        stmt = select(ConfigurationAuditLog).order_by(ConfigurationAuditLog.changed_at.desc())

        if setting_key:
            stmt = stmt.where(ConfigurationAuditLog.setting_key == setting_key)
        if user_id:
            stmt = stmt.where(ConfigurationAuditLog.changed_by == user_id)

        stmt = stmt.limit(limit)

        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    def get_predefined_configurations(self) -> Dict[str, Dict[str, Any]]:
        """Get predefined configuration definitions"""
        return {
            # OCR Settings
            "ocr_service_enabled": {
                "category": ConfigCategory.ocr,
                "data_type": ConfigDataType.boolean,
                "is_sensitive": False,
                "description": "Enable or disable OCR service for bank passbook extraction",
                "default_value": "false",
            },
            "gemini_api_key": {
                "category": ConfigCategory.api_keys,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "Google Gemini API key for OCR services",
                "validation_regex": r"^AIza[0-9A-Za-z-_]{35}$",
            },
            "gemini_model": {
                "category": ConfigCategory.ocr,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "Gemini model to use for OCR",
                "default_value": "gemini-2.0-flash",
                "validation_regex": r"^gemini-[0-9\.]+-[a-z]+$",
            },
            "ocr_timeout": {
                "category": ConfigCategory.ocr,
                "data_type": ConfigDataType.integer,
                "is_sensitive": False,
                "description": "OCR request timeout in seconds",
                "default_value": "30",
                "validation_regex": r"^[1-9]\d*$",
            },
            # Email Settings
            "smtp_host": {
                "category": ConfigCategory.email,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "SMTP server hostname",
                "default_value": "smtp.gmail.com",
            },
            "smtp_port": {
                "category": ConfigCategory.email,
                "data_type": ConfigDataType.integer,
                "is_sensitive": False,
                "description": "SMTP server port",
                "default_value": "587",
                "validation_regex": r"^[1-9]\d{1,4}$",
            },
            "smtp_username": {
                "category": ConfigCategory.email,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "SMTP username for authentication",
            },
            "smtp_password": {
                "category": ConfigCategory.email,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "SMTP password for authentication",
            },
            "smtp_from_email": {
                "category": ConfigCategory.email,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "Default sender email address",
                "validation_regex": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            },
            # File Storage Settings
            "minio_endpoint": {
                "category": ConfigCategory.file_storage,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "MinIO server endpoint",
                "default_value": "localhost:9000",
            },
            "minio_access_key": {
                "category": ConfigCategory.file_storage,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "MinIO access key",
            },
            "minio_secret_key": {
                "category": ConfigCategory.file_storage,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "MinIO secret key",
            },
            "minio_bucket": {
                "category": ConfigCategory.file_storage,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "MinIO bucket name for file storage",
                "default_value": "scholarship-files",
            },
            "max_file_size": {
                "category": ConfigCategory.file_storage,
                "data_type": ConfigDataType.integer,
                "is_sensitive": False,
                "description": "Maximum file size in bytes (10MB default)",
                "default_value": "10485760",
                "validation_regex": r"^[1-9]\d*$",
            },
            # Security Settings
            "cors_origins": {
                "category": ConfigCategory.security,
                "data_type": ConfigDataType.string,
                "is_sensitive": False,
                "description": "Comma-separated list of allowed CORS origins",
                "default_value": "http://localhost:3000",
            },
            "access_token_expire_minutes": {
                "category": ConfigCategory.security,
                "data_type": ConfigDataType.integer,
                "is_sensitive": False,
                "description": "JWT access token expiry time in minutes",
                "default_value": "30",
                "validation_regex": r"^[1-9]\d*$",
            },
            # API Integration Settings
            "nycu_emp_account": {
                "category": ConfigCategory.integrations,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "NYCU Employee API account",
            },
            "nycu_emp_key_hex": {
                "category": ConfigCategory.integrations,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "NYCU Employee API HMAC key in hex format",
            },
            "student_api_account": {
                "category": ConfigCategory.integrations,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "Student API account for data retrieval",
            },
            "student_api_hmac_key": {
                "category": ConfigCategory.integrations,
                "data_type": ConfigDataType.string,
                "is_sensitive": True,
                "description": "Student API HMAC key for authentication",
            },
            # Feature Flags
            "enable_mock_sso": {
                "category": ConfigCategory.features,
                "data_type": ConfigDataType.boolean,
                "is_sensitive": False,
                "description": "Enable mock SSO for development",
                "default_value": "false",
            },
            "portal_sso_enabled": {
                "category": ConfigCategory.features,
                "data_type": ConfigDataType.boolean,
                "is_sensitive": False,
                "description": "Enable Portal SSO authentication",
                "default_value": "true",
            },
            "enable_virus_scan": {
                "category": ConfigCategory.features,
                "data_type": ConfigDataType.boolean,
                "is_sensitive": False,
                "description": "Enable virus scanning for uploaded files",
                "default_value": "false",
            },
        }

    async def initialize_default_configurations(self, user_id: int):
        """Initialize default configurations if they don't exist"""
        predefined = self.get_predefined_configurations()

        for key, config in predefined.items():
            existing = await self.get_configuration(key)
            if not existing and config.get("default_value"):
                await self.set_configuration(
                    key=key,
                    value=config["default_value"],
                    user_id=user_id,
                    category=config["category"],
                    data_type=config["data_type"],
                    is_sensitive=config["is_sensitive"],
                    description=config["description"],
                    validation_regex=config.get("validation_regex"),
                    default_value=config["default_value"],
                    change_reason="System initialization",
                )
