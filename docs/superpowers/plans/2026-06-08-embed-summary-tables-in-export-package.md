# Embed 申請總表 into /export-package ZIP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Embed 學生資料彙整表 (申請總表) Excel files into the `/export-package` ZIP — one college-level table at the ZIP root plus one per-department table inside each department folder.

**Architecture:** A new service module `export_summary_tables.py` builds the workbooks from the *already-grouped* `dept_groups` that `ExportPackageService` assembled (never re-querying — so each table's rows match the student folders next to it). It reuses `CollegeRankingExportService.build_workbook` (pure xlsx render) and `load_export_aux_data` (dynamic fields / sub-type labels / bank account / advisor). `ExportPackageService.generate_export_zip` calls it after writing the per-student PDFs/files and `writestr`s the results into the same ZIP.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy async, openpyxl, pytest / pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-06-08-embed-summary-tables-in-export-package-design.md`

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/export_summary_tables.py` | **Create** | `build_embedded_summary_tables()` + helpers `_sort_key`, `_dept_name_from_apps`. Owns 申請總表 embedding logic. |
| `backend/app/services/export_package_service.py` | Modify | `_get_scholarship_name` → `_get_scholarship_type`; call the new helper inside `generate_export_zip` and `writestr` results. |
| `backend/app/api/v1/endpoints/college_review/application_summary_export.py` | Modify | Drop the duplicate local `_sort_key`; import it from the new service module (DRY). Behavior unchanged. |
| `backend/app/tests/test_export_summary_tables.py` | **Create** | Unit tests for helpers + `build_embedded_summary_tables` (happy path, college grouping, empty rank column, per-table failure). |
| `backend/app/tests/test_export_package_embeds_summary.py` | **Create** | Integration test: `generate_export_zip` namelist contains the tables; table 學號 == student folders. |

### Import-cycle note (read before coding)

`export_summary_tables` imports `_sanitize_filename` **from** `export_package_service` at module top. To avoid a cycle, `export_package_service` imports `build_embedded_summary_tables` **lazily inside the method** (not at module top). `_sort_key` lives in `export_summary_tables` (the lower/service layer); `application_summary_export` imports it from there (one-directional, endpoint→service). `_helpers.load_export_aux_data` and `college_ranking_export_service` have no back-imports, so they are safe to import from the new module.

---

## Task 1: New module with pure helpers (`_sort_key`, `_dept_name_from_apps`)

**Files:**
- Create: `backend/app/services/export_summary_tables.py`
- Test: `backend/app/tests/test_export_summary_tables.py`

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_export_summary_tables.py`:

```python
"""Unit tests for export_summary_tables: pure helpers + build_embedded_summary_tables.

These tests avoid DB / MinIO / reportlab font by monkeypatching load_export_aux_data
and constructing transient Application objects via Application(**defaults) (never
Application.__new__, which leaves _sa_instance_state unset).
"""

import io

import pytest
from openpyxl import load_workbook

from app.models.application import Application
from app.services.export_summary_tables import _dept_name_from_apps, _sort_key


def _mk_app(app_id, user_id, dep_no, dep_name, std_code, cname="某生", academy="某學院"):
    a = Application(
        user_id=user_id,
        scholarship_type_id=1,
        academic_year=114,
        student_data={
            "trm_depno": dep_no,
            "trm_depname": dep_name,
            "trm_academyname": academy,
            "std_stdcode": std_code,
            "std_cname": cname,
        },
    )
    a.id = app_id
    return a


class TestSortKey:
    def test_sorts_by_student_code_blanks_last(self):
        a1 = _mk_app(1, 11, "1000", "A系", "002")
        a2 = _mk_app(2, 12, "1000", "A系", "001")
        a3 = _mk_app(3, 13, "1000", "A系", "")  # blank code → last
        ordered = sorted([a1, a2, a3], key=_sort_key)
        assert [a.id for a in ordered] == [2, 1, 3]


class TestDeptNameFromApps:
    def test_takes_first_non_empty_depname(self):
        apps = [_mk_app(1, 11, "1000", "", "001"), _mk_app(2, 12, "1000", "教育博", "002")]
        assert _dept_name_from_apps(apps) == "教育博"

    def test_falls_back_when_all_blank(self):
        apps = [_mk_app(1, 11, "1000", "", "001")]
        assert _dept_name_from_apps(apps) == "未知系所"
```

- [ ] **Step 2: Run test to verify it fails**

Run (inside the dev container): `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.export_summary_tables'`

- [ ] **Step 3: Create the module with helpers**

Create `backend/app/services/export_summary_tables.py`:

```python
"""
Embedded Summary Tables (申請總表) for the export package.

Builds the 學生資料彙整表 Excel workbooks embedded inside the /export-package
ZIP: one college-level table at the ZIP root plus one per-department table
inside each department folder.

Applications are NOT re-queried here — they are the exact same dept_groups
ExportPackageService already assembled, so every table's rows match the
student folders sitting next to it in the ZIP.

Reuses CollegeRankingExportService.build_workbook (pure xlsx render) and
load_export_aux_data (dynamic fields / sub-type labels / bank account /
advisor names).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.college_review._helpers import load_export_aux_data
from app.models.application import Application
from app.models.scholarship import ScholarshipType
from app.services.college_ranking_export_service import (
    CollegeRankingExportService,
    ExportRow,
)

# NOTE: imported at top is safe — export_package_service has no top-level
# import of this module (it imports build_embedded_summary_tables lazily
# inside generate_export_zip), so there is no import cycle.
from app.services.export_package_service import _sanitize_filename

logger = logging.getLogger(__name__)


def _sort_key(a: Application):
    """Sort key: renewal applications first, then by student code (blanks last)."""
    code = ((a.student_data or {}).get("std_stdcode") or "").strip()
    renewal_group = 0 if getattr(a, "is_renewal", False) else 1  # 0=renewal first, 1=new
    return (renewal_group, not code, code, a.id)


def _dept_name_from_apps(apps: List[Application]) -> str:
    """Department display name taken from the first application's student_data."""
    for a in apps:
        name = (a.student_data or {}).get("trm_depname")
        if name:
            return str(name)
    return "未知系所"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_summary_tables.py backend/app/tests/test_export_summary_tables.py
git commit -m "feat(export): add export_summary_tables module with sort/dept helpers"
```

---

## Task 2: `build_embedded_summary_tables` — happy path

**Files:**
- Modify: `backend/app/services/export_summary_tables.py`
- Test: `backend/app/tests/test_export_summary_tables.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_export_summary_tables.py`:

```python
from types import SimpleNamespace

from app.services.export_summary_tables import build_embedded_summary_tables


@pytest.fixture
def _patch_aux(monkeypatch):
    async def _fake_aux(db, *, scholarship_type, applications):
        # (dynamic_fields, sub_type_labels, account_by_user, advisor_by_user)
        return ([], {}, {}, {})

    monkeypatch.setattr(
        "app.services.export_summary_tables.load_export_aux_data", _fake_aux
    )


def _read_col(xlsx_bytes, col_idx):
    """Return values of `col_idx` (1-based) for all data rows (row >= 3)."""
    wb = load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active
    return [ws.cell(row=r, column=col_idx).value for r in range(3, ws.max_row + 1)]


@pytest.mark.asyncio
async def test_builds_college_and_per_dept_tables(_patch_aux):
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])
    dept_groups = {
        "1000_A系": [
            _mk_app(2, 12, "1000", "A系", "002"),
            _mk_app(1, 11, "1000", "A系", "001"),  # deliberately out of order
        ],
        "2000_B系": [_mk_app(3, 13, "2000", "B系", "003")],
    }

    tables = await build_embedded_summary_tables(
        db=None, scholarship_type=stype, dept_groups=dept_groups,
        college_name="某學院", academic_year=114,
    )

    college_key = "114學年度某獎學金學生資料彙整表_某學院.xlsx"
    a_key = "1000_A系/114學年度某獎學金學生資料彙整表_A系.xlsx"
    b_key = "2000_B系/114學年度某獎學金學生資料彙整表_B系.xlsx"
    assert set(tables.keys()) == {college_key, a_key, b_key}

    # Per-dept row counts == dept sizes; codes sorted within dept
    assert _read_col(tables[a_key], 13) == ["001", "002"]
    assert _read_col(tables[b_key], 13) == ["003"]

    # College table: grouped by dept folder order (A系 before B系), sorted within
    assert _read_col(tables[college_key], 13) == ["001", "002", "003"]
    assert _read_col(tables[college_key], 5) == ["A系", "A系", "B系"]  # 系所 column

    # 排序 column (學院初審會議之學院排序, col 2) is empty for every row
    assert _read_col(tables[college_key], 2) == ["", "", ""]


@pytest.mark.asyncio
async def test_college_name_falls_back_to_全校(_patch_aux):
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])
    dept_groups = {"1000_A系": [_mk_app(1, 11, "1000", "A系", "001")]}
    tables = await build_embedded_summary_tables(
        db=None, scholarship_type=stype, dept_groups=dept_groups,
        college_name=None, academic_year=114,
    )
    assert "114學年度某獎學金學生資料彙整表_全校.xlsx" in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py -v -k "builds_college or 全校"`
Expected: FAIL — `ImportError: cannot import name 'build_embedded_summary_tables'`

- [ ] **Step 3: Implement the happy path (no error handling yet)**

Append to `backend/app/services/export_summary_tables.py`:

```python
async def build_embedded_summary_tables(
    db: AsyncSession,
    scholarship_type: ScholarshipType,
    dept_groups: Dict[str, List[Application]],
    college_name: Optional[str],
    academic_year: int,
) -> Dict[str, bytes]:
    """Return { zip_inner_path : xlsx_bytes } for the college-level table
    (ZIP root) plus one table per department folder.

    The same dept_groups assembled by ExportPackageService is used directly,
    guaranteeing each table's rows match the student folders next to it.
    """
    all_apps = [app for apps in dept_groups.values() for app in apps]

    dynamic_fields, sub_type_labels, account_by_user, advisor_by_user = await load_export_aux_data(
        db,
        scholarship_type=scholarship_type,
        applications=all_apps,
    )

    scholarship_name = scholarship_type.name or "獎學金"
    service = CollegeRankingExportService()
    sheet_name = f"{academic_year}學年"
    result: Dict[str, bytes] = {}

    def _rows(apps: List[Application]) -> List[ExportRow]:
        ordered = sorted(apps, key=_sort_key)
        return [
            ExportRow(
                rank_position=None,  # 學院初審會議之學院排序 left blank (ranking not done yet)
                application=app,
                bank_account=account_by_user.get(app.user_id),
                advisor_names=advisor_by_user.get(app.user_id),
            )
            for app in ordered
        ]

    # (a) one table per department folder
    for dept_folder, apps in sorted(dept_groups.items()):
        dept_name = _dept_name_from_apps(apps)
        title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
        xlsx = await asyncio.to_thread(
            service.build_workbook,
            rows=_rows(apps),
            dynamic_fields=dynamic_fields,
            sub_type_labels=sub_type_labels,
            title=title,
            sheet_name=sheet_name,
        )
        fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{dept_name}.xlsx"
        result[f"{dept_folder}/{_sanitize_filename(fname)}"] = xlsx

    # (b) college-level table: grouped by department folder, sorted within each group
    college_rows: List[ExportRow] = []
    for _dept_folder, apps in sorted(dept_groups.items()):
        college_rows.extend(_rows(apps))
    college_label = college_name or "全校"
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {college_label}"
    xlsx = await asyncio.to_thread(
        service.build_workbook,
        rows=college_rows,
        dynamic_fields=dynamic_fields,
        sub_type_labels=sub_type_labels,
        title=title,
        sheet_name=sheet_name,
    )
    fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{college_label}.xlsx"
    result[_sanitize_filename(fname)] = xlsx

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py -v`
Expected: PASS (all tests including the 3 from Task 1)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_summary_tables.py backend/app/tests/test_export_summary_tables.py
git commit -m "feat(export): build embedded college + per-dept 申請總表 workbooks"
```

---

## Task 3: Per-table failure handling (don't abort the ZIP)

**Files:**
- Modify: `backend/app/services/export_summary_tables.py`
- Test: `backend/app/tests/test_export_summary_tables.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_export_summary_tables.py`:

```python
@pytest.mark.asyncio
async def test_table_build_failure_writes_error_txt(_patch_aux, monkeypatch):
    def _boom(self, *, rows, dynamic_fields, sub_type_labels, title, sheet_name):
        raise RuntimeError("render exploded")

    monkeypatch.setattr(
        "app.services.export_summary_tables.CollegeRankingExportService.build_workbook",
        _boom,
    )
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])
    dept_groups = {"1000_A系": [_mk_app(1, 11, "1000", "A系", "001")]}

    tables = await build_embedded_summary_tables(
        db=None, scholarship_type=stype, dept_groups=dept_groups,
        college_name="某學院", academic_year=114,
    )

    # Each failed table becomes an error .txt instead of aborting the whole build
    assert "1000_A系/_錯誤_總表生成失敗.txt" in tables
    assert "_錯誤_學院總表生成失敗.txt" in tables
    assert b"render exploded" in tables["1000_A系/_錯誤_總表生成失敗.txt"]
    # No xlsx produced when every build fails
    assert not any(k.endswith(".xlsx") for k in tables)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py::test_table_build_failure_writes_error_txt -v`
Expected: FAIL — `RuntimeError: render exploded` propagates (no try/except yet)

- [ ] **Step 3: Wrap each build in try/except**

In `backend/app/services/export_summary_tables.py`, replace the per-department block with:

```python
    # (a) one table per department folder
    for dept_folder, apps in sorted(dept_groups.items()):
        dept_name = _dept_name_from_apps(apps)
        title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {dept_name}"
        try:
            xlsx = await asyncio.to_thread(
                service.build_workbook,
                rows=_rows(apps),
                dynamic_fields=dynamic_fields,
                sub_type_labels=sub_type_labels,
                title=title,
                sheet_name=sheet_name,
            )
            fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{dept_name}.xlsx"
            result[f"{dept_folder}/{_sanitize_filename(fname)}"] = xlsx
        except Exception as e:  # one bad table must not abort the whole ZIP
            logger.exception("dept summary table build failed: %s", dept_folder)
            result[f"{dept_folder}/_錯誤_總表生成失敗.txt"] = f"系總表生成失敗：{e}".encode("utf-8")
```

And replace the college-level build with:

```python
    college_label = college_name or "全校"
    title = f"{academic_year}學年度{scholarship_name}學生資料彙整表 - {college_label}"
    try:
        xlsx = await asyncio.to_thread(
            service.build_workbook,
            rows=college_rows,
            dynamic_fields=dynamic_fields,
            sub_type_labels=sub_type_labels,
            title=title,
            sheet_name=sheet_name,
        )
        fname = f"{academic_year}學年度{scholarship_name}學生資料彙整表_{college_label}.xlsx"
        result[_sanitize_filename(fname)] = xlsx
    except Exception as e:
        logger.exception("college summary table build failed")
        result["_錯誤_學院總表生成失敗.txt"] = f"學院總表生成失敗：{e}".encode("utf-8")
```

(`logger.exception` already records the traceback — no `exc_info=True` needed, and `e` is not interpolated into the log call, so the WARNING/ERROR-traceback AST invariant does not apply.)

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_summary_tables.py backend/app/tests/test_export_summary_tables.py
git commit -m "feat(export): tolerate per-table build failures with error placeholders"
```

---

## Task 4: Wire into `ExportPackageService.generate_export_zip`

**Files:**
- Modify: `backend/app/services/export_package_service.py:144-151` (`_get_scholarship_name` → `_get_scholarship_type`)
- Modify: `backend/app/services/export_package_service.py:95-142` (`generate_export_zip` body)
- Test: `backend/app/tests/test_export_package_embeds_summary.py`

- [ ] **Step 1: Write the failing integration test**

Create `backend/app/tests/test_export_package_embeds_summary.py`:

```python
"""Integration test: generate_export_zip embeds the 申請總表 workbooks and the
table rows match the student folders. Avoids DB / MinIO / reportlab font by
monkeypatching _ensure_font, _query_applications, _get_scholarship_type,
_generate_summary_pdf, and load_export_aux_data.
"""

import io
import zipfile
from types import SimpleNamespace

import pytest
from openpyxl import load_workbook

from app.models.application import Application
from app.services.export_package_service import ExportPackageService


def _mk_app(app_id, user_id, dep_no, dep_name, std_code, cname, academy="某學院"):
    a = Application(
        user_id=user_id,
        scholarship_type_id=1,
        academic_year=114,
        student_data={
            "trm_depno": dep_no,
            "trm_depname": dep_name,
            "trm_academyname": academy,
            "std_stdcode": std_code,
            "std_cname": cname,
        },
    )
    a.id = app_id
    a.files = []  # no uploaded files → no MinIO access
    return a


def _coro_returning(value):
    async def _inner(*args, **kwargs):
        return value
    return _inner


@pytest.mark.asyncio
async def test_export_zip_contains_summary_tables_matching_folders(monkeypatch):
    monkeypatch.setattr("app.services.export_package_service._ensure_font", lambda: None)

    async def _fake_aux(db, *, scholarship_type, applications):
        return ([], {}, {}, {})

    monkeypatch.setattr("app.services.export_summary_tables.load_export_aux_data", _fake_aux)

    apps = [
        _mk_app(1, 11, "1000", "A系", "001", "甲"),
        _mk_app(2, 12, "1000", "A系", "002", "乙"),
        _mk_app(3, 13, "2000", "B系", "003", "丙"),
    ]
    stype = SimpleNamespace(name="某獎學金", code="phd", sub_type_configs=[])

    svc = ExportPackageService(db=None, minio_service=None)
    monkeypatch.setattr(svc, "_get_scholarship_type", _coro_returning(stype))
    monkeypatch.setattr(svc, "_query_applications", _coro_returning(apps))
    monkeypatch.setattr(svc, "_generate_summary_pdf", lambda *a, **k: b"%PDF-1.4 fake")

    buf, fname = await svc.generate_export_zip(
        scholarship_type_id=1, academic_year=114, semester="first", college_code="A",
    )

    names = zipfile.ZipFile(buf).namelist()

    # College-level table at ZIP root
    assert "114學年度某獎學金學生資料彙整表_某學院.xlsx" in names
    # Per-department tables inside each dept folder
    assert "1000_A系/114學年度某獎學金學生資料彙整表_A系.xlsx" in names
    assert "2000_B系/114學年度某獎學金學生資料彙整表_B系.xlsx" in names

    # Consistency: A系 table 學號 set == A系 student folders
    zf = zipfile.ZipFile(buf)
    a_xlsx = zf.read("1000_A系/114學年度某獎學金學生資料彙整表_A系.xlsx")
    wb = load_workbook(io.BytesIO(a_xlsx))
    ws = wb.active
    table_codes = {ws.cell(row=r, column=13).value for r in range(3, ws.max_row + 1)}
    folder_codes = {
        n.split("/")[1].split("_")[0]
        for n in names
        if n.startswith("1000_A系/") and n.count("/") == 2  # dept/student/file
    }
    assert table_codes == folder_codes == {"001", "002"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_package_embeds_summary.py -v`
Expected: FAIL — either `AttributeError: ... has no attribute '_get_scholarship_type'` or the xlsx names are missing from `namelist()` (tables not embedded yet).

- [ ] **Step 3a: Replace `_get_scholarship_name` with `_get_scholarship_type`**

In `backend/app/services/export_package_service.py`, replace the method at lines 144-151:

```python
    async def _get_scholarship_type(self, scholarship_type_id: int) -> ScholarshipType:
        """Load the full ScholarshipType (with sub_type_configs) — name drives the
        ZIP/PDF filenames; the object is also passed to the summary-table builder."""
        stmt = (
            select(ScholarshipType)
            .where(ScholarshipType.id == scholarship_type_id)
            .options(selectinload(ScholarshipType.sub_type_configs))
        )
        result = await self.db.execute(stmt)
        scholarship = result.scalar_one_or_none()
        if not scholarship:
            raise ValueError(f"找不到獎學金類型 ID={scholarship_type_id}")
        return scholarship
```

(`select`, `selectinload`, and `ScholarshipType` are already imported in this file.)

- [ ] **Step 3b: Update `generate_export_zip` to load the type and embed tables**

In `generate_export_zip`, change line 96 from:

```python
        scholarship_name = await self._get_scholarship_name(scholarship_type_id)
```

to:

```python
        scholarship_type = await self._get_scholarship_type(scholarship_type_id)
        scholarship_name = scholarship_type.name
```

Then, immediately after the `dept_groups` grouping loop (currently ending at line 123, just before `# 4. Build ZIP`), insert the table-build call:

```python
        # 3.5 Build the embedded 申請總表 workbooks from the SAME dept_groups
        # (lazy import avoids an import cycle with export_summary_tables).
        from app.services.export_summary_tables import build_embedded_summary_tables

        summary_tables = await build_embedded_summary_tables(
            self.db, scholarship_type, dept_groups, college_name, academic_year
        )
```

Finally, inside the `with zipfile.ZipFile(...) as zf:` block, after the per-application loop (currently lines 128-130), add:

```python
            for inner_path, payload in summary_tables.items():
                zf.writestr(inner_path, payload)
```

For reference, the resulting `with` block reads:

```python
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for dept_folder, apps in sorted(dept_groups.items()):
                for app in apps:
                    await self._add_application_to_zip(zf, dept_folder, app, scholarship_name, academic_year, semester)
            for inner_path, payload in summary_tables.items():
                zf.writestr(inner_path, payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_package_embeds_summary.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/export_package_service.py backend/app/tests/test_export_package_embeds_summary.py
git commit -m "feat(export): embed 申請總表 workbooks into /export-package ZIP"
```

---

## Task 5: DRY — single `_sort_key` shared with the summary-export endpoint

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/application_summary_export.py:60-64` (remove local def, import shared)
- Test (existing, must stay green): `backend/app/tests/test_application_summary_export_helpers.py`

- [ ] **Step 1: Replace the local `_sort_key` with an import**

In `backend/app/api/v1/endpoints/college_review/application_summary_export.py`, delete the local definition (lines 60-64):

```python
def _sort_key(a: "Application"):
    """Sort key: renewal applications first, then by student code (blanks last)."""
    code = ((a.student_data or {}).get("std_stdcode") or "").strip()
    renewal_group = 0 if getattr(a, "is_renewal", False) else 1  # 0=renewal first, 1=new
    return (renewal_group, not code, code, a.id)
```

and add this import alongside the other `app.services` imports near the top of the file (after the `from app.services.college_ranking_export_service import (...)` block):

```python
# Re-exported so existing callers/tests can keep importing _sort_key from this
# module; the single definition now lives in the service layer.
from app.services.export_summary_tables import _sort_key
```

The two existing `apps.sort(key=_sort_key)` call sites (now around lines 156 and 321) are unchanged.

- [ ] **Step 2: Run the existing helper tests to verify still green**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_application_summary_export_helpers.py -v`
Expected: PASS — `_sort_key` is still importable from `application_summary_export` (re-export), behavior identical.

- [ ] **Step 3: Sanity-check no import cycle at app startup**

Run: `docker compose -f docker-compose.dev.yml exec backend python -c "import app.api.v1.endpoints.college_review.application_summary_export; import app.services.export_package_service; import app.services.export_summary_tables; print('imports OK')"`
Expected: prints `imports OK` (no `ImportError` / circular import).

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/application_summary_export.py
git commit -m "refactor(export): share single _sort_key between summary-export and package"
```

---

## Task 6: Lint gates + full touched-test run

**Files:** none (verification + final commit if formatting changes)

- [ ] **Step 1: Format check**

Run: `cd backend && uvx --from "black==26.3.1" black --line-length=120 app/services/export_summary_tables.py app/services/export_package_service.py app/api/v1/endpoints/college_review/application_summary_export.py app/tests/test_export_summary_tables.py app/tests/test_export_package_embeds_summary.py`
Expected: files reformatted in place (or "unchanged"). If anything changed, re-stage it.

- [ ] **Step 2: Flake8 hard-gated rules**

Run: `cd backend && flake8 app/services/export_summary_tables.py app/services/export_package_service.py app/api/v1/endpoints/college_review/application_summary_export.py --select=B904,B014 --max-line-length=120`
Expected: no output (no B904/B014 violations).

- [ ] **Step 3: Run all touched tests together**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_export_summary_tables.py app/tests/test_export_package_embeds_summary.py app/tests/test_application_summary_export_helpers.py app/tests/test_export_package_pure_helpers.py -v -p no:cacheprovider`
Expected: ALL PASS (new unit + integration tests, plus the two pre-existing test modules that touch these files).

- [ ] **Step 4: Commit any formatting fixups**

```bash
git add -A
git commit -m "chore(export): black/flake8 formatting for embedded summary tables" || echo "nothing to commit"
```

---

## Self-Review (completed by plan author)

**Spec coverage**
- §1 goal (college table at root + per-dept table in folders) → Tasks 2 & 4.
- §3 "tables from the same dept_groups, never re-query" → Task 4 Step 3b passes `dept_groups` straight through; integration test asserts table 學號 == folder 學號.
- §4 new module / build_embedded_summary_tables → Tasks 1-3.
- §4 confirmed decisions (empty rank column; college table grouped by dept) → Task 2 test asserts col 2 empty and col 5/13 grouped order.
- §5 `_get_scholarship_name` → `_get_scholarship_type` + writestr → Task 4.
- §6 edge cases: 全校 fallback → Task 2 `test_college_name_falls_back_to_全校`; 未知系所 → `_dept_name_from_apps` fallback test (Task 1).
- §7 error handling → Task 3.
- §8 tests + lint gates → Tasks 2/3/4 + Task 6.
- §9 "grep _get_scholarship_name callers" → confirmed during planning: only internal caller (line 96), updated in Task 4.

**Placeholder scan:** none — every code step shows complete code.

**Type/name consistency:** `build_embedded_summary_tables(db, scholarship_type, dept_groups, college_name, academic_year)` signature identical in module (Task 2), endpoint call (Task 4 Step 3b), and tests. `_get_scholarship_type` name consistent across Task 4 steps and the integration test monkeypatch. `_sort_key` defined once (Task 1), re-exported (Task 5).
