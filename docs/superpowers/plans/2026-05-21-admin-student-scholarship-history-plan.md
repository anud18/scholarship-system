# Admin Student Scholarship History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a single-student scholarship history lookup tool inside the admin shell — input 學號, see academic info + every locked payment roster record for that student, with totals.

**Architecture:** One backend endpoint `GET /api/v1/admin/student-history/{student_number}` returns `{ academic_info, summary, payment_records[] }`. The endpoint fans out to SIS API + a single SQL query against locked payment rosters. Frontend adds a new tab `學生領取歷史` to `AdminManagementShell` that mounts a new `StudentHistoryPanel` (input + 3 sub-components).

**Tech Stack:** FastAPI + SQLAlchemy AsyncSession + Pydantic v2 (backend); Next.js + React Query + shadcn/ui Tabs/Card/Table (frontend); pytest + httpx async client (backend tests); Playwright (e2e).

**Reference spec:** `docs/superpowers/specs/2026-05-21-admin-student-scholarship-history-design.md`

---

## File Structure Summary

**Backend — Create:**
- `backend/app/schemas/student_scholarship_history.py` — Pydantic response models
- `backend/app/services/student_scholarship_history_service.py` — fetch + assemble logic
- `backend/app/api/v1/endpoints/admin/student_history.py` — single GET endpoint
- `backend/app/tests/test_student_scholarship_history_service.py` — service unit tests
- `backend/app/tests/test_admin_student_history_endpoint.py` — endpoint integration tests

**Backend — Modify:**
- `backend/app/api/v1/endpoints/admin/__init__.py` — register the new sub-router
- `backend/app/api/v1/api.py` — (no change needed — `admin.router` is already mounted at `/admin`)

**Frontend — Create:**
- `frontend/lib/api/modules/student-history.ts` — API client module
- `frontend/components/admin/student-history/StudentHistoryPanel.tsx` — top-level panel
- `frontend/components/admin/student-history/AcademicInfoCard.tsx` — academic display + SIS warning
- `frontend/components/admin/student-history/SummaryCards.tsx` — three KPI cards
- `frontend/components/admin/student-history/PaymentHistoryTable.tsx` — flat table
- `frontend/e2e/specs/admin-student-history.spec.ts` — Playwright test

**Frontend — Modify:**
- `frontend/lib/api/index.ts` — register `studentHistory` getter on `ExtendedApiClient`
- `frontend/lib/api/generated/schema.d.ts` — regenerated from OpenAPI (auto)
- `frontend/components/admin/AdminManagementShell.tsx` — add new tab trigger + content

---

## Task 1: Backend response schemas

**Files:**
- Create: `backend/app/schemas/student_scholarship_history.py`

- [ ] **Step 1: Create the Pydantic models**

```python
"""Response schemas for admin student scholarship history endpoint."""

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field


class AcademicBasicInfo(BaseModel):
    """SIS basic info subset rendered on the page."""

    std_cname: Optional[str] = None
    std_ename: Optional[str] = None
    std_degree: Optional[str] = None  # "1"=博士, "2"=碩士, "3"=學士
    std_studingstatus: Optional[str] = None
    std_aca_cname: Optional[str] = None
    std_depname: Optional[str] = None
    std_depno: Optional[str] = None
    com_email: Optional[str] = None


class AcademicInfo(BaseModel):
    """Wraps SIS lookup result. available=False when SIS errored."""

    available: bool
    error: Optional[str] = None
    basic_info: Optional[AcademicBasicInfo] = None


class PaymentRecord(BaseModel):
    """One locked roster item belonging to the student."""

    roster_id: int
    roster_code: str
    period_label: str
    academic_year: int
    roster_cycle: str  # monthly / semi_yearly / yearly
    scholarship_name: str
    scholarship_amount: Decimal
    scholarship_subtype: Optional[str] = None
    allocation_year: Optional[int] = None
    locked_at: Optional[datetime] = None


class HistorySummary(BaseModel):
    """Aggregates across all payment_records."""

    total_records: int
    total_amount: Decimal
    scholarship_type_count: int = Field(
        ..., description="Number of distinct scholarship_name values"
    )
    snapshot_name: Optional[str] = Field(
        None,
        description="Student name from the most recent roster item; used when SIS fails",
    )


class StudentScholarshipHistoryData(BaseModel):
    """Full response payload (data of the ApiResponse envelope)."""

    student_number: str
    academic_info: AcademicInfo
    summary: HistorySummary
    payment_records: List[PaymentRecord]
```

- [ ] **Step 2: Verify file compiles**

Run: `cd backend && python -c "from app.schemas.student_scholarship_history import StudentScholarshipHistoryData; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/student_scholarship_history.py
git commit -m "feat: add Pydantic schemas for admin student scholarship history"
```

---

## Task 2: Backend service — `_build_summary` (pure helper, TDD)

**Files:**
- Create: `backend/app/services/student_scholarship_history_service.py`
- Test: `backend/app/tests/test_student_scholarship_history_service.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_student_scholarship_history_service.py` with:

```python
"""Unit tests for StudentScholarshipHistoryService helpers."""

from decimal import Decimal

from app.schemas.student_scholarship_history import PaymentRecord
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py::TestBuildSummary -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.student_scholarship_history_service'`

- [ ] **Step 3: Write minimal implementation**

Create `backend/app/services/student_scholarship_history_service.py`:

```python
"""Service: assemble admin student scholarship history (academic + payments)."""

from decimal import Decimal
from typing import List, Optional

from app.schemas.student_scholarship_history import HistorySummary, PaymentRecord


class StudentScholarshipHistoryService:
    """Orchestrates SIS lookup and locked-roster payment retrieval."""

    def _build_summary(
        self,
        records: List[PaymentRecord],
        snapshot_name: Optional[str],
    ) -> HistorySummary:
        total_amount = sum((r.scholarship_amount for r in records), Decimal("0"))
        type_count = len({r.scholarship_name for r in records})
        return HistorySummary(
            total_records=len(records),
            total_amount=total_amount,
            scholarship_type_count=type_count,
            snapshot_name=snapshot_name,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py::TestBuildSummary -v`
Expected: PASS — 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/student_scholarship_history_service.py \
        backend/app/tests/test_student_scholarship_history_service.py
git commit -m "feat: add StudentScholarshipHistoryService._build_summary helper"
```

---

## Task 3: Backend service — `_build_academic_info` (TDD)

**Files:**
- Modify: `backend/app/services/student_scholarship_history_service.py`
- Modify: `backend/app/tests/test_student_scholarship_history_service.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/app/tests/test_student_scholarship_history_service.py`:

```python
from app.schemas.student_scholarship_history import AcademicInfo


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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py::TestBuildAcademicInfo -v`
Expected: FAIL with `AttributeError: 'StudentScholarshipHistoryService' object has no attribute '_build_academic_info'`

- [ ] **Step 3: Add the method to the service**

In `backend/app/services/student_scholarship_history_service.py`, update imports and add the method:

```python
from decimal import Decimal
from typing import Any, Dict, List, Optional

from app.schemas.student_scholarship_history import (
    AcademicBasicInfo,
    AcademicInfo,
    HistorySummary,
    PaymentRecord,
)


class StudentScholarshipHistoryService:
    """Orchestrates SIS lookup and locked-roster payment retrieval."""

    _BASIC_INFO_FIELDS = {
        "std_cname",
        "std_ename",
        "std_degree",
        "std_studingstatus",
        "std_aca_cname",
        "std_depname",
        "std_depno",
        "com_email",
    }

    def _build_academic_info(
        self,
        sis_data: Optional[Dict[str, Any]],
        error_message: Optional[str],
    ) -> AcademicInfo:
        if not sis_data:
            return AcademicInfo(available=False, error=error_message, basic_info=None)
        subset = {k: sis_data.get(k) for k in self._BASIC_INFO_FIELDS}
        return AcademicInfo(
            available=True,
            error=None,
            basic_info=AcademicBasicInfo(**subset),
        )

    def _build_summary(
        self,
        records: List[PaymentRecord],
        snapshot_name: Optional[str],
    ) -> HistorySummary:
        total_amount = sum((r.scholarship_amount for r in records), Decimal("0"))
        type_count = len({r.scholarship_name for r in records})
        return HistorySummary(
            total_records=len(records),
            total_amount=total_amount,
            scholarship_type_count=type_count,
            snapshot_name=snapshot_name,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py -v`
Expected: PASS — 5 tests pass (3 build_summary + 2 build_academic_info).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/student_scholarship_history_service.py \
        backend/app/tests/test_student_scholarship_history_service.py
git commit -m "feat: add _build_academic_info helper to scholarship history service"
```

---

## Task 4: Backend service — `_fetch_locked_payments` query (TDD with real DB)

**Files:**
- Modify: `backend/app/services/student_scholarship_history_service.py`
- Modify: `backend/app/tests/test_student_scholarship_history_service.py`

- [ ] **Step 1: Append failing test**

Append to `backend/app/tests/test_student_scholarship_history_service.py`:

```python
import pytest
import pytest_asyncio
from datetime import datetime, timezone

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


@pytest_asyncio.fixture
async def seeded_rosters(db):
    """Seed: 1 admin + 1 config + 3 rosters with mixed status/included for stdcodes S001/S002."""
    admin = User(
        nycu_id="adminseed",
        name="Admin Seed",
        email="adminseed@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.flush()

    cfg = ScholarshipConfiguration(
        config_code="TEST-001",
        config_name="Test Config",
        is_active=True,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py::test_fetch_locked_payments_returns_only_locked_and_included -v`
Expected: FAIL with `AttributeError: 'StudentScholarshipHistoryService' object has no attribute '_fetch_locked_payments'`

- [ ] **Step 3: Implement `_fetch_locked_payments`**

Add to `backend/app/services/student_scholarship_history_service.py` — extend imports and add the method. The method returns `(records, snapshot_name)` so callers can show a name fallback when SIS fails.

```python
from typing import Tuple  # add to existing typing imports

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus


class StudentScholarshipHistoryService:
    # ... existing _build_academic_info, _build_summary ...

    async def _fetch_locked_payments(
        self,
        db: AsyncSession,
        student_number: str,
    ) -> Tuple[List[PaymentRecord], Optional[str]]:
        stmt = (
            select(PaymentRosterItem, PaymentRoster)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .where(
                PaymentRosterItem.student_id_number == student_number,
                PaymentRosterItem.is_included.is_(True),
                PaymentRoster.status == RosterStatus.LOCKED,
            )
            .order_by(
                PaymentRoster.academic_year.desc(),
                PaymentRoster.period_label.desc(),
            )
        )
        result = await db.execute(stmt)
        rows = result.all()
        records = [
            PaymentRecord(
                roster_id=roster.id,
                roster_code=roster.roster_code,
                period_label=roster.period_label,
                academic_year=roster.academic_year,
                roster_cycle=roster.roster_cycle.value,
                scholarship_name=item.scholarship_name,
                scholarship_amount=item.scholarship_amount,
                scholarship_subtype=item.scholarship_subtype,
                allocation_year=item.allocation_year,
                locked_at=roster.locked_at,
            )
            for item, roster in rows
        ]
        snapshot_name = rows[0][0].student_name if rows else None
        return records, snapshot_name
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py -v`
Expected: PASS — both new tests pass plus the earlier ones.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/student_scholarship_history_service.py \
        backend/app/tests/test_student_scholarship_history_service.py
git commit -m "feat: add _fetch_locked_payments query to scholarship history service"
```

---

## Task 5: Backend service — `get_history` orchestrator (TDD)

**Files:**
- Modify: `backend/app/services/student_scholarship_history_service.py`
- Modify: `backend/app/tests/test_student_scholarship_history_service.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/app/tests/test_student_scholarship_history_service.py`:

```python
from unittest.mock import AsyncMock, patch

from app.core.exceptions import NotFoundError


class TestGetHistory:
    @pytest.mark.asyncio
    async def test_raises_not_found_when_sis_fails_and_no_payments(self, async_db):
        """Both SIS error AND empty payment list → NotFoundError."""
        svc = StudentScholarshipHistoryService()
        with patch.object(svc, "_fetch_locked_payments", new=AsyncMock(return_value=([], None))):
            with patch(
                "app.services.student_scholarship_history_service.StudentService"
            ) as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(
                    side_effect=Exception("SIS down")
                )
                async with async_db() as session:
                    with pytest.raises(NotFoundError):
                        await svc.get_history(session, "DOES_NOT_EXIST")

    @pytest.mark.asyncio
    async def test_returns_data_when_sis_fails_but_payments_exist(self, async_db):
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
        with patch.object(
            svc, "_fetch_locked_payments", new=AsyncMock(return_value=(sample_records, "王小明"))
        ):
            with patch(
                "app.services.student_scholarship_history_service.StudentService"
            ) as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(
                    side_effect=Exception("SIS down")
                )
                async with async_db() as session:
                    result = await svc.get_history(session, "S001")
                assert result.academic_info.available is False
                assert "SIS down" in (result.academic_info.error or "")
                assert result.summary.total_records == 1
                assert result.summary.snapshot_name == "王小明"

    @pytest.mark.asyncio
    async def test_returns_full_data_when_both_succeed(self, async_db):
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
        with patch.object(
            svc, "_fetch_locked_payments", new=AsyncMock(return_value=(sample_records, "王小明"))
        ):
            with patch(
                "app.services.student_scholarship_history_service.StudentService"
            ) as MockStudent:
                MockStudent.return_value.get_student_basic_info = AsyncMock(
                    return_value={
                        "std_cname": "王小明",
                        "std_degree": "1",
                        "std_depname": "EE PhD",
                    }
                )
                async with async_db() as session:
                    result = await svc.get_history(session, "S001")
                assert result.academic_info.available is True
                assert result.academic_info.basic_info.std_cname == "王小明"
                assert result.payment_records[0].scholarship_name == "A"
                assert result.student_number == "S001"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py::TestGetHistory -v`
Expected: FAIL with `AttributeError: 'StudentScholarshipHistoryService' object has no attribute 'get_history'`

- [ ] **Step 3: Implement `get_history`**

Add to `backend/app/services/student_scholarship_history_service.py`:

```python
import logging

from app.core.exceptions import NotFoundError
from app.schemas.student_scholarship_history import StudentScholarshipHistoryData
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)


class StudentScholarshipHistoryService:
    # ... existing helpers ...

    async def get_history(
        self,
        db: AsyncSession,
        student_number: str,
    ) -> StudentScholarshipHistoryData:
        """Orchestrate SIS lookup + locked-payment retrieval. Raises NotFoundError
        when both sources are empty."""
        sis_error: Optional[str] = None
        sis_data: Optional[Dict[str, Any]] = None
        try:
            sis_data = await StudentService().get_student_basic_info(student_number)
        except Exception as exc:  # noqa: BLE001 — tolerate any SIS failure
            logger.warning(
                "SIS lookup failed for student %s: %s", student_number, exc
            )
            sis_error = str(exc)

        records, snapshot_name = await self._fetch_locked_payments(db, student_number)

        academic_info = self._build_academic_info(sis_data, error_message=sis_error)

        if not academic_info.available and not records:
            raise NotFoundError(f"查無此學生資料: {student_number}")

        summary = self._build_summary(records, snapshot_name=snapshot_name)
        return StudentScholarshipHistoryData(
            student_number=student_number,
            academic_info=academic_info,
            summary=summary,
            payment_records=records,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest app/tests/test_student_scholarship_history_service.py -v`
Expected: PASS — all tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/student_scholarship_history_service.py \
        backend/app/tests/test_student_scholarship_history_service.py
git commit -m "feat: add get_history orchestrator for scholarship history service"
```

---

## Task 6: Backend endpoint (TDD)

**Files:**
- Create: `backend/app/api/v1/endpoints/admin/student_history.py`
- Modify: `backend/app/api/v1/endpoints/admin/__init__.py`
- Create: `backend/app/tests/test_admin_student_history_endpoint.py`

- [ ] **Step 1: Write the failing endpoint test**

Create `backend/app/tests/test_admin_student_history_endpoint.py`:

```python
"""Integration tests for GET /api/v1/admin/student-history/{student_number}.

Auth pattern follows test_admin_endpoints.py — overrides require_admin per test
class. The conftest `client` fixture is unauthenticated; the conftest
`admin_client` only sets a header (no dependency override), so we wire our own.
"""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def authed_admin_client(client, admin_user):
    """AsyncClient with require_admin overridden to return the mock admin_user."""
    from app.core.security import require_admin
    from app.main import app

    async def override_require_admin():
        return admin_user

    app.dependency_overrides[require_admin] = override_require_admin
    yield client
    del app.dependency_overrides[require_admin]


@pytest.mark.asyncio
async def test_invalid_student_number_format_returns_400(authed_admin_client):
    """Invalid chars in path → 400 from regex validation."""
    response = await authed_admin_client.get("/api/v1/admin/student-history/bad@@chars")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_nonexistent_student_returns_404(authed_admin_client):
    """No SIS data + no roster records → 404."""
    from app.core.exceptions import NotFoundError

    with patch(
        "app.api.v1.endpoints.admin.student_history.StudentScholarshipHistoryService"
    ) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(
            side_effect=NotFoundError("查無此學生資料: GHOST")
        )
        response = await authed_admin_client.get("/api/v1/admin/student-history/GHOST1")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_valid_student_returns_wrapped_api_response(authed_admin_client):
    """Successful path returns ApiResponse-wrapped data per CLAUDE.md §5."""
    from decimal import Decimal

    from app.schemas.student_scholarship_history import (
        AcademicInfo,
        HistorySummary,
        PaymentRecord,
        StudentScholarshipHistoryData,
    )

    fake_data = StudentScholarshipHistoryData(
        student_number="S001",
        academic_info=AcademicInfo(available=True, basic_info=None),
        summary=HistorySummary(
            total_records=1,
            total_amount=Decimal("1000"),
            scholarship_type_count=1,
            snapshot_name="王小明",
        ),
        payment_records=[
            PaymentRecord(
                roster_id=1,
                roster_code="R",
                period_label="114-10",
                academic_year=114,
                roster_cycle="monthly",
                scholarship_name="A",
                scholarship_amount=Decimal("1000"),
            )
        ],
    )

    with patch(
        "app.api.v1.endpoints.admin.student_history.StudentScholarshipHistoryService"
    ) as MockSvc:
        MockSvc.return_value.get_history = AsyncMock(return_value=fake_data)
        response = await authed_admin_client.get("/api/v1/admin/student-history/S001")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["student_number"] == "S001"
    assert body["data"]["summary"]["total_records"] == 1
    assert body["data"]["payment_records"][0]["scholarship_name"] == "A"


@pytest.mark.asyncio
async def test_unauthenticated_returns_401_or_403(client):
    """Bare client (no admin override) → require_admin rejects."""
    response = await client.get("/api/v1/admin/student-history/S001")
    assert response.status_code in (401, 403)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest app/tests/test_admin_student_history_endpoint.py -v`
Expected: FAIL — endpoint doesn't exist; mostly 404 responses.

- [ ] **Step 3: Create the endpoint**

Create `backend/app/api/v1/endpoints/admin/student_history.py`:

```python
"""Admin endpoint: GET /admin/student-history/{student_number}."""

import logging
import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.security import require_admin
from app.db.deps import get_db
from app.models.user import User
from app.services.student_scholarship_history_service import (
    StudentScholarshipHistoryService,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_STUDENT_NUMBER_PATTERN = re.compile(r"^[A-Za-z0-9]{4,15}$")


@router.get("/{student_number}")
async def get_student_scholarship_history(
    student_number: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Single-student scholarship history lookup. See spec for response shape."""
    if not _STUDENT_NUMBER_PATTERN.match(student_number):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="學號格式不正確",
        )

    service = StudentScholarshipHistoryService()
    try:
        data = await service.get_history(db, student_number)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    return {
        "success": True,
        "message": "Student history retrieved",
        "data": data.model_dump(mode="json"),
    }
```

- [ ] **Step 4: Register the new router**

Edit `backend/app/api/v1/endpoints/admin/__init__.py`:

After the existing import block, add:
```python
from .student_history import router as student_history_router
```

Inside the `router.include_router(...)` block, add (place near `students_router` for grouping):
```python
router.include_router(
    student_history_router,
    prefix="/student-history",
    tags=["Admin - Student History"],
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest app/tests/test_admin_student_history_endpoint.py -v`
Expected: PASS — 4 tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/admin/student_history.py \
        backend/app/api/v1/endpoints/admin/__init__.py \
        backend/app/tests/test_admin_student_history_endpoint.py
git commit -m "feat: add GET /admin/student-history/{student_number} endpoint"
```

---

## Task 7: Regenerate frontend OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (auto-generated)

- [ ] **Step 1: Start the backend if not running**

Run: `docker compose -f docker-compose.dev.yml up -d backend`
Wait for it to be healthy. Verify: `curl -s http://localhost:8000/openapi.json | python -c "import json, sys; d = json.load(sys.stdin); print('/api/v1/admin/student-history/{student_number}' in d['paths'])"`
Expected: `True`

- [ ] **Step 2: Regenerate types**

Run: `cd frontend && npm run api:generate`
Expected: command exits 0; `lib/api/generated/schema.d.ts` is updated.

- [ ] **Step 3: Verify the new path is in the generated schema**

Run: `grep -c "/api/v1/admin/student-history/" frontend/lib/api/generated/schema.d.ts`
Expected: nonzero count.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore: regenerate OpenAPI types for student-history endpoint"
```

---

## Task 8: Frontend API module

**Files:**
- Create: `frontend/lib/api/modules/student-history.ts`
- Modify: `frontend/lib/api/index.ts`

- [ ] **Step 1: Create the module**

Create `frontend/lib/api/modules/student-history.ts`:

```typescript
/**
 * Admin Student Scholarship History API Module
 *
 * Single-student lookup by 學號 — returns academic info + locked-roster payment records.
 */

import { typedClient } from "../typed-client";
import { toApiResponse } from "../compat";
import type { ApiResponse } from "../types";

export interface AcademicBasicInfo {
  std_cname: string | null;
  std_ename: string | null;
  std_degree: string | null;
  std_studingstatus: string | null;
  std_aca_cname: string | null;
  std_depname: string | null;
  std_depno: string | null;
  com_email: string | null;
}

export interface AcademicInfo {
  available: boolean;
  error: string | null;
  basic_info: AcademicBasicInfo | null;
}

export interface PaymentRecord {
  roster_id: number;
  roster_code: string;
  period_label: string;
  academic_year: number;
  roster_cycle: "monthly" | "semi_yearly" | "yearly";
  scholarship_name: string;
  scholarship_amount: string; // Decimal serialized as string
  scholarship_subtype: string | null;
  allocation_year: number | null;
  locked_at: string | null;
}

export interface HistorySummary {
  total_records: number;
  total_amount: string;
  scholarship_type_count: number;
  snapshot_name: string | null;
}

export interface StudentScholarshipHistoryData {
  student_number: string;
  academic_info: AcademicInfo;
  summary: HistorySummary;
  payment_records: PaymentRecord[];
}

export function createStudentHistoryApi() {
  return {
    async getByNumber(
      studentNumber: string,
    ): Promise<ApiResponse<StudentScholarshipHistoryData>> {
      const response = await typedClient.raw.GET(
        "/api/v1/admin/student-history/{student_number}",
        {
          params: { path: { student_number: studentNumber } },
        },
      );
      return toApiResponse<StudentScholarshipHistoryData>(response);
    },
  };
}
```

- [ ] **Step 2: Register on ExtendedApiClient**

Edit `frontend/lib/api/index.ts`:

After the existing `import { createManualDistributionApi } from './modules/manual-distribution';` line (or wherever other module imports live), add:
```typescript
import { createStudentHistoryApi } from './modules/student-history';
```

Inside `class ExtendedApiClient extends ApiClient`, in the private properties block, add (near the other private props):
```typescript
  private _studentHistory?: ReturnType<typeof createStudentHistoryApi>;
```

Then add a getter near the other getters:
```typescript
  get studentHistory(): ReturnType<typeof createStudentHistoryApi> {
    if (!this._studentHistory) this._studentHistory = createStudentHistoryApi();
    return this._studentHistory;
  }
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/modules/student-history.ts frontend/lib/api/index.ts
git commit -m "feat: add studentHistory API client module"
```

---

## Task 9: Frontend — AcademicInfoCard component

**Files:**
- Create: `frontend/components/admin/student-history/AcademicInfoCard.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { AlertCircle, GraduationCap } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { AcademicInfo } from "@/lib/api/modules/student-history";

interface AcademicInfoCardProps {
  academicInfo: AcademicInfo;
  snapshotName: string | null;
}

const DEGREE_LABEL: Record<string, string> = {
  "1": "博士",
  "2": "碩士",
  "3": "學士",
};

export function AcademicInfoCard({
  academicInfo,
  snapshotName,
}: AcademicInfoCardProps) {
  if (!academicInfo.available) {
    return (
      <Card className="border-yellow-500">
        <CardContent className="flex items-start gap-3 pt-6">
          <AlertCircle className="h-5 w-5 text-yellow-500 mt-0.5" />
          <div>
            <p className="font-medium text-yellow-700">無即時學籍資料</p>
            <p className="text-sm text-muted-foreground mt-1">
              {academicInfo.error ??
                "無法取得 SIS 即時學籍資料,以下顯示造冊時的姓名快照。"}
            </p>
            {snapshotName && (
              <p className="text-sm mt-2">
                <span className="text-muted-foreground">造冊快照姓名:</span>{" "}
                <span className="font-medium">{snapshotName}</span>
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  const info = academicInfo.basic_info;
  if (!info) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GraduationCap className="h-5 w-5" />
          學籍資料
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-sm font-medium text-muted-foreground">中文姓名</p>
            <p className="text-lg">{info.std_cname ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">英文姓名</p>
            <p className="text-lg">{info.std_ename ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">學位</p>
            <p>{info.std_degree ? DEGREE_LABEL[info.std_degree] ?? info.std_degree : "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">在學狀態</p>
            <p>{info.std_studingstatus ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">學院</p>
            <p>{info.std_aca_cname ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">系所</p>
            <p>{info.std_depname ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">系所代碼</p>
            <p className="font-mono">{info.std_depno ?? "N/A"}</p>
          </div>
          <div>
            <p className="text-sm font-medium text-muted-foreground">電子郵件</p>
            <p className="text-sm">{info.com_email ?? "N/A"}</p>
          </div>
        </div>
        <Separator className="my-3" />
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/student-history/AcademicInfoCard.tsx
git commit -m "feat: add AcademicInfoCard for student history panel"
```

---

## Task 10: Frontend — SummaryCards component

**Files:**
- Create: `frontend/components/admin/student-history/SummaryCards.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { Card, CardContent } from "@/components/ui/card";
import type { HistorySummary } from "@/lib/api/modules/student-history";

interface SummaryCardsProps {
  summary: HistorySummary;
}

function formatAmount(amount: string): string {
  const num = Number(amount);
  if (Number.isNaN(num)) return amount;
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(num);
}

export function SummaryCards({ summary }: SummaryCardsProps) {
  const items = [
    { label: "總筆數", value: summary.total_records.toString() },
    { label: "總金額", value: formatAmount(summary.total_amount) },
    { label: "獎學金類型數", value: summary.scholarship_type_count.toString() },
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      {items.map((it) => (
        <Card key={it.label}>
          <CardContent className="pt-6">
            <p className="text-sm font-medium text-muted-foreground">{it.label}</p>
            <p className="text-3xl font-semibold mt-1">{it.value}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/student-history/SummaryCards.tsx
git commit -m "feat: add SummaryCards for student history panel"
```

---

## Task 11: Frontend — PaymentHistoryTable component

**Files:**
- Create: `frontend/components/admin/student-history/PaymentHistoryTable.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { PaymentRecord } from "@/lib/api/modules/student-history";

interface PaymentHistoryTableProps {
  records: PaymentRecord[];
}

function formatAmount(amount: string): string {
  const num = Number(amount);
  if (Number.isNaN(num)) return amount;
  return new Intl.NumberFormat("zh-TW").format(num);
}

export function PaymentHistoryTable({ records }: PaymentHistoryTableProps) {
  if (records.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>領取明細</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">尚無領取記錄</p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>領取明細 ({records.length} 筆)</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>期間</TableHead>
              <TableHead>獎學金</TableHead>
              <TableHead>子類型</TableHead>
              <TableHead className="text-right">金額 (NT$)</TableHead>
              <TableHead>配額學年</TableHead>
              <TableHead>造冊號</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {records.map((r) => (
              <TableRow key={`${r.roster_id}-${r.scholarship_name}`}>
                <TableCell className="font-mono">{r.period_label}</TableCell>
                <TableCell>{r.scholarship_name}</TableCell>
                <TableCell>{r.scholarship_subtype ?? "—"}</TableCell>
                <TableCell className="text-right font-mono">
                  {formatAmount(r.scholarship_amount)}
                </TableCell>
                <TableCell>{r.allocation_year ?? "—"}</TableCell>
                <TableCell className="font-mono text-xs">{r.roster_code}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/student-history/PaymentHistoryTable.tsx
git commit -m "feat: add PaymentHistoryTable for student history panel"
```

---

## Task 12: Frontend — StudentHistoryPanel (top-level composition)

**Files:**
- Create: `frontend/components/admin/student-history/StudentHistoryPanel.tsx`

- [ ] **Step 1: Create the component**

```tsx
"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, Loader2 } from "lucide-react";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiClient } from "@/lib/api";

import { AcademicInfoCard } from "./AcademicInfoCard";
import { SummaryCards } from "./SummaryCards";
import { PaymentHistoryTable } from "./PaymentHistoryTable";

const STUDENT_NUMBER_REGEX = /^[A-Za-z0-9]{4,15}$/;

export function StudentHistoryPanel() {
  const [input, setInput] = useState("");
  const [submitted, setSubmitted] = useState<string | null>(null);
  const [inputError, setInputError] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["admin", "student-history", submitted],
    enabled: submitted !== null,
    queryFn: async () => {
      const response = await apiClient.studentHistory.getByNumber(submitted!);
      if (!response.success) {
        throw new Error(response.message || "查詢失敗");
      }
      return response.data!;
    },
    retry: false,
  });

  const handleSubmit = () => {
    const trimmed = input.trim();
    if (!STUDENT_NUMBER_REGEX.test(trimmed)) {
      setInputError("請輸入有效的學號 (4-15 位英數字)");
      return;
    }
    setInputError(null);
    setSubmitted(trimmed);
  };

  const notFound =
    query.isError && /404|查無/.test((query.error as Error)?.message ?? "");

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>學生領取歷史查詢</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-end gap-3">
            <div className="flex-1">
              <Label htmlFor="student-number-input">學號</Label>
              <Input
                id="student-number-input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSubmit();
                }}
                placeholder="例: 310460031"
                autoFocus
              />
              {inputError && (
                <p className="text-sm text-destructive mt-1">{inputError}</p>
              )}
            </div>
            <Button onClick={handleSubmit} disabled={query.isFetching}>
              {query.isFetching ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Search className="h-4 w-4 mr-2" />
              )}
              查詢
            </Button>
          </div>
        </CardContent>
      </Card>

      {query.isFetching && (
        <Card>
          <CardContent className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            <span className="ml-2 text-muted-foreground">查詢中...</span>
          </CardContent>
        </Card>
      )}

      {notFound && (
        <Card className="border-destructive">
          <CardContent className="pt-6">
            <p className="font-medium text-destructive">查無此學生資料</p>
            <p className="text-sm text-muted-foreground mt-1">
              學號 <span className="font-mono">{submitted}</span> 既無學籍資料也無領取記錄。
            </p>
          </CardContent>
        </Card>
      )}

      {query.data && (
        <>
          <AcademicInfoCard
            academicInfo={query.data.academic_info}
            snapshotName={query.data.summary.snapshot_name}
          />
          <SummaryCards summary={query.data.summary} />
          <PaymentHistoryTable records={query.data.payment_records} />
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/student-history/StudentHistoryPanel.tsx
git commit -m "feat: add StudentHistoryPanel top-level composition"
```

---

## Task 13: Wire the new tab into AdminManagementShell

**Files:**
- Modify: `frontend/components/admin/AdminManagementShell.tsx`

- [ ] **Step 1: Read the current shell to confirm structure**

Run: `grep -n "TabsTrigger\|TabsContent\|grid-cols-" frontend/components/admin/AdminManagementShell.tsx`
Expected output shows the existing 11/12 column setup.

- [ ] **Step 2: Edit the shell**

In `frontend/components/admin/AdminManagementShell.tsx`:

1. Find the import block for existing panels (around `import { StudentListManagement } from "./students/StudentListManagement";`). Add:
```tsx
import { StudentHistoryPanel } from "./student-history/StudentHistoryPanel";
```

2. Find the `TabsList` `className`:
```tsx
className={`grid w-full ${hasQuotaPermission ? "grid-cols-12" : "grid-cols-11"}`}
```
Change to:
```tsx
className={`grid w-full ${hasQuotaPermission ? "grid-cols-13" : "grid-cols-12"}`}
```

3. Inside `<TabsList>`, after `<TabsTrigger value="students">學生列表</TabsTrigger>` (line 106), insert:
```tsx
          <TabsTrigger value="student-history">學生領取歷史</TabsTrigger>
```

4. After the existing `<TabsContent value="students">...</TabsContent>` block (around line 128-130), insert:
```tsx
        <TabsContent value="student-history" className="space-y-4">
          <StudentHistoryPanel />
        </TabsContent>
```

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Verify the dev frontend renders**

Run: `docker compose -f docker-compose.dev.yml up -d frontend backend postgres`
Wait ~10s. Then visit `http://localhost:3000` and log in as `admin@nycu.edu.tw`. Confirm the "學生領取歷史" tab is visible in the admin shell.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/AdminManagementShell.tsx
git commit -m "feat: add 學生領取歷史 tab to AdminManagementShell"
```

---

## Task 14: Playwright e2e test

**Files:**
- Create: `frontend/e2e/specs/admin-student-history.spec.ts`

- [ ] **Step 1: Write the test**

Create `frontend/e2e/specs/admin-student-history.spec.ts`:

```typescript
/**
 * E2E: Admin student scholarship history lookup.
 *
 * Tab: AdminManagementShell → "學生領取歷史"
 * Endpoint: GET /api/v1/admin/student-history/{student_number}
 *
 * Mirrors the auth pattern from admin-manual-distribution.spec.ts: log in as
 * the seeded "admin" user, reuse its BrowserContext, navigate to "/" which
 * mounts AdminManagementShell, click the new tab.
 */

import { test, expect } from "@playwright/test";
import { loginAs } from "../helpers/auth";

test.describe("Admin student scholarship history", () => {
  test("rejects invalid student number client-side", async ({ browser }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("@@");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(page.getByText(/請輸入有效的學號/)).toBeVisible();
    await context.close();
  });

  test("shows 查無此學生資料 for unknown student", async ({ browser }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("GHOST00000");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(page.getByText("查無此學生資料")).toBeVisible({
      timeout: 10000,
    });
    await context.close();
  });

  // NOTE: This test uses seeded `stuphd001` (see backend/app/seed.py). The
  // dev DB may or may not have locked rosters for them by default. If not, the
  // table will show the "尚無領取記錄" empty state — both outcomes are valid
  // for "the page renders without error". A stronger assertion needs roster
  // seeding which is out of scope for this plan.
  test("renders page for seeded student (table OR empty state)", async ({
    browser,
  }) => {
    const { context } = await loginAs(browser, "admin");
    const page = await context.newPage();
    await page.goto("/");
    await page.getByRole("tab", { name: "學生領取歷史" }).click();
    await page.getByLabel("學號").fill("stuphd001");
    await page.getByRole("button", { name: "查詢" }).click();
    await expect(
      page.getByText(/領取明細|查無此學生資料|尚無領取記錄/),
    ).toBeVisible({ timeout: 10000 });
    await context.close();
  });
});
```

- [ ] **Step 2: Run the e2e test**

Ensure dev stack is up:
```bash
docker compose -f docker-compose.dev.yml up -d
```

Then run:
```bash
cd frontend && npx playwright test e2e/specs/admin-student-history.spec.ts
```
Expected: at least the first two tests pass. The third may pass or skip depending on seed data — the implementer should confirm.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/specs/admin-student-history.spec.ts
git commit -m "test: add e2e spec for admin student scholarship history"
```

---

## Task 15: Final verification

**Files:** none (no edits)

- [ ] **Step 1: Run backend tests for the new feature end-to-end**

```bash
cd backend && python -m pytest \
  app/tests/test_student_scholarship_history_service.py \
  app/tests/test_admin_student_history_endpoint.py -v
```
Expected: all green.

- [ ] **Step 2: Run frontend type check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 3: Run linters (if present)**

```bash
cd backend && python -m black --check app/services/student_scholarship_history_service.py \
                                       app/api/v1/endpoints/admin/student_history.py \
                                       app/schemas/student_scholarship_history.py
cd backend && python -m flake8 app/services/student_scholarship_history_service.py \
                                app/api/v1/endpoints/admin/student_history.py \
                                app/schemas/student_scholarship_history.py
```
Expected: clean. Fix any issues and commit `style: format student-history files`.

- [ ] **Step 4: Manual smoke (browser)**

1. `docker compose -f docker-compose.dev.yml up -d`
2. Visit `http://localhost:3000`, log in as admin
3. Click "學生領取歷史" tab
4. Enter a known seeded student number (or one that has locked rosters in the dev DB) → verify cards + table render
5. Enter `GHOST00000` → verify "查無此學生資料" empty state
6. Enter `@@` → verify client-side validation triggers

- [ ] **Step 5: Final commit if any formatting fixes**

```bash
git status
# if there are unstaged formatter changes, commit them
```

---

## Notes for the implementer

- **Sync vs async DB:** `payment_rosters.py` endpoint module uses sync sessions; the rest of `admin/*` mostly uses async. This new endpoint uses **async** (via `AsyncSession` and `get_db`). Don't pull in `get_sync_db`.
- **Decimal serialization:** Pydantic v2 serializes `Decimal` as a string by default when using `model_dump(mode="json")`. The endpoint uses `mode="json"` to preserve the string form for frontend display.
- **No fallback data:** Per CLAUDE.md §1, the service must `raise NotFoundError` when both SIS and DB are empty — do not return an empty-shaped object instead.
- **OpenAPI sync:** Per CLAUDE.md §8, Task 7 (type regeneration) is mandatory after the backend endpoint lands. CI may fail if `schema.d.ts` drifts from the live OpenAPI spec.
- **Student number regex:** `^[A-Za-z0-9]{4,15}$` is permissive to cover NYCU patterns like `310460031`, `stuphd001`, etc. If staging uncovers a real student number that violates this, widen the regex in both backend and frontend together.
- **Test fixture names:** Several tests reference fixtures like `async_db`, `admin_client`, `client`. These may differ in this repo's `conftest.py` — the implementer should `grep` conftest first and adapt.
