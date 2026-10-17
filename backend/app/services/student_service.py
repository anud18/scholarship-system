"""
Student service that handles student data from external API.
Supports both mock API (development) and production student information system.

SIS records are cached in Redis (``app.services.student_api_cache``); pass
``fresh=True`` to skip the cache read when the caller must see live SIS data.
Stored snapshots (``get_student_snapshot``) are always live by default.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Tuple, Union

import httpx

from app.core.college_mappings import ORIGINAL_ACADEMY_CODES_KEY, normalize_student_academy
from app.core.config import settings
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.services.student_api_cache import basic_key, get_cached_record, set_cached_record, term_key

logger = logging.getLogger(__name__)

# Concurrent connections to SIS; callers beyond this wait in the pool
SIS_MAX_CONNECTIONS = 20
# Seconds a call may wait for a free pooled connection (separate from the SIS response timeout)
SIS_POOL_TIMEOUT = 30.0
# Concurrent term lookups per get_term_history call
TERM_LOOKUP_CONCURRENCY = 6

# One pooled client per event loop instead of a new connection per SIS call.
# The loop check matters for scripts / tests that each run their own loop.
_http_client: Optional[httpx.AsyncClient] = None
_http_client_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client, _http_client_loop
    loop = asyncio.get_running_loop()
    if _http_client is None or _http_client.is_closed or _http_client_loop is not loop:
        _http_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=SIS_MAX_CONNECTIONS))
        _http_client_loop = loop
    return _http_client


class _UnexpectedSISAnswer(Exception):
    """SIS answered with an unknown code: report "no record" but never cache it."""


async def close_http_client() -> None:
    """Close the shared SIS client (app shutdown)."""
    global _http_client, _http_client_loop
    if _http_client is not None and not _http_client.is_closed:
        await _http_client.aclose()
    _http_client = None
    _http_client_loop = None


def _is_code(code: Any, expected: int) -> bool:
    # API returns code as string, need to check both string and int
    return code == expected or code == str(expected)


class StudentService:
    """Service for accessing student data from external API"""

    def __init__(self):
        # Get API configuration from settings
        self.api_base_url = getattr(settings, "student_api_base_url", None)
        self.api_timeout = getattr(settings, "student_api_timeout", 10.0)
        self.api_enabled = getattr(settings, "student_api_enabled", False)

        # Validate configuration. The external API no longer requires HMAC/account
        # auth, so only the base URL is needed to reach it.
        if self.api_enabled and not self.api_base_url:
            logger.warning("Student API is enabled but STUDENT_API_BASE_URL is not set.")
            self.api_enabled = False

    async def get_student_basic_info(
        self, student_code: str, fresh: bool = False, retry_empty: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        Get student basic information from external API

        Args:
            student_code: Student ID code (e.g., 'stu_under', 'stu_phd')
            fresh: Skip the cache read (the live answer still refreshes the cache)
            retry_empty: Re-ask an empty answer before accepting it. Login turns this
                off: staff are always empty, so retries would only slow their login.

        Returns:
            Student data dictionary or None if not found
        """
        if not self.api_enabled:
            logger.warning("Student API is not enabled. Returning None.")
            return None

        try:
            record = await self._cached_fetch(
                basic_key(student_code),
                lambda: self._fetch_basic_info(student_code),
                fresh=fresh,
                retry_empty=retry_empty,
            )
        except _UnexpectedSISAnswer:
            return None
        # Retired academy codes (電資學院 Y) are remapped at the SIS boundary
        return normalize_student_academy(record)

    async def get_student_term_info(
        self, student_code: str, academic_year: str, term: str, fresh: bool = False
    ) -> Optional[Dict[str, Any]]:
        """
        Get student term information from external API

        Args:
            student_code: Student ID code
            academic_year: Academic year (e.g., '113')
            term: Term (e.g., '1', '2')
            fresh: Skip the cache read (the live answer still refreshes the cache)

        Returns:
            Term data dictionary or None if not found
        """
        if not self.api_enabled:
            logger.warning("Student API is not enabled. Returning None.")
            return None

        record = await self._cached_fetch(
            term_key(student_code, academic_year, term),
            lambda: self._fetch_term_info(student_code, academic_year, term),
            fresh=fresh,
        )
        return normalize_student_academy(record)

    async def _cached_fetch(
        self,
        key: str,
        fetch: Callable[[], Awaitable[Optional[Dict[str, Any]]]],
        fresh: bool,
        retry_empty: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Serve ``key`` from Redis, else fetch (re-asking empty answers) and cache the result.

        Exceptions from ``fetch`` propagate and are never cached. An empty answer is
        cached only after the retries confirmed it; with ``retry_empty=False`` it is
        returned but not cached, so one flaky 無資料 cannot hide a record from other callers.
        """
        if not fresh:
            hit, record = await get_cached_record(key)
            if hit:
                return record

        record = await fetch()
        # SIS sometimes answers 無資料 for data it does have; re-ask before caching the empty answer
        retries = settings.student_api_empty_retries if retry_empty else 0
        for attempt in range(1, retries + 1):
            if record is not None:
                break
            await asyncio.sleep(settings.student_api_empty_retry_delay * attempt)
            record = await fetch()

        if record is not None or retry_empty:
            await set_cached_record(key, record)
        return record

    async def get_term_history(
        self, student_code: str, periods: Sequence[Tuple[str, str]]
    ) -> List[Tuple[str, str, Union[Optional[Dict[str, Any]], Exception]]]:
        """Fetch several ``(academic_year, term)`` records concurrently (bounded), in ``periods`` order.

        A term that fails yields its exception in place of the record, so callers keep
        their per-term skip / count logic. Cancellation still propagates.
        """
        semaphore = asyncio.Semaphore(TERM_LOOKUP_CONCURRENCY)

        async def fetch_one(academic_year: str, term: str) -> Optional[Dict[str, Any]]:
            async with semaphore:
                return await self.get_student_term_info(student_code, academic_year, term)

        results = await asyncio.gather(*(fetch_one(year, term) for year, term in periods), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                raise result
        return [(year, term, result) for (year, term), result in zip(periods, results)]

    async def _post(self, endpoint: str, request_data: Dict[str, Any]) -> httpx.Response:
        headers = {
            "Content-Type": "application/json;charset=UTF-8",
        }

        if hasattr(settings, "student_api_encode_type"):
            headers["ENCODE_TYPE"] = settings.student_api_encode_type

        return await _get_http_client().post(
            f"{self.api_base_url}/{endpoint}",
            headers=headers,
            content=json.dumps(request_data, separators=(",", ":")),
            timeout=httpx.Timeout(self.api_timeout, pool=SIS_POOL_TIMEOUT),
        )

    async def _fetch_basic_info(self, student_code: str) -> Optional[Dict[str, Any]]:
        """One live ScholarshipStudent call; returns the raw record, or None for 403 無資料 / 404.

        Any other SIS code raises ``_UnexpectedSISAnswer`` so it is not cached as "no record".
        """
        try:
            response = await self._post(
                "ScholarshipStudent",
                {"action": "qrySoaaScholarshipStudent", "stdcode": student_code},
            )

            if response.status_code != 200:
                logger.error(f"Student API request failed: {response.status_code}")
                raise ServiceUnavailableError("Student API is unavailable")

            result = response.json()
            code = result.get("code")
            if _is_code(code, 200) and result.get("data"):
                return result["data"][0]  # First student record
            if _is_code(code, 403) or _is_code(code, 404):
                # 403 無資料 is what SIS answers for staff / unknown codes
                logger.info(f"Student {student_code} not found in API (code {code})")
                return None

            logger.warning(
                f"Student API returned unexpected response - "
                f"code: {result.get('code')} (type: {type(code).__name__}), "
                f"msg: {result.get('msg')}, student_code: {student_code}"
            )
            raise _UnexpectedSISAnswer(f"code {code}")

        except (ServiceUnavailableError, _UnexpectedSISAnswer):
            raise
        except httpx.TimeoutException as exc:
            logger.error(f"Student API request timed out for {student_code}")
            raise ServiceUnavailableError("Student API request timed out") from exc
        except httpx.RequestError as e:
            logger.exception("Student API request error")
            raise ServiceUnavailableError(f"Student API request failed: {str(e)}") from e
        except Exception as e:
            logger.exception(f"Unexpected error fetching student data for {student_code}")
            raise ServiceUnavailableError(f"Failed to fetch student data: {str(e)}") from e

    async def _fetch_term_info(self, student_code: str, academic_year: str, term: str) -> Optional[Dict[str, Any]]:
        """One live ScholarshipStudentTerm call; returns the raw record or None."""
        try:
            response = await self._post(
                "ScholarshipStudentTerm",
                {
                    "action": "qrySoaaScholarshipStudent",
                    "stdcode": student_code,
                    "trmyear": academic_year,
                    "trmterm": term,
                },
            )

            if response.status_code != 200:
                logger.error(f"Student term API request failed: {response.status_code}")
                raise ServiceUnavailableError("Student API is unavailable")

            result = response.json()
            code = result.get("code")
            if _is_code(code, 200) and result.get("data"):
                return result["data"][0]  # First term record
            if _is_code(code, 403):
                # 403 means no data for this term - return None to allow fallback logic
                logger.info(f"Student term data not available for {student_code} (403 - 無資料)")
                return None
            if _is_code(code, 404):
                # 404 means student not found - return None
                logger.info(f"Student term data not found for {student_code} (404)")
                return None

            # Other error codes should raise exception
            logger.error(
                f"Student term API returned error - "
                f"code: {code} (type: {type(code).__name__}), "
                f"msg: {result.get('msg')}, student_code: {student_code}"
            )
            raise ServiceUnavailableError(f"Student term API error: {result.get('msg')}")

        except ServiceUnavailableError:
            raise
        except httpx.TimeoutException as exc:
            logger.error(f"Student term API request timed out for {student_code}")
            raise ServiceUnavailableError("Student API request timed out") from exc
        except httpx.RequestError as e:
            logger.exception("Student term API request error")
            raise ServiceUnavailableError(f"Student API request failed: {str(e)}") from e
        except Exception as e:
            logger.exception(f"Unexpected error fetching student term data for {student_code}")
            raise ServiceUnavailableError(f"Failed to fetch student term data: {str(e)}") from e

    async def _get_yearly_term_info(
        self, student_code: str, academic_year: str, fresh: bool
    ) -> tuple[Optional[Dict[str, Any]], str, Optional[str]]:
        """Yearly scholarship: term 2 first, then term 1. Returns ``(data, status, error_message)``.

        A failed term-2 lookup (timeout, 5xx) still falls back to term 1, but the
        snapshot is marked ``partial`` — term 2 may exist, so it is re-fetched at submit.
        """
        logger.info(f"Fetching term data for {student_code}: {academic_year} (yearly, trying term 2 first)")
        term2_error: Optional[Exception] = None
        try:
            term_data = await self.get_student_term_info(student_code, academic_year, "2", fresh=fresh)
        except ServiceUnavailableError as exc:
            logger.warning(f"Term 2 lookup failed for {student_code}, falling back to term 1", exc_info=True)
            term_data, term2_error = None, exc

        if term_data:
            return term_data, "success", None

        logger.info(f"Term 2 not found for {student_code}, trying term 1")
        term_data = await self.get_student_term_info(student_code, academic_year, "1", fresh=fresh)

        if term2_error is None:
            if term_data:
                return term_data, "success", None
            return None, "error", f"No data for {academic_year} in both term 1 and 2"

        if term_data:
            return term_data, "partial", f"Term 2 lookup failed ({term2_error}); used {academic_year} term 1"
        return None, "error", f"Term 2 lookup failed ({term2_error}); no data for {academic_year} term 1"

    async def get_student_snapshot(
        self,
        student_code: str,
        academic_year: Optional[str] = None,
        semester: Optional[str] = None,
        fresh: bool = True,
    ) -> Dict[str, Any]:
        """
        Get student data snapshot for application storage

        Fetches both basic student info (API 1) and term-specific data (API 2).

        Args:
            student_code: Student ID code
            academic_year: Academic year (e.g., '114') for term data query
            semester: Semester ('first', 'second', or None for yearly scholarships)
            fresh: Ask SIS live (default) — the snapshot is stored with the application
                and stamped ``_api_fetched_at``, so it must not be a cached copy

        Returns:
            Student data snapshot dictionary with both std_* and trm_* fields

        Raises:
            NotFoundError: If student not found
            ServiceUnavailableError: If API is unavailable
        """
        if not self.api_enabled:
            raise ServiceUnavailableError("Student API is not configured")

        # Fetch basic student info (API 1)
        student_data = await self.get_student_basic_info(student_code, fresh=fresh)

        if not student_data:
            raise NotFoundError(f"Student {student_code} not found in external API")

        # Fetch term-specific data (API 2) if academic_year is provided
        term_data = None
        term_data_status = "not_requested"
        term_error_message = None

        if academic_year:
            try:
                if semester in ("first", "second"):
                    # Semester-based: query that semester only
                    term = "1" if semester == "first" else "2"
                    logger.info(f"Fetching term data for {student_code}: {academic_year} term {term}")
                    term_data = await self.get_student_term_info(student_code, academic_year, term, fresh=fresh)
                    term_data_status = "success" if term_data else "error"
                    if not term_data:
                        term_error_message = f"No data for {academic_year} term {term}"
                else:
                    term_data, term_data_status, term_error_message = await self._get_yearly_term_info(
                        student_code, academic_year, fresh
                    )

            except Exception as e:
                logger.warning(f"Failed to fetch term data for {student_code}", exc_info=True)
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

        # Both records may carry the raw codes normalization replaced; keep the union
        original_codes = {
            **(student_data.get(ORIGINAL_ACADEMY_CODES_KEY) or {}),
            **((term_data or {}).get(ORIGINAL_ACADEMY_CODES_KEY) or {}),
        }
        if original_codes:
            snapshot[ORIGINAL_ACADEMY_CODES_KEY] = original_codes

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
