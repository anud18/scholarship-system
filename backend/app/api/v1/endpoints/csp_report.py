"""
CSP Violation Reporting Endpoint

This endpoint receives and logs Content Security Policy violation reports
from the browser. Used for monitoring and debugging CSP issues.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

router = APIRouter()
logger = logging.getLogger(__name__)

# Configure logger for CSP violations
csp_logger = logging.getLogger("csp_violations")
csp_logger.setLevel(logging.WARNING)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/csp-report", status_code=status.HTTP_204_NO_CONTENT)
async def report_csp_violation(request: Request):
    """
    Receive and log CSP violation reports from browsers.

    The browser sends violation reports to this endpoint when CSP blocks a resource.
    Format follows the CSP Level 2 specification.

    Returns 204 No Content as per CSP specification.
    """
    client_ip = _client_ip(request)
    user_agent = request.headers.get("User-Agent", "unknown")
    try:
        # Parse CSP violation report
        body = await request.json()

        # Extract violation details
        csp_report = body.get("csp-report", {})

        # Log violation with structured data
        violation_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "blocked_uri": csp_report.get("blocked-uri", "unknown"),
            "violated_directive": csp_report.get("violated-directive", "unknown"),
            "original_policy": csp_report.get("original-policy", "unknown"),
            "document_uri": csp_report.get("document-uri", "unknown"),
            "referrer": csp_report.get("referrer", ""),
            "status_code": csp_report.get("status-code", 0),
            "script_sample": csp_report.get("script-sample", ""),
            "source_file": csp_report.get("source-file", ""),
            "line_number": csp_report.get("line-number", 0),
            "column_number": csp_report.get("column-number", 0),
            "ip": client_ip,
            "user_agent": user_agent,
        }

        # Log as warning for monitoring
        csp_logger.warning(
            f"CSP Violation: {violation_data['violated_directive']} "
            f"blocked {violation_data['blocked_uri']} "
            f"on {violation_data['document_uri']}",
            extra={"violation_data": violation_data},
        )

        # Also log to main logger for centralized logging
        logger.info(
            "CSP violation reported",
            extra={"violation_data": violation_data},
        )

        # Return 204 No Content (standard for CSP reports)
        return JSONResponse(content="", status_code=status.HTTP_204_NO_CONTENT)

    except Exception:
        # logger.exception preserves the traceback so 5xx-style failures from
        # malformed bodies / parser bugs are debuggable in Loki + Sentry.
        logger.exception(
            "Failed to process CSP violation report",
            extra={"ip": client_ip, "user_agent": user_agent},
        )
        # Still return 204 to prevent browser errors
        return JSONResponse(content="", status_code=status.HTTP_204_NO_CONTENT)


@router.get("/csp-report")
async def csp_report_info():
    """
    Information endpoint about CSP reporting.
    Browsers use POST, this GET is for documentation.
    """
    return {
        "success": True,
        "message": "CSP Violation Reporting Endpoint",
        "data": {
            "endpoint": "/api/v1/csp-report",
            "method": "POST",
            "description": "Receives Content Security Policy violation reports from browsers",
            "specification": "https://www.w3.org/TR/CSP2/#reporting",
            "note": "Violations are logged for security monitoring and debugging",
        },
    }
