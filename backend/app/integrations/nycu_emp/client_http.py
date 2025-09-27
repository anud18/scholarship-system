"""
HTTP client for NYCU Employee API with HMAC-SHA256 authentication.
"""

import hashlib
import hmac
import json
import logging
import zoneinfo
from datetime import datetime
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .client_base import NYCUEmpClientBase
from .exceptions import (
    NYCUEmpAuthenticationError,
    NYCUEmpConnectionError,
    NYCUEmpError,
    NYCUEmpTimeoutError,
    NYCUEmpValidationError,
)
from .models import NYCUEmpPage

logger = logging.getLogger(__name__)


class NYCUEmpHttpClient(NYCUEmpClientBase):
    """HTTP client for NYCU Employee API with HMAC authentication."""

    def __init__(
        self,
        account: str,
        key_hex: Optional[str] = None,
        key_raw: Optional[str] = None,
        endpoint: str = "",
        insecure: bool = False,
        timeout: float = 10.0,
        retries: int = 3,
    ):
        """
        Initialize HTTP client.

        Args:
            account: API account name
            key_hex: HMAC key in hex format (preferred)
            key_raw: HMAC key in raw string format (fallback)
            endpoint: API endpoint URL
            insecure: Whether to skip SSL verification
            timeout: Request timeout in seconds
            retries: Number of retry attempts
        """
        self.account = account
        self.endpoint = endpoint
        self.timeout = timeout
        self.retries = retries

        # Initialize HMAC key
        if key_hex:
            self.hmac_key = bytes.fromhex(key_hex)
        elif key_raw:
            self.hmac_key = key_raw.encode("utf-8")
        else:
            raise ValueError("Either key_hex or key_raw must be provided")

        # Configure HTTP client
        verify = not insecure
        self.client = httpx.AsyncClient(timeout=timeout, verify=verify)

        logger.info(f"NYCUEmpHttpClient initialized: account={account}, endpoint={endpoint}")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.client.aclose()

    def _get_taipei_time(self) -> str:
        """Get current time in Asia/Taipei timezone formatted as YYYYMMDDHHMMSS."""
        taipei_tz = zoneinfo.ZoneInfo("Asia/Taipei")
        now = datetime.now(taipei_tz)
        return now.strftime("%Y%m%d%H%M%S")

    def _generate_hmac_signature(self, exe_time: str, body: str) -> str:
        """
        Generate HMAC-SHA256 signature.

        Args:
            exe_time: Execution time (YYYYMMDDHHMMSS)
            body: Request body as compact JSON string

        Returns:
            HMAC signature as lowercase hex string
        """
        # Message = EXE_TIME + REQUEST_BODY
        message = exe_time + body
        signature = hmac.new(self.hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest().lower()

        logger.debug(f"Generated HMAC signature for message length: {len(message)}")
        return signature

    def _create_request_body(self, page_row: str, status: str) -> str:
        """
        Create compact JSON request body.

        Args:
            page_row: Page number as string
            status: Employee status as string

        Returns:
            Compact JSON string (no spaces)
        """
        request_data = {"page_row": str(page_row), "status": str(status)}
        # Generate compact JSON with no spaces
        return json.dumps(request_data, separators=(",", ":"), ensure_ascii=False)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry_error_callback=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number} for NYCU Employee API failed"
        ),
    )
    async def get_employee_page(self, page_row: str = "1", status: str = "01") -> NYCUEmpPage:
        """
        Get employee data page from NYCU API.

        Args:
            page_row: Page number as string
            status: Employee status as string

        Returns:
            NYCUEmpPage: Employee data with pagination info

        Raises:
            NYCUEmpError: Various API errors
        """
        try:
            # Generate timestamp and request body
            exe_time = self._get_taipei_time()
            body = self._create_request_body(page_row, status)

            # Generate HMAC signature
            signature = self._generate_hmac_signature(exe_time, body)

            # Create headers
            headers = {
                "Authorization": f"NYCU-HMAC-SHA256 {self.account}:{signature}",
                "Content-Type": "application/json;charset=UTF-8",
                "EXE_TIME": exe_time,
                "Accept": "application/json",
            }

            logger.info(f"Making request to {self.endpoint} with page_row={page_row}, status={status}")

            # Make HTTP request
            response = await self.client.post(self.endpoint, content=body, headers=headers)

            # Handle response
            if response.status_code == 200:
                response_data = response.json()
                return NYCUEmpPage(**response_data)

            elif response.status_code == 401:
                raise NYCUEmpAuthenticationError(f"Authentication failed: {response.text}")

            elif response.status_code == 400:
                raise NYCUEmpValidationError(f"Request validation failed: {response.text}")

            else:
                raise NYCUEmpError(
                    f"API request failed with status {response.status_code}: {response.text}",
                    http_status=response.status_code,
                )

        except httpx.TimeoutException as e:
            logger.error(f"Request timeout: {e}")
            raise NYCUEmpTimeoutError(f"Request timed out after {self.timeout}s")

        except httpx.ConnectError as e:
            logger.error(f"Connection error: {e}")
            raise NYCUEmpConnectionError(f"Failed to connect to {self.endpoint}")

        except Exception as e:
            if isinstance(e, NYCUEmpError):
                raise
            logger.error(f"Unexpected error: {e}")
            raise NYCUEmpError(f"Unexpected error: {str(e)}")
