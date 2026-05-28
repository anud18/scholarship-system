"""
Core behavior tests for `RosterService._create_roster_item`.

`_create_roster_item` (roster_service.py ~752) is the per-application
"build one roster row" leaf that is exercised by both
`generate_roster` (the canonical entry point) and
`_generate_one_sub_type_roster` (the matrix-distribution batch path).
It encodes the contract for what ends up in a `PaymentRosterItem`:

- Which student-data field becomes the `身分證字號` column on the bank
  payment Excel (PR #819: must be `std_pid`, not `std_stdcode`).
- The inclusion gate — bank account presence, verification status, and
  rule-eligibility result all collapse into `is_included` + a human
  `exclusion_reason` string.
- The `application_identity` snapshot ("114新申請" vs "114續領") that
  finance reads on the payment voucher to distinguish first-time vs
  renewal payments.

The method is a leaf that only touches `self.db.query(...)` for backup
allocation info (which we don't exercise here — `roster.ranking_id=None`
+ no allocated items in DB short-circuits both query chains to None),
and ends with `self.db.add(roster_item)`. So MagicMock for the DB is
sufficient — no SQLAlchemy session required.

Regression target: PR #819 fixed `student_id_number=std_stdcode` →
`student_id_number=std_pid`. The first test pins the corrected behavior
so any future refactor that drops std_pid back to std_stdcode breaks CI.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.models.payment_roster import (
    PaymentRosterItem,
    StudentVerificationStatus,
)
from app.services.roster_service import RosterService

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_db_mock() -> MagicMock:
    """A DB mock that returns no CollegeRankingItem rows.

    `_create_roster_item` issues two query chains on `self.db`:
      1. (only if roster.ranking_id) .query(CollegeRankingItem).filter(...).first()
      2. (always, if allocated_sub_type still None) .query(CollegeRankingItem)
         .join(CollegeRanking, ...).filter(...).first()

    Returning None on both keeps the allocation_year + allocated_sub_type
    code paths at their defaults so the test focuses on the fields the
    method itself derives from `application.student_data` + form data.
    """
    db = MagicMock()
    # Path 1: .query.filter.first → None
    db.query.return_value.filter.return_value.first.return_value = None
    # Path 2: .query.join.filter.first → None
    db.query.return_value.join.return_value.filter.return_value.first.return_value = None
    return db


def _make_roster(roster_id: int = 1, academic_year: int = 114, ranking_id=None) -> SimpleNamespace:
    return SimpleNamespace(
        id=roster_id,
        ranking_id=ranking_id,
        academic_year=academic_year,
    )


def _make_application(
    *,
    app_id: int = 1001,
    std_pid: str | None = "A123456789",
    std_stdcode: str | None = "110550001",
    std_cname: str | None = "王小明",
    com_email: str | None = "wang@nycu.edu.tw",
    bank_account: str | None = "00012345678",
    is_renewal: bool = False,
    previous_application_id: int | None = None,
    academic_year: int = 114,
    amount: int = 10000,
    config_amount: int = 50000,
    sub_scholarship_type: str = "nstc",
    scholarship_name: str = "博士班獎學金",
) -> SimpleNamespace:
    """Build an Application stub with just the attributes _create_roster_item reads.

    student_data: drives the std_pid/std_cname/com_email lookups.
    submitted_form_data: drives the bank_account inclusion check via the
    nested ("fields") schema-compliant structure.
    """
    student_data: dict = {}
    if std_pid is not None:
        student_data["std_pid"] = std_pid
    if std_stdcode is not None:
        student_data["std_stdcode"] = std_stdcode
    if std_cname is not None:
        student_data["std_cname"] = std_cname
    if com_email is not None:
        student_data["com_email"] = com_email

    submitted_form_data: dict = {"fields": {}}
    if bank_account is not None:
        submitted_form_data["fields"]["postal_account"] = {
            "field_id": "postal_account",
            "field_type": "text",
            "value": bank_account,
            "required": True,
        }

    scholarship_configuration = SimpleNamespace(
        amount=config_amount,
        scholarship_type=SimpleNamespace(name=scholarship_name),
    )

    return SimpleNamespace(
        id=app_id,
        student_data=student_data,
        submitted_form_data=submitted_form_data,
        amount=amount,
        scholarship_configuration=scholarship_configuration,
        sub_scholarship_type=sub_scholarship_type,
        is_renewal=is_renewal,
        previous_application_id=previous_application_id,
        academic_year=academic_year,
    )


@pytest.fixture
def service() -> RosterService:
    """RosterService with a no-op DB mock. The mocked `add` is the only
    side-effect we care about — verify_student / audit calls go through
    other methods, not _create_roster_item."""
    svc = RosterService(db=_make_db_mock())  # type: ignore[arg-type]
    return svc


# ---------------------------------------------------------------------------
# Regression: PR #819 — std_pid, not std_stdcode
# ---------------------------------------------------------------------------


def test_create_roster_item_stores_national_id_not_student_number(service: RosterService) -> None:
    """SECURITY/CORRECTNESS regression: PR #819 fixed
    `student_id_number = student_data["std_stdcode"]` (student number)
    →   `student_id_number = student_data["std_pid"]` (national ID).

    The Excel payment template column 1 is 身分證字號 (national ID),
    required by the government accounting system for tax reporting.
    Putting the student number there would route payments incorrectly
    AND leak a different identifier than the tax authority expects.

    Pinning std_pid here means any future refactor that flips the dict
    key back to std_stdcode breaks CI before it can ship.
    """
    roster = _make_roster()
    application = _make_application(std_pid="A123456789", std_stdcode="110550001")

    item: PaymentRosterItem = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.VERIFIED, "message": "ok"},
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result={"is_eligible": True, "failed_rules": [], "warning_rules": []},
    )

    assert item.student_id_number == "A123456789", (
        "student_id_number must come from std_pid (national ID), not " "std_stdcode (student number). See PR #819."
    )
    # And explicitly NOT the student number
    assert item.student_id_number != "110550001"


def test_create_roster_item_empty_string_when_std_pid_missing(service: RosterService) -> None:
    """If std_pid is absent from student_data, the column gets an empty
    string (the `.get("std_pid", "")` default), not a KeyError. This
    preserves the existing behavior that `validate_roster_consistency`
    catches downstream as a missing-field error rather than crashing
    the whole roster generation."""
    roster = _make_roster()
    application = _make_application(std_pid=None, std_stdcode="110550001")

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.student_id_number == ""


# ---------------------------------------------------------------------------
# Inclusion gate — bank account / verification / eligibility
# ---------------------------------------------------------------------------


def test_create_roster_item_included_when_bank_account_present(service: RosterService) -> None:
    """Happy path: verified + bank account in submitted_form_data ⇒ is_included=True."""
    roster = _make_roster()
    application = _make_application(bank_account="00012345678")

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.VERIFIED, "message": "ok"},
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result={"is_eligible": True, "failed_rules": [], "warning_rules": []},
    )

    assert item.is_included is True
    assert item.exclusion_reason is None
    assert item.bank_account == "00012345678"


def test_create_roster_item_excluded_when_bank_account_missing(service: RosterService) -> None:
    """No bank account anywhere in submitted_form_data ⇒ is_included=False
    with the 缺少銀行帳戶資訊 reason. Critical because we cannot pay a
    student with no account number — and the exclusion_reason is what the
    operator sees in the UI to know WHY they were dropped."""
    roster = _make_roster()
    application = _make_application(bank_account=None)

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.VERIFIED, "message": "ok"},
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result={"is_eligible": True, "failed_rules": [], "warning_rules": []},
    )

    assert item.is_included is False
    assert item.exclusion_reason == "缺少銀行帳戶資訊"
    assert item.bank_account == ""


def test_create_roster_item_excluded_when_verification_failed(service: RosterService) -> None:
    """A non-VERIFIED status (graduated, suspended, withdrawn, api_error,
    not_found) excludes the student regardless of bank account presence.
    Pin: the exclusion_reason explicitly includes the failed status's
    .value so operators can see which kind of failure occurred."""
    roster = _make_roster()
    application = _make_application(bank_account="00012345678")

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.GRADUATED, "message": "已畢業"},
        verification_status=StudentVerificationStatus.GRADUATED,
        eligibility_result={"is_eligible": True, "failed_rules": [], "warning_rules": []},
    )

    assert item.is_included is False
    assert "graduated" in item.exclusion_reason
    assert item.verification_status == StudentVerificationStatus.GRADUATED


def test_create_roster_item_excluded_when_eligibility_failed(service: RosterService) -> None:
    """Verified but failed eligibility rules ⇒ is_included=False, and
    the failed rule messages are concatenated into exclusion_reason."""
    roster = _make_roster()
    application = _make_application(bank_account="00012345678")

    eligibility = {
        "is_eligible": False,
        "failed_rules": ["GPA低於 3.0", "未提交推薦信"],
        "warning_rules": [],
    }
    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.VERIFIED, "message": "ok"},
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=eligibility,
    )

    assert item.is_included is False
    assert "不符合獎學金規則" in item.exclusion_reason
    assert "GPA低於 3.0" in item.exclusion_reason
    assert "未提交推薦信" in item.exclusion_reason
    # rule_validation_result + failed_rules columns preserve the full snapshot
    assert item.rule_validation_result == eligibility
    assert item.failed_rules == ["GPA低於 3.0", "未提交推薦信"]


# ---------------------------------------------------------------------------
# application_identity snapshot — 新申請 vs 續領
# ---------------------------------------------------------------------------


def test_create_roster_item_application_identity_new(service: RosterService) -> None:
    """A non-renewal application (is_renewal=False OR no previous_application_id)
    gets the "{academic_year}新申請" tag — finance reads this on the payment
    voucher to mark first-time payments."""
    roster = _make_roster(academic_year=114)
    application = _make_application(
        academic_year=114,
        is_renewal=False,
        previous_application_id=None,
    )

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.application_identity == "114新申請"


def test_create_roster_item_application_identity_renewal(service: RosterService) -> None:
    """A renewal (is_renewal=True AND previous_application_id set) gets
    the "{academic_year}續領" tag. Both flags must be true — a stray
    is_renewal=True with no previous_application_id falls back to 新申請
    rather than mislabeling."""
    roster = _make_roster(academic_year=114)
    application = _make_application(
        academic_year=114,
        is_renewal=True,
        previous_application_id=42,
    )

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.application_identity == "114續領"


def test_create_roster_item_renewal_flag_without_previous_id_is_new(service: RosterService) -> None:
    """Defensive: is_renewal=True but previous_application_id=None means
    the renewal data is incomplete. Fall back to 新申請 rather than emitting
    a misleading 續領 label. Pins the AND-of-both-conditions branch."""
    roster = _make_roster(academic_year=114)
    application = _make_application(
        academic_year=114,
        is_renewal=True,
        previous_application_id=None,
    )

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.application_identity == "114新申請"


# ---------------------------------------------------------------------------
# Misc field-mapping sanity checks
# ---------------------------------------------------------------------------


def test_create_roster_item_uses_application_amount_when_set(service: RosterService) -> None:
    """`scholarship_amount = application.amount or config.amount` — per-application
    amount overrides the config default. Pin: if amount is set, it wins."""
    roster = _make_roster()
    application = _make_application(amount=12345, config_amount=99999)

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.scholarship_amount == 12345


def test_create_roster_item_falls_back_to_config_amount_when_app_amount_none(service: RosterService) -> None:
    """If application.amount is falsy, fall back to the configuration's
    default amount. Without this, monthly auto-renewals (where amount is
    pre-filled to None) would silently produce a 0-amount roster row."""
    roster = _make_roster()
    application = _make_application(amount=None, config_amount=50000)

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert item.scholarship_amount == 50000


def test_create_roster_item_db_add_called_once(service: RosterService) -> None:
    """The contract includes the side-effect of calling `self.db.add(item)`
    so the caller's commit picks up the new row. Without this side-effect
    the generated PaymentRosterItem would never persist."""
    roster = _make_roster()
    application = _make_application()

    item = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    service.db.add.assert_called_once_with(item)


def test_create_roster_item_verification_at_set_when_result_present(service: RosterService) -> None:
    """When a verification_result is provided, verification_at is stamped
    with `datetime.now(UTC)`. When verification_result is None (e.g.
    student_verification_enabled=False), verification_at stays None so
    audit logs don't lie about a verification that never happened."""
    roster = _make_roster()
    application = _make_application()

    with_result = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result={"status": StudentVerificationStatus.VERIFIED, "message": "ok"},
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )
    without_result = service._create_roster_item(
        roster=roster,
        application=application,
        verification_result=None,
        verification_status=StudentVerificationStatus.VERIFIED,
        eligibility_result=None,
    )

    assert with_result.verification_at is not None
    assert with_result.verification_at.tzinfo == timezone.utc
    # Sanity: very recent
    delta = datetime.now(timezone.utc) - with_result.verification_at
    assert delta.total_seconds() < 60

    assert without_result.verification_at is None
