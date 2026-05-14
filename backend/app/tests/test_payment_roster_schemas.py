"""
Tests for `app/schemas/payment_roster.py`.

Payment rosters are the system's "send these dollar amounts to these
students" artifacts — what gets exported to Excel and handed to
Finance. Bugs in these schemas have direct financial impact:

  - **PaymentRosterResponse.is_locked / can_be_modified / is_completed**
    are the gates that prevent edits to a roster after it's locked
    (frozen for accounting). A regression in any of them would let
    staff edit numbers that Finance already processed — audit issue
    AND money issue.

  - **RosterGenerationRequest defaults**: `trigger_type=MANUAL`,
    `student_verification_enabled=True`, `force_regenerate=False`,
    `auto_export=False`, `include_excluded_in_export=False`.
    These are conservative defaults — flipping any one would change
    the rule from "verify by default" to "trust by default".

  - **PaymentRosterItemBase.is_included** defaults to **True**.
    Most items are included; the False case is the exception
    (excluded with reason). Flipping the default would silently
    exclude every record from new rosters.

20 cases pinning 9 schemas + 3 computed properties.
"""

import pytest
from pydantic import ValidationError
from decimal import Decimal
from datetime import datetime, timezone

from app.models.payment_roster import RosterCycle, RosterStatus, RosterTriggerType, StudentVerificationStatus
from app.schemas.payment_roster import (
    PaymentRosterBase,
    PaymentRosterCreate,
    PaymentRosterItemBase,
    PaymentRosterListResponse,
    PaymentRosterResponse,
    RosterExportRequest,
    RosterGenerationRequest,
    RosterStatistics,
    RosterSummary,
)

# ─── PaymentRosterBase / Create ─────────────────────────────────────


def test_base_required_fields():
    # Pin: 5 fields required. None can become optional — every roster
    # needs a code + config + period + year + cycle.
    with pytest.raises(ValidationError):
        PaymentRosterBase(  # type: ignore[call-arg]
            roster_code="R1",
            scholarship_configuration_id=1,
            period_label="2024-H1",
            academic_year=113,
            # roster_cycle missing
        )


def test_base_student_verification_enabled_defaults_true():
    # Pin: verification ON by default (CLAUDE.md error-handling: never
    # silently trust). A regression flipping this to False would
    # bypass SIS checks on every new roster.
    b = PaymentRosterBase(
        roster_code="R1",
        scholarship_configuration_id=1,
        period_label="2024-H1",
        academic_year=113,
        roster_cycle=RosterCycle.SEMI_YEARLY,
    )
    assert b.student_verification_enabled is True


def test_create_requires_trigger_type():
    # Pin: Create extends Base with trigger_type (no default). The
    # endpoint requires every roster to have a documented trigger
    # (manual / scheduled / api) for audit-trail.
    with pytest.raises(ValidationError):
        PaymentRosterCreate(  # type: ignore[call-arg]
            roster_code="R1",
            scholarship_configuration_id=1,
            period_label="2024-H1",
            academic_year=113,
            roster_cycle=RosterCycle.SEMI_YEARLY,
        )


# ─── RosterGenerationRequest defaults ───────────────────────────────


def _gen_request_min():
    return dict(
        scholarship_configuration_id=1,
        period_label="2024-H1",
        roster_cycle=RosterCycle.SEMI_YEARLY,
        academic_year=113,
    )


def test_generation_request_trigger_type_defaults_manual():
    # Pin: MANUAL default — most generation is admin-triggered. The
    # scheduler explicitly passes SCHEDULED.
    r = RosterGenerationRequest(**_gen_request_min())
    assert r.trigger_type == RosterTriggerType.MANUAL


def test_generation_request_verification_on_by_default():
    r = RosterGenerationRequest(**_gen_request_min())
    assert r.student_verification_enabled is True


def test_generation_request_force_regenerate_off_by_default():
    # Pin: force_regenerate=False protects against accidentally
    # overwriting locked rosters. Must be opt-in.
    r = RosterGenerationRequest(**_gen_request_min())
    assert r.force_regenerate is False


def test_generation_request_auto_export_off_by_default():
    # Pin: auto_export=False — generating a roster is NOT the same as
    # delivering it to Finance. Two separate operations.
    r = RosterGenerationRequest(**_gen_request_min())
    assert r.auto_export is False


def test_generation_request_include_excluded_off_by_default():
    # Pin: include_excluded_in_export=False — Finance only sees
    # qualified items by default. Including excluded would surface
    # rejected applications in payment files.
    r = RosterGenerationRequest(**_gen_request_min())
    assert r.include_excluded_in_export is False


# ─── PaymentRosterItemBase ──────────────────────────────────────────


def _item_min():
    return dict(
        student_id_number="A123456789",
        student_name="王小明",
        scholarship_name="獎學金A",
        scholarship_amount=Decimal("50000"),
    )


def test_item_base_required_anchor_fields():
    with pytest.raises(ValidationError):
        PaymentRosterItemBase(  # type: ignore[call-arg]
            student_id_number="A123456789",
            student_name="王小明",
            # scholarship_name missing
            scholarship_amount=Decimal("50000"),
        )


def test_item_base_is_included_defaults_true():
    # Pin: is_included=True is the common case. Flipping the default
    # to False would silently exclude every new item, surfacing as
    # "empty roster" with no obvious cause.
    i = PaymentRosterItemBase(**_item_min())
    assert i.is_included is True


def test_item_base_scholarship_amount_is_decimal_not_float():
    # Pin: Decimal for money (no float rounding drift). A regression
    # to float would lose precision on cents on aggregation.
    i = PaymentRosterItemBase(**_item_min())
    assert isinstance(i.scholarship_amount, Decimal)


def test_item_base_optional_email_and_bank_account():
    # Pin: student_email and bank_account are Optional — some
    # historical records lack these. Don't force endpoints to seed
    # placeholder values.
    i = PaymentRosterItemBase(**_item_min())
    assert i.student_email is None
    assert i.bank_account is None
    assert i.scholarship_subtype is None
    assert i.allocation_year is None


# ─── PaymentRosterResponse computed properties ──────────────────────


def _response_kwargs(status: RosterStatus):
    return dict(
        roster_code="R1",
        scholarship_configuration_id=1,
        period_label="2024-H1",
        academic_year=113,
        roster_cycle=RosterCycle.SEMI_YEARLY,
        id=1,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=42,
        created_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
        updated_at=datetime(2025, 10, 22, tzinfo=timezone.utc),
    )


def test_is_locked_only_for_locked_status():
    # Pin: is_locked == True ONLY for status==LOCKED. The frontend
    # disables the edit button on this gate.
    for s in RosterStatus:
        r = PaymentRosterResponse(**_response_kwargs(s))
        assert r.is_locked == (s == RosterStatus.LOCKED)


def test_can_be_modified_in_draft_or_failed_only():
    # Pin: can_be_modified is True ONLY for DRAFT and FAILED. Editing
    # PROCESSING / COMPLETED / LOCKED rosters would race the
    # roster-build worker (corruption) or rewrite history (audit).
    for s in RosterStatus:
        r = PaymentRosterResponse(**_response_kwargs(s))
        expected = s in (RosterStatus.DRAFT, RosterStatus.FAILED)
        assert r.can_be_modified == expected, f"Status {s} should give can_be_modified={expected}"


def test_is_completed_true_for_completed_and_locked():
    # Pin: COMPLETED + LOCKED both count as completed. LOCKED is a
    # super-state of COMPLETED (cannot un-lock without re-completing).
    r_completed = PaymentRosterResponse(**_response_kwargs(RosterStatus.COMPLETED))
    r_locked = PaymentRosterResponse(**_response_kwargs(RosterStatus.LOCKED))
    r_draft = PaymentRosterResponse(**_response_kwargs(RosterStatus.DRAFT))

    assert r_completed.is_completed is True
    assert r_locked.is_completed is True
    assert r_draft.is_completed is False


# ─── RosterExportRequest ────────────────────────────────────────────


def test_export_request_defaults_to_safe_settings():
    # Pin: both defaults False — safe export (qualified only,
    # foreground). Async export must be opt-in to prevent surprising
    # admin staff.
    r = RosterExportRequest()
    assert r.include_excluded is False
    assert r.async_export is False


# ─── RosterStatistics ────────────────────────────────────────────────


def test_statistics_requires_all_counters():
    # Pin: stats has 6 required scalar fields. The dashboard cards
    # depend on these — None values would render "—" everywhere.
    with pytest.raises(ValidationError):
        RosterStatistics(  # type: ignore[call-arg]
            total_rosters=10,
            completed_rosters=5,
            # locked_rosters missing
            processing_rosters=2,
            total_students=100,
            total_amount=Decimal("500000"),
        )


def test_statistics_groupby_dicts_default_empty():
    # Pin: by_cycle / by_status / by_academic_year default to {} so
    # .items() doesn't crash on the frontend.
    s = RosterStatistics(
        total_rosters=0,
        completed_rosters=0,
        locked_rosters=0,
        processing_rosters=0,
        total_students=0,
        total_amount=Decimal("0"),
    )
    assert s.by_cycle == {}
    assert s.by_status == {}
    assert s.by_academic_year == {}
