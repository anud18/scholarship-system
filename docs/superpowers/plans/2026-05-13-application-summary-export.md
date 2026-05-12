# Application Summary Excel Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a department-scoped 「申請總表」 Excel export reachable by college users (own academy only) and admins, reusing the existing 學生資料彙整表 layout with the rank column left blank. Supports single-department `.xlsx` and multi-department `.zip` modes.

**Architecture:** Reuse `CollegeRankingExportService.build_workbook` by making `ExportRow.rank_position` optional. Extract the shared "load aux data" pipeline (dynamic fields, sub-type labels, profile account, advisor names) from the existing ranking export endpoint into a `_helpers.load_export_aux_data` function. Add two new endpoints under `/api/v1/college-review/applications/` — one returning a single `.xlsx`, one returning a `.zip` bundle. Frontend adds a department selector + 「匯出申請總表」 button to `ApplicationReviewPanel`.

**Tech Stack:** FastAPI, SQLAlchemy (async), openpyxl, Python `zipfile`, Next.js, React, TypeScript, `fetch + blob` for binary downloads.

**Spec:** `docs/superpowers/specs/2026-05-13-application-summary-export-design.md`

---

## Pre-flight

### Task 0: Verify endpoint test infrastructure

**Why:** The prior ranking-export spec deferred endpoint integration tests due to an `aiosqlite` / `httpx.AsyncClient(app=...)` gap in `backend/app/tests/conftest.py`. Find out whether the gap still applies before depending on endpoint tests in later tasks.

**Files:**
- Inspect: `backend/app/tests/conftest.py`
- Inspect: `backend/tests/conftest.py` (if exists)

- [ ] **Step 1: Find the conftest and any existing endpoint tests**

```bash
find backend -name "conftest.py" -type f
ls backend/tests/test_*endpoint*.py 2>/dev/null
ls backend/app/tests/ 2>/dev/null
```

- [ ] **Step 2: Try running a smoke endpoint test if one exists**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_mock_sso.py -v 2>&1 | head -40
```

Expected outcomes:
- PASS → endpoint tests work, proceed straight to Task 4.
- FAIL with `httpx.AsyncClient(app=...)` or `aiosqlite` errors → record this; Task 4 must include the conftest fix as Step 1.

- [ ] **Step 3: Document the decision**

No commit. Just note in the conversation whether endpoint tests are usable as-is or whether Task 4 has to fix conftest first.

---

## Phase 1 — Service change (TDD)

### Task 1: Make `ExportRow.rank_position` optional and render empty cell when `None`

**Files:**
- Modify: `backend/app/services/college_ranking_export_service.py`
- Test: `backend/tests/test_college_ranking_export_service.py`

- [ ] **Step 1: Add failing regression test**

Append the following inside `backend/tests/test_college_ranking_export_service.py` at the end of the existing `class TestStaticColumns` block (so the helper imports are already in scope):

```python
    def test_rank_position_none_renders_empty_cell(self):
        """Empty rank cell — used by 申請總表 export which has no rank yet."""
        row = ExportRow(
            rank_position=None,
            application=FakeApplication(
                sub_type_preferences=["nstc"],
                student_data=_full_student_data(),
            ),
        )
        wb_bytes = _build_workbook(rows=[row])
        wb = load_workbook(io.BytesIO(wb_bytes))
        ws = wb.active
        # Data row is row 3 (row 1 = title, row 2 = header)
        # Column 1 = NO. (row index = 1), Column 2 = rank
        assert ws.cell(row=3, column=1).value == 1
        assert ws.cell(row=3, column=2).value == ""
```

- [ ] **Step 2: Run the test, expect failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_college_ranking_export_service.py::TestStaticColumns::test_rank_position_none_renders_empty_cell -v
```

Expected: FAIL. Most likely the dataclass currently types `rank_position: int` and either the failure is a type complaint at construction time OR `ws.cell(...).value` ends up as `None` (openpyxl coerces `None` → empty) — either way the assertion will fail OR pass spuriously. We want the explicit `""` after the change, so check the failure message carefully.

- [ ] **Step 3: Make `rank_position` optional and render `""` when `None`**

In `backend/app/services/college_ranking_export_service.py`:

```python
# Around line 54 — change the dataclass field type
@dataclass
class ExportRow:
    """One ranked application's data."""

    rank_position: Optional[int]
    application: Any  # Duck-typed: needs sub_type_preferences, sub_scholarship_type, student_data, submitted_form_data
    bank_account: Optional[str] = None  # 郵局帳號 (from user_profiles.account_number)
    advisor_names: Optional[str] = None  # 指導教授姓名 (comma-joined if multiple advisors)
```

```python
# Around line 126 — change the cell value
ws.cell(
    row=excel_row,
    column=2,
    value=(row.rank_position if row.rank_position is not None else ""),
)
```

- [ ] **Step 4: Run the new test plus the full service test file**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_college_ranking_export_service.py -v
```

Expected: ALL pass (new test + every existing test).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/college_ranking_export_service.py backend/tests/test_college_ranking_export_service.py
git commit -m "feat(export-service): allow Optional rank_position; render empty cell when None"
```

---

## Phase 2 — Extract shared load helper (refactor)

### Task 2: Move the export-aux-data loading block into `_helpers.load_export_aux_data`

**Why:** Both the existing ranking export and the new summary export need the same four lookups (dynamic fields, sub-type labels, profile account numbers, advisor names). Centralising them in `_helpers.py` keeps the new endpoint compact and prevents drift.

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/_helpers.py`
- Modify: `backend/app/api/v1/endpoints/college_review/ranking_management.py:1127-1199` (the load block; line numbers may have drifted slightly)
- Test: covered by re-running existing service tests + the existing ranking export endpoint behaviour (manual smoke).

- [ ] **Step 1: Add the helper function to `_helpers.py`**

Append the following at the bottom of `backend/app/api/v1/endpoints/college_review/_helpers.py`. Imports go at the top of the file alongside the existing ones.

```python
# Add to imports at top of file
from typing import Iterable

from app.models.application_field import ApplicationField, FieldType
from app.models.professor_student import ProfessorStudentRelationship
from app.models.user_profile import UserProfile
from app.services.college_ranking_export_service import DynamicFieldSpec


async def load_export_aux_data(
    db: AsyncSession,
    *,
    scholarship_type,  # ScholarshipType ORM object or None
    applications: Iterable[Any],
) -> tuple[
    list[DynamicFieldSpec],
    dict[str, str],
    dict[int, str],
    dict[int, str],
]:
    """Bulk-load auxiliary data shared by the 學生資料彙整表 exports.

    Returns:
        (dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user)
    """

    # 1. Dynamic text fields flagged for export
    dynamic_fields: list[DynamicFieldSpec] = []
    scholarship_type_code = scholarship_type.code if scholarship_type else None
    if scholarship_type_code:
        df_stmt = (
            select(ApplicationField)
            .where(
                ApplicationField.scholarship_type == scholarship_type_code,
                ApplicationField.include_in_college_export.is_(True),
                ApplicationField.is_active.is_(True),
                ApplicationField.field_type == FieldType.TEXT.value,
            )
            .order_by(ApplicationField.display_order, ApplicationField.id)
        )
        rows = (await db.execute(df_stmt)).scalars().all()
        dynamic_fields = [
            DynamicFieldSpec(
                field_name=f.field_name,
                field_label=f.field_label,
                export_column_label=f.export_column_label,
                display_order=f.display_order or 0,
            )
            for f in rows
        ]

    # 2. Sub-type Chinese labels
    sub_type_labels: dict[str, str] = {}
    if scholarship_type:
        for cfg in getattr(scholarship_type, "sub_type_configs", []) or []:
            if cfg.sub_type_code and cfg.name:
                sub_type_labels[cfg.sub_type_code] = cfg.name

    # 3. Profile lookups (account_number, advisor_name fallback)
    user_ids: set[int] = set()
    for app in applications:
        if app is None:
            continue
        uid = getattr(app, "user_id", None)
        if uid is not None:
            user_ids.add(uid)

    account_number_by_user: dict[int, str] = {}
    advisor_name_by_user: dict[int, str] = {}

    if user_ids:
        profile_stmt = select(
            UserProfile.user_id, UserProfile.account_number, UserProfile.advisor_name
        ).where(UserProfile.user_id.in_(user_ids))
        for uid, acct, adv in (await db.execute(profile_stmt)).all():
            if acct:
                account_number_by_user[uid] = acct
            if adv:
                advisor_name_by_user[uid] = adv

    # 4. Advisor names from relationships
    advisor_names_by_user: dict[int, list[str]] = {uid: [] for uid in user_ids}
    if user_ids:
        from app.models.user import User  # local to avoid circular imports

        rel_stmt = (
            select(ProfessorStudentRelationship.student_id, User.name)
            .join(User, User.id == ProfessorStudentRelationship.professor_id)
            .where(
                ProfessorStudentRelationship.student_id.in_(user_ids),
                ProfessorStudentRelationship.is_active.is_(True),
                ProfessorStudentRelationship.relationship_type.in_(["advisor", "co_advisor"]),
            )
            .order_by(ProfessorStudentRelationship.student_id, User.name)
        )
        for student_id, prof_name in (await db.execute(rel_stmt)).all():
            if prof_name:
                advisor_names_by_user[student_id].append(prof_name)

    advisor_string_by_user: dict[int, str] = {}
    for uid in user_ids:
        names = advisor_names_by_user.get(uid) or []
        if names:
            advisor_string_by_user[uid] = "、".join(names)
        elif uid in advisor_name_by_user:
            advisor_string_by_user[uid] = advisor_name_by_user[uid]

    return dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user
```

- [ ] **Step 2: Replace the inline block in `ranking_management.py` with a helper call**

In `backend/app/api/v1/endpoints/college_review/ranking_management.py`, locate the `export_ranking_excel` function (around line 1093). Replace the loading section (currently lines ~1127-1199, the four blocks loading dynamic fields, sub_type_labels, profile accounts, advisor names) with:

```python
    # 3-5. Bulk-load aux data (dynamic fields, sub-type labels, accounts, advisors)
    from ._helpers import load_export_aux_data  # local import keeps top-of-file imports small

    items_sorted = sorted(ranking.items or [], key=lambda x: x.rank_position)
    apps_in_ranking = [item.application for item in items_sorted if item.application is not None]

    dynamic_fields, sub_type_labels, account_number_by_user, advisor_string_by_user = (
        await load_export_aux_data(
            db,
            scholarship_type=ranking.scholarship_type,
            applications=apps_in_ranking,
        )
    )
```

Then update the `ExportRow` construction below to use the new dicts:

```python
    export_rows = [
        ExportRow(
            rank_position=item.rank_position,
            application=item.application,
            bank_account=account_number_by_user.get(item.application.user_id),
            advisor_names=advisor_string_by_user.get(item.application.user_id),
        )
        for item in items_sorted
        if item.application is not None
    ]
```

Remove the now-unused imports from the top of `ranking_management.py` (`ApplicationField`, `FieldType`, `ProfessorStudentRelationship`, `UserProfile`) **only if no other code in the file still uses them**. Run `grep -n "ApplicationField\b\|FieldType\b\|ProfessorStudentRelationship\b\|UserProfile\b" backend/app/api/v1/endpoints/college_review/ranking_management.py` to verify before deleting any import.

- [ ] **Step 3: Verify the refactor against existing service tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_college_ranking_export_service.py -v
```

Expected: all pass (refactor is at endpoint level; service tests still cover the rendering path).

- [ ] **Step 4: Manual smoke — start dev stack and hit the existing ranking export endpoint**

```bash
docker compose -f docker-compose.dev.yml up -d backend postgres
# Wait until backend is ready
docker compose -f docker-compose.dev.yml logs --tail 30 backend
```

In a separate terminal or with `curl`:
```bash
TOKEN="<dev admin token>"
RANKING_ID="<any existing ranking id>"
curl -s -o /tmp/ranking.xlsx -w "%{http_code}\n" \
  -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/college-review/rankings/$RANKING_ID/export-excel"
file /tmp/ranking.xlsx
```

Expected: `200` and `/tmp/ranking.xlsx: Microsoft Excel 2007+`.

If no existing ranking is available, skip this step but log it in the commit message ("Smoke deferred — no seed ranking in dev env").

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/_helpers.py \
        backend/app/api/v1/endpoints/college_review/ranking_management.py
git commit -m "refactor(college-review): extract load_export_aux_data helper"
```

---

## Phase 3 — New endpoint module (TDD)

### Task 3: Scaffold the new endpoint module and register the router

**Files:**
- Create: `backend/app/api/v1/endpoints/college_review/application_summary_export.py`
- Modify: `backend/app/api/v1/endpoints/college_review/__init__.py`

- [ ] **Step 1: Create the empty module with the router stub**

Create `backend/app/api/v1/endpoints/college_review/application_summary_export.py`:

```python
"""
Application Summary (申請總表) Excel Export Endpoints

Two endpoints, both under /api/v1/college-review/applications/:
- GET /department-summary-export       → single department .xlsx
- GET /department-summary-export-bulk  → multi-department .zip

Reuses CollegeRankingExportService with ExportRow.rank_position=None so the
學院初審會議之學院排序 column renders empty cells.
"""

from __future__ import annotations

import io
import logging
import re
import zipfile
from typing import Optional
from urllib.parse import quote as _url_quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import require_college
from app.db.deps import get_db
from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.models.student import Department
from app.models.user import User, UserRole
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

from ._helpers import load_export_aux_data, normalize_semester_value

logger = logging.getLogger(__name__)

router = APIRouter()

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ZIP_MEDIA_TYPE = "application/zip"

# Characters not allowed in cross-platform filenames
_UNSAFE_FILENAME_RE = re.compile(r'[\\/:*?"<>|]')


def _sanitise_filename_part(value: str) -> str:
    return _UNSAFE_FILENAME_RE.sub("_", value).strip() or "untitled"
```

- [ ] **Step 2: Register the router in `__init__.py`**

Edit `backend/app/api/v1/endpoints/college_review/__init__.py`:

```python
from .application_review import router as application_router
from .application_summary_export import router as application_summary_export_router
from .distribution import router as distribution_router
from .export_package import router as export_package_router
from .ranking_management import router as ranking_router
from .utilities import router as utilities_router

# ... existing setup ...

router.include_router(application_router, tags=["College Review - Applications"])
router.include_router(application_summary_export_router, tags=["College Review - Applications Summary"])
router.include_router(ranking_router, tags=["College Review - Rankings"])
router.include_router(distribution_router, tags=["College Review - Distribution"])
router.include_router(utilities_router, tags=["College Review - Utilities"])
router.include_router(export_package_router, tags=["College Review - Export"])
```

- [ ] **Step 3: Verify backend starts**

```bash
docker compose -f docker-compose.dev.yml up -d backend
docker compose -f docker-compose.dev.yml logs --tail 50 backend | grep -E "Application startup|Error|Traceback" | head -20
```

Expected: `Application startup complete` and no import errors.

- [ ] **Step 4: Commit the scaffold**

```bash
git add backend/app/api/v1/endpoints/college_review/application_summary_export.py \
        backend/app/api/v1/endpoints/college_review/__init__.py
git commit -m "feat(application-summary-export): scaffold router and module"
```

---

### Task 4: Implement single-department endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/application_summary_export.py`
- Create: `backend/tests/test_application_summary_export_endpoint.py`

**Note:** If Task 0 found the conftest broken, fix it as Step 0 here before writing tests:

```python
# In backend/app/tests/conftest.py — replace the broken AsyncClient pattern with:
from httpx import ASGITransport, AsyncClient

@pytest_asyncio.fixture
async def async_client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

And ensure `aiosqlite` is in `backend/pyproject.toml` `[project.optional-dependencies].dev`:

```toml
dev = [
    # ... existing deps ...
    "aiosqlite>=0.20.0",
]
```

Skip this fix-step entirely if Task 0 confirmed endpoint tests already work.

- [ ] **Step 1: Write the failing happy-path test**

Create `backend/tests/test_application_summary_export_endpoint.py`:

```python
"""Integration tests for the 申請總表 (application summary) Excel export endpoints."""

import io
import zipfile

import pytest
from openpyxl import load_workbook


pytestmark = pytest.mark.asyncio


SINGLE_PATH = "/api/v1/college-review/applications/department-summary-export"
BULK_PATH = "/api/v1/college-review/applications/department-summary-export-bulk"


async def test_single_department_happy_path(
    async_client, admin_token, seed_phd_apps_two_depts
):
    """Admin downloads a single dept .xlsx — should be 200 with non-empty body."""

    scholarship_type_id, academic_year, dept_code = seed_phd_apps_two_depts
    resp = await async_client.get(
        SINGLE_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "department_code": dept_code,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    body = resp.content
    assert len(body) > 0

    wb = load_workbook(io.BytesIO(body))
    ws = wb.active
    # Row 1 = title, Row 2 = header, Row 3+ = data
    # Column 2 = 學院初審會議之學院排序 — must be empty for summary export
    assert ws.cell(row=3, column=2).value == ""


async def test_single_department_college_user_own_dept_ok(
    async_client, college_token_dept_a, seed_phd_apps_two_depts
):
    scholarship_type_id, academic_year, dept_code = seed_phd_apps_two_depts
    resp = await async_client.get(
        SINGLE_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "department_code": dept_code,
        },
        headers={"Authorization": f"Bearer {college_token_dept_a}"},
    )
    assert resp.status_code == 200


async def test_single_department_college_user_other_dept_forbidden(
    async_client, college_token_dept_a, seed_phd_apps_two_depts_other_college
):
    scholarship_type_id, academic_year, dept_code = seed_phd_apps_two_depts_other_college
    resp = await async_client.get(
        SINGLE_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "department_code": dept_code,
        },
        headers={"Authorization": f"Bearer {college_token_dept_a}"},
    )
    assert resp.status_code == 403


async def test_single_department_not_found_returns_404(
    async_client, admin_token, seed_phd_apps_two_depts
):
    scholarship_type_id, academic_year, _ = seed_phd_apps_two_depts
    resp = await async_client.get(
        SINGLE_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "department_code": "ZZZZ_DOES_NOT_EXIST",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404


async def test_single_department_no_applications_returns_header_only_workbook(
    async_client, admin_token, seed_empty_department
):
    scholarship_type_id, academic_year, dept_code = seed_empty_department
    resp = await async_client.get(
        SINGLE_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "department_code": dept_code,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    ws = wb.active
    # Only title + header — no data row
    assert ws.cell(row=3, column=1).value is None
```

> Fixtures (`async_client`, `admin_token`, `college_token_dept_a`, `seed_phd_apps_two_depts`, `seed_phd_apps_two_depts_other_college`, `seed_empty_department`) must exist in `backend/tests/conftest.py` or `backend/app/tests/conftest.py`. Add them now if any are missing — keep them minimal: factory functions that insert a `ScholarshipType`, two `Department` rows (one matching the college user's `college_code` academy), and a small batch of `Application` rows with `student_data["std_depno"]` set.

> If the conftest setup is non-trivial (existing tests don't follow this pattern), keep the test file but mark each test `@pytest.mark.skipif(not has_fixture, reason="needs db seed fixture")` and surface the gap. The endpoint code still ships in Steps 2-4; service-only correctness is covered by Task 1's tests.

- [ ] **Step 2: Run the test, expect failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_application_summary_export_endpoint.py::test_single_department_happy_path -v
```

Expected: FAIL with a 404 (endpoint not yet defined) or a 422 (path matched but handler missing).

- [ ] **Step 3: Implement the single-department endpoint**

Append the handler to `backend/app/api/v1/endpoints/college_review/application_summary_export.py`:

```python
@router.get("/applications/department-summary-export")
async def export_department_summary_single(
    scholarship_type_id: int = Query(..., description="Scholarship type ID"),
    academic_year: int = Query(..., description="Academic year"),
    semester: Optional[str] = Query(None, description="first / second / yearly / null"),
    department_code: str = Query(..., min_length=1, description="Department code (Department.code)"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Generate the 申請總表 (申請總表) Excel for one department."""

    normalised_semester = normalize_semester_value(semester)

    # Resolve department row + auth check
    dept = (
        await db.execute(select(Department).where(Department.code == department_code))
    ).scalar_one_or_none()
    if dept is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到系所代碼 {department_code}")

    if current_user.role not in (UserRole.admin, UserRole.super_admin):
        user_college = (current_user.college_code or "").strip()
        dept_academy = (dept.academy_code or "").strip()
        if not user_college or not dept_academy or user_college != dept_academy:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限匯出此系所之資料")

    # Load scholarship type with sub_type_configs eager-loaded
    stype = (
        await db.execute(
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
    ).scalar_one_or_none()
    if stype is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到獎學金類型 ID={scholarship_type_id}")

    # Load applications. student_data is plain JSON (not JSONB) so filter by
    # std_depno in Python rather than via SQL JSON-path. Typical N is < 1k per
    # (scholarship_type, year, semester) so this is fine.
    stmt = select(Application).where(
        Application.scholarship_type_id == scholarship_type_id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status != "deleted",
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    apps = [
        a for a in raw_apps
        if ((a.student_data or {}).get("std_depno") or "").strip() == department_code
    ]
    apps.sort(key=lambda a: ((a.student_data or {}).get("std_stdcode") or "", a.id))

    # Aux data
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db, scholarship_type=stype, applications=apps,
    )

    # Build rows with rank_position=None
    export_rows = [
        ExportRow(
            rank_position=None,
            application=app,
            bank_account=account_by_user.get(app.user_id),
            advisor_names=advisor_by_user.get(app.user_id),
        )
        for app in apps
    ]

    scholarship_name = stype.name or "獎學金"
    dept_name = dept.name or department_code
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
    sheet_name = f"{academic_year}學年"
    base_filename = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{_sanitise_filename_part(dept_name)}.xlsx"
    encoded = _url_quote(base_filename, safe="")

    service = CollegeRankingExportService()
    payload = service.build_workbook(
        rows=export_rows,
        dynamic_fields=dynamic_fields,
        sub_type_labels=sub_type_labels,
        title=title,
        sheet_name=sheet_name,
    )

    return StreamingResponse(
        iter([payload]),
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )
```

- [ ] **Step 4: Run all single-endpoint tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_application_summary_export_endpoint.py -v -k "single"
```

Expected: all `test_single_*` pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/application_summary_export.py \
        backend/tests/test_application_summary_export_endpoint.py
git commit -m "feat(application-summary-export): single-department endpoint"
```

---

### Task 5: Implement bulk (ZIP) endpoint (TDD)

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/application_summary_export.py`
- Modify: `backend/tests/test_application_summary_export_endpoint.py`

- [ ] **Step 1: Append failing bulk tests**

Append to `backend/tests/test_application_summary_export_endpoint.py`:

```python
async def test_bulk_admin_scope_all_returns_zip_with_multiple_files(
    async_client, admin_token, seed_phd_apps_two_depts
):
    scholarship_type_id, academic_year, _ = seed_phd_apps_two_depts
    resp = await async_client.get(
        BULK_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "scope": "all",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/zip")

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert len(names) == 2  # one per dept


async def test_bulk_college_scope_returns_zip_of_own_departments(
    async_client, college_token_dept_a, seed_phd_apps_two_depts
):
    scholarship_type_id, academic_year, _ = seed_phd_apps_two_depts
    resp = await async_client.get(
        BULK_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "scope": "college",
        },
        headers={"Authorization": f"Bearer {college_token_dept_a}"},
    )
    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    # college_token_dept_a's academy has exactly 1 dept with apps
    assert len(zf.namelist()) == 1


async def test_bulk_college_scope_all_forbidden_for_college_user(
    async_client, college_token_dept_a, seed_phd_apps_two_depts
):
    scholarship_type_id, academic_year, _ = seed_phd_apps_two_depts
    resp = await async_client.get(
        BULK_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": academic_year,
            "scope": "all",
        },
        headers={"Authorization": f"Bearer {college_token_dept_a}"},
    )
    assert resp.status_code == 403


async def test_bulk_no_matches_returns_404(
    async_client, admin_token, seed_phd_apps_two_depts
):
    scholarship_type_id, _, _ = seed_phd_apps_two_depts
    resp = await async_client.get(
        BULK_PATH,
        params={
            "scholarship_type_id": scholarship_type_id,
            "academic_year": 999,  # no apps for this year
            "scope": "all",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 404
```

- [ ] **Step 2: Run, expect failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_application_summary_export_endpoint.py -v -k "bulk"
```

Expected: FAIL (handler not defined yet → 404 from FastAPI).

- [ ] **Step 3: Implement the bulk endpoint**

Append to `application_summary_export.py`:

```python
@router.get("/applications/department-summary-export-bulk")
async def export_department_summary_bulk(
    scholarship_type_id: int = Query(...),
    academic_year: int = Query(...),
    semester: Optional[str] = Query(None),
    scope: str = Query(..., pattern="^(college|all)$"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    normalised_semester = normalize_semester_value(semester)
    is_admin = current_user.role in (UserRole.admin, UserRole.super_admin)

    if scope == "all" and not is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="學院使用者僅能匯出本學院資料")

    if scope == "college":
        college_code = (current_user.college_code or "").strip()
        if not college_code:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="未設定學院，無法使用本學院範圍")
        dept_rows = (
            await db.execute(select(Department).where(Department.academy_code == college_code))
        ).scalars().all()
        target_dept_codes = [d.code for d in dept_rows if d.code]
    else:  # scope == "all"
        target_dept_codes = None  # no dept filter on the query

    # Load scholarship type
    stype = (
        await db.execute(
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
    ).scalar_one_or_none()
    if stype is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到獎學金類型 ID={scholarship_type_id}")

    # Load applications. Filter by std_depno in Python since student_data is plain JSON.
    if target_dept_codes is not None and not target_dept_codes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到符合條件的申請資料")

    stmt = select(Application).where(
        Application.scholarship_type_id == scholarship_type_id,
        Application.academic_year == academic_year,
        Application.deleted_at.is_(None),
        Application.status != "deleted",
    )
    if normalised_semester is None:
        stmt = stmt.where(Application.semester.is_(None))
    else:
        stmt = stmt.where(Application.semester == normalised_semester)

    raw_apps = list((await db.execute(stmt)).scalars().all())
    if target_dept_codes is not None:
        allowed = set(target_dept_codes)
        apps = [
            a for a in raw_apps
            if ((a.student_data or {}).get("std_depno") or "").strip() in allowed
        ]
    else:
        apps = raw_apps
    if not apps:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到符合條件的申請資料")

    apps.sort(key=lambda a: ((a.student_data or {}).get("std_stdcode") or "", a.id))

    # Group by std_depno
    groups: dict[str, list] = {}
    for app in apps:
        dept_code = ((app.student_data or {}).get("std_depno") or "").strip() or "未知"
        groups.setdefault(dept_code, []).append(app)

    # Department name lookup
    dept_codes = list(groups.keys())
    dept_rows = (
        await db.execute(select(Department).where(Department.code.in_(dept_codes)))
    ).scalars().all()
    name_by_code = {d.code: d.name for d in dept_rows}

    # Aux data — loaded once over the union of applicants
    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db, scholarship_type=stype, applications=apps,
    )

    scholarship_name = stype.name or "獎學金"
    service = CollegeRankingExportService()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for dept_code, dept_apps in groups.items():
            dept_name = name_by_code.get(dept_code) or dept_code
            export_rows = [
                ExportRow(
                    rank_position=None,
                    application=app,
                    bank_account=account_by_user.get(app.user_id),
                    advisor_names=advisor_by_user.get(app.user_id),
                )
                for app in dept_apps
            ]
            title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
            sheet_name = f"{academic_year}學年"
            xlsx_bytes = service.build_workbook(
                rows=export_rows,
                dynamic_fields=dynamic_fields,
                sub_type_labels=sub_type_labels,
                title=title,
                sheet_name=sheet_name,
            )
            inner_name = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{_sanitise_filename_part(dept_name)}.xlsx"
            zf.writestr(inner_name, xlsx_bytes)

    payload = buf.getvalue()

    scope_label = current_user.college_code if scope == "college" else "全部"
    base_filename = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{_sanitise_filename_part(scope_label or '全部')}.zip"
    encoded = _url_quote(base_filename, safe="")

    return StreamingResponse(
        iter([payload]),
        media_type=ZIP_MEDIA_TYPE,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )
```

- [ ] **Step 4: Run all endpoint tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/test_application_summary_export_endpoint.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/application_summary_export.py \
        backend/tests/test_application_summary_export_endpoint.py
git commit -m "feat(application-summary-export): bulk ZIP endpoint"
```

---

## Phase 4 — Frontend

### Task 6: Add API client helpers

**Files:**
- Modify: `frontend/lib/api/modules/college.ts` (existing module that already hosts `exportRankingExcel`)

- [ ] **Step 1: Inspect the existing module to mirror its style**

```bash
grep -n "exportRankingExcel\|export async function" frontend/lib/api/modules/college.ts | head -20
```

Note the existing helper's pattern (fetch + blob + auth header).

- [ ] **Step 2: Add the two new helpers**

Append to `frontend/lib/api/modules/college.ts`:

```typescript
type SummaryExportArgs = {
  scholarship_type_id: number;
  academic_year: number;
  semester?: string | null;
};

export async function exportDepartmentSummary(
  args: SummaryExportArgs & { department_code: string },
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams();
  params.set("scholarship_type_id", String(args.scholarship_type_id));
  params.set("academic_year", String(args.academic_year));
  if (args.semester) params.set("semester", args.semester);
  params.set("department_code", args.department_code);

  const res = await fetch(
    `${apiBaseUrl}/api/v1/college-review/applications/department-summary-export?${params}`,
    { headers: { Authorization: `Bearer ${getToken()}` } },
  );
  if (!res.ok) {
    throw new Error(await res.text());
  }
  const blob = await res.blob();
  const filename = parseFilenameFromHeader(res.headers.get("content-disposition")) || "申請總表.xlsx";
  return { blob, filename };
}

export async function exportDepartmentSummaryBulk(
  args: SummaryExportArgs & { scope: "college" | "all" },
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams();
  params.set("scholarship_type_id", String(args.scholarship_type_id));
  params.set("academic_year", String(args.academic_year));
  if (args.semester) params.set("semester", args.semester);
  params.set("scope", args.scope);

  const res = await fetch(
    `${apiBaseUrl}/api/v1/college-review/applications/department-summary-export-bulk?${params}`,
    { headers: { Authorization: `Bearer ${getToken()}` } },
  );
  if (!res.ok) {
    throw new Error(await res.text());
  }
  const blob = await res.blob();
  const filename = parseFilenameFromHeader(res.headers.get("content-disposition")) || "申請總表.zip";
  return { blob, filename };
}
```

> `apiBaseUrl`, `getToken`, and `parseFilenameFromHeader` should already exist as module-scope helpers (the existing `exportRankingExcel` uses them). If `parseFilenameFromHeader` does not exist, add it as a local utility that reads RFC 5987 `filename*=UTF-8''<encoded>` and falls back to `filename="..."`. Reuse exactly what `exportRankingExcel` does — do not duplicate logic.

- [ ] **Step 3: Verify the frontend type-checks**

```bash
cd frontend && npm run typecheck
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/modules/college.ts
git commit -m "feat(frontend): add department summary export client helpers"
```

---

### Task 7: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (regenerated)

- [ ] **Step 1: Ensure backend is running**

```bash
docker compose -f docker-compose.dev.yml up -d backend
docker compose -f docker-compose.dev.yml logs --tail 10 backend | grep "Application startup complete"
```

- [ ] **Step 2: Regenerate**

```bash
cd frontend && npm run api:generate
```

- [ ] **Step 3: Verify the new endpoints appear**

```bash
grep -n "department-summary-export" frontend/lib/api/generated/schema.d.ts | head -10
```

Expected: both `/api/v1/college-review/applications/department-summary-export` and `...-bulk` are present.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(frontend): regenerate OpenAPI types for summary export endpoints"
```

---

### Task 8: Wire UI into `ApplicationReviewPanel`

**Files:**
- Modify: `frontend/components/college/review/ApplicationReviewPanel.tsx`

- [ ] **Step 1: Locate where other export buttons live**

```bash
grep -n "下載\|匯出\|Export\|FileArchive\|Download" frontend/components/college/review/ApplicationReviewPanel.tsx | head -20
```

The new control sits next to the existing 「下載」 / 「匯出 ZIP」 toolbar buttons.

- [ ] **Step 2: Add the dropdown + button**

Inside the toolbar block of `ApplicationReviewPanel.tsx`, add:

```tsx
{/* Department selector + 申請總表 download */}
const ALL_DEPTS_OWN = "__college_all__";
const ALL_DEPTS_SYSTEM = "__all__";

const visibleDepartments = useMemo(() => {
  if (!departments) return [];
  if (user.role === "admin" || user.role === "super_admin") return departments;
  return departments.filter((d) => d.academy_code === user.college_code);
}, [departments, user]);

const [summaryDept, setSummaryDept] = useState<string>("");

const handleDownloadSummary = useCallback(async () => {
  if (!summaryDept || !selectedCombination) return;
  try {
    const common = {
      scholarship_type_id: selectedCombination.scholarship_type_id,
      academic_year: selectedCombination.academic_year,
      semester: selectedCombination.semester ?? null,
    };
    let result: { blob: Blob; filename: string };
    if (summaryDept === ALL_DEPTS_OWN) {
      result = await exportDepartmentSummaryBulk({ ...common, scope: "college" });
    } else if (summaryDept === ALL_DEPTS_SYSTEM) {
      result = await exportDepartmentSummaryBulk({ ...common, scope: "all" });
    } else {
      result = await exportDepartmentSummary({ ...common, department_code: summaryDept });
    }
    triggerBlobDownload(result.blob, result.filename);
  } catch (err) {
    toast.error(`匯出失敗：${(err as Error).message}`);
  }
}, [summaryDept, selectedCombination]);
```

And in the JSX render section, next to existing toolbar controls:

```tsx
<Select value={summaryDept} onValueChange={setSummaryDept}>
  <SelectTrigger className="w-[200px]">
    <SelectValue placeholder="選擇系所" />
  </SelectTrigger>
  <SelectContent>
    {visibleDepartments.map((d) => (
      <SelectItem key={d.code} value={d.code}>
        {d.name}
      </SelectItem>
    ))}
    {(user.role === "admin" || user.role === "super_admin" || user.college_code) && (
      <SelectItem value={ALL_DEPTS_OWN}>本學院全部 (ZIP)</SelectItem>
    )}
    {(user.role === "admin" || user.role === "super_admin") && (
      <SelectItem value={ALL_DEPTS_SYSTEM}>全部系所 (ZIP)</SelectItem>
    )}
  </SelectContent>
</Select>
<Button
  variant="outline"
  disabled={!summaryDept || !selectedCombination}
  onClick={handleDownloadSummary}
>
  <Download className="mr-2 h-4 w-4" />
  匯出申請總表
</Button>
```

Add the imports at the top:

```tsx
import { exportDepartmentSummary, exportDepartmentSummaryBulk } from "@/lib/api/modules/college";
import { useMemo, useState, useCallback } from "react";
```

If a `triggerBlobDownload(blob, filename)` helper doesn't already exist in the file, add it locally:

```tsx
function triggerBlobDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
```

- [ ] **Step 3: Typecheck + lint**

```bash
cd frontend && npm run typecheck && npm run lint
```

Expected: clean.

- [ ] **Step 4: Manual smoke (browser)**

```bash
docker compose -f docker-compose.dev.yml up -d
```

Log in as `admin@nycu.edu.tw` / any password (per memory note). Navigate to the college review / applications page. Select a scholarship + year + semester. Pick a department, click 匯出申請總表 → confirm `.xlsx` downloads. Pick 全部系所 → confirm `.zip` downloads with multiple files.

Log in as a college user. Confirm only their academy's departments appear plus 「本學院全部」.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/college/review/ApplicationReviewPanel.tsx
git commit -m "feat(application-summary-export): add UI controls to ApplicationReviewPanel"
```

---

## Phase 5 — Wrap-up

### Task 9: Final verification

- [ ] **Step 1: Run the full backend test suite for the affected files**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  backend/tests/test_college_ranking_export_service.py \
  backend/tests/test_application_summary_export_endpoint.py \
  -v
```

Expected: all pass.

- [ ] **Step 2: Run frontend type/lint**

```bash
cd frontend && npm run typecheck && npm run lint
```

- [ ] **Step 3: Check that nothing else broke**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest backend/tests/ -x --timeout=60 2>&1 | tail -30
```

Expected: no new failures (pre-existing skipped/xfail tests are OK).

- [ ] **Step 4: Verify git log**

```bash
git log --oneline main..HEAD
```

Expected sequence (give or take Task 0/conftest):

```
feat(application-summary-export): add UI controls to ApplicationReviewPanel
chore(frontend): regenerate OpenAPI types for summary export endpoints
feat(frontend): add department summary export client helpers
feat(application-summary-export): bulk ZIP endpoint
feat(application-summary-export): single-department endpoint
feat(application-summary-export): scaffold router and module
refactor(college-review): extract load_export_aux_data helper
feat(export-service): allow Optional rank_position; render empty cell when None
docs(application-summary-export): add design spec
```

- [ ] **Step 5: Open PR**

```bash
git push -u origin worktree-application-summary-export
gh pr create --title "feat: 系所申請總表 Excel 匯出（學院端 + 管理員）" --body "$(cat <<'EOF'
## Summary
- Adds the 申請總表 Excel export reachable by college users (own academy only) and admins.
- Reuses the existing 18-column 學生資料彙整表 layout with the rank column left blank.
- Two endpoints: single-department `.xlsx` and multi-department `.zip` (本學院/全部系所).

## Test plan
- [ ] Service tests pass (`pytest backend/tests/test_college_ranking_export_service.py`).
- [ ] Endpoint tests pass (`pytest backend/tests/test_application_summary_export_endpoint.py`).
- [ ] Manual: admin downloads single dept + ZIP for 全部系所 in dev.
- [ ] Manual: college user sees only own academy's departments + 本學院全部 ZIP.
- [ ] Frontend typecheck + lint clean.

Spec: `docs/superpowers/specs/2026-05-13-application-summary-export-design.md`
EOF
)"
```

---

## Notes for the executing engineer

- **Worktree:** All work happens in `/home/howard/scholarship-system/.claude/worktrees/application-summary-export` on branch `worktree-application-summary-export`. Do NOT `cd` to the main repo.
- **No DB migration.** This feature reuses existing `application_fields.include_in_college_export` and `Department`/`Academy`.
- **Trust the existing pattern.** The `ranking_management.export_ranking_excel` endpoint is the working reference for `Content-Disposition` encoding, auxiliary data loading, and StreamingResponse. Match its style.
- **Test fixtures may need a small one-time investment.** If the project's existing endpoint tests are sparse, expect to add 2-3 fixtures (`seed_phd_apps_two_depts` etc.) the first time. Keep them minimal — they're not production code.
- **YAGNI.** Resist any urge to also surface this from the admin 歷史申請 tab or add a status filter. Both are explicitly out of scope per the spec.
