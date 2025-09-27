"""
Tests for Configuration Management System
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.models.system_setting import ConfigCategory, ConfigDataType, SystemSetting
from app.services.config_management_service import ConfigurationService, ConfigEncryption
from app.schemas.config_management import ConfigurationCreateSchema


class TestConfigEncryption:
    """Test encryption/decryption functionality"""

    def test_encrypt_decrypt_cycle(self):
        """Test that we can encrypt and decrypt values correctly"""
        encryption = ConfigEncryption()

        original_value = "test_api_key_12345"
        encrypted = encryption.encrypt_value(original_value)
        decrypted = encryption.decrypt_value(encrypted)

        assert decrypted == original_value
        assert encrypted != original_value
        assert len(encrypted) > len(original_value)

    def test_encrypt_empty_string(self):
        """Test encryption of empty string"""
        encryption = ConfigEncryption()

        original_value = ""
        encrypted = encryption.encrypt_value(original_value)
        decrypted = encryption.decrypt_value(encrypted)

        assert decrypted == original_value

    def test_encrypt_unicode_characters(self):
        """Test encryption of unicode characters"""
        encryption = ConfigEncryption()

        original_value = "测试中文字符和🔑emoji"
        encrypted = encryption.encrypt_value(original_value)
        decrypted = encryption.decrypt_value(encrypted)

        assert decrypted == original_value


class TestConfigurationService:
    """Test Configuration Management Service"""

    @pytest.fixture
    def mock_db(self):
        """Mock database session"""
        return AsyncMock()

    @pytest.fixture
    def config_service(self, mock_db):
        """Create configuration service with mocked database"""
        return ConfigurationService(mock_db)

    @pytest.mark.asyncio
    async def test_get_configuration_existing(self, config_service, mock_db):
        """Test getting an existing configuration"""
        # Mock database response
        mock_setting = SystemSetting(
            id=1,
            key="test_key",
            value="test_value",
            category=ConfigCategory.FEATURES,
            data_type=ConfigDataType.STRING,
            is_sensitive=False
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_db.execute.return_value = mock_result

        result = await config_service.get_configuration("test_key")

        assert result == mock_setting
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_configuration_not_found(self, config_service, mock_db):
        """Test getting a non-existent configuration"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await config_service.get_configuration("nonexistent_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_decrypted_value_non_sensitive(self, config_service):
        """Test getting decrypted value for non-sensitive setting"""
        setting = SystemSetting(
            key="test_key",
            value="test_value",
            data_type=ConfigDataType.STRING,
            is_sensitive=False
        )

        result = await config_service.get_decrypted_value(setting)
        assert result == "test_value"

    @pytest.mark.asyncio
    async def test_get_decrypted_value_boolean(self, config_service):
        """Test getting decrypted value for boolean setting"""
        setting = SystemSetting(
            key="test_bool",
            value="true",
            data_type=ConfigDataType.BOOLEAN,
            is_sensitive=False
        )

        result = await config_service.get_decrypted_value(setting)
        assert result is True

        setting.value = "false"
        result = await config_service.get_decrypted_value(setting)
        assert result is False

    @pytest.mark.asyncio
    async def test_get_decrypted_value_integer(self, config_service):
        """Test getting decrypted value for integer setting"""
        setting = SystemSetting(
            key="test_int",
            value="42",
            data_type=ConfigDataType.INTEGER,
            is_sensitive=False
        )

        result = await config_service.get_decrypted_value(setting)
        assert result == 42

    @pytest.mark.asyncio
    async def test_get_decrypted_value_json(self, config_service):
        """Test getting decrypted value for JSON setting"""
        setting = SystemSetting(
            key="test_json",
            value='{"key": "value", "number": 123}',
            data_type=ConfigDataType.JSON,
            is_sensitive=False
        )

        result = await config_service.get_decrypted_value(setting)
        assert result == {"key": "value", "number": 123}

    @pytest.mark.asyncio
    async def test_set_configuration_new(self, config_service, mock_db):
        """Test creating a new configuration"""
        mock_db.execute.return_value.scalar_one_or_none.return_value = None  # No existing config
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        result = await config_service.set_configuration(
            key="new_key",
            value="new_value",
            user_id=1,
            category=ConfigCategory.API_KEYS,
            data_type=ConfigDataType.STRING,
            is_sensitive=True,
            description="Test configuration"
        )

        mock_db.add.assert_called()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_set_configuration_readonly_error(self, config_service, mock_db):
        """Test that readonly configurations cannot be modified"""
        existing_setting = SystemSetting(
            key="readonly_key",
            value="old_value",
            is_readonly=True
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_setting
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="readonly and cannot be modified"):
            await config_service.set_configuration(
                key="readonly_key",
                value="new_value",
                user_id=1
            )

    @pytest.mark.asyncio
    async def test_validate_configuration_valid_integer(self, config_service):
        """Test validation of valid integer configuration"""
        is_valid, message = await config_service.validate_configuration(
            "test_key", "42", ConfigDataType.INTEGER
        )

        assert is_valid is True
        assert message == "Valid"

    @pytest.mark.asyncio
    async def test_validate_configuration_invalid_integer(self, config_service):
        """Test validation of invalid integer configuration"""
        is_valid, message = await config_service.validate_configuration(
            "test_key", "not_a_number", ConfigDataType.INTEGER
        )

        assert is_valid is False
        assert "Validation error" in message

    @pytest.mark.asyncio
    async def test_validate_configuration_valid_json(self, config_service):
        """Test validation of valid JSON configuration"""
        is_valid, message = await config_service.validate_configuration(
            "test_key", '{"valid": "json"}', ConfigDataType.JSON
        )

        assert is_valid is True
        assert message == "Valid"

    @pytest.mark.asyncio
    async def test_validate_configuration_invalid_json(self, config_service):
        """Test validation of invalid JSON configuration"""
        is_valid, message = await config_service.validate_configuration(
            "test_key", "{invalid json}", ConfigDataType.JSON
        )

        assert is_valid is False
        assert "Validation error" in message

    @pytest.mark.asyncio
    async def test_validate_configuration_boolean(self, config_service):
        """Test validation of boolean configuration"""
        valid_booleans = ["true", "false", "1", "0", "yes", "no", "on", "off"]

        for value in valid_booleans:
            is_valid, message = await config_service.validate_configuration(
                "test_key", value, ConfigDataType.BOOLEAN
            )
            assert is_valid is True, f"Failed for value: {value}"

        # Test invalid boolean
        is_valid, message = await config_service.validate_configuration(
            "test_key", "maybe", ConfigDataType.BOOLEAN
        )
        assert is_valid is False
        assert "Boolean value must be" in message

    def test_get_predefined_configurations(self, config_service):
        """Test that predefined configurations are properly defined"""
        predefined = config_service.get_predefined_configurations()

        # Check that important configurations are defined
        assert "ocr_service_enabled" in predefined
        assert "gemini_api_key" in predefined
        assert "smtp_host" in predefined
        assert "cors_origins" in predefined

        # Check structure of a configuration
        ocr_config = predefined["ocr_service_enabled"]
        assert ocr_config["category"] == ConfigCategory.OCR
        assert ocr_config["data_type"] == ConfigDataType.BOOLEAN
        assert ocr_config["is_sensitive"] is False
        assert "description" in ocr_config

        # Check sensitive configuration
        api_key_config = predefined["gemini_api_key"]
        assert api_key_config["is_sensitive"] is True
        assert api_key_config["category"] == ConfigCategory.API_KEYS
        assert "validation_regex" in api_key_config

    @pytest.mark.asyncio
    async def test_bulk_update_configurations(self, config_service, mock_db):
        """Test bulk update of configurations"""
        # Mock existing configurations
        existing_configs = [
            SystemSetting(key="key1", value="old1", category=ConfigCategory.FEATURES, data_type=ConfigDataType.STRING, is_sensitive=False, is_readonly=False),
            SystemSetting(key="key2", value="old2", category=ConfigCategory.FEATURES, data_type=ConfigDataType.STRING, is_sensitive=False, is_readonly=False)
        ]

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.side_effect = existing_configs
        mock_db.execute.return_value = mock_result
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()
        mock_db.add = MagicMock()

        updates = [
            {"key": "key1", "value": "new1"},
            {"key": "key2", "value": "new2"}
        ]

        result = await config_service.bulk_update_configurations(updates, user_id=1)

        assert len(result) == 2
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_configuration_success(self, config_service, mock_db):
        """Test successful deletion of configuration"""
        existing_setting = SystemSetting(
            key="deletable_key",
            value="some_value",
            is_readonly=False
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_setting
        mock_db.execute.return_value = mock_result
        mock_db.delete = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()  # For audit log

        result = await config_service.delete_configuration("deletable_key", user_id=1)

        assert result is True
        mock_db.delete.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_configuration_readonly_error(self, config_service, mock_db):
        """Test that readonly configurations cannot be deleted"""
        existing_setting = SystemSetting(
            key="readonly_key",
            value="some_value",
            is_readonly=True
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_setting
        mock_db.execute.return_value = mock_result

        with pytest.raises(ValueError, match="readonly and cannot be deleted"):
            await config_service.delete_configuration("readonly_key", user_id=1)

    @pytest.mark.asyncio
    async def test_delete_configuration_not_found(self, config_service, mock_db):
        """Test deletion of non-existent configuration"""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        result = await config_service.delete_configuration("nonexistent_key", user_id=1)

        assert result is False