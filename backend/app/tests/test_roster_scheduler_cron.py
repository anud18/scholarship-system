"""
Tests for `RosterSchedulerService._parse_cron_expression` — pure cron-string
parser used to seed APScheduler triggers.

This helper sits between operator-supplied cron strings (stored in
`roster_schedules.cron_expression`) and APScheduler's keyword-argument
trigger API. A regression here would silently mis-schedule (or fail to
schedule) every roster job:

- Daily 9am rosters might fire at 9 minute :00 of every hour instead
- Weekly jobs could parse as monthly, etc.

The original `RosterSchedulerService` is heavy (APScheduler + Redis job
store + DB hooks), but `_parse_cron_expression` itself only reads its
string argument — we instantiate without going through `_setup_scheduler`
via a minimal `__new__` trick to test the helper in isolation.

Wave 2f — sixth pure-function test coverage PR in the production-readiness
rollout. Targets a genuinely-untested service (per re-audit, three services
had zero tests: roster_scheduler_service, email_service, excel_export_service).
"""

from __future__ import annotations

import pytest

from app.services.roster_scheduler_service import RosterSchedulerService

pytestmark = pytest.mark.smoke


@pytest.fixture
def parser():
    """
    Construct a RosterSchedulerService without running `__init__` (which
    would create an APScheduler instance + Redis connection). The
    `_parse_cron_expression` method only reads its argument, so a stub
    instance works fine.
    """
    return RosterSchedulerService.__new__(RosterSchedulerService)


class TestParseCronExpressionHappyPath:
    """Standard 5-part cron strings parse to the documented dict shape."""

    def test_daily_9am(self, parser: RosterSchedulerService) -> None:
        result = parser._parse_cron_expression("0 9 * * *")
        assert result == {
            "minute": "0",
            "hour": "9",
            "day": "*",
            "month": "*",
            "day_of_week": "*",
        }

    def test_weekly_monday_midnight(self, parser: RosterSchedulerService) -> None:
        """Cron uses 0 or 7 for Sunday; APScheduler day_of_week is the same
        string, so we just pass through verbatim."""
        result = parser._parse_cron_expression("0 0 * * 1")
        assert result["day_of_week"] == "1"
        assert result["hour"] == "0"
        assert result["minute"] == "0"

    def test_monthly_first_8am(self, parser: RosterSchedulerService) -> None:
        result = parser._parse_cron_expression("0 8 1 * *")
        assert result["day"] == "1"
        assert result["month"] == "*"

    def test_every_5_minutes(self, parser: RosterSchedulerService) -> None:
        """Step-value syntax is passed through verbatim — APScheduler
        understands the same forms."""
        result = parser._parse_cron_expression("*/5 * * * *")
        assert result["minute"] == "*/5"

    def test_range_syntax(self, parser: RosterSchedulerService) -> None:
        """Range (a-b) and list (a,b,c) forms are passed through."""
        result = parser._parse_cron_expression("0 9-17 * * 1-5")
        assert result["hour"] == "9-17"
        assert result["day_of_week"] == "1-5"


class TestParseCronExpressionValidation:
    """Invalid cron strings raise ValueError; the docstring documents the
    "exactly 5 parts" requirement."""

    @pytest.mark.parametrize(
        "bad",
        [
            "",  # empty
            "0",  # 1 part
            "0 9",  # 2 parts
            "0 9 *",  # 3 parts
            "0 9 * *",  # 4 parts
            "0 9 * * * *",  # 6 parts (could be APScheduler's 7-part w/ second/year but our parser only accepts 5)
            "0 9 * * * * *",  # 7 parts
        ],
    )
    def test_wrong_part_count_raises(self, parser: RosterSchedulerService, bad: str) -> None:
        with pytest.raises(ValueError) as excinfo:
            parser._parse_cron_expression(bad)
        assert "Invalid cron expression format" in str(excinfo.value)

    def test_leading_trailing_whitespace_tolerated(self, parser: RosterSchedulerService) -> None:
        """The parser strips surrounding whitespace before splitting — useful
        because operators sometimes copy-paste with leading/trailing spaces."""
        result = parser._parse_cron_expression("  0 9 * * *  ")
        assert result["hour"] == "9"

    def test_multiple_internal_spaces_tolerated(self, parser: RosterSchedulerService) -> None:
        """`str.split()` with no argument collapses runs of whitespace, so
        '0   9  *  *  *' still parses correctly."""
        result = parser._parse_cron_expression("0   9  *  *  *")
        assert result == {
            "minute": "0",
            "hour": "9",
            "day": "*",
            "month": "*",
            "day_of_week": "*",
        }

    def test_error_message_includes_input(self, parser: RosterSchedulerService) -> None:
        """The error message echoes the bad input so operators can copy-paste
        into a bug report. Pin this so a future "helpful generic message"
        refactor doesn't lose the context."""
        with pytest.raises(ValueError) as excinfo:
            parser._parse_cron_expression("not a cron")
        assert "not a cron" in str(excinfo.value)
