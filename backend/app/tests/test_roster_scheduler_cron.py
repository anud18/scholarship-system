"""
Pure-unit tests for `RosterSchedulerService._parse_cron_expression`.

Schedules drive the once-a-month payment roster fire — a parser regression
silently shifts the fire window or refuses to schedule. The method itself is
DB-free; we just instantiate the service.

Covers issue #124 § 6a (cron parsing, pure unit).
"""

import pytest

from app.services.roster_scheduler_service import RosterSchedulerService


@pytest.fixture
def parser():
    return RosterSchedulerService()._parse_cron_expression


# ---------------------------------------------------------------------------
# Happy path — standard 5-field "min hour day month dow"
# ---------------------------------------------------------------------------


def test_parses_standard_five_field_expression(parser):
    assert parser("0 3 * * *") == {
        "minute": "0",
        "hour": "3",
        "day": "*",
        "month": "*",
        "day_of_week": "*",
    }


def test_parses_specific_day_of_month(parser):
    # 1st of every month at 09:30 — typical monthly roster cadence.
    assert parser("30 9 1 * *") == {
        "minute": "30",
        "hour": "9",
        "day": "1",
        "month": "*",
        "day_of_week": "*",
    }


def test_parses_step_and_range_atoms_passthrough(parser):
    # We don't expand cron atoms — APScheduler does. Just confirm the
    # passthrough preserves them exactly.
    parsed = parser("*/5 8-18 * * 1-5")
    assert parsed["minute"] == "*/5"
    assert parsed["hour"] == "8-18"
    assert parsed["day_of_week"] == "1-5"


# ---------------------------------------------------------------------------
# Whitespace tolerance — copy-paste from HackMD often introduces tabs or
# multiple spaces. Standard split() collapses them.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "0 3 * * *",
        "  0 3 * * *  ",
        "0  3  *  *  *",
        "0\t3\t*\t*\t*",
    ],
)
def test_tolerates_extra_whitespace(parser, raw):
    parsed = parser(raw)
    assert parsed == {
        "minute": "0",
        "hour": "3",
        "day": "*",
        "month": "*",
        "day_of_week": "*",
    }


# ---------------------------------------------------------------------------
# Field-count enforcement — APScheduler accepts a `seconds` field too, but
# this codebase deliberately rejects 6+ to keep the contract simple. A 4-field
# expression silently changes meaning (legacy 4-field cron has different
# field positions), so we reject those too.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw",
    [
        "",  # empty
        "0",  # one field
        "0 3",  # two fields
        "0 3 *",  # three fields
        "0 3 * *",  # four fields
        "0 3 * * * *",  # six fields (APScheduler-style with seconds)
        "0 0 3 * * * *",  # seven fields
    ],
)
def test_rejects_wrong_field_count(parser, raw):
    with pytest.raises(ValueError, match="Invalid cron expression format"):
        parser(raw)


# ---------------------------------------------------------------------------
# Edge cases that have bitten production cron parsers in other systems.
# We DON'T validate the ranges (APScheduler does that on schedule registration)
# but we should make sure they parse without crashing.
# ---------------------------------------------------------------------------


def test_day_31_month_specifier_parses(parser):
    # APScheduler is responsible for skipping months without a 31st;
    # the parser just hands the field through.
    parsed = parser("0 3 31 * *")
    assert parsed["day"] == "31"


def test_leap_day_specifier_parses(parser):
    # Feb 29 — APScheduler will run this only on leap years.
    parsed = parser("0 3 29 2 *")
    assert parsed["day"] == "29"
    assert parsed["month"] == "2"


def test_complex_expression_with_lists_and_steps(parser):
    # 09:00, 12:00, 17:00 on weekdays
    parsed = parser("0 9,12,17 * * 1-5")
    assert parsed["hour"] == "9,12,17"
    assert parsed["day_of_week"] == "1-5"
