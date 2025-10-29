"""
NYCU Employee API Integration.

Three-environment integration (DEV/STAGING/PROD) with environment-aware client switching.
- DEV: Uses mock client for local development
- STAGING: Uses HTTP client with test credentials
- PRODUCTION: Uses HTTP client with production credentials
"""

from .exceptions import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
)
from .factory import create_nycu_emp_client, create_nycu_emp_client_from_env
from .models import NYCUEmpItem, NYCUEmpPage

__all__ = [
    "create_nycu_emp_client",
    "create_nycu_emp_client_from_env",
    "NYCUEmpItem",
    "NYCUEmpPage",
    "NYCUEmpError",
    "NYCUEmpConnectionError",
    "NYCUEmpAuthenticationError",
    "NYCUEmpTimeoutError",
    "NYCUEmpValidationError",
]
