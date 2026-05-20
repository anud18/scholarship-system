"""Unit tests for StudentScholarshipHistoryService helpers."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.core.exceptions import NotFoundError
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import ScholarshipConfiguration
from app.models.user import User, UserRole, UserType
from app.schemas.student_scholarship_history import AcademicInfo, PaymentRecord
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)


def _record(name: str, amount: str, period: str = "114-10") -> PaymentRecord:
    return PaymentRecord(
        roster_id=1,
        roster_code="ROSTER-X",
        period_label=period,
        academic_year=114,
        roster_cycle="monthly",
        scholarship_name=name,
        scholarship_amount=Decimal(amount),
    )


class TestBuildSummary:
    def test_empty_records_yields_zero_summary(self):
        svc = StudentScholarshipHistoryService()
        result = svc._build_summary([], snapshot_name=None)
        assert result.total_records == 0
        assert result.total_amount == Decimal("0")
        assert result.scholarship_type_count == 0
        assert result.snapshot_name is None

    def test_counts_records_and_sums_amounts(self):
        svc = StudentScholarshipHistoryService()
        records = [_record("A", "1000"), _record("A", "2000"), _record("B", "500")]
        result = svc._build_summary(records, snapshot_name="王小明")
        assert result.total_records == 3
        assert result.total_amount == Decimal("3500")
        assert result.scholarship_type_count == 2  # A and B
        assert result.snapshot_name == "王小明"

    def test_scholarship_type_count_dedupes_by_name(self):
        svc = StudentScholarshipHistoryService()
        records = [_record("國科會", "100"), _record("國科會", "100"), _record("國科會", "100")]
        result = svc._build_summary(records, snapshot_name=None)
        assert result.scholarship_type_count == 1


class TestBuildAcademicInfo:
    def test_none_sis_data_marks_unavailable(self):
        svc = StudentScholarshipHistoryService()
        result = svc._build_academic_info(None, error_message="SIS timeout")
        assert isinstance(result, AcademicInfo)
        assert result.available is False
        assert result.error == "SIS timeout"
        assert result.basic_info is None

    def test_valid_sis_data_extracts_basic_info(self):
        svc = StudentScholarshipHistoryService()
        sis = {
            "std_cname": "王小明",
            "std_ename": "Wang",
            "std_degree": "1",
            "std_studingstatus": "在學",
            "std_aca_cname": "電機學院",
            "std_depname": "電子博士班",
            "std_depno": "4460",
            "com_email": "wang@nycu.edu.tw",
            "irrelevant_field": "ignored",
        }
        result = svc._build_academic_info(sis, error_message=None)
        assert result.available is True
        assert result.error is None
        assert result.basic_info is not None
        assert result.basic_info.std_cname == "王小明"
        assert result.basic_info.std_degree == "1"
        assert result.basic_info.com_email == "wang@nycu.edu.tw"

    def test_coerces_int_sis_fields_to_str(self):
        """SIS sometimes returns std_degree/std_studingstatus as ints — coerce to str."""
        svc = StudentScholarshipHistoryService()
        sis = {"std_cname": "王小明", "std_degree": 1, "std_studingstatus": 2}
        result = svc._build_academic_info(sis, error_message=None)
        assert result.available is True
        assert result.basic_info.std_degree == "1"
        assert result.basic_info.std_studingstatus == "2"


@pytest_asyncio.fixture
async def seeded_rosters(db):
    """Seed: 1 admin + 1 config + 3 rosters with mixed status/included for stdcodes S001/S002."""
    from app.models.scholarship import ScholarshipType

    admin = User(
        nycu_id="adminseed",
        name="Admin Seed",
        email="adminseed@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.flush()

    stype = ScholarshipType(
        code="TEST",
        name="Test Scholarship",
    )
    db.add(stype)
    await db.flush()

    cfg = ScholarshipConfiguration(
        config_code="TEST-001",
        config_name="Test Config",
        is_active=True,
        scholarship_type_id=stype.id,
        academic_year=114,
        amount=10000,
    )
    db.add(cfg)
    await db.flush()

    def make_roster(period: str, year: int, status: RosterStatus) -> PaymentRoster:
        roster = PaymentRoster(
            roster_code=f"ROSTER-{year}-{period}-{cfg.config_code}",
            scholarship_configuration_id=cfg.id,
            period_label=period,
            academic_year=year,
            roster_cycle=RosterCycle.MONTHLY,
            status=status,
            trigger_type=RosterTriggerType.MANUAL,
            created_by=admin.id,
            locked_at=datetime.now(timezone.utc) if status == RosterStatus.LOCKED else None,
        )
        db.add(roster)
        return roster

    roster_a = make_roster("114-10", 114, RosterStatus.LOCKED)
    roster_b = make_roster("114-09", 114, RosterStatus.LOCKED)
    roster_c = make_roster("114-08", 114, RosterStatus.DRAFT)
    await db.flush()

    def make_item(roster, stdcode: str, name: str, amount: str, included: bool = True):
        item = PaymentRosterItem(
            roster_id=roster.id,
            application_id=1,  # placeholder — SQLite test DB doesn't enforce FK
            student_id_number=stdcode,
            student_name="王小明",
            scholarship_name=name,
            scholarship_amount=amount,
            verification_status=StudentVerificationStatus.VERIFIED,
            is_included=included,
        )
        db.add(item)
        return item

    make_item(roster_a, "S001", "國科會", "10000")
    make_item(roster_a, "S001", "MOE", "5000")
    make_item(roster_b, "S001", "國科會", "999", included=False)  # excluded → filter
    make_item(roster_c, "S001", "國科會", "888")  # draft → filter
    make_item(roster_a, "S002", "國科會", "777")  # different student → filter
    await db.commit()


@pytest.mark.asyncio
async def test_fetch_locked_payments_returns_only_locked_and_included(db, seeded_rosters):
    """Service must filter status=LOCKED AND is_included=TRUE AND matching student_id_number."""
    svc = StudentScholarshipHistoryService()
    records, snapshot_name = await svc._fetch_locked_payments(db, "S001")

    assert len(records) == 2
    # Sort: most-recent first — both items live on roster_a (114-10)
    assert {r.scholarship_name for r in records} == {"國科會", "MOE"}
    assert all(r.period_label == "114-10" for r in records)
    assert all(r.academic_year == 114 for r in records)
    assert sum(r.scholarship_amount for r in records) == Decimal("15000")
    assert snapshot_name == "王小明"


@pytest.mark.asyncio
async def test_fetch_locked_payments_returns_empty_for_unknown_student(db, seeded_rosters):
    svc = StudentScholarshipHistoryService()
    records, snapshot_name = await svc._fetch_locked_payments(db, "NOBODY")
    assert records == []
    assert snapshot_name is None


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_raises_not_found_when_sis_fails_and_no_payments(self, db):
        """Both SIS error AND empty payment list → NotFoundError."""
        svc = StudentScholarshipHistoryService()
        with patch.object(svc, "_fetch_locked_payments", new=AsyncMock(return_value=([], None))):
            with patch("app.services.student_scholarship_history_service.StudentService") as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(side_effect=Exception("SIS down"))
                with pytest.raises(NotFoundError):
                    await svc.get_history(db, "DOES_NOT_EXIST")

    @pytest.mark.asyncio
    async def test_returns_data_when_sis_fails_but_payments_exist(self, db):
        """SIS error but payments present → returns data with academic_info.available=False."""
        svc = StudentScholarshipHistoryService()
        sample_records = [
            PaymentRecord(
                roster_id=1,
                roster_code="R",
                period_label="114-10",
                academic_year=114,
                roster_cycle="monthly",
                scholarship_name="A",
                scholarship_amount=Decimal("1000"),
            )
        ]
        with patch.object(svc, "_fetch_locked_payments", new=AsyncMock(return_value=(sample_records, "王小明"))):
            with patch("app.services.student_scholarship_history_service.StudentService") as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(side_effect=Exception("SIS down"))
                result = await svc.get_history(db, "S001")
        assert result.academic_info.available is False
        assert "SIS down" in (result.academic_info.error or "")
        assert result.summary.total_records == 1
        assert result.summary.snapshot_name == "王小明"

    @pytest.mark.asyncio
    async def test_returns_full_data_when_both_succeed(self, db):
        svc = StudentScholarshipHistoryService()
        sample_records = [
            PaymentRecord(
                roster_id=1,
                roster_code="R",
                period_label="114-10",
                academic_year=114,
                roster_cycle="monthly",
                scholarship_name="A",
                scholarship_amount=Decimal("1000"),
            )
        ]
        with patch.object(svc, "_fetch_locked_payments", new=AsyncMock(return_value=(sample_records, "王小明"))):
            with patch("app.services.student_scholarship_history_service.StudentService") as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(
                    return_value={
                        "std_cname": "王小明",
                        "std_degree": "1",
                        "std_depname": "EE PhD",
                    }
                )
                result = await svc.get_history(db, "S001")
        assert result.academic_info.available is True
        assert result.academic_info.basic_info.std_cname == "王小明"
        assert result.payment_records[0].scholarship_name == "A"
        assert result.student_number == "S001"
