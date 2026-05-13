"""
Pure-helper tests for `ScholarshipConfiguration` model methods.

These helpers drive the **runtime gates** of the scholarship lifecycle:
- `is_effective` decides whether the config is exposed at all
- `is_application_period` controls the student-facing apply button
- `is_renewal_*_period` / `is_*_review_period` control reviewer access
- `get_matrix_quota` / `set_matrix_quota` / `validate_quota_config` are the
  quota-management gate (over-allocation = budget overrun)
- `export_config` is the backup/migration round-trip

Regression risks pinned here:
- `is_effective` returning True when `is_active=False` → an inactive
  scholarship suddenly accepts applications.
- Naive-datetime path returning the wrong window → off-by-tz bugs around
  midnight UTC.
- `validate_quota_config` not catching college-quota overflow → admin
  saves a misconfigured matrix that exceeds the institutional cap.
- `set_matrix_quota` mutating `None` → AttributeError in admin UI on
  fresh configs.
- `current_application_type` returning 'general' while renewal window is
  active → renewal applicants forced through general flow.

19 cases across 10 helpers, no DB / no I/O.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.enums import QuotaManagementMode, Semester
from app.models.scholarship import ScholarshipConfiguration


def _cfg(**overrides) -> ScholarshipConfiguration:
    """Construct a ScholarshipConfiguration without invoking SQLAlchemy ORM init."""
    c = object.__new__(ScholarshipConfiguration)
    defaults = {
        "id": 1,
        "scholarship_type_id": 1,
        "academic_year": 113,
        "semester": Semester.first,
        "config_code": "TEST-113-1",
        "config_name": "Test Config",
        "description": None,
        "description_en": None,
        "has_quota_limit": False,
        "has_college_quota": False,
        "quota_management_mode": QuotaManagementMode.none,
        "total_quota": None,
        "quotas": None,
        "amount": 10000,
        "currency": "TWD",
        "whitelist_student_ids": None,
        "is_active": True,
        "effective_start_date": None,
        "effective_end_date": None,
        "version": "1.0",
        "renewal_application_start_date": None,
        "renewal_application_end_date": None,
        "application_start_date": None,
        "application_end_date": None,
        "renewal_professor_review_start": None,
        "renewal_professor_review_end": None,
        "renewal_college_review_start": None,
        "renewal_college_review_end": None,
        "requires_professor_recommendation": False,
        "professor_review_start": None,
        "professor_review_end": None,
        "requires_college_review": False,
        "college_review_start": None,
        "college_review_end": None,
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        object.__setattr__(c, k, v)
    return c


# ─── cycle + academic_year_label ──────────────────────────────────────


def test_cycle_includes_semester_value():
    """cycle property used in URLs / audit logs — pin format."""
    c = _cfg(academic_year=113, semester=Semester.first)
    assert c.cycle == "113-first"


def test_cycle_without_semester_is_just_year():
    """Yearly-only configs (semester is None) → just the year string.
    Pin so the trailing dash doesn't sneak in."""
    c = _cfg(academic_year=114, semester=None)
    assert c.cycle == "114"


def test_academic_year_label_localized_semester():
    """Display label uses Chinese semester names — UI relies on this."""
    c = _cfg(academic_year=113, semester=Semester.first)
    assert c.academic_year_label == "113學年度 第一學期"

    c2 = _cfg(academic_year=113, semester=Semester.second)
    assert c2.academic_year_label == "113學年度 第二學期"

    c3 = _cfg(academic_year=113, semester=Semester.yearly)
    assert c3.academic_year_label == "113學年度 全年"

    c4 = _cfg(academic_year=114, semester=None)
    assert c4.academic_year_label == "114學年度"


# ─── is_effective ─────────────────────────────────────────────────────


def test_is_effective_blocked_when_inactive():
    """SECURITY: is_active=False short-circuits — pin so an admin's
    'disable' click is honored even if effective_*_date hasn't arrived yet
    or has already passed."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    c = _cfg(is_active=False, effective_start_date=past, effective_end_date=future)
    assert c.is_effective is False


def test_is_effective_blocked_before_start_date():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    c = _cfg(is_active=True, effective_start_date=future)
    assert c.is_effective is False


def test_is_effective_blocked_after_end_date():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    c = _cfg(is_active=True, effective_end_date=past)
    assert c.is_effective is False


def test_is_effective_naive_datetime_treated_as_utc():
    """Pin: naive datetimes (legacy rows imported pre-tz-migration) get
    coerced to UTC, not raised on. A regression that throws TypeError
    here would break any read of these configs."""
    past_naive = datetime.utcnow() - timedelta(hours=1)
    future_naive = datetime.utcnow() + timedelta(hours=1)
    c = _cfg(is_active=True, effective_start_date=past_naive, effective_end_date=future_naive)
    assert c.is_effective is True


def test_is_effective_open_window_no_dates():
    """Active + no effective dates → effective indefinitely."""
    c = _cfg(is_active=True, effective_start_date=None, effective_end_date=None)
    assert c.is_effective is True


# ─── Matrix quota CRUD ────────────────────────────────────────────────


def test_get_matrix_quota_returns_none_when_no_college_quota():
    """has_college_quota=False → None regardless of stored quotas dict
    (defensive: don't leak stale quota data after admin disables college
    quotas)."""
    c = _cfg(has_college_quota=False, quotas={"nstc": {"EE": 5}})
    assert c.get_matrix_quota("nstc", "EE") is None


def test_get_matrix_quota_returns_value():
    c = _cfg(has_college_quota=True, quotas={"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6}})
    assert c.get_matrix_quota("nstc", "EE") == 5
    assert c.get_matrix_quota("nstc", "EN") == 4
    assert c.get_matrix_quota("moe_1w", "EE") == 6
    # Missing sub_type / college → None.
    assert c.get_matrix_quota("nstc", "UNKNOWN") is None
    assert c.get_matrix_quota("missing_sub", "EE") is None


def test_set_matrix_quota_initializes_nested_dicts():
    """Pin: setting on a None-quotas config initializes the dict — admin
    creating quotas on a fresh config must not AttributeError."""
    c = _cfg(has_college_quota=True, quotas=None)
    c.set_matrix_quota("nstc", "EE", 7)
    assert c.quotas == {"nstc": {"EE": 7}}

    # Adding another college under same sub_type extends, doesn't overwrite.
    c.set_matrix_quota("nstc", "EN", 3)
    assert c.quotas == {"nstc": {"EE": 7, "EN": 3}}

    # New sub_type adds a new top-level key.
    c.set_matrix_quota("moe_1w", "EE", 5)
    assert c.quotas == {"nstc": {"EE": 7, "EN": 3}, "moe_1w": {"EE": 5}}


# ─── Aggregations ─────────────────────────────────────────────────────


def test_get_sub_type_total_quota_sums_across_colleges():
    c = _cfg(has_college_quota=True, quotas={"nstc": {"EE": 5, "EN": 4, "MA": 3}})
    assert c.get_sub_type_total_quota("nstc") == 12
    # Missing sub_type → 0 (not error).
    assert c.get_sub_type_total_quota("missing") == 0


def test_get_college_total_quota_sums_across_sub_types():
    """Pin: sums one college's quota across all sub-types. Used in the
    college dashboard 'total available' display."""
    c = _cfg(
        has_college_quota=True,
        quotas={"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6, "EN": 2}},
    )
    assert c.get_college_total_quota("EE") == 11
    assert c.get_college_total_quota("EN") == 6
    assert c.get_college_total_quota("UNKNOWN") == 0


def test_get_matrix_quota_summary_full_shape():
    """The admin matrix-overview API returns this exact shape — pin the
    keys + grand_total computation so the frontend table doesn't break."""
    c = _cfg(
        has_college_quota=True,
        quotas={"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6}},
    )
    summary = c.get_matrix_quota_summary()
    assert summary["sub_type_totals"] == {"nstc": 9, "moe_1w": 6}
    assert summary["college_totals"] == {"EE": 11, "EN": 4}
    assert summary["grand_total"] == 15
    assert summary["matrix"] == {"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6}}


def test_get_matrix_quota_summary_empty_when_no_college_quota():
    """Pin: returns the empty shape (not None) — frontend reads keys
    without null-checks."""
    c = _cfg(has_college_quota=False, quotas=None)
    summary = c.get_matrix_quota_summary()
    assert summary == {"sub_types": {}, "colleges": {}, "grand_total": 0}


# ─── get_total_available_quota ────────────────────────────────────────


def test_get_total_available_quota_unlimited_marker():
    """-1 is the sentinel for unlimited — pin so caller's quota-remaining
    math doesn't treat 'no limit' as zero."""
    c = _cfg(has_quota_limit=False)
    assert c.get_total_available_quota() == -1

    # quota_management_mode == none also unlimited
    c2 = _cfg(has_quota_limit=True, quota_management_mode=QuotaManagementMode.none, total_quota=100)
    assert c2.get_total_available_quota() == -1


def test_get_total_available_quota_returns_total():
    c = _cfg(
        has_quota_limit=True,
        quota_management_mode=QuotaManagementMode.simple,
        total_quota=50,
    )
    assert c.get_total_available_quota() == 50

    # None total_quota with limit enabled → 0 (not None) — pin so arithmetic
    # downstream doesn't TypeError.
    c2 = _cfg(
        has_quota_limit=True,
        quota_management_mode=QuotaManagementMode.simple,
        total_quota=None,
    )
    assert c2.get_total_available_quota() == 0


# ─── validate_quota_config ────────────────────────────────────────────


def test_validate_quota_config_clean_passes():
    c = _cfg(has_quota_limit=False, has_college_quota=False)
    assert c.validate_quota_config() == []


def test_validate_quota_config_catches_quota_limit_without_total():
    """has_quota_limit=True but no total_quota → error message."""
    c = _cfg(has_quota_limit=True, total_quota=None)
    errors = c.validate_quota_config()
    assert any("總配額" in e for e in errors)


def test_validate_quota_config_catches_college_overflow():
    """CRITICAL: matrix sum > total_quota must surface as an error —
    pin so the admin can't accidentally over-allocate the institutional
    cap (would cause budget overrun downstream)."""
    c = _cfg(
        has_quota_limit=True,
        total_quota=10,
        has_college_quota=True,
        quotas={"nstc": {"EE": 8, "EN": 5}},  # sum=13 > 10
    )
    errors = c.validate_quota_config()
    assert any("學院配額總和" in e and "超過總配額" in e for e in errors)


def test_validate_quota_config_renewal_dates_without_professor_flag():
    """Pin: renewal_professor_review_* set but requires_professor_recommendation=False
    → error. Otherwise admin sets dates that the runtime ignores → silent UX bug."""
    c = _cfg(
        requires_professor_recommendation=False,
        renewal_professor_review_start=datetime.now(timezone.utc),
    )
    errors = c.validate_quota_config()
    assert any("續領教授審查時間" in e for e in errors)


# ─── is_application_period (composite gate) ───────────────────────────


def test_is_application_period_open_general_window():
    """Within general window, no renewal window → True."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    c = _cfg(application_start_date=past, application_end_date=future)
    assert c.is_application_period is True


def test_is_application_period_renewal_takes_precedence():
    """SECURITY-ADJACENT: renewal window 'wins' over general — pin so a
    renewal candidate isn't accidentally routed through general flow
    when both windows overlap."""
    past = datetime.now(timezone.utc) - timedelta(days=1)
    future = datetime.now(timezone.utc) + timedelta(days=1)
    far_future = datetime.now(timezone.utc) + timedelta(days=7)
    c = _cfg(
        renewal_application_start_date=past,
        renewal_application_end_date=future,
        application_start_date=future,
        application_end_date=far_future,
    )
    assert c.is_application_period is True
    assert c.current_application_type == "renewal"


def test_is_application_period_closed_when_no_dates():
    """Pin: missing both windows → closed. Don't fall through to open."""
    c = _cfg(
        renewal_application_start_date=None,
        renewal_application_end_date=None,
        application_start_date=None,
        application_end_date=None,
    )
    assert c.is_application_period is False
    assert c.current_application_type is None


def test_is_application_period_naive_datetime_coerced():
    """Pin: naive datetimes get UTC-coerced rather than crashing."""
    past_naive = datetime.utcnow() - timedelta(hours=1)
    future_naive = datetime.utcnow() + timedelta(hours=1)
    c = _cfg(application_start_date=past_naive, application_end_date=future_naive)
    assert c.is_application_period is True


# ─── Renewal review gates ─────────────────────────────────────────────


def test_is_renewal_professor_review_period_open_window():
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    c = _cfg(renewal_professor_review_start=past, renewal_professor_review_end=future)
    assert c.is_renewal_professor_review_period() is True


def test_is_renewal_professor_review_period_closed_without_dates():
    c = _cfg(renewal_professor_review_start=None, renewal_professor_review_end=None)
    assert c.is_renewal_professor_review_period() is False


# ─── export_config (backup/migration round-trip) ──────────────────────


def test_export_config_serializes_enums_and_dates():
    """Pin: enums export as their .value strings, datetimes as ISO 8601.
    The restore script consumes this exact shape — a regression that
    exports the enum object directly would crash json.dumps."""
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 12, 31, tzinfo=timezone.utc)
    c = _cfg(
        config_code="EXPORT-TEST",
        config_name="Export Test",
        semester=Semester.first,
        quota_management_mode=QuotaManagementMode.matrix_based,
        effective_start_date=start,
        effective_end_date=end,
        amount=20000,
    )
    exported = c.export_config()
    assert exported["config_code"] == "EXPORT-TEST"
    assert exported["config_name"] == "Export Test"
    assert exported["semester"] == "first"  # enum.value, not the enum
    assert exported["quota_management_mode"] == "matrix_based"
    assert exported["effective_start_date"] == "2024-01-01T00:00:00+00:00"
    assert exported["effective_end_date"] == "2024-12-31T00:00:00+00:00"
    assert exported["amount"] == 20000


def test_export_config_handles_none_semester_and_dates():
    """Pin: yearly configs (semester=None) + missing dates export as None,
    not as the string 'None'."""
    c = _cfg(semester=None, effective_start_date=None, effective_end_date=None)
    exported = c.export_config()
    assert exported["semester"] is None
    assert exported["effective_start_date"] is None
    assert exported["effective_end_date"] is None
