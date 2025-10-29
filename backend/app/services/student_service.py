"""
Student service that handles student data from external API.
Supports both mock API (development) and production student information system.
"""

import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import httpx

from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError

logger = logging.getLogger(__name__)


class StudentService:
    """Service for accessing student data from external API"""

    def __init__(self):
        # Get API configuration from settings
        self.api_base_url = getattr(settings, "student_api_base_url", None)
        self.api_account = getattr(settings, "student_api_account", None)
        self.hmac_key_hex = getattr(settings, "student_api_hmac_key", None)
        self.api_timeout = getattr(settings, "student_api_timeout", 10.0)
        self.api_enabled = getattr(settings, "student_api_enabled", False)

        # Validate configuration
        if self.api_enabled and not all([self.api_base_url, self.api_account, self.hmac_key_hex]):
            logger.warning(
                "Student API is enabled but not properly configured. "
                "Please set STUDENT_API_BASE_URL, STUDENT_API_ACCOUNT, and STUDENT_API_HMAC_KEY"
            )
            self.api_enabled = False

        if self.api_enabled and self.hmac_key_hex:
            try:
                self.hmac_key = bytes.fromhex(self.hmac_key_hex)
            except ValueError:
                logger.error("Invalid STUDENT_API_HMAC_KEY format. Must be a valid hex string.")
                self.api_enabled = False

    def _generate_hmac_auth_header(self, request_body: str) -> str:
        """Generate HMAC-SHA256 authorization header"""
        time_str = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        message = time_str + request_body
        signature = hmac.new(self.hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest().lower()

        return f"HMAC-SHA256:{time_str}:{self.api_account}:{signature}"

    async def get_student_basic_info(self, student_code: str) -> Optional[Dict[str, Any]]:
        """
        Get student basic information from external API

        Args:
            student_code: Student ID code (e.g., 'stu_under', 'stu_phd')

        Returns:
            Student data dictionary or None if not found
        """
        if not self.api_enabled:
            logger.warning("Student API is not enabled. Returning None.")
            return None

        try:
            request_data = {
                "account": self.api_account,
                "action": "qrySoaaScholarshipStudent",
                "stdcode": student_code,
            }

            request_body = json.dumps(request_data, separators=(",", ":"))
            auth_header = self._generate_hmac_auth_header(request_body)

            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json;charset=UTF-8",
            }

            if hasattr(settings, "student_api_encode_type"):
                headers["ENCODE_TYPE"] = settings.student_api_encode_type

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/ScholarshipStudent",
                    headers=headers,
                    content=request_body,
                    timeout=self.api_timeout,
                )

                if response.status_code == 200:
                    result = response.json()
                    # API returns code as string, need to check both string and int
                    code = result.get("code")
                    if (code == 200 or code == "200") and result.get("data"):
                        return result["data"][0]  # Return first student record
                    elif code == 404 or code == "404":
                        logger.info(f"Student {student_code} not found in API")
                        return None
                    else:
                        logger.warning(
                            f"Student API returned unexpected response - "
                            f"code: {result.get('code')} (type: {type(code).__name__}), "
                            f"msg: {result.get('msg')}, student_code: {student_code}"
                        )
                        return None
                else:
                    logger.error(f"Student API request failed: {response.status_code}")
                    raise ServiceUnavailableError("Student API is unavailable")

        except httpx.TimeoutException:
            logger.error(f"Student API request timed out for {student_code}")
            raise ServiceUnavailableError("Student API request timed out")
        except httpx.RequestError as e:
            logger.error(f"Student API request error: {str(e)}")
            raise ServiceUnavailableError(f"Student API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching student data for {student_code}: {str(e)}")
            raise ServiceUnavailableError(f"Failed to fetch student data: {str(e)}")

    async def get_student_term_info(self, student_code: str, academic_year: str, term: str) -> Optional[Dict[str, Any]]:
        """
        Get student term information from external API

        Args:
            student_code: Student ID code
            academic_year: Academic year (e.g., '113')
            term: Term (e.g., '1', '2')

        Returns:
            Term data dictionary or None if not found
        """
        if not self.api_enabled:
            logger.warning("Student API is not enabled. Returning None.")
            return None

        try:
            request_data = {
                "account": self.api_account,
                "action": "qrySoaaScholarshipStudent",
                "stdcode": student_code,
                "trmyear": academic_year,
                "trmterm": term,
            }

            request_body = json.dumps(request_data, separators=(",", ":"))
            auth_header = self._generate_hmac_auth_header(request_body)

            headers = {
                "Authorization": auth_header,
                "Content-Type": "application/json;charset=UTF-8",
            }

            if hasattr(settings, "student_api_encode_type"):
                headers["ENCODE_TYPE"] = settings.student_api_encode_type

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_base_url}/ScholarshipStudentTerm",
                    headers=headers,
                    content=request_body,
                    timeout=self.api_timeout,
                )

                if response.status_code == 200:
                    result = response.json()
                    # API returns code as string, need to check both string and int
                    code = result.get("code")
                    if (code == 200 or code == "200") and result.get("data"):
                        return result["data"][0]  # Return first term record
                    elif code == 403 or code == "403":
                        # 403 means no data for this term - return None to allow fallback logic
                        logger.info(f"Student term data not available for {student_code} (403 - 無資料)")
                        return None
                    elif code == 404 or code == "404":
                        # 404 means student not found - return None
                        logger.info(f"Student term data not found for {student_code} (404)")
                        return None
                    else:
                        # Other error codes should raise exception
                        logger.error(
                            f"Student term API returned error - "
                            f"code: {code} (type: {type(code).__name__}), "
                            f"msg: {result.get('msg')}, student_code: {student_code}"
                        )
                        raise ServiceUnavailableError(f"Student term API error: {result.get('msg')}")
                else:
                    logger.error(f"Student term API request failed: {response.status_code}")
                    raise ServiceUnavailableError("Student API is unavailable")

        except httpx.TimeoutException:
            logger.error(f"Student term API request timed out for {student_code}")
            raise ServiceUnavailableError("Student API request timed out")
        except httpx.RequestError as e:
            logger.error(f"Student term API request error: {str(e)}")
            raise ServiceUnavailableError(f"Student API request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error fetching student term data for {student_code}: {str(e)}")
            raise ServiceUnavailableError(f"Failed to fetch student term data: {str(e)}")

    async def get_student_snapshot(
        self, student_code: str, academic_year: Optional[str] = None, semester: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get student data snapshot for application storage

        Fetches both basic student info (API 1) and term-specific data (API 2).

        Args:
            student_code: Student ID code
            academic_year: Academic year (e.g., '114') for term data query
            semester: Semester ('first', 'second', or None for yearly scholarships)

        Returns:
            Student data snapshot dictionary with both std_* and trm_* fields

        Raises:
            NotFoundError: If student not found
            ServiceUnavailableError: If API is unavailable
        """
        if not self.api_enabled:
            raise ServiceUnavailableError("Student API is not configured")

        # Fetch basic student info (API 1)
        student_data = await self.get_student_basic_info(student_code)

        if not student_data:
            raise NotFoundError(f"Student {student_code} not found in external API")

        # Fetch term-specific data (API 2) if academic_year is provided
        term_data = None
        term_data_status = "not_requested"
        term_error_message = None

        if academic_year:
            try:
                if semester == "first":
                    # Semester-based: query first semester only
                    logger.info(f"Fetching term data for {student_code}: {academic_year} term 1")
                    term_data = await self.get_student_term_info(student_code, academic_year, "1")
                    term_data_status = "success" if term_data else "error"
                    if not term_data:
                        term_error_message = f"No data for {academic_year} term 1"

                elif semester == "second":
                    # Semester-based: query second semester only
                    logger.info(f"Fetching term data for {student_code}: {academic_year} term 2")
                    term_data = await self.get_student_term_info(student_code, academic_year, "2")
                    term_data_status = "success" if term_data else "error"
                    if not term_data:
                        term_error_message = f"No data for {academic_year} term 2"

                else:
                    # Yearly scholarship: try term 2 first, then term 1
                    logger.info(f"Fetching term data for {student_code}: {academic_year} (yearly, trying term 2 first)")
                    term_data = await self.get_student_term_info(student_code, academic_year, "2")

                    if not term_data:
                        logger.info(f"Term 2 not found for {student_code}, trying term 1")
                        term_data = await self.get_student_term_info(student_code, academic_year, "1")

                    if term_data:
                        term_data_status = "success"
                    else:
                        term_data_status = "error"
                        term_error_message = f"No data for {academic_year} in both term 1 and 2"

            except Exception as e:
                logger.warning(f"Failed to fetch term data for {student_code}: {e}")
                term_data_status = "error"
                term_error_message = str(e)

        # Create snapshot with API data
        snapshot = {
            **student_data,  # Include all API 1 fields directly
            # Add internal metadata
            "_api_fetched_at": datetime.now(timezone.utc).isoformat(),
            "_api_source": self.api_base_url,
            "_term_data_status": term_data_status,
            "_term_error_message": term_error_message,
        }

        # Add API 2: Term-specific data (trm_* fields) if available
        if term_data:
            snapshot.update(term_data)

        return snapshot

    def get_student_type_from_data(self, student_data: Dict[str, Any]) -> str:
        """
        Determine student type from student data

        Args:
            student_data: Student data dictionary

        Returns:
            Student type string
        """
        degree = student_data.get("std_degree", "3")

        if degree == "1":
            return "phd"
        elif degree == "2":
            return "master"
        else:
            return "undergraduate"

    def determine_student_api_type(self, scholarship_config=None) -> str:
        """
        Determine which student API to call based on scholarship configuration

        Args:
            scholarship_config: ScholarshipConfiguration object (optional)

        Returns:
            API type: "student" or "student_term"
        """
        # For now, default to "student" type for basic info
        # In the future, we can add logic to determine based on scholarship requirements
        # if scholarship_config and scholarship_config.requires_term_data:
        #     return "student_term"

        # You can customize this logic based on your scholarship requirements
        return "student"

    async def get_student_data_by_type(
        self,
        student_code: str,
        api_type: str = "student",
        academic_year: str = None,
        term: str = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get student data using specified API type

        Args:
            student_code: Student ID code
            api_type: "student" for basic info, "student_term" for term-specific data
            academic_year: Academic year (required if api_type is "student_term")
            term: Term (required if api_type is "student_term")

        Returns:
            Student data dictionary or None
        """
        if api_type == "student_term":
            if not academic_year or not term:
                logger.error("Academic year and term are required for student_term API")
                return None
            return await self.get_student_term_info(student_code, academic_year, term)
        else:
            return await self.get_student_basic_info(student_code)

    async def validate_student_exists(self, student_code: str) -> bool:
        """
        Check if a student exists in the external API

        Args:
            student_code: Student ID code

        Returns:
            True if student exists, False otherwise
        """
        if not self.api_enabled:
            logger.warning("Student API is not enabled. Cannot validate student.")
            return False

        try:
            student_data = await self.get_student_basic_info(student_code)
            return student_data is not None
        except ServiceUnavailableError:
            logger.error(f"Cannot validate student {student_code} - API unavailable")
            return False

    def is_api_available(self) -> bool:
        """Check if the student API is configured and available"""
        return self.api_enabled
