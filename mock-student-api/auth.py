"""
HMAC-SHA256 Authentication Module for Mock Student API

This module provides HMAC authentication functionality to reduce code duplication
in the main API endpoints.
"""

import hashlib
import hmac
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Configuration
MOCK_HMAC_KEY_HEX = os.getenv(
    "MOCK_HMAC_KEY_HEX", "4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a"
)
STRICT_TIME_CHECK = os.getenv("STRICT_TIME_CHECK", "true").lower() == "true"
STRICT_ENCODE_CHECK = os.getenv("STRICT_ENCODE_CHECK", "false").lower() == "true"
TIME_TOLERANCE_MINUTES = int(os.getenv("TIME_TOLERANCE_MINUTES", "5"))


def verify_hmac_signature(
    authorization: str, request_body: str, content_type: str, encode_type: Optional[str] = None
) -> bool:
    """
    Verify HMAC-SHA256 signature according to university API specification

    Authorization format: HMAC-SHA256:<TIME>:<ACCOUNT>:<SIGNATURE_HEX>
    Message format: <TIME> + <REQUEST_JSON> (no whitespace)

    Note: TIME should be in UTC format (YYYYMMDDHHMMSS)
    """
    try:
        if not authorization.startswith("HMAC-SHA256:"):
            logger.warning(f"Invalid authorization format: {authorization}")
            return False

        parts = authorization[12:].split(":")
        if len(parts) != 3:
            logger.warning(f"Invalid authorization parts count: {len(parts)}")
            return False

        time_str, account, signature_hex = parts

        if len(time_str) != 14 or not time_str.isdigit():
            logger.warning(f"Invalid time format: {time_str}")
            return False

        if STRICT_TIME_CHECK:
            try:
                request_time = datetime.strptime(time_str, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                current_time = datetime.now(timezone.utc)
                time_diff = abs((current_time - request_time).total_seconds() / 60)

                if time_diff > TIME_TOLERANCE_MINUTES:
                    logger.warning(f"Time difference too large: {time_diff} minutes")
                    return False
            except ValueError:
                logger.warning(f"Invalid time format for parsing: {time_str}")
                return False

        if STRICT_ENCODE_CHECK and encode_type != "UTF-8":
            logger.warning(f"Invalid encode type: {encode_type}")
            return False

        if content_type != "application/json;charset=UTF-8":
            logger.warning(f"Invalid content type: {content_type}")
            return False

        message = time_str + request_body
        hmac_key = bytes.fromhex(MOCK_HMAC_KEY_HEX)

        expected_signature = hmac.new(hmac_key, message.encode("utf-8"), hashlib.sha256).hexdigest().lower()

        if signature_hex.lower() != expected_signature:
            logger.warning(f"Signature mismatch. Expected: {expected_signature}, Got: {signature_hex}")
            return False

        logger.info(f"HMAC verification successful for account: {account}")
        return True

    except Exception as e:
        logger.error(f"HMAC verification error: {str(e)}")
        return False


def validate_request_params(account: str, action: str, expected_action: str) -> Optional[dict]:
    """
    Validate common request parameters

    Returns error response dict if validation fails, None if successful
    """
    if account != "scholarship":
        return {"code": 400, "msg": "Invalid account", "data": []}

    if action != expected_action:
        return {"code": 400, "msg": "Invalid action", "data": []}

    return None
