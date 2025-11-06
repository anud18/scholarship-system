"""
Application configuration module.
Handles all environment variables and application settings.
"""

import os
from typing import List, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings configuration"""

    # Application
    app_name: str = "Scholarship Management System"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "production"
    api_v1_str: str = "/api/v1"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False
    base_url: str = "http://localhost:8000"  # Base URL for the application
    frontend_url: str = "http://localhost:3000"  # Frontend URL for the application (external/user-facing)
    frontend_internal_url: str = "http://frontend:3000"  # Frontend URL for backend API calls (internal Docker network)

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/scholarship_test"
    database_url_sync: str = "postgresql://postgres:postgres@localhost:5432/scholarship_test"

    # Security
    secret_key: str  # Required: Must be set via SECRET_KEY environment variable
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # CORS
    cors_origins: str = "http://localhost:3000,http://140.113.207.40:3000,http://140.113.0.229:3000"

    # Email Configuration
    # Note: SMTP credentials are loaded from environment variables via Pydantic Settings
    # Empty defaults allow no-auth SMTP (e.g., port 25 internal relay)
    # Production systems should set SMTP_PASSWORD in environment if auth is required
    smtp_host: str = "140.113.7.200"
    smtp_port: int = 25
    smtp_user: str = ""
    smtp_password: str = ""  # Empty default is valid for no-auth SMTP
    smtp_use_tls: bool = False  # STARTTLS/TLS encryption (default: False for plain SMTP)
    email_from: str = "ss-test.aa@nycu.edu.tw"
    email_from_name: str = "(測試)獎學金申請與簽核系統"

    # File Upload
    upload_dir: str = "./uploads"
    max_file_size: int = 10485760  # 10MB
    allowed_file_types: str = "pdf,jpg,jpeg,png,doc,docx"
    max_files_per_application: int = 5
    max_document_image_width: int = 1200
    max_document_image_height: int = 1200

    # Virus Scanning
    enable_virus_scan: bool = False
    virus_scan_api_url: Optional[str] = None
    virus_scan_api_key: Optional[str] = None
    virus_scan_timeout: int = 30  # seconds

    # MinIO Configuration
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str  # Required: Must be set via MINIO_ACCESS_KEY environment variable
    minio_secret_key: str  # Required: Must be set via MINIO_SECRET_KEY environment variable
    minio_bucket: str = "scholarship-files"
    minio_secure: bool = False

    # OCR Service (Gemini API)
    ocr_service_enabled: bool = False
    gemini_api_key: Optional[str] = None
    gemini_model: str = "gemini-2.0-flash"  # Best model for OCR tasks
    ocr_timeout: int = 30  # seconds
    gemini_query_delay: float = 5.0  # Delay between API queries to avoid rate limit

    # Redis Cache
    redis_url: str = "redis://localhost:6379/0"

    # Scheduler Control
    enable_scheduler: bool = True  # Default: enabled for production
    cache_ttl: int = 600  # 10 minutes

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"
    sqlalchemy_log_level: str = "WARNING"  # 簡化 SQLAlchemy 日誌

    # Prometheus Metrics
    enable_metrics: bool = True  # Enable/disable Prometheus metrics collection
    metrics_include_endpoint_labels: bool = True  # Include detailed endpoint labels
    metrics_include_business_metrics: bool = True  # Include business-specific metrics

    # Mock SSO for development
    enable_mock_sso: bool = True
    mock_sso_domain: str = "dev.university.edu"

    # Portal SSO Configuration
    portal_sso_enabled: bool = True
    portal_jwt_server_url: str = "https://portal.test.nycu.edu.tw/jwt/portal"
    portal_test_mode: bool = False  # Set to True for testing with mock data
    portal_sso_timeout: float = 10.0  # Timeout for Portal JWT verification

    # Super Admin Configuration
    super_admin_nycu_id: str = "super_admin"  # NYCU ID that should be granted super_admin role

    # Security configurations
    bypass_time_restrictions: bool = False  # Only True in testing environments

    # Student API Configuration
    student_api_enabled: bool = True
    student_api_base_url: str = "http://localhost:8080"  # Mock API in development
    student_api_account: str = "scholarship"
    student_api_hmac_key: str = (
        "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"  # Mock key for development
    )
    student_api_timeout: float = 10.0
    student_api_encode_type: Optional[str] = "UTF-8"

    # Payment Roster Configuration
    roster_template_dir: str = "./app/templates"
    roster_export_dir: str = "./exports"
    roster_excel_template: str = "STD_UP_MIXLISTA.xlsx"
    roster_retention_days: int = 90  # 造冊檔案保留天數
    roster_minio_bucket: str = "roster-files"  # MinIO bucket for roster files

    # Excel Export Configuration
    excel_max_rows: int = 10000  # 單檔最大筆數
    excel_encoding: str = "utf-8-sig"  # UTF-8 with BOM
    excel_auto_width: bool = True  # 自動調整欄寬

    # Student Verification Enhanced Configuration
    student_verify_timeout: int = 5  # API逾時秒數
    student_verify_retry_count: int = 3  # 重試次數
    student_verify_batch_size: int = 50  # 批次驗證大小

    # Roster Processing Configuration
    roster_scheduler_enabled: bool = True
    roster_scheduler_timezone: str = "Asia/Taipei"
    roster_auto_lock_after_completion: bool = False
    roster_max_execution_time_minutes: int = 60

    # Student Verification Configuration
    student_verification_api_url: Optional[str] = None
    student_verification_api_key: Optional[str] = None
    student_verification_mock_mode: bool = True
    # NYCU Employee API Configuration
    nycu_emp_mode: str = "mock"  # "mock" or "http"
    nycu_emp_account: Optional[str] = None
    nycu_emp_key_hex: Optional[str] = None
    nycu_emp_key_raw: Optional[str] = None
    nycu_emp_endpoint: Optional[str] = None
    nycu_emp_insecure: bool = False
    nycu_emp_timeout: float = 10.0
    nycu_emp_retries: int = 3

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

    @field_validator("bypass_time_restrictions", mode="before")
    @classmethod
    def validate_time_restrictions_bypass(cls, v) -> bool:
        """Only allow bypassing time restrictions in test environments"""
        import os

        # Convert string to boolean properly
        if isinstance(v, str):
            v = v.lower() in ("true", "1", "yes", "on")

        if v and not (os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI") or os.getenv("TESTING") == "true"):
            raise ValueError("Time restrictions bypass only allowed in test environments")
        return bool(v)

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v) -> str:
        """Keep CORS origins as string for now"""
        if isinstance(v, list):
            return ",".join(v)
        return str(v) if v else "http://localhost:3000"

    @field_validator("allowed_file_types", mode="before")
    @classmethod
    def parse_allowed_file_types(cls, v) -> str:
        """Keep allowed file types as string for now"""
        if isinstance(v, list):
            return ",".join(v)
        return str(v) if v else "pdf,jpg,jpeg,png,doc,docx"

    @field_validator("upload_dir", mode="before")
    @classmethod
    def create_upload_directory(cls, v: str) -> str:
        """Ensure upload directory exists"""
        os.makedirs(v, exist_ok=True)
        return v

    @property
    def should_start_scheduler(self) -> bool:
        """
        Determine if scheduler should start based on context.

        Scheduler is disabled in the following cases:
        - Running pytest tests (PYTEST_CURRENT_TEST env var)
        - Running Alembic migrations (sys.argv contains 'alembic')
        - Explicitly disabled via ENABLE_SCHEDULER env var
        """
        import sys

        # Check if running in pytest
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False

        # Check if explicitly disabled
        if not self.enable_scheduler:
            return False

        # Check if running Alembic migrations
        if "alembic" in sys.argv:
            return False

        return True

    @field_validator("roster_template_dir", mode="before")
    @classmethod
    def create_roster_template_directory(cls, v: str) -> str:
        """Ensure roster template directory exists"""
        os.makedirs(v, exist_ok=True)
        return v

    @field_validator("roster_export_dir", mode="before")
    @classmethod
    def create_roster_export_directory(cls, v: str) -> str:
        """Ensure roster export directory exists"""
        os.makedirs(v, exist_ok=True)
        return v

    @property
    def cors_origins_list(self) -> List[str]:
        """Get CORS origins as a list"""
        return [s.strip() for s in self.cors_origins.split(",") if s.strip()]

    @property
    def allowed_file_types_list(self) -> List[str]:
        """Get allowed file types as a list"""
        return [s.strip() for s in self.allowed_file_types.split(",") if s.strip()]

    @property
    def testing(self) -> bool:
        """Check if we're in a testing environment"""
        return bool(os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI") or os.getenv("TESTING"))

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
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}

# Development scholarship settings
DEV_SCHOLARSHIP_SETTINGS = {
    "ALWAYS_OPEN_APPLICATION": False,  # Respect real application periods
    "BYPASS_WHITELIST": False,  # Enforce whitelist checks
    "MOCK_APPLICATION_PERIOD": False,
}
