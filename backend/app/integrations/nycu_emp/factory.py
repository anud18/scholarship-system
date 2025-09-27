"""
Factory for creating NYCU Employee API clients based on environment configuration.
"""

import os
from typing import Optional

from .client_base import NYCUEmpClientBase
from .client_http import NYCUEmpHttpClient
from .client_mock import NYCUEmpMockClient


def create_nycu_emp_client(
    mode: Optional[str] = None,
    account: Optional[str] = None,
    key_hex: Optional[str] = None,
    key_raw: Optional[str] = None,
    endpoint: Optional[str] = None,
    insecure: bool = False,
    timeout: float = 10.0,
    retries: int = 3,
) -> NYCUEmpClientBase:
    """
    Create NYCU Employee API client based on environment configuration.

    Args:
        mode: Client mode ("mock", "http"). Defaults to NYCU_EMP_MODE env var
        account: API account name (required for HTTP mode)
        key_hex: HMAC key in hex format (for HTTP mode)
        key_raw: HMAC key in raw string format (for HTTP mode)
        endpoint: API endpoint URL (required for HTTP mode)
        insecure: Whether to skip SSL verification (for HTTP mode)
        timeout: Request timeout in seconds (for HTTP mode)
        retries: Number of retry attempts (for HTTP mode)

    Returns:
        NYCUEmpClientBase: Configured client instance

    Raises:
        ValueError: When required parameters are missing or invalid mode is specified
    """
    # Get mode from parameter or environment
    client_mode = mode or os.getenv("NYCU_EMP_MODE", "mock")

    if client_mode and client_mode.lower() == "mock":
        return NYCUEmpMockClient()

    elif client_mode and client_mode.lower() == "http":
        # Validate required parameters for HTTP client
        if not account:
            raise ValueError("account is required for HTTP client mode")

        if not endpoint:
            raise ValueError("endpoint is required for HTTP client mode")

        if not key_hex and not key_raw:
            raise ValueError("Either key_hex or key_raw is required for HTTP client mode")

        return NYCUEmpHttpClient(
            account=account,
            key_hex=key_hex,
            key_raw=key_raw,
            endpoint=endpoint,
            insecure=insecure,
            timeout=timeout,
            retries=retries,
        )

    else:
        raise ValueError(f"Invalid NYCU_EMP_MODE: {client_mode}. Must be 'mock' or 'http'")


def create_nycu_emp_client_from_env() -> NYCUEmpClientBase:
    """
    Create NYCU Employee API client using environment variables.

    Environment Variables:
        NYCU_EMP_MODE: Client mode ("mock" or "http")
        NYCU_EMP_ACCOUNT: API account name (for HTTP mode)
        NYCU_EMP_KEY_HEX: HMAC key in hex format (for HTTP mode)
        NYCU_EMP_KEY_RAW: HMAC key in raw format (for HTTP mode, fallback)
        NYCU_EMP_ENDPOINT: API endpoint URL (for HTTP mode)
        NYCU_EMP_INSECURE: Skip SSL verification ("true"/"false", for HTTP mode)
        NYCU_EMP_TIMEOUT: Request timeout in seconds (for HTTP mode)
        NYCU_EMP_RETRIES: Number of retry attempts (for HTTP mode)

    Returns:
        NYCUEmpClientBase: Configured client instance

    Raises:
        ValueError: When required environment variables are missing
    """
    return create_nycu_emp_client(
        mode=os.getenv("NYCU_EMP_MODE"),
        account=os.getenv("NYCU_EMP_ACCOUNT"),
        key_hex=os.getenv("NYCU_EMP_KEY_HEX"),
        key_raw=os.getenv("NYCU_EMP_KEY_RAW"),
        endpoint=os.getenv("NYCU_EMP_ENDPOINT"),
        insecure=os.getenv("NYCU_EMP_INSECURE", "false").lower() == "true",
        timeout=float(os.getenv("NYCU_EMP_TIMEOUT", "10.0")),
        retries=int(os.getenv("NYCU_EMP_RETRIES", "3")),
    )
