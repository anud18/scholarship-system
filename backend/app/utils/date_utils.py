"""
Date and time utility functions for the scholarship system
"""

import logging
from datetime import datetime
from typing import Optional, Union

import dateutil.parser

logger = logging.getLogger(__name__)


def parse_date_field(date_input: Optional[Union[str, datetime]]) -> Optional[datetime]:
    """
    Parse a date string into a datetime object with multiple format support.

    Args:
        date_input: Date string in various formats or datetime object

    Returns:
        datetime object or None if input is None/empty

    Supported formats:
        - ISO format: 2024-03-25T14:30:00Z
        - Date only: 2024-03-25
        - Datetime: 2024-03-25 14:30:00
        - Already a datetime object (returns as-is)
    """
    if date_input is None or date_input == "":
        return None

    if isinstance(date_input, datetime):
        return date_input

    if isinstance(date_input, str):
        try:
            # Try ISO format first (most common)
            if "T" in date_input:
                return datetime.fromisoformat(date_input.replace("Z", "+00:00"))
            # Try standard date format
            elif "-" in date_input and len(date_input) == 10:
                return datetime.strptime(date_input, "%Y-%m-%d")
            # Try datetime format
            elif " " in date_input:
                return datetime.strptime(date_input, "%Y-%m-%d %H:%M:%S")
            # Fallback to dateutil parser for other formats
            else:
                return dateutil.parser.parse(date_input)
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to parse date string '{date_input}': {e}")
            # Try dateutil as last resort
            try:
                return dateutil.parser.parse(date_input)
            except Exception as e2:
                logger.error(f"Could not parse date '{date_input}' with any method: {e2}")
                raise ValueError(f"Invalid date format: {date_input}")

    return None


def format_date_for_display(date_obj: Optional[datetime], format_string: str = "%Y-%m-%d", default: str = "N/A") -> str:
    """
    Format a datetime object for display.

    Args:
        date_obj: Datetime object to format
        format_string: strftime format string
        default: Default value if date_obj is None

    Returns:
        Formatted date string or default value
    """
    if date_obj is None:
        return default

    try:
        return date_obj.strftime(format_string)
    except Exception as e:
        logger.error(f"Failed to format date {date_obj}: {e}")
        return default


def is_within_date_range(
    check_date: datetime,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> bool:
    """
    Check if a date falls within a given range.

    Args:
        check_date: Date to check
        start_date: Range start (inclusive), None means no lower bound
        end_date: Range end (inclusive), None means no upper bound

    Returns:
        True if date is within range
    """
    if start_date and check_date < start_date:
        return False
    if end_date and check_date > end_date:
        return False
    return True
