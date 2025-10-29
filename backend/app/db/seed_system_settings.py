"""
System Settings Seed Data
Initialize system settings from environment variables
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.system_setting import ConfigCategory, ConfigDataType
from app.services.config_management_service import ConfigurationService


async def seed_system_settings(db: AsyncSession, system_user_id: int = 1):
    """
    Initialize system settings from environment variables.

    This creates default settings in the database that can be modified via the admin interface.
    Only dynamic configurations are seeded - static configs remain in environment variables only.

    Args:
        db: Database session
        system_user_id: User ID for audit trail (default: 1 for system)
    """
    config_service = ConfigurationService(db)

    # Define all dynamic settings to seed
    settings_to_seed = [
        # Email/SMTP Settings
        {
            "key": "smtp_host",
            "value": settings.smtp_host,
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.string,
            "description": "SMTP 伺服器位址",
            "is_sensitive": False,
        },
        {
            "key": "smtp_port",
            "value": str(settings.smtp_port),
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.integer,
            "description": "SMTP 伺服器連接埠",
            "is_sensitive": False,
        },
        {
            "key": "smtp_user",
            "value": settings.smtp_user,
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.string,
            "description": "SMTP 使用者名稱",
            "is_sensitive": True,
        },
        {
            "key": "smtp_password",
            "value": settings.smtp_password,
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.string,
            "description": "SMTP 密碼",
            "is_sensitive": True,
        },
        {
            "key": "smtp_use_tls",
            "value": str(settings.smtp_use_tls).lower(),
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.boolean,
            "description": "啟用 SMTP TLS/STARTTLS 加密（預設：關閉，適用於 Port 25 純 SMTP）",
            "is_sensitive": False,
        },
        {
            "key": "email_from",
            "value": settings.email_from,
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.string,
            "description": "寄件者電子郵件地址",
            "is_sensitive": False,
        },
        {
            "key": "email_from_name",
            "value": settings.email_from_name,
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.string,
            "description": "寄件者顯示名稱",
            "is_sensitive": False,
        },
        {
            "key": "email_processor_interval_seconds",
            "value": "60",
            "category": ConfigCategory.email,
            "data_type": ConfigDataType.integer,
            "description": "郵件處理器執行間隔（秒）- 控制自動發送郵件的檢查頻率",
            "is_sensitive": False,
        },
        # OCR/Gemini API Settings
        {
            "key": "ocr_service_enabled",
            "value": str(settings.ocr_service_enabled).lower(),
            "category": ConfigCategory.ocr,
            "data_type": ConfigDataType.boolean,
            "description": "啟用 OCR 服務",
            "is_sensitive": False,
        },
        {
            "key": "gemini_api_key",
            "value": settings.gemini_api_key or "",
            "category": ConfigCategory.api_keys,
            "data_type": ConfigDataType.string,
            "description": "Google Gemini API 金鑰",
            "is_sensitive": True,
        },
        {
            "key": "gemini_model",
            "value": settings.gemini_model,
            "category": ConfigCategory.ocr,
            "data_type": ConfigDataType.string,
            "description": "Gemini 模型名稱",
            "is_sensitive": False,
        },
        {
            "key": "ocr_timeout",
            "value": str(settings.ocr_timeout),
            "category": ConfigCategory.ocr,
            "data_type": ConfigDataType.integer,
            "description": "OCR 請求逾時時間（秒）",
            "is_sensitive": False,
        },
        # File Upload Settings
        {
            "key": "max_file_size",
            "value": str(settings.max_file_size),
            "category": ConfigCategory.file_storage,
            "data_type": ConfigDataType.integer,
            "description": "最大檔案大小（位元組）",
            "is_sensitive": False,
        },
        {
            "key": "allowed_file_types",
            "value": settings.allowed_file_types,
            "category": ConfigCategory.file_storage,
            "data_type": ConfigDataType.string,
            "description": "允許的檔案類型（逗號分隔）",
            "is_sensitive": False,
        },
        {
            "key": "max_files_per_application",
            "value": str(settings.max_files_per_application),
            "category": ConfigCategory.file_storage,
            "data_type": ConfigDataType.integer,
            "description": "每個申請可上傳的最大檔案數",
            "is_sensitive": False,
        },
        {
            "key": "max_document_image_width",
            "value": str(settings.max_document_image_width),
            "category": ConfigCategory.file_storage,
            "data_type": ConfigDataType.integer,
            "description": "文件圖片最大寬度（像素）",
            "is_sensitive": False,
        },
        {
            "key": "max_document_image_height",
            "value": str(settings.max_document_image_height),
            "category": ConfigCategory.file_storage,
            "data_type": ConfigDataType.integer,
            "description": "文件圖片最大高度（像素）",
            "is_sensitive": False,
        },
        # Cache Settings
        {
            "key": "cache_ttl",
            "value": str(settings.cache_ttl),
            "category": ConfigCategory.performance,
            "data_type": ConfigDataType.integer,
            "description": "快取存活時間（秒）",
            "is_sensitive": False,
        },
        # Token Expiry Settings
        {
            "key": "access_token_expire_minutes",
            "value": str(settings.access_token_expire_minutes),
            "category": ConfigCategory.security,
            "data_type": ConfigDataType.integer,
            "description": "存取權杖過期時間（分鐘）",
            "is_sensitive": False,
        },
        {
            "key": "refresh_token_expire_days",
            "value": str(settings.refresh_token_expire_days),
            "category": ConfigCategory.security,
            "data_type": ConfigDataType.integer,
            "description": "重新整理權杖過期時間（天）",
            "is_sensitive": False,
        },
    ]

    # Create or update each setting
    created_count = 0
    skipped_count = 0

    for setting_data in settings_to_seed:
        try:
            # Check if setting already exists
            existing = await config_service.get_configuration(setting_data["key"])

            if existing:
                # Skip if already exists (don't overwrite user modifications)
                skipped_count += 1
                # SECURITY: Only log key name, not value
                print(f"  ⊘ Skipped existing setting: {setting_data['key']}")
                continue

            # Create new setting
            await config_service.set_configuration(
                key=setting_data["key"],
                value=setting_data["value"],
                category=setting_data["category"],
                data_type=setting_data["data_type"],
                description=setting_data["description"],
                is_sensitive=setting_data["is_sensitive"],
                user_id=system_user_id,
                change_reason="Initial system setup",
            )
            created_count += 1
            # SECURITY: Only log key name, not value
            print(f"  ✓ Created setting: {setting_data['key']}")

        except Exception:
            # SECURITY: Don't log exception details which might contain sensitive values
            print(f"  ✗ Failed to seed setting '{setting_data['key']}'")
            continue

    print("\n✓ System settings seed completed:")
    print(f"  - Created: {created_count}")
    print(f"  - Skipped (existing): {skipped_count}")
    print(f"  - Total: {len(settings_to_seed)}")
