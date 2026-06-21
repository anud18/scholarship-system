"""
Regression: roster generation failures must surface the REAL reason.

Bug report: 造冊失敗時 UI 只顯示「產生造冊失敗: 造冊產生失敗」(generic), never the
actual cause (e.g. 找不到已執行分發的排名 / 尚未執行分發 / 造冊資料一致性驗證失敗).

Root cause: RosterService.generate_roster wraps every internal failure in
RosterGenerationError(...) preserving the original as __cause__ (a contract
pinned by test_roster_generate_concurrency). The endpoint handler
(_generate_payment_roster_inner) caught RosterGenerationError but raised a
hard-coded detail="造冊產生失敗", discarding the cause — so the curated reason
never reached the client.

Fix: the handler re-dispatches on e.__cause__ — surfacing the curated message +
correct HTTP status for known domain causes, staying generic for raw/unexpected
causes so internal detail (paths, SQL, SDK errors) never leaks
(test_no_exception_leak_in_endpoints pins that invariant).

These tests drive _generate_payment_roster_inner directly (the same approach
test_roster_generate_concurrency uses for the service) and assert on the raised
HTTPException's status_code + detail — the observable client-facing contract.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.payment_rosters import _generate_payment_roster_inner
from app.core.exceptions import RosterGenerationError
from app.models.enums import QuotaManagementMode, Semester
from app.models.payment_roster import PaymentRoster, RosterCycle, RosterStatus, RosterTriggerType
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.schemas.roster import RosterCreateRequest

pytestmark = pytest.mark.integration


@pytest.fixture
def patch_dependencies():
    """No-op SIS verification + audit emits (mirrors the roster test suites)."""
    with (
        patch("app.services.roster_service.StudentVerificationService") as svs,
        patch("app.services.roster_service.audit_service"),
    ):
        svs.return_value.verify_student.return_value = {"status": "verified", "verified": True, "data": {}}
        yield


def _admin(db_sync) -> User:
    u = User(
        nycu_id="roster_err_admin",
        email="roster_err_admin@nycu.edu.tw",
        name="Roster Err Admin",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.commit()
    db_sync.refresh(u)
    return u


def _scholarship(db_sync) -> ScholarshipType:
    s = ScholarshipType(code="roster_err_sch", name="Roster Err Scholarship", description="x")
    db_sync.add(s)
    db_sync.commit()
    db_sync.refresh(s)
    return s


def _config(db_sync, scholarship, *, quota_mode=QuotaManagementMode.simple) -> ScholarshipConfiguration:
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code="RE-113-1",
        config_name="Roster Err Config",
        academic_year=113,
        semester=Semester.first,
        quota_management_mode=quota_mode,
        has_quota_limit=False,
        amount=50000,
    )
    db_sync.add(c)
    db_sync.commit()
    db_sync.refresh(c)
    return c


def _request(config, **overrides) -> RosterCreateRequest:
    base = dict(
        scholarship_configuration_id=config.id,
        period_label="113-1",
        roster_cycle=RosterCycle.MONTHLY,
        academic_year=113,
        student_verification_enabled=False,
        ranking_id=None,
        auto_export_excel=False,
        force_regenerate=False,
    )
    base.update(overrides)
    return RosterCreateRequest(**base)


def test_matrix_no_executed_ranking_surfaces_reason(db_sync, patch_dependencies):
    """Matrix config with no executed ranking → the service raises
    ValueError('找不到已執行分發的排名…'); the endpoint must surface THAT reason
    (400), not the opaque「造冊產生失敗」."""
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _config(db_sync, sch, quota_mode=QuotaManagementMode.matrix_based)

    with pytest.raises(HTTPException) as ei:
        _generate_payment_roster_inner(_request(cfg), db_sync, admin)

    assert ei.value.status_code == 400
    assert "找不到已執行分發的排名" in ei.value.detail
    assert ei.value.detail != "造冊產生失敗"


def test_duplicate_roster_surfaces_already_exists_as_409(db_sync, patch_dependencies):
    """A second generation for the same (config, period) → the service raises
    RosterAlreadyExistsError (wrapped); the endpoint must translate __cause__ to
    409 with the real 'already exists' reason, not a generic 500."""
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _config(db_sync, sch)
    # Pre-create the existing roster row directly (no need to run a full success).
    existing = PaymentRoster(
        roster_code="ROSTER-113-113-1-RE-113-1",
        scholarship_configuration_id=cfg.id,
        period_label="113-1",
        academic_year=113,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.COMPLETED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
    )
    db_sync.add(existing)
    db_sync.commit()

    with pytest.raises(HTTPException) as ei:
        _generate_payment_roster_inner(_request(cfg), db_sync, admin)

    assert ei.value.status_code == 409
    assert "already exists" in ei.value.detail.lower()


_SECRET = "secret-internal-token-/app/backend/exports/x.xlsx"


@pytest.mark.parametrize(
    "raw",
    [
        OSError(f"[Errno 13] Permission denied: '{_SECRET}'"),  # chmod/exports class
        KeyError(_SECRET),  # missing internal key
        RuntimeError(f"connection to db://{_SECRET} failed"),  # generic infra error
        Exception(f"boom {_SECRET}"),  # bare unexpected
    ],
    ids=["oserror", "keyerror", "runtimeerror", "exception"],
)
def test_raw_cause_stays_generic_no_leak(db_sync, patch_dependencies, raw):
    """SECURITY: when the wrapped cause is a RAW exception (the chmod/exports
    class of failure, a DB/infra error, an unexpected bug), the detail must stay
    the generic「造冊產生失敗」and must NOT echo the internal message. This is the
    behavioural guard against a future edit adding an isinstance branch for a raw
    type — stronger than the AST name-check in test_no_exception_leak_in_endpoints,
    which would miss `detail=str(cause)`."""
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    cfg = _config(db_sync, sch)

    wrapped = RosterGenerationError(f"Failed to generate roster: {raw}")
    wrapped.__cause__ = raw  # model the service's `raise RosterGenerationError(...) from raw`

    with patch(
        "app.api.v1.endpoints.payment_rosters.RosterService.generate_roster",
        side_effect=wrapped,
    ):
        with pytest.raises(HTTPException) as ei:
            _generate_payment_roster_inner(_request(cfg), db_sync, admin)

    assert ei.value.status_code == 500
    assert ei.value.detail == "造冊產生失敗"
    assert _SECRET not in ei.value.detail
