"""
Custom exceptions for NYCU Employee API integration.
"""

from typing import Optional


class NYCUEmpError(Exception):
    """Base exception for NYCU Employee API errors."""

    def __init__(self, message: str, status: Optional[str] = None, http_status: Optional[int] = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.http_status = http_status

    def __str__(self):
        return f"NYCUEmpError: {self.message} (status={self.status}, http_status={self.http_status})"


class NYCUEmpConnectionError(NYCUEmpError):
    """Exception raised when connection to NYCU Employee API fails."""

    def __init__(self, message: str = "Failed to connect to NYCU Employee API"):
        super().__init__(message)


class NYCUEmpAuthenticationError(NYCUEmpError):
    """Exception raised when authentication with NYCU Employee API fails."""

    def __init__(self, message: str = "Authentication failed with NYCU Employee API"):
        super().__init__(message, http_status=401)


class NYCUEmpTimeoutError(NYCUEmpError):
    """Exception raised when NYCU Employee API request times out."""

    def __init__(self, message: str = "Request to NYCU Employee API timed out"):
        super().__init__(message)


class NYCUEmpValidationError(NYCUEmpError):
    """Exception raised when request validation fails."""

    def __init__(self, message: str = "Request validation failed"):
        super().__init__(message, http_status=400)
