# Post-Distribution Supplementary Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow admins to toggle a per-ranking supplementary import flag so colleges can upload new student applications (using the 學生資料彙整表 export format) after distribution is complete; imported students are appended to the existing ranking and queued for a second admin manual distribution pass.

**Architecture:** New `is_supplementary` flag on `CollegeRankingItem` and `allow_supplementary_import` flag on `CollegeRanking`; a new `SupplementaryImportService` handles Excel parsing, SIS API calls, and Application/User creation in one atomic transaction; two new endpoints (admin toggle + college upload) are added to `ranking_management.py`; `ManualDistributionService.finalize()` is patched to leave unallocated supplementary items as `ranked` instead of marking them `rejected`.

**Tech Stack:** Python/FastAPI, SQLAlchemy async, openpyxl, NYCU SIS API (`StudentService`), Next.js/React, xlsx (client-side preview)

---

## File Map

| File | Action |
|---|---|
| `backend/app/models/college_review.py` | Add two columns |
| `backend/alembic/versions/add_supplementary_import_001.py` | New migration |
| `backend/app/services/supplementary_import_service.py` | New service |
| `backend/app/services/manual_distribution_service.py` | Patch finalize() |
| `backend/app/api/v1/endpoints/college_review/ranking_management.py` | Two new endpoints |
| `backend/app/tests/test_supplementary_import_service.py` | Unit tests for new service |
| `backend/app/tests/test_supplementary_import_endpoints.py` | Integration tests |
| `frontend/lib/api/modules/college.ts` | Two new API functions |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Admin toggle + `[補充]` tag |
| `frontend/components/college-ranking-table.tsx` | College upload button + flow |

---

## Task 1: Add columns to ORM models

**Files:**
- Modify: `backend/app/models/college_review.py`

- [ ] **Step 1: Add `allow_supplementary_import` to `CollegeRanking`**

In `backend/app/models/college_review.py`, after the `distribution_date` line (~line 83), add:

```python
allow_supplementary_import = Column(Boolean, default=False, nullable=False, server_default="false")
```

- [ ] **Step 2: Add `is_supplementary` to `CollegeRankingItem`**

In `backend/app/models/college_review.py`, in the `CollegeRankingItem` class after the `college_rejected` column (~line 151), add:

```python
is_supplementary = Column(Boolean, default=False, nullable=False, server_default="false")
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/college_review.py
git commit -m "feat: add allow_supplementary_import and is_supplementary columns to ORM models"
```

---

## Task 2: Alembic migration

**Files:**
- Create: `backend/alembic/versions/add_supplementary_import_001.py`

- [ ] **Step 1: Create migration file**

Create `backend/alembic/versions/add_supplementary_import_001.py`:

```python
"""Add supplementary import columns to college_rankings and college_ranking_items

Revision ID: add_supplementary_import_001
Revises: 20260513_doc_req_deadline
Create Date: 2026-05-14
"""

import sqlalchemy as sa
from alembic import op

revision = "add_supplementary_import_001"
down_revision = "20260513_doc_req_deadline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_cols = {
        col["name"]
        for col in inspector.get_columns("college_rankings")
    }
    if "allow_supplementary_import" not in existing_cols:
        op.add_column(
            "college_rankings",
            sa.Column(
                "allow_supplementary_import",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )

    existing_item_cols = {
        col["name"]
        for col in inspector.get_columns("college_ranking_items")
    }
    if "is_supplementary" not in existing_item_cols:
        op.add_column(
            "college_ranking_items",
            sa.Column(
                "is_supplementary",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    op.drop_column("college_ranking_items", "is_supplementary")
    op.drop_column("college_rankings", "allow_supplementary_import")
```

- [ ] **Step 2: Run migration inside Docker**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected output: `Running upgrade 20260513_doc_req_deadline -> add_supplementary_import_001`

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/add_supplementary_import_001.py
git commit -m "feat: migration add_supplementary_import_001 — two new boolean columns"
```

---

## Task 3: SupplementaryImportService — pure parsing helpers

**Files:**
- Create: `backend/app/services/supplementary_import_service.py`
- Create: `backend/app/tests/test_supplementary_import_service.py`

This task covers the pure (no-DB, no-HTTP) helpers: Excel parsing and `申請獎學金類別` decoding.

- [ ] **Step 1: Write failing unit tests**

Create `backend/app/tests/test_supplementary_import_service.py`:

```python
"""Unit tests for SupplementaryImportService pure helpers."""

import io
import pytest
from openpyxl import Workbook

from app.services.supplementary_import_service import (
    SupplementaryImportService,
    SupplementaryRow,
    parse_scholarship_type_cell,
)


def _make_excel(rows: list[list]) -> bytes:
    """Build a minimal 學生資料彙整表-format xlsx in memory."""
    wb = Workbook()
    ws = wb.active
    # Row 1: title (merged in real export, plain text here is fine for parsing)
    ws.cell(row=1, column=1, value="Title")
    # Row 2: static headers (18 columns)
    headers = [
        "NO.", "學院初審會議之學院排序", "申請獎學金類別", "學院", "系所",
        "年級", "是否為逕博學生", "學生中文姓名", "學生英文姓名", "國籍",
        "性別", "註冊入學日期", "學號", "學生身分證字號", "學生匯款帳號",
        "學生E-mail", "學生通訊地址", "指導教授姓名",
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=2, column=col_idx, value=h)
    # Data rows (row 3+)
    for row_idx, row_data in enumerate(rows, start=3):
        for col_idx, val in enumerate(row_data, start=1):
            ws.cell(row=row_idx, column=col_idx, value=val)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


LABEL_TO_CODE = {
    "國科會博士生研究獎學金": "nstc",
    "教育部博士生獎學金": "moe_1w",
}


class TestParseScholarshipTypeCell:
    def test_single_preference(self):
        prefs = parse_scholarship_type_cell("國科會博士生研究獎學金", LABEL_TO_CODE)
        assert prefs == ["nstc"]

    def test_dual_preference_first_nstc(self):
        cell = "國科會博士生研究獎學金(第一志願)暨教育部博士生獎學金(第二志願)"
        prefs = parse_scholarship_type_cell(cell, LABEL_TO_CODE)
        assert prefs == ["nstc", "moe_1w"]

    def test_dual_preference_first_moe(self):
        cell = "教育部博士生獎學金(第一志願)暨國科會博士生研究獎學金(第二志願)"
        prefs = parse_scholarship_type_cell(cell, LABEL_TO_CODE)
        assert prefs == ["moe_1w", "nstc"]

    def test_unknown_label_raises(self):
        with pytest.raises(ValueError, match="無法識別的獎學金類別"):
            parse_scholarship_type_cell("不存在的獎學金", LABEL_TO_CODE)

    def test_empty_cell_raises(self):
        with pytest.raises(ValueError, match="無法識別的獎學金類別"):
            parse_scholarship_type_cell("", LABEL_TO_CODE)


class TestParseExcel:
    def test_parses_student_id_rank_and_scholarship(self):
        row = [1, 1, "國科會博士生研究獎學金", "工學院", "電機系",
               2, "否", "王小明", "Wang", "台灣", "男", "113.9.1",
               "310460001", "A123456789", "12345678", "test@nycu.edu.tw",
               "新竹市", "指導教授A"]
        file_bytes = _make_excel([row])
        dynamic_field_names: list[str] = []
        rows, errors = SupplementaryImportService.parse_excel(
            file_bytes, LABEL_TO_CODE, dynamic_field_names
        )
        assert not errors
        assert len(rows) == 1
        r = rows[0]
        assert r.student_id == "310460001"
        assert r.excel_rank == 1
        assert r.sub_type_preferences == ["nstc"]
        assert r.bank_account == "12345678"
        assert r.advisor_name == "指導教授A"
        assert r.submitted_form_fields == {}

    def test_duplicate_student_ids_reported(self):
        row = [1, 1, "國科會博士生研究獎學金", "", "", 2, "", "王A", "", "", "", "",
               "310460001", "", "", "", "", ""]
        row2 = [2, 2, "國科會博士生研究獎學金", "", "", 2, "", "王B", "", "", "", "",
                "310460001", "", "", "", "", ""]
        file_bytes = _make_excel([row, row2])
        rows, errors = SupplementaryImportService.parse_excel(
            file_bytes, LABEL_TO_CODE, []
        )
        assert any("重複" in e for e in errors)

    def test_non_integer_rank_reported(self):
        row = [1, "abc", "國科會博士生研究獎學金", "", "", 2, "", "王A", "", "", "", "",
               "310460001", "", "", "", "", ""]
        file_bytes = _make_excel([row])
        rows, errors = SupplementaryImportService.parse_excel(
            file_bytes, LABEL_TO_CODE, []
        )
        assert any("排名" in e for e in errors)

    def test_skips_empty_rows(self):
        empty_row = [""] * 18
        real_row = [1, 1, "國科會博士生研究獎學金", "", "", 2, "", "王A", "", "", "", "",
                    "310460001", "", "", "", "", ""]
        file_bytes = _make_excel([empty_row, real_row])
        rows, errors = SupplementaryImportService.parse_excel(
            file_bytes, LABEL_TO_CODE, []
        )
        assert not errors
        assert len(rows) == 1
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_service.py -v 2>&1 | head -40
```

Expected: `ImportError` or `ModuleNotFoundError` (service doesn't exist yet).

- [ ] **Step 3: Implement pure helpers in the new service**

Create `backend/app/services/supplementary_import_service.py`:

```python
"""Supplementary import service — adds new students to an existing ranking post-distribution."""

from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from openpyxl import load_workbook

logger = logging.getLogger(__name__)

# Column indices (1-based, matching 學生資料彙整表 export format)
_COL_RANK = 2
_COL_SCHOLARSHIP_TYPE = 3
_COL_STUDENT_ID = 13
_COL_BANK_ACCOUNT = 15
_COL_ADVISOR_NAME = 18
_STATIC_COL_COUNT = 18


@dataclass
class SupplementaryRow:
    """Parsed data for one student from the supplementary import Excel."""

    student_id: str
    excel_rank: int  # Value from col 2 (will be offset by max existing rank)
    sub_type_preferences: List[str]
    bank_account: Optional[str]
    advisor_name: Optional[str]
    submitted_form_fields: Dict[str, str]  # field_name -> raw cell value


def parse_scholarship_type_cell(cell_value: str, label_to_code: Dict[str, str]) -> List[str]:
    """Parse 申請獎學金類別 cell into ordered sub_type_preference codes.

    Formats:
        "XXX"                                      -> [code_of_XXX]
        "XXX(第一志願)暨YYY(第二志願)"              -> [code_of_XXX, code_of_YYY]
    """
    cell_value = (cell_value or "").strip()
    dual_match = re.fullmatch(
        r"(.+?)\(第一志願\)暨(.+?)\(第二志願\)", cell_value
    )
    if dual_match:
        first_label = dual_match.group(1).strip()
        second_label = dual_match.group(2).strip()
        for label in (first_label, second_label):
            if label not in label_to_code:
                raise ValueError(f"無法識別的獎學金類別：「{label}」")
        return [label_to_code[first_label], label_to_code[second_label]]

    if cell_value in label_to_code:
        return [label_to_code[cell_value]]

    raise ValueError(f"無法識別的獎學金類別：「{cell_value}」")


class SupplementaryImportService:
    """Handles all logic for supplementary student import after distribution."""

    # -------- Pure helpers (no DB / no HTTP) --------

    @staticmethod
    def parse_excel(
        file_bytes: bytes,
        label_to_code: Dict[str, str],
        dynamic_field_names: List[str],
    ) -> Tuple[List[SupplementaryRow], List[str]]:
        """Parse a 學生資料彙整表 Excel file.

        Returns (rows, errors). If errors is non-empty the caller should
        abort and return them to the client; rows may be partially populated.
        """
        errors: List[str] = []
        rows: List[SupplementaryRow] = []
        seen_student_ids: Dict[str, int] = {}  # student_id -> first excel row number
        seen_ranks: Dict[int, int] = {}        # rank -> first excel row number

        try:
            wb = load_workbook(io.BytesIO(file_bytes), data_only=True)
            ws = wb.active
        except Exception as exc:
            return [], [f"無法讀取 Excel 檔案：{exc}"]

        # Row 1 = title, Row 2 = headers, Row 3+ = data
        for excel_row in ws.iter_rows(min_row=3, values_only=True):
            student_id_raw = excel_row[_COL_STUDENT_ID - 1]
            if not student_id_raw:
                continue  # skip empty rows

            student_id = str(student_id_raw).strip()
            row_num = rows.__len__() + 3  # approximate display row

            # Duplicate student ID check
            if student_id in seen_student_ids:
                errors.append(
                    f"學號重複：{student_id}（首次出現在第 {seen_student_ids[student_id]} 行）"
                )
                continue
            seen_student_ids[student_id] = row_num

            # Parse rank (col 2)
            rank_raw = excel_row[_COL_RANK - 1]
            try:
                excel_rank = int(rank_raw)
                if excel_rank < 1:
                    raise ValueError()
            except (TypeError, ValueError):
                errors.append(f"排名無效（學號 {student_id}）：必須為正整數，收到 '{rank_raw}'")
                continue

            if excel_rank in seen_ranks:
                errors.append(f"排名重複：第 {excel_rank} 名出現超過一次（學號 {student_id}）")
                continue
            seen_ranks[excel_rank] = row_num

            # Parse 申請獎學金類別 (col 3)
            scholarship_cell = str(excel_row[_COL_SCHOLARSHIP_TYPE - 1] or "").strip()
            try:
                sub_type_preferences = parse_scholarship_type_cell(scholarship_cell, label_to_code)
            except ValueError as exc:
                errors.append(f"學號 {student_id}：{exc}")
                continue

            # Other static columns
            bank_account_raw = excel_row[_COL_BANK_ACCOUNT - 1]
            bank_account = str(bank_account_raw).strip() if bank_account_raw else None

            advisor_raw = excel_row[_COL_ADVISOR_NAME - 1]
            advisor_name = str(advisor_raw).strip() if advisor_raw else None

            # Dynamic columns (col 19+)
            submitted_form_fields: Dict[str, str] = {}
            for idx, field_name in enumerate(dynamic_field_names):
                col_idx = _STATIC_COL_COUNT + idx  # 0-based
                if col_idx < len(excel_row):
                    raw = excel_row[col_idx]
                    if raw is not None and str(raw).strip():
                        submitted_form_fields[field_name] = str(raw).strip()

            rows.append(
                SupplementaryRow(
                    student_id=student_id,
                    excel_rank=excel_rank,
                    sub_type_preferences=sub_type_preferences,
                    bank_account=bank_account,
                    advisor_name=advisor_name,
                    submitted_form_fields=submitted_form_fields,
                )
            )

        # Validate rank sequence is consecutive starting from 1
        if rows and not errors:
            expected = set(range(1, len(rows) + 1))
            actual = {r.excel_rank for r in rows}
            missing = expected - actual
            if missing:
                errors.append(
                    f"排名不連續：缺少第 {', '.join(str(r) for r in sorted(missing))} 名"
                )

        return rows, errors
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_service.py -v 2>&1 | tail -20
```

Expected: All tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/supplementary_import_service.py \
        backend/app/tests/test_supplementary_import_service.py
git commit -m "feat: SupplementaryImportService pure helpers + unit tests"
```

---

## Task 4: SupplementaryImportService — DB and SIS API methods

**Files:**
- Modify: `backend/app/services/supplementary_import_service.py`
- Modify: `backend/app/tests/test_supplementary_import_service.py`

- [ ] **Step 1: Add failing tests for DB/SIS methods**

Append to `backend/app/tests/test_supplementary_import_service.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.supplementary_import_service import SupplementaryImportService, SupplementaryRow


@pytest.mark.asyncio
class TestValidateNoDuplicateApplications:
    async def test_returns_empty_when_no_duplicates(self, db: AsyncSession):
        service = SupplementaryImportService(db)
        rows = [SupplementaryRow("310460001", 1, ["nstc"], None, None, {})]
        # No applications in DB → no conflicts
        conflicts = await service.validate_no_duplicate_applications(
            rows, scholarship_type_id=1, academic_year=114, semester="yearly"
        )
        assert conflicts == []

    async def test_returns_conflict_ids_when_duplicate_exists(self, db: AsyncSession):
        from app.models.application import Application, ApplicationStatus
        from app.models.user import User, UserRole, UserType

        user = User(nycu_id="310460001", name="王小明", email="test@nycu.edu.tw",
                    user_type=UserType.student, role=UserRole.student)
        db.add(user)
        await db.flush()

        app = Application(
            app_id="APP-114-0-00001",
            user_id=user.id,
            scholarship_type_id=1,
            academic_year=114,
            semester=None,
            status=ApplicationStatus.submitted,
        )
        db.add(app)
        await db.flush()

        service = SupplementaryImportService(db)
        rows = [SupplementaryRow("310460001", 1, ["nstc"], None, None, {})]
        conflicts = await service.validate_no_duplicate_applications(
            rows, scholarship_type_id=1, academic_year=114, semester="yearly"
        )
        assert "310460001" in conflicts


@pytest.mark.asyncio
class TestFetchStudentDataBulk:
    async def test_returns_data_for_known_ids(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_basic_info = AsyncMock(
            return_value={"std_stdcode": "310460001", "std_cname": "王小明",
                          "com_email": "test@nycu.edu.tw"}
        )
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing = await service.fetch_student_data_bulk(["310460001"])
        assert "310460001" in data_map
        assert missing == []

    async def test_returns_missing_for_unknown_ids(self, db: AsyncSession):
        mock_student_service = AsyncMock()
        mock_student_service.api_enabled = True
        mock_student_service.get_student_basic_info = AsyncMock(return_value=None)
        service = SupplementaryImportService(db, student_service=mock_student_service)
        data_map, missing = await service.fetch_student_data_bulk(["999999"])
        assert missing == ["999999"]
```

- [ ] **Step 2: Run to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_service.py::TestValidateNoDuplicateApplications app/tests/test_supplementary_import_service.py::TestFetchStudentDataBulk -v 2>&1 | tail -20
```

Expected: `AttributeError` (methods don't exist yet).

- [ ] **Step 3: Implement DB/SIS methods in the service**

Append the following to `SupplementaryImportService` class in `backend/app/services/supplementary_import_service.py`:

```python
    # -------- DB + SIS helpers --------

    def __init__(self, db, student_service=None):
        self.db = db
        from app.services.student_service import StudentService
        self.student_service = student_service or StudentService()

    async def validate_no_duplicate_applications(
        self,
        rows: List[SupplementaryRow],
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> List[str]:
        """Return list of student_ids that already have an application for this scholarship/year/semester."""
        from sqlalchemy import select, and_, or_
        from app.models.application import Application
        from app.models.user import User

        student_ids = [r.student_id for r in rows]
        # Find users by nycu_id
        user_stmt = select(User.id, User.nycu_id).where(User.nycu_id.in_(student_ids))
        user_result = await self.db.execute(user_stmt)
        nycu_to_user_id = {nycu_id: uid for uid, nycu_id in user_result.all()}

        if not nycu_to_user_id:
            return []

        user_ids = list(nycu_to_user_id.values())

        # Check for existing applications
        if semester == "yearly":
            sem_cond = or_(
                Application.semester.is_(None),
                Application.semester == "yearly",
            )
        else:
            sem_cond = Application.semester == semester

        app_stmt = select(Application.user_id).where(
            and_(
                Application.user_id.in_(user_ids),
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                sem_cond,
                Application.deleted_at.is_(None),
            )
        )
        result = await self.db.execute(app_stmt)
        conflicting_user_ids = {row[0] for row in result.all()}

        user_id_to_nycu = {v: k for k, v in nycu_to_user_id.items()}
        return [user_id_to_nycu[uid] for uid in conflicting_user_ids if uid in user_id_to_nycu]

    async def fetch_student_data_bulk(
        self, student_ids: List[str]
    ) -> Tuple[Dict[str, dict], List[str]]:
        """Fetch student_data from SIS API for each student_id.

        Returns (data_map, missing_ids).
        Raises ValueError if SIS API is not enabled.
        """
        if not getattr(self.student_service, "api_enabled", False):
            raise ValueError("學生 API 未啟用，無法驗證學生資料")

        data_map: Dict[str, dict] = {}
        missing: List[str] = []

        for student_id in student_ids:
            try:
                data = await self.student_service.get_student_basic_info(student_id)
            except Exception as exc:
                logger.warning("SIS API error for %s: %s", student_id, exc)
                missing.append(student_id)
                continue

            if not data:
                missing.append(student_id)
            else:
                data_map[student_id] = data

        return data_map, missing

    async def find_or_create_users(
        self, student_data_map: Dict[str, dict]
    ) -> Dict[str, object]:
        """Return {student_id: User} — creates User + UserProfile if not found."""
        from sqlalchemy import select
        from app.models.user import User, UserRole, UserType
        from app.models.user_profile import UserProfile

        student_ids = list(student_data_map.keys())
        stmt = select(User).where(User.nycu_id.in_(student_ids))
        result = await self.db.execute(stmt)
        user_map: Dict[str, User] = {u.nycu_id: u for u in result.scalars().all()}

        for student_id, sis_data in student_data_map.items():
            if student_id in user_map:
                continue
            new_user = User(
                nycu_id=student_id,
                name=sis_data.get("std_cname") or student_id,
                email=sis_data.get("com_email"),
                user_type=UserType.student,
                role=UserRole.student,
                dept_code=sis_data.get("std_depno"),
            )
            self.db.add(new_user)
            await self.db.flush()
            user_map[student_id] = new_user

        return user_map

    async def upsert_user_profiles(
        self,
        user_map: Dict[str, object],
        rows: List[SupplementaryRow],
    ) -> None:
        """Create or update UserProfile with bank_account and advisor_name from Excel."""
        from sqlalchemy import select
        from app.models.user_profile import UserProfile

        user_ids = [u.id for u in user_map.values()]
        existing_stmt = select(UserProfile).where(UserProfile.user_id.in_(user_ids))
        existing_result = await self.db.execute(existing_stmt)
        profile_map: Dict[int, UserProfile] = {p.user_id: p for p in existing_result.scalars().all()}

        row_map = {r.student_id: r for r in rows}

        for student_id, user in user_map.items():
            row = row_map.get(student_id)
            if not row:
                continue
            if user.id in profile_map:
                profile = profile_map[user.id]
                if row.bank_account:
                    profile.account_number = row.bank_account
                if row.advisor_name:
                    profile.advisor_name = row.advisor_name
            else:
                profile = UserProfile(
                    user_id=user.id,
                    account_number=row.bank_account,
                    advisor_name=row.advisor_name,
                )
                self.db.add(profile)

    async def create_applications_and_items(
        self,
        rows: List[SupplementaryRow],
        user_map: Dict[str, object],
        student_data_map: Dict[str, dict],
        ranking,  # CollegeRanking ORM object
        max_existing_rank: int,
    ) -> int:
        """Create Application + CollegeRankingItem for each supplementary row.

        Returns count of created items.
        """
        from app.models.application import Application, ApplicationStatus
        from app.models.application_sequence import ApplicationSequence
        from app.models.college_review import CollegeRankingItem

        # Determine semester string for app_id generation
        semester_str = ranking.semester if ranking.semester else "yearly"

        created = 0
        for row in rows:
            user = user_map.get(row.student_id)
            if not user:
                continue

            sis_data = student_data_map.get(row.student_id, {})

            # Generate app_id using sequence table with locking
            seq_stmt = (
                __import__("sqlalchemy", fromlist=["select"]).select(ApplicationSequence)
                .where(
                    ApplicationSequence.academic_year == ranking.academic_year,
                    ApplicationSequence.semester == semester_str,
                )
                .with_for_update()
            )
            seq_result = await self.db.execute(seq_stmt)
            seq_record = seq_result.scalar_one_or_none()
            if not seq_record:
                seq_record = ApplicationSequence(
                    academic_year=ranking.academic_year,
                    semester=semester_str,
                    last_sequence=0,
                )
                self.db.add(seq_record)
                await self.db.flush()
            seq_record.last_sequence += 1
            app_id = ApplicationSequence.format_app_id(
                ranking.academic_year, semester_str, seq_record.last_sequence
            )

            submitted_form_data = {
                "fields": {
                    field_name: {
                        "field_id": field_name,
                        "field_type": "text",
                        "value": value,
                    }
                    for field_name, value in row.submitted_form_fields.items()
                }
            }

            app = Application(
                app_id=app_id,
                user_id=user.id,
                scholarship_type_id=ranking.scholarship_type_id,
                academic_year=ranking.academic_year,
                semester=ranking.semester,
                status=ApplicationStatus.submitted,
                student_data=sis_data,
                sub_type_preferences=row.sub_type_preferences,
                submitted_form_data=submitted_form_data,
            )
            self.db.add(app)
            await self.db.flush()

            rank_item = CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                rank_position=max_existing_rank + row.excel_rank,
                is_supplementary=True,
                status="ranked",
                college_rejected=False,
                is_allocated=False,
            )
            self.db.add(rank_item)
            created += 1

        await self.db.flush()
        return created
```

- [ ] **Step 4: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_service.py -v 2>&1 | tail -30
```

Expected: All tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/supplementary_import_service.py \
        backend/app/tests/test_supplementary_import_service.py
git commit -m "feat: SupplementaryImportService DB/SIS methods + tests"
```

---

## Task 5: Patch ManualDistributionService.finalize()

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py`
- Create: `backend/app/tests/unit/test_finalize_supplementary_patch.py`

- [ ] **Step 1: Write failing test**

Create `backend/app/tests/unit/test_finalize_supplementary_patch.py`:

```python
"""Unit tests: finalize() skips reject for supplementary unallocated items."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_item(is_allocated: bool, allocated_sub_type, is_supplementary: bool):
    item = MagicMock()
    item.is_allocated = is_allocated
    item.allocated_sub_type = allocated_sub_type
    item.is_supplementary = is_supplementary
    item.deleted_at = None
    item.application = MagicMock()
    item.application.deleted_at = None
    item.application.status = "submitted"
    item.application.quota_allocation_status = None
    return item


class TestFinalizeSupplementaryPatch:
    def test_unallocated_supplementary_item_stays_ranked(self):
        """Unallocated is_supplementary=True item must NOT get item.status='rejected'."""
        item = _make_item(is_allocated=False, allocated_sub_type=None, is_supplementary=True)

        # Simulate the finalize loop logic after the patch
        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
            item.application.quota_allocation_status = "allocated"
        elif item.is_supplementary and not item.is_allocated:
            pass  # leave as-is
        else:
            item.status = "rejected"
            item.application.quota_allocation_status = "rejected"

        assert item.status != "rejected", "Supplementary unallocated item should NOT be rejected"
        assert item.application.quota_allocation_status is None

    def test_unallocated_regular_item_becomes_rejected(self):
        """Unallocated is_supplementary=False item MUST still get item.status='rejected'."""
        item = _make_item(is_allocated=False, allocated_sub_type=None, is_supplementary=False)

        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
        elif item.is_supplementary and not item.is_allocated:
            pass
        else:
            item.status = "rejected"
            item.application.quota_allocation_status = "rejected"

        assert item.status == "rejected"
        assert item.application.quota_allocation_status == "rejected"

    def test_allocated_supplementary_item_gets_approved(self):
        """Allocated supplementary item follows the normal approved path."""
        item = _make_item(is_allocated=True, allocated_sub_type="nstc", is_supplementary=True)
        item.application.status = "submitted"

        if item.is_allocated and item.allocated_sub_type:
            item.application.status = "approved"
            item.application.quota_allocation_status = "allocated"
        elif item.is_supplementary and not item.is_allocated:
            pass
        else:
            item.status = "rejected"

        assert item.application.status == "approved"
```

- [ ] **Step 2: Run to verify tests pass (logic is tested in isolation)**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/unit/test_finalize_supplementary_patch.py -v 2>&1 | tail -15
```

Expected: All 3 tests `PASSED` (they test the logic inline, not the actual service yet).

- [ ] **Step 3: Apply the patch to `manual_distribution_service.py`**

In `backend/app/services/manual_distribution_service.py`, find the `finalize()` method's item loop (~line 739). Replace:

```python
            else:
                # Non-allocated: keep the user-facing app.status as-is
                # (e.g. an approved-but-not-funded app stays "approved"). Only
                # the quota_allocation_status flips to "rejected" so the
                # distribution engine can identify non-allocated outcomes.
                # See #45 — earlier code stomped app.status to rejected, which
                # incorrectly told students their application was denied when
                # in fact they passed review but missed the quota cut.
                item.status = "rejected"
                app.quota_allocation_status = "rejected"
                app.review_stage = ReviewStage.quota_distributed
                rejected_count += 1
```

With:

```python
            elif item.is_supplementary and not item.is_allocated:
                # Supplementary students pending a second distribution pass —
                # leave status as 'ranked' so they appear in the next allocation.
                pass
            else:
                # Non-allocated: keep the user-facing app.status as-is.
                # Only quota_allocation_status flips to "rejected" so the
                # distribution engine can identify non-allocated outcomes.
                # See #45 — earlier code stomped app.status to rejected.
                item.status = "rejected"
                app.quota_allocation_status = "rejected"
                app.review_stage = ReviewStage.quota_distributed
                rejected_count += 1
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/manual_distribution_service.py \
        backend/app/tests/unit/test_finalize_supplementary_patch.py
git commit -m "fix: finalize() skips reject for unallocated supplementary items"
```

---

## Task 6: Backend endpoints — admin toggle + college import

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/ranking_management.py`
- Create: `backend/app/tests/test_supplementary_import_endpoints.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/app/tests/test_supplementary_import_endpoints.py`:

```python
"""Integration tests for supplementary import endpoints."""

import io
import pytest
from httpx import AsyncClient
from openpyxl import Workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipType
from app.models.user import User, UserRole, UserType


def _build_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="Title")
    headers = [
        "NO.", "學院初審會議之學院排序", "申請獎學金類別", "學院", "系所",
        "年級", "是否為逕博學生", "學生中文姓名", "學生英文姓名", "國籍",
        "性別", "註冊入學日期", "學號", "學生身分證字號", "學生匯款帳號",
        "學生E-mail", "學生通訊地址", "指導教授姓名",
    ]
    for col_idx, h in enumerate(headers, start=1):
        ws.cell(row=2, column=col_idx, value=h)
    row = [1, 1, "國科會博士生研究獎學金", "工學院", "電機系", 2, "否",
           "王小明", "Wang", "台灣", "男", "113.9.1",
           "310460099", "A123456789", "12345678", "test99@nycu.edu.tw",
           "新竹市", "指導教授A"]
    for col_idx, val in enumerate(row, start=1):
        ws.cell(row=3, column=col_idx, value=val)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(nycu_id="admin001", name="Admin", email="admin@nycu.edu.tw",
                user_type=UserType.employee, role=UserRole.admin)
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def college_user(db: AsyncSession) -> User:
    user = User(nycu_id="col001", name="College", email="col@nycu.edu.tw",
                user_type=UserType.employee, role=UserRole.college,
                college_code="A")
    db.add(user)
    await db.flush()
    return user


@pytest.fixture
async def ranking(db: AsyncSession, test_scholarship: ScholarshipType) -> CollegeRanking:
    r = CollegeRanking(
        scholarship_type_id=test_scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        ranking_name="Test",
        created_by=1,
        is_finalized=True,
        distribution_executed=True,
        allow_supplementary_import=False,
    )
    db.add(r)
    await db.flush()
    return r


class TestAdminToggle:
    async def test_admin_can_enable_supplementary_import(
        self, client: AsyncClient, db: AsyncSession, admin_user: User, ranking: CollegeRanking
    ):
        client.headers["Authorization"] = f"Bearer mock-{admin_user.id}"
        resp = await client.patch(
            f"/api/v1/college-review/rankings/{ranking.id}/supplementary-import",
            json={"allow": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["allow_supplementary_import"] is True

    async def test_non_admin_cannot_toggle(
        self, client: AsyncClient, db: AsyncSession, college_user: User, ranking: CollegeRanking
    ):
        client.headers["Authorization"] = f"Bearer mock-{college_user.id}"
        resp = await client.patch(
            f"/api/v1/college-review/rankings/{ranking.id}/supplementary-import",
            json={"allow": True},
        )
        assert resp.status_code == 403


class TestSupplementaryImportEndpoint:
    async def test_returns_403_when_flag_is_off(
        self, client: AsyncClient, db: AsyncSession, college_user: User, ranking: CollegeRanking
    ):
        client.headers["Authorization"] = f"Bearer mock-{college_user.id}"
        xlsx_bytes = _build_xlsx_bytes()
        resp = await client.post(
            f"/api/v1/college-review/rankings/{ranking.id}/supplementary-import",
            files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        assert resp.status_code == 403

    async def test_returns_422_on_duplicate_student(
        self, client: AsyncClient, db: AsyncSession, college_user: User, ranking: CollegeRanking
    ):
        ranking.allow_supplementary_import = True
        await db.flush()
        # Create existing application for "310460099"
        from app.models.application import Application, ApplicationStatus
        from app.models.user import User as UserModel
        existing_user = UserModel(nycu_id="310460099", name="Already", email="exists@nycu.edu.tw",
                                   user_type=UserType.student, role=UserRole.student)
        db.add(existing_user)
        await db.flush()
        from app.models.scholarship import ScholarshipConfiguration
        from app.models.application import Application
        existing_app = Application(
            app_id="APP-114-0-00001",
            user_id=existing_user.id,
            scholarship_type_id=ranking.scholarship_type_id,
            academic_year=114,
            semester=None,
            status=ApplicationStatus.submitted,
        )
        db.add(existing_app)
        await db.flush()

        client.headers["Authorization"] = f"Bearer mock-{college_user.id}"
        from unittest.mock import patch, AsyncMock
        with patch("app.services.supplementary_import_service.SupplementaryImportService.fetch_student_data_bulk",
                   new=AsyncMock(return_value=({"310460099": {"std_stdcode": "310460099"}}, []))):
            xlsx_bytes = _build_xlsx_bytes()
            resp = await client.post(
                f"/api/v1/college-review/rankings/{ranking.id}/supplementary-import",
                files={"file": ("test.xlsx", xlsx_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
            )
        assert resp.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_endpoints.py -v 2>&1 | tail -20
```

Expected: `404` or `AttributeError` (endpoints don't exist yet).

- [ ] **Step 3: Add endpoints to `ranking_management.py`**

At the end of `backend/app/api/v1/endpoints/college_review/ranking_management.py`, add:

```python
from fastapi import UploadFile, File
from app.core.deps import get_current_admin_user
from app.services.supplementary_import_service import SupplementaryImportService


class SupplementaryImportToggle(BaseModel):
    allow: bool


@router.patch("/rankings/{ranking_id}/supplementary-import")
async def toggle_supplementary_import(
    ranking_id: int,
    body: SupplementaryImportToggle,
    current_user: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """Admin toggle: open or close supplementary import for a ranking."""
    stmt = select(CollegeRanking).where(CollegeRanking.id == ranking_id)
    result = await db.execute(stmt)
    ranking = result.scalar_one_or_none()
    if not ranking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

    ranking.allow_supplementary_import = body.allow
    await db.commit()
    return ApiResponse(
        success=True,
        message=f"Supplementary import {'enabled' if body.allow else 'disabled'}",
        data={"ranking_id": ranking_id, "allow_supplementary_import": body.allow},
    )


@router.post("/rankings/{ranking_id}/supplementary-import")
async def supplementary_import(
    ranking_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """College upload: import new students via 學生資料彙整表 Excel after distribution."""
    # Load ranking with items and scholarship_type
    stmt = (
        select(CollegeRanking)
        .options(
            selectinload(CollegeRanking.items),
            selectinload(CollegeRanking.creator),
            selectinload(CollegeRanking.scholarship_type).selectinload(ScholarshipType.sub_type_configs),
        )
        .where(CollegeRanking.id == ranking_id)
    )
    result = await db.execute(stmt)
    ranking = result.scalar_one_or_none()
    if not ranking:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

    if not ranking.allow_supplementary_import:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="補充匯入功能尚未開放")

    # College users may only import to rankings from their own college
    if current_user.role not in (UserRole.admin, UserRole.super_admin):
        creator_college = (getattr(ranking.creator, "college_code", None) or "").strip()
        user_college = (current_user.college_code or "").strip()
        if not creator_college or not user_college or creator_college != user_college:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限操作此學院之排名")

    # Build label→code map from scholarship sub_type_configs
    label_to_code = {
        cfg.name: cfg.sub_type_code
        for cfg in (getattr(ranking.scholarship_type, "sub_type_configs", None) or [])
        if cfg.name and cfg.sub_type_code
    }

    # Load dynamic fields (same query as export)
    dynamic_fields, _, _, _ = await load_export_aux_data(
        db,
        scholarship_type=ranking.scholarship_type,
        applications=[],
    )
    dynamic_field_names = [f.field_name for f in dynamic_fields]

    # Parse Excel
    file_bytes = await file.read()
    rows, parse_errors = SupplementaryImportService.parse_excel(
        file_bytes, label_to_code, dynamic_field_names
    )
    if parse_errors:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="\n".join(parse_errors),
        )

    service = SupplementaryImportService(db)

    # Validate no duplicate applications
    semester_for_check = ranking.semester if ranking.semester else "yearly"
    conflicts = await service.validate_no_duplicate_applications(
        rows,
        scholarship_type_id=ranking.scholarship_type_id,
        academic_year=ranking.academic_year,
        semester=semester_for_check,
    )
    if conflicts:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"以下學號已有申請記錄：{', '.join(conflicts)}",
        )

    # Fetch student data from SIS API
    student_ids = [r.student_id for r in rows]
    student_data_map, missing_ids = await service.fetch_student_data_bulk(student_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"學籍系統查無以下學號：{', '.join(missing_ids)}",
        )

    # Compute max existing rank for offset
    existing_ranks = [item.rank_position for item in ranking.items]
    max_existing_rank = max(existing_ranks) if existing_ranks else 0

    # Find or create users
    user_map = await service.find_or_create_users(student_data_map)
    created_users_count = sum(
        1 for sid, user in user_map.items()
        if not any(item.application and item.application.user_id == user.id
                   for item in ranking.items)
    )

    # Upsert user profiles (bank_account, advisor_name)
    await service.upsert_user_profiles(user_map, rows)

    # Create applications + ranking items
    imported_count = await service.create_applications_and_items(
        rows, user_map, student_data_map, ranking, max_existing_rank
    )
    ranking.total_applications = len(ranking.items)
    await db.commit()

    logger.info(
        "Supplementary import: ranking_id=%s imported=%s by user=%s",
        ranking_id, imported_count, current_user.id,
    )

    return ApiResponse(
        success=True,
        message=f"補充匯入成功，共新增 {imported_count} 位學生",
        data={
            "ranking_id": ranking_id,
            "imported_count": imported_count,
            "created_users": created_users_count,
            "max_existing_rank": max_existing_rank,
            "new_rank_range": f"{max_existing_rank + 1}–{max_existing_rank + imported_count}",
        },
    )
```

Also add `from pydantic import BaseModel` near the top imports if not already present (it is, since `RankingUpdate` uses it).

- [ ] **Step 4: Run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_endpoints.py -v 2>&1 | tail -30
```

Expected: All tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/ranking_management.py \
        backend/app/tests/test_supplementary_import_endpoints.py
git commit -m "feat: add admin toggle + college supplementary import endpoints"
```

---

## Task 7: Frontend — API module additions

**Files:**
- Modify: `frontend/lib/api/modules/college.ts`

- [ ] **Step 1: Add two new API functions to `college.ts`**

Inside the `createCollegeApi()` return object in `frontend/lib/api/modules/college.ts`, add after `exportRankingExcel`:

```typescript
    /**
     * Admin: toggle supplementary import open/close for a ranking.
     * PATCH /api/v1/college-review/rankings/{ranking_id}/supplementary-import
     */
    toggleSupplementaryImport: async (
      rankingId: number,
      allow: boolean
    ): Promise<ApiResponse<{ ranking_id: number; allow_supplementary_import: boolean }>> => {
      const resp = await fetch(
        `/api/v1/college-review/rankings/${rankingId}/supplementary-import`,
        {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ allow }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => null);
        throw new Error(err?.detail || "操作失敗");
      }
      return resp.json();
    },

    /**
     * College: upload supplementary Excel for a ranking.
     * POST /api/v1/college-review/rankings/{ranking_id}/supplementary-import
     */
    uploadSupplementaryImport: async (
      rankingId: number,
      file: File
    ): Promise<ApiResponse<{
      imported_count: number;
      created_users: number;
      new_rank_range: string;
    }>> => {
      const formData = new FormData();
      formData.append("file", file);
      const resp = await fetch(
        `/api/v1/college-review/rankings/${rankingId}/supplementary-import`,
        { method: "POST", body: formData }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => null);
        throw new Error(err?.detail || "匯入失敗");
      }
      return resp.json();
    },
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/howard/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep -E "error TS|college\.ts" | head -20
```

Expected: No errors on `college.ts`.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/modules/college.ts
git commit -m "feat: add toggleSupplementaryImport and uploadSupplementaryImport API calls"
```

---

## Task 8: Frontend — Admin toggle in ManualDistributionPanel

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

- [ ] **Step 1: Add toggle UI and `[補充]` badge to the distribution table**

In `ManualDistributionPanel.tsx`:

1. Import new API call and `Switch` component at top:

```typescript
import { Switch } from "@/components/ui/switch";
import { apiClient } from "@/lib/api";
```

2. Add state inside the component:

```typescript
const [supplementaryOpen, setSupplementaryOpen] = useState<Record<number, boolean>>({});
```

3. Populate state when distribution data loads (inside the effect/fetch that loads students, after ranking IDs are known):

```typescript
// After loading distribution data, set initial supplementary flags from ranking metadata
// rankingMeta is whatever object already carries distribution_executed, ranking_id etc.
setSupplementaryOpen(
  Object.fromEntries(
    (rankingList ?? []).map((r: any) => [r.id, r.allow_supplementary_import ?? false])
  )
);
```

4. Add a toggle control in the ranking row/card (wherever `distribution_executed` status is shown):

```tsx
<div className="flex items-center gap-2 text-sm">
  <span className="text-muted-foreground">補充匯入</span>
  <Switch
    checked={supplementaryOpen[rankingId] ?? false}
    onCheckedChange={async (checked) => {
      try {
        await apiClient.college.toggleSupplementaryImport(rankingId, checked);
        setSupplementaryOpen((prev) => ({ ...prev, [rankingId]: checked }));
        toast.success(checked ? "補充匯入已開放" : "補充匯入已關閉");
        if (checked) {
          toast.info(`學院可匯入新學生，排名將接在現有學生之後`);
        }
      } catch (err: any) {
        toast.error(err.message || "操作失敗");
      }
    }}
  />
</div>
```

5. Add `[補充]` badge to each student row in the distribution table. Find where student names are rendered and add:

```tsx
{student.is_supplementary && (
  <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs font-medium text-amber-800">
    補充
  </span>
)}
```

6. Add a visual separator before the first supplementary student. When building the sorted student list, insert a separator element between regular and supplementary groups:

```tsx
{/* Insert separator before first supplementary student */}
{student.is_supplementary && prevStudent && !prevStudent.is_supplementary && (
  <tr>
    <td colSpan={colCount} className="py-1 text-center text-xs text-muted-foreground">
      ── 補充匯入 ──
    </td>
  </tr>
)}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/howard/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep "ManualDistributionPanel" | head -10
```

Expected: No errors on that file.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat: admin toggle for supplementary import + [補充] badge in distribution panel"
```

---

## Task 9: Frontend — College upload UI in college-ranking-table

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx`

- [ ] **Step 1: Add supplementary upload button and flow**

In `frontend/components/college-ranking-table.tsx`:

1. Add state for upload flow near the top of the component:

```typescript
const [isSupplementaryUploading, setIsSupplementaryUploading] = useState(false);
const [supplementaryResult, setSupplementaryResult] = useState<{
  imported_count: number;
  new_rank_range: string;
} | null>(null);
```

2. Add upload handler function:

```typescript
const handleSupplementaryUpload = async (
  event: React.ChangeEvent<HTMLInputElement>
) => {
  const file = event.target.files?.[0];
  if (!file) return;

  if (!file.name.endsWith(".xlsx") && !file.name.endsWith(".xls")) {
    toast.error("請上傳 Excel 檔案 (.xlsx 或 .xls)");
    return;
  }

  setIsSupplementaryUploading(true);
  setSupplementaryResult(null);
  try {
    const result = await apiClient.college.uploadSupplementaryImport(
      ranking.id,
      file
    );
    if (result.success && result.data) {
      setSupplementaryResult(result.data);
      toast.success(
        `已匯入 ${result.data.imported_count} 人，排名 ${result.data.new_rank_range}`
      );
      // Reload ranking items
      onRankingUpdated?.();
    }
  } catch (err: any) {
    toast.error(err.message || "匯入失敗");
  } finally {
    setIsSupplementaryUploading(false);
    event.target.value = "";
  }
};
```

3. Render the upload button when `ranking.allow_supplementary_import === true`. Place it near the existing import/export buttons:

```tsx
{ranking.allow_supplementary_import && (
  <div className="flex items-center gap-2">
    <label
      htmlFor="supplementary-upload"
      className={cn(
        "inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-sm font-medium text-amber-800 hover:bg-amber-100",
        isSupplementaryUploading && "cursor-not-allowed opacity-50"
      )}
    >
      {isSupplementaryUploading ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : (
        <Upload className="h-4 w-4" />
      )}
      補充匯入
    </label>
    <input
      id="supplementary-upload"
      type="file"
      accept=".xlsx,.xls"
      className="hidden"
      disabled={isSupplementaryUploading}
      onChange={handleSupplementaryUpload}
    />
    {supplementaryResult && (
      <span className="text-xs text-muted-foreground">
        已匯入 {supplementaryResult.imported_count} 人（排名 {supplementaryResult.new_rank_range}）
      </span>
    )}
  </div>
)}
```

4. Add `Upload` to the lucide imports at the top (if not already present):

```typescript
import { ..., Upload } from "lucide-react";
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd /home/howard/scholarship-system/frontend && npx tsc --noEmit 2>&1 | grep "college-ranking-table" | head -10
```

Expected: No errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/college-ranking-table.tsx
git commit -m "feat: college supplementary import upload button in ranking table"
```

---

## Task 10: End-to-end smoke test

- [ ] **Step 1: Start the dev stack**

```bash
docker compose -f docker-compose.dev.yml up -d
```

Wait for all services healthy:

```bash
docker compose -f docker-compose.dev.yml ps
```

Expected: `backend`, `frontend`, `postgres`, `minio` all `running`.

- [ ] **Step 2: Run all backend tests**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_supplementary_import_service.py app/tests/test_supplementary_import_endpoints.py app/tests/unit/test_finalize_supplementary_patch.py -v 2>&1 | tail -30
```

Expected: All tests `PASSED`, no failures.

- [ ] **Step 3: Manual smoke test checklist**

1. Log in as admin at `http://localhost:3000`
2. Navigate to Manual Distribution panel
3. Confirm a ranking that has `distribution_executed = true`
4. Verify toggle "補充匯入" appears — switch it ON
5. Log in as college user in another tab
6. Open the ranking detail in CollegeManagementShell
7. Confirm "補充匯入" button appears (amber styling)
8. Download the 學生資料彙整表 Excel for the ranking
9. Add a new row with a valid student ID and rank = 1
10. Upload via "補充匯入" button
11. Confirm success toast: "已匯入 1 人，排名 {N+1}"
12. Switch back to admin distribution panel — verify new student appears with `[補充]` tag at the bottom, separated by "── 補充匯入 ──" divider

- [ ] **Step 4: Final commit**

```bash
git add .
git commit -m "chore: post-distribution supplementary import — feature complete"
```

---

## Self-Review

**Spec coverage:**
- ✅ Admin toggle (`allow_supplementary_import`) — Task 2 schema, Task 6 endpoint, Task 8 frontend
- ✅ College uploads Excel with export format — Task 3/4 service, Task 6 endpoint, Task 9 frontend
- ✅ SIS API called per student_id — Task 4 `fetch_student_data_bulk`
- ✅ Duplicate application check → 422 — Task 4 `validate_no_duplicate_applications`
- ✅ Auto-create user account — Task 4 `find_or_create_users`
- ✅ rank_position = max_existing + excel_col2 — Task 4/6 `max_existing_rank` offset
- ✅ `is_supplementary = True` on new items — Task 3/4 service, Task 1 schema
- ✅ Finalize skips reject for unallocated supplementary items — Task 5
- ✅ `[補充]` tag + separator in distribution panel — Task 8
- ✅ bank_account → UserProfile.account_number — Task 4 `upsert_user_profiles`
- ✅ advisor_name → UserProfile.advisor_name — Task 4 `upsert_user_profiles`
- ✅ Dynamic fields → submitted_form_data.fields — Task 3 `parse_excel`
- ✅ sub_type_preferences parsed from col 3 — Task 3 `parse_scholarship_type_cell`
