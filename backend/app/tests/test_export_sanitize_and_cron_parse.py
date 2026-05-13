"""
Pure-helper tests for `app.services.export_package_service._sanitize_filename`
and `app.services.roster_scheduler_service.RosterSchedulerService._parse_cron_expression`.

`_sanitize_filename` is the safety gate for ZIP entry paths inside the
college export package — admins download these on Windows so filenames
must not contain Windows-reserved characters. A regression would either
crash ZipFile.extract on Windows or let an attacker inject `..` segments.

`_parse_cron_expression` converts standard 5-field cron strings into the
APScheduler `{minute, hour, day, month, day_of_week}` kwargs dict.
Malformed strings must raise before the scheduler ingests them; a bug
here would create silently-broken schedules.

2 helpers (12 cases). Pure, no I/O.
"""

import pytest

from app.services.export_package_service import _sanitize_filename
from app.services.roster_scheduler_service import RosterSchedulerService

# ─── _sanitize_filename ──────────────────────────────────────────────


def test_sanitize_replaces_windows_reserved_chars():
    """Pin: replaces /, \\, :, *, ?, ", <, >, | with underscore.
    SECURITY-ADJACENT: '/' and '\\' would otherwise create nested
    directories inside the ZIP, potentially with traversal patterns."""
    assert _sanitize_filename("a/b\\c") == "a_b_c"
    assert _sanitize_filename("file:name") == "file_name"
    assert _sanitize_filename("query?glob*") == "query_glob_"
    assert _sanitize_filename('quoted"path') == "quoted_path"
    assert _sanitize_filename("lt<gt>") == "lt_gt_"
    assert _sanitize_filename("pipe|sep") == "pipe_sep"


def test_sanitize_preserves_plain_filenames():
    """Pin: alphanumerics, CJK, hyphens, dots, underscores untouched."""
    assert _sanitize_filename("report-2024.pdf") == "report-2024.pdf"
    assert _sanitize_filename("申請書_王小明.docx") == "申請書_王小明.docx"


def test_sanitize_strips_outer_whitespace():
    """Pin: outer whitespace stripped. Defends against admin paste
    with trailing spaces."""
    assert _sanitize_filename("  good  ") == "good"


def test_sanitize_empty_input():
    """Pin: empty string → empty string (no crash). Caller is
    responsible for filling in a default if needed."""
    assert _sanitize_filename("") == ""


def test_sanitize_all_reserved_chars_in_one_pass():
    """Pin: every reserved char in one call gets replaced. Defensive
    against any single character being missed."""
    result = _sanitize_filename('/\\:*?"<>|')
    assert result == "_________"


# ─── RosterSchedulerService._parse_cron_expression ───────────────────


def _scheduler() -> RosterSchedulerService:
    """Construct without going through __init__ (which builds an
    AsyncIOScheduler — irrelevant to parse logic)."""
    svc = object.__new__(RosterSchedulerService)
    return svc


def test_cron_parse_5field_standard():
    """Pin: standard 5-field cron parsed into APScheduler kwargs."""
    result = _scheduler()._parse_cron_expression("0 2 * * *")
    assert result == {
        "minute": "0",
        "hour": "2",
        "day": "*",
        "month": "*",
        "day_of_week": "*",
    }


def test_cron_parse_supports_step_values():
    """Pin: APScheduler-style step values (`*/15`) pass through as
    strings unchanged — APScheduler itself parses them."""
    result = _scheduler()._parse_cron_expression("*/15 * * * 1-5")
    assert result["minute"] == "*/15"
    assert result["day_of_week"] == "1-5"


def test_cron_parse_strips_outer_whitespace():
    """Pin: leading/trailing whitespace stripped before split.
    Defensive against admin paste from formatted docs."""
    result = _scheduler()._parse_cron_expression("  0 9 1 * *  ")
    assert result == {
        "minute": "0",
        "hour": "9",
        "day": "1",
        "month": "*",
        "day_of_week": "*",
    }


def test_cron_parse_too_few_fields_rejected():
    """Pin: < 5 fields raises ValueError. Otherwise APScheduler would
    get a malformed kwargs dict and silently never fire."""
    with pytest.raises(ValueError) as exc:
        _scheduler()._parse_cron_expression("* * *")
    assert "Invalid cron expression" in str(exc.value)


def test_cron_parse_too_many_fields_rejected():
    """Pin: > 5 fields rejected. Crontab seconds-precision format
    (6 fields) is NOT supported here — admin must convert to standard
    5-field."""
    with pytest.raises(ValueError):
        _scheduler()._parse_cron_expression("0 0 2 * * *")  # 6 fields


def test_cron_parse_empty_string_rejected():
    """Pin: empty string raises (not silently produces empty dict)."""
    with pytest.raises(ValueError):
        _scheduler()._parse_cron_expression("")


def test_cron_parse_whitespace_only_rejected():
    """Pin: whitespace-only string raises after strip+split → empty
    list → 0 fields → reject."""
    with pytest.raises(ValueError):
        _scheduler()._parse_cron_expression("   ")
