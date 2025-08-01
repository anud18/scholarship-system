"""
Application configuration module.
Handles all environment variables and application settings.
"""

import os
from typing import List, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings
from decouple import config


class Settings(BaseSettings):
    """Application settings configuration"""
    
    # Application
    app_name: str = config("APP_NAME", default="Scholarship Management System")
    app_version: str = config("APP_VERSION", default="1.0.0")
    debug: bool = config("DEBUG", default=False, cast=bool)
    environment: str = config("ENVIRONMENT", default="production")
    api_v1_str: str = config("API_V1_STR", default="/api/v1")
    
    # Server
    host: str = config("HOST", default="0.0.0.0")
    port: int = config("PORT", default=8000, cast=int)
    reload: bool = config("RELOAD", default=False, cast=bool)
    
    # Database
    database_url: str = config("DATABASE_URL", default="postgresql+asyncpg://postgres:postgres@localhost:5432/scholarship_test")
    database_url_sync: str = config("DATABASE_URL_SYNC", default="postgresql://postgres:postgres@localhost:5432/scholarship_test")
    
    # Security
    secret_key: str = config("SECRET_KEY", default="test-secret-key-for-development-only-please-change-in-production-this-is-32-chars")
    algorithm: str = config("ALGORITHM", default="HS256")
    access_token_expire_minutes: int = config("ACCESS_TOKEN_EXPIRE_MINUTES", default=30, cast=int)
    refresh_token_expire_days: int = config("REFRESH_TOKEN_EXPIRE_DAYS", default=7, cast=int)
    
    # CORS
    cors_origins: List[str] = config("CORS_ORIGINS", default="http://localhost:3000", cast=lambda v: [s.strip() for s in v.split(',')])
    
    # Email
    smtp_host: str = config("SMTP_HOST", default="smtp.gmail.com")
    smtp_port: int = config("SMTP_PORT", default=587, cast=int)
    smtp_user: str = config("SMTP_USER", default="")
    smtp_password: str = config("SMTP_PASSWORD", default="")
    email_from: str = config("EMAIL_FROM", default="noreply@scholarshipapp.com")
    email_from_name: str = config("EMAIL_FROM_NAME", default="Scholarship System")
    
    # File Upload
    upload_dir: str = config("UPLOAD_DIR", default="./uploads")
    max_file_size: int = config("MAX_FILE_SIZE", default=10485760, cast=int)  # 10MB
    allowed_file_types: List[str] = config("ALLOWED_FILE_TYPES", default="pdf,jpg,jpeg,png,doc,docx", cast=lambda v: [s.strip() for s in v.split(',')])
    max_files_per_application: int = config("MAX_FILES_PER_APPLICATION", default=5, cast=int)
    
    # MinIO Configuration
    minio_endpoint: str = config("MINIO_ENDPOINT", default="localhost:9000")
    minio_access_key: str = config("MINIO_ACCESS_KEY", default="minioadmin")
    minio_secret_key: str = config("MINIO_SECRET_KEY", default="minioadmin123")
    minio_bucket: str = config("MINIO_BUCKET_NAME", default="scholarship-files")
    minio_secure: bool = config("MINIO_SECURE", default=False, cast=bool)
    
    # OCR Service
    ocr_service_enabled: bool = config("OCR_SERVICE_ENABLED", default=False, cast=bool)
    ocr_api_key: Optional[str] = config("OCR_API_KEY", default=None)
    ocr_endpoint: Optional[str] = config("OCR_ENDPOINT", default=None)
    
    # Redis Cache
    redis_url: str = config("REDIS_URL", default="redis://localhost:6379/0")
    cache_ttl: int = config("CACHE_TTL", default=600, cast=int)  # 10 minutes
    
    # Logging
    log_level: str = config("LOG_LEVEL", default="INFO")
    log_format: str = config("LOG_FORMAT", default="json")
    sqlalchemy_log_level: str = config("SQLALCHEMY_LOG_LEVEL", default="WARNING")  # 簡化 SQLAlchemy 日誌
    
    # Mock SSO for development
    enable_mock_sso: bool = config("ENABLE_MOCK_SSO", default=True, cast=bool)
    mock_sso_domain: str = config("MOCK_SSO_DOMAIN", default="dev.university.edu")
    
    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        """Validate database URL format"""
        # Allow SQLite URLs in test/CI environments
        if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI") or os.getenv("TESTING"):
            if v.startswith(("sqlite", "postgresql")):
                return v
        
        if not v.startswith("postgresql"):
            raise ValueError("Database URL must be PostgreSQL")
        return v
    
    @field_validator("secret_key", mode="before")
    @classmethod
    def validate_secret_key(cls, v: str) -> str:
        """Validate secret key is not empty and has minimum length"""
        if not v:
            raise ValueError("SECRET_KEY cannot be empty")
        if len(v) < 32:
            # For testing environments, just warn but don't fail
            import os
            if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI"):
                pass  # Allow shorter keys in test environments
            else:
                raise ValueError("SECRET_KEY must be at least 32 characters long")
        return v
    
    @field_validator("upload_dir", mode="before")
    @classmethod
    def create_upload_directory(cls, v: str) -> str:
        """Ensure upload directory exists"""
        os.makedirs(v, exist_ok=True)
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()

# Application constants
MAX_PERSONAL_STATEMENT_LENGTH = 2000
MIN_PASSWORD_LENGTH = 8
MAX_USERNAME_LENGTH = 50
MAX_EMAIL_LENGTH = 255

# File type mappings
MIME_TYPE_MAPPING = {
    "pdf": "application/pdf",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg", 
    "png": "image/png",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}

# Development scholarship settings
DEV_SCHOLARSHIP_SETTINGS = {
    "ALWAYS_OPEN_APPLICATION": True,
    "BYPASS_WHITELIST": True,
    "MOCK_APPLICATION_PERIOD": True,
}
