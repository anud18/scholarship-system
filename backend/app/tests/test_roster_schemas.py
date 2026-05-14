"""
Tests for `app/schemas/roster.py`.

This is the SECOND roster module — `payment_roster.py` (covered by
wave 6a71) is the financial-side schema; `roster.py` is the
operational-side wire shape used by the roster endpoint set
(`/api/v1/rosters/...`).

The two modules have intentionally divergent defaults — pin them
side-by-side so a future "refactor that unifies the two" doesn't
silently change behaviour:

  - **`RosterCreateRequest.auto_export_excel = True`** (this module)
    vs **`RosterGenerationRequest.auto_export = False`**
    (payment_roster.py, wave 6a71). The operational endpoint defaults
    to auto-exporting; the financial flow requires explicit opt-in.

  - **`RosterExportRequest.template_name = "STD_UP_MIXLISTA"`** — the
    specific NYCU template name. Hardcoded magic string; pinned so a
    rename forces explicit review.

  - **`RosterExportRequest.max_preview_rows = 10`** — preview cap on
    the Excel-preview endpoint. Bumping this would slow the preview
    UI; cutting would render incomplete previews.

  - **`RosterResponse` uses `alias="created_by"` / `"locked_by"`** for
    `created_by_user_id` / `locked_by_user_id` — the ORM columns are
    short names, the wire shape is long names. Drift breaks
    model_validate(orm_row).

18 cases.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.models.payment_roster import RosterCycle, RosterStatus, RosterTriggerType, StudentVerificationStatus
from app.schemas.roster import (
    RosterCreateRequest,
    RosterExportRequest,
    RosterItemResponse,
    RosterResponse,
    RosterScheduleRequest,
    RosterStatisticsResponse,
)

# ─── RosterCreateRequest ────────────────────────────────────────────


def _create_req_min():
    return dict(
        scholarship_configuration_id=1,
        period_label="2024-H1",
        roster_cycle=RosterCycle.SEMI_YEARLY,
        academic_year=113,
    )


def test_create_request_required_fields():
    with pytest.raises(ValidationError):
        RosterCreateRequest(  # type: ignore[call-arg]
            scholarship_configuration_id=1,
            period_label="2024-H1",
            # roster_cycle missing
            academic_year=113,
        )


def test_create_request_student_verification_on_by_default():
    # Pin: same as payment_roster.RosterGenerationRequest — both
    # operational and financial flows verify by default.
    r = RosterCreateRequest(**_create_req_min())
    assert r.student_verification_enabled is True


def test_create_request_auto_export_excel_on_by_default():
    # Pin: divergent from payment_roster.RosterGenerationRequest
    # (which defaults auto_export=False). The /api/v1/rosters
    # endpoint produces an Excel file on every create as the common
    # UX expectation.
    #
    # If a future refactor unifies the two flows, this test breaks
    # loudly and forces explicit review of behaviour change.
    r = RosterCreateRequest(**_create_req_min())
    assert r.auto_export_excel is True


def test_create_request_force_regenerate_off_by_default():
    # Pin: same as payment_roster — opt-in protection against
    # overwriting existing rosters.
    r = RosterCreateRequest(**_create_req_min())
    assert r.force_regenerate is False


def test_create_request_ranking_id_optional():
    r = RosterCreateRequest(**_create_req_min())
    assert r.ranking_id is None


# ─── RosterExportRequest ────────────────────────────────────────────


def test_export_request_template_name_defaults_to_nycu_template():
    # Pin: STD_UP_MIXLISTA is the canonical NYCU Excel template name.
    # Renaming requires updating the Excel-rendering engine too —
    # pin so a rename forces explicit review.
    r = RosterExportRequest()
    assert r.template_name == "STD_UP_MIXLISTA"


def test_export_request_header_and_stats_on_by_default():
    # Pin: both default True. Finance staff expect a labeled file
    # with summary stats; flipping defaults to False would surface
    # as "no headers, looks corrupted".
    r = RosterExportRequest()
    assert r.include_header is True
    assert r.include_statistics is True


def test_export_request_max_preview_rows_defaults_10():
    # Pin: 10-row preview cap. Bumping slows UI; cutting renders
    # incomplete previews.
    r = RosterExportRequest()
    assert r.max_preview_rows == 10


def test_export_request_async_mode_off_by_default():
    # Pin: foreground export by default. Async is opt-in to avoid
    # the "where's my file?" UX confusion.
    r = RosterExportRequest()
    assert r.async_mode is False


def test_export_request_include_excluded_off_by_default():
    # Pin: same as payment_roster — Finance only sees qualified
    # items by default.
    r = RosterExportRequest()
    assert r.include_excluded is False


# ─── RosterResponse alias mapping ────────────────────────────────────


def _response_kwargs_with_aliases():
    """Use the alias keys (created_by, locked_by) as an ORM row would."""
    return dict(
        id=1,
        roster_code="R1",
        scholarship_configuration_id=1,
        period_label="2024-H1",
        roster_cycle=RosterCycle.SEMI_YEARLY,
        academic_year=113,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        qualified_count=0,
        disqualified_count=0,
        total_amount=Decimal("0"),
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        created_by=42,  # alias for created_by_user_id
    )


def test_response_accepts_orm_alias_keys():
    # Pin: model_validate accepts the ORM column names (created_by,
    # locked_by) via populate_by_name + alias= setup. Drift here
    # breaks model_validate(orm_row) at runtime.
    r = RosterResponse(**_response_kwargs_with_aliases())
    assert r.created_by_user_id == 42


def test_response_locked_by_alias_optional():
    # Pin: locked_by alias optional — null until the roster is
    # locked.
    r = RosterResponse(**_response_kwargs_with_aliases())
    assert r.locked_by_user_id is None


def test_response_accepts_python_field_names_too():
    # Pin: populate_by_name=True means BOTH the alias and the actual
    # field name are accepted. Pin so a regression that broke either
    # entry point surfaces.
    kwargs = _response_kwargs_with_aliases()
    kwargs.pop("created_by")
    kwargs["created_by_user_id"] = 99
    r = RosterResponse(**kwargs)
    assert r.created_by_user_id == 99


# ─── RosterItemResponse ─────────────────────────────────────────────


def test_item_response_required_fields():
    # Pin: 7 required scalar fields. The optional list of
    # display-only fields (college_code, college_name, etc.) is
    # explicitly Optional so the endpoint can populate them lazily.
    with pytest.raises(ValidationError):
        RosterItemResponse(  # type: ignore[call-arg]
            id=1,
            roster_id=1,
            # application_id missing
            student_id_number="A1",
            student_name="王",
            scholarship_amount=Decimal("1000"),
            verification_status=StudentVerificationStatus.VERIFIED,
            is_included=True,
            created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        )


def test_item_response_display_fields_optional():
    # Pin: college_code / college_name / department_name +
    # application_identity + allocated_sub_type are derived from
    # related data, defaulting None for incomplete records.
    r = RosterItemResponse(
        id=1,
        roster_id=1,
        application_id=1,
        student_id_number="A1",
        student_name="王",
        scholarship_amount=Decimal("1000"),
        verification_status=StudentVerificationStatus.VERIFIED,
        is_included=True,
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )
    assert r.college_code is None
    assert r.college_name is None
    assert r.department_name is None
    assert r.application_identity is None
    assert r.allocated_sub_type is None


# ─── RosterStatisticsResponse ───────────────────────────────────────


def test_statistics_requires_verification_counts():
    # Pin: verification_status_counts is required (no default).
    # The dashboard breakdown card depends on it.
    with pytest.raises(ValidationError):
        RosterStatisticsResponse(  # type: ignore[call-arg]
            roster_id=1,
            total_items=10,
            qualified_count=8,
            disqualified_count=2,
            total_amount=Decimal("500000"),
            # verification_status_counts missing
            created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
            status=RosterStatus.COMPLETED,
        )


# ─── RosterScheduleRequest ──────────────────────────────────────────


def test_schedule_request_is_active_defaults_true():
    # Pin: scheduling a new entry defaults to ACTIVE — admins won't
    # forget to enable it. Flipping to False would silently leave
    # every new schedule paused.
    r = RosterScheduleRequest(
        scholarship_configuration_id=1,
        roster_cycle=RosterCycle.SEMI_YEARLY,
        schedule_cron="0 2 * * *",
    )
    assert r.is_active is True


def test_schedule_request_required_fields():
    with pytest.raises(ValidationError):
        RosterScheduleRequest(  # type: ignore[call-arg]
            scholarship_configuration_id=1,
            roster_cycle=RosterCycle.SEMI_YEARLY,
            # schedule_cron missing
        )
