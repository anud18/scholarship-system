# 匯入續領生 (Import Renewal Students) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin upload a spreadsheet of renewal candidates and import only the renewal-*passed* rows as **approved renewal applications** into a chosen scholarship+year, so the existing 造冊 (roster generation) includes them.

**Architecture:** A dedicated `RenewalImportService` (async) parses the sheet, filters to `學生是否申請續領=是 AND 續領審核結果=通過`, SIS-looks-up each 學號, and creates `Application` rows shaped exactly like an approved renewal (`is_renewal=True`, `status=approved`, `review_stage=quota_distributed`, `allocation_config_id` set, `sub_scholarship_type` from a `獎學金類別` column). The upload/preview/confirm bookkeeping reuses the `BatchImport` table via a new `import_type` discriminator. The shared roster generator is extended to include approved renewals per `(allocation_config_id, sub_scholarship_type)` group — fixing a latent gap where renewals never reach matrix-mode 造冊.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 + PostgreSQL + Alembic; Next.js/React + TypeScript frontend; pandas/openpyxl for Excel; MinIO for file storage.

**Design spec:** `docs/superpowers/specs/2026-07-09-import-renewal-students-design.md`

## Global Constraints

- **English git commit messages** (project rule); attribution disabled globally.
- **Enum consistency:** Python lowercase members matching DB values, `values_callable` on columns; TS UPPERCASE. `import_type` is a plain `String(20)` (NOT a PG enum) to avoid enum-pin tripwire tests.
- **ApiResponse format:** every endpoint returns `{"success": bool, "message": str, "data": ...}`; no `response_model=`.
- **No fallback/mock data on failure** — raise errors.
- **Sub-type is configuration-driven** (lowercase `String(50)`); reject the synthetic `"general"` category when the scholarship defines real sub-types.
- **Migrations** include `inspector` existence guards (see Task 1 pattern); current Alembic head = `add_app_doc_note_001`.
- **Lint gate (hard):** `black --check --line-length=120 backend/app`; `flake8 app --select=B904,B014 --max-line-length=120`. `raise ... from exc` inside `except`; no redundant exception tuples.
- **Tests:** async service tests are `@pytest.mark.asyncio` + `async def` and run in the **integration** CI lane (`asyncio_mode=auto`). Build in-memory objects with `Mock(spec=Model)` + attribute assignment (never `Model.__new__`), or real rows via the sync session for roster tests. Local run: `python -m pytest app/tests/<file> -p no:cacheprovider` (worktree host also needs `DATABASE_URL/DATABASE_URL_SYNC/SECRET_KEY/MINIO_*` inline and `--no-cov`).
- **OpenAPI:** after endpoint/schema changes run `cd frontend && npm run api:generate` and commit `lib/api/generated/schema.d.ts` (backend must be up on :8000).
- **Immutability / small files / KISS-DRY-YAGNI** per repo coding style.

## Reference Anchors (verbatim ground truth — copy these patterns)

- Batch service to mirror: `backend/app/services/batch_import_service.py` — `parse_excel_file` (77), `_get_or_create_users_bulk` (598), `create_applications_from_batch` (662; inline app-id sequence at 757-794 uses suffix `"U"`), `create_batch_import_record` (567). Async, `db: AsyncSession`.
- Renewal field reference: `application_service.py::create_renewal_from_previous` (3027) and `_generate_app_id` (282).
- Endpoints to mirror: `backend/app/api/v1/endpoints/batch_import.py` — `require_college_role` (48), `upload_batch_import_data` (58), `confirm_batch_import` (997), `download_batch_import_template` (1604). Router registered `api.py:70`.
- Roster to edit: `backend/app/services/roster_service.py` — `generate_rosters_from_distribution` (1478), `_generate_one_sub_type_roster` (1641), `_create_roster_item` (795), `_build_semester_filter` (1461). Renewal predicate reference: `manual_distribution_service.py::_renewal_filters` (216).
- Amount: `ScholarshipConfiguration.amount` is `Integer, nullable=False` (`scholarship.py:561`); `is_renewal_application_period` property (`scholarship.py:839`).
- Frontend to mirror: `frontend/components/batch-import-panel.tsx`, `frontend/lib/api/modules/batch-import.ts`, `frontend/lib/api/index.ts` (lazy getter), `frontend/lib/i18n.ts` (`batch_import.field_labels` zh:322 / en:839), mount `frontend/app/page.tsx:37,545`.

---

### Task 1: Add `import_type` discriminator to `BatchImport`

**Files:**
- Modify: `backend/app/models/batch_import.py`
- Create: `backend/alembic/versions/add_batch_import_type_001.py`
- Modify: `backend/app/api/v1/endpoints/batch_import.py` (history query filter)
- Test: `backend/app/tests/test_batch_import_type_migration.py`

**Interfaces:**
- Produces: `BatchImport.import_type: str` (values `"application"` | `"renewal"`, default `"application"`).

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/batch_import.py`, after the `import_status` column block (line ~51) add:

```python
    # Discriminates the general application importer ("application") from the
    # renewal-students importer ("renewal"); lets both reuse this table.
    import_type = Column(String(20), nullable=False, default="application", index=True)
```

- [ ] **Step 2: Write the migration**

Create `backend/alembic/versions/add_batch_import_type_001.py`:

```python
"""Add import_type discriminator to batch_imports

Revision ID: add_batch_import_type_001
Revises: add_app_doc_note_001
"""

import sqlalchemy as sa

from alembic import op

revision = "add_batch_import_type_001"
down_revision = "add_app_doc_note_001"
branch_labels = None
depends_on = None

TABLE = "batch_imports"
COLUMN = "import_type"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN not in existing_columns:
        op.add_column(
            TABLE,
            sa.Column(COLUMN, sa.String(length=20), nullable=False, server_default="application"),
        )
        op.create_index(f"ix_{TABLE}_{COLUMN}", TABLE, [COLUMN])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if TABLE not in inspector.get_table_names():
        return
    existing_columns = {col["name"] for col in inspector.get_columns(TABLE)}
    if COLUMN in existing_columns:
        op.drop_index(f"ix_{TABLE}_{COLUMN}", table_name=TABLE)
        op.drop_column(TABLE, COLUMN)
```

- [ ] **Step 3: Keep the existing batch-import history scoped to `"application"`**

In `backend/app/api/v1/endpoints/batch_import.py::get_batch_import_history` (line ~1213), add `import_type` to the query filter so renewal imports never appear in the batch-import history. Find the `select(BatchImport)` (or `db.query`) statement and add `.where(BatchImport.import_type == "application")` (adapt to the existing `.where(...)`/`.filter(...)` chain — it currently filters out `pending` and scopes by importer for non-super-admin).

- [ ] **Step 4: Write the migration test**

Create `backend/app/tests/test_batch_import_type_migration.py`:

```python
import pytest

from app.models.batch_import import BatchImport


@pytest.mark.asyncio
async def test_batch_import_defaults_import_type_application(db):
    batch = BatchImport(
        importer_id=1,
        college_code="A",
        scholarship_type_id=1,
        academic_year=113,
        file_name="x.xlsx",
        total_records=0,
    )
    db.add(batch)
    await db.flush()
    assert batch.import_type == "application"
```

- [ ] **Step 5: Run migration + test**

Run: `python -m pytest app/tests/test_batch_import_type_migration.py -p no:cacheprovider`
Expected: PASS (SQLAlchemy applies the model default `"application"`).
Apply the migration on a throwaway DB per the worktree recipe and confirm `alembic upgrade head` succeeds with head now `add_batch_import_type_001`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/batch_import.py backend/alembic/versions/add_batch_import_type_001.py backend/app/api/v1/endpoints/batch_import.py backend/app/tests/test_batch_import_type_migration.py
git commit -m "feat: add import_type discriminator to batch_imports"
```

---

### Task 2: Renewal-import Pydantic schemas

**Files:**
- Create: `backend/app/schemas/renewal_import.py`
- Test: `backend/app/tests/test_renewal_import_schema.py`

**Interfaces:**
- Produces: `RenewalDataRow` (per-row parsed model), `RenewalImportUploadResponse`, `RenewalImportConfirmRequest`, `RenewalImportConfirmResponse`, `RenewalImportHistoryItem`, `RenewalImportHistoryResponse`, `RenewalImportDetailResponse`.
- Consumed by: Tasks 3-5 (service) and Task 7 (endpoints).

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_renewal_import_schema.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas.renewal_import import RenewalDataRow


def test_renewal_row_valid():
    row = RenewalDataRow(
        student_id="413271002",
        student_name="曾美麗",
        sub_type="nstc",
        postal_account="1234567890123",
        advisor_nycu_id="P001234",
    )
    assert row.sub_type == "nstc"
    assert row.postal_account == "1234567890123"


def test_renewal_row_rejects_bad_student_id():
    with pytest.raises(ValidationError):
        RenewalDataRow(student_id="413-271!", student_name="x", sub_type="nstc")


def test_renewal_row_rejects_bad_postal_account():
    with pytest.raises(ValidationError):
        RenewalDataRow(student_id="413271002", student_name="x", sub_type="nstc", postal_account="12ab")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/tests/test_renewal_import_schema.py -p no:cacheprovider`
Expected: FAIL (module `app.schemas.renewal_import` does not exist).

- [ ] **Step 3: Write the schemas**

Create `backend/app/schemas/renewal_import.py` (mirror `schemas/batch_import.py`; validators copied from `ApplicationDataRow`):

```python
"""Renewal-import schemas for API requests and responses."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RenewalDataRow(BaseModel):
    """Single renewal-passed row imported from Excel/CSV."""

    student_id: str = Field(..., description="學號", min_length=1, max_length=20)
    student_name: str = Field(..., description="姓名", min_length=1, max_length=100)
    sub_type: str = Field(..., description="獎學金子類型代碼 (e.g. nstc, moe_1w)", min_length=1, max_length=50)
    postal_account: Optional[str] = Field(None, description="郵局帳號", max_length=20)
    advisor_nycu_id: Optional[str] = Field(None, description="指導教授本校人事編號", max_length=50)
    advisor_name: Optional[str] = Field(None, description="指導教授姓名", max_length=100)

    @field_validator("student_id")
    @classmethod
    def validate_student_id(cls, v: str) -> str:
        v = v.strip()
        if not re.match(r"^[A-Za-z0-9]+$", v):
            raise ValueError("學號僅能包含英文字母和數字")
        return v

    @field_validator("student_name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if re.search(r"<[^>]*script|<[^>]*iframe|javascript:", v, re.IGNORECASE):
            raise ValueError("名稱欄位包含不允許的字元")
        return v

    @field_validator("postal_account")
    @classmethod
    def validate_postal_account(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[0-9\-]+$", v):
            raise ValueError("郵局帳號僅能包含數字和連字號")
        return v


class RenewalImportUploadResponse(BaseModel):
    batch_id: int
    file_name: str
    total_records: int = Field(..., description="通過並將匯入的筆數")
    skipped_records: int = Field(..., description="未通過/未申請而跳過的筆數")
    preview_data: List[Dict[str, Any]]
    validation_summary: Dict[str, Any]


class RenewalImportConfirmRequest(BaseModel):
    batch_id: int
    confirm: bool = True


class RenewalImportConfirmResponse(BaseModel):
    batch_id: int
    success_count: int
    failed_count: int
    errors: List[Dict[str, Any]] = Field(default=[])
    created_application_ids: List[int] = Field(default=[])


class RenewalImportHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    college_code: str
    scholarship_type_id: Optional[int] = None
    academic_year: int
    semester: Optional[str] = None
    file_name: str
    total_records: int
    success_count: int
    failed_count: int
    import_status: str
    created_at: datetime
    importer_name: Optional[str] = None


class RenewalImportHistoryResponse(BaseModel):
    total: int
    items: List[RenewalImportHistoryItem]


class RenewalImportDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    college_code: str
    scholarship_type_id: Optional[int] = None
    academic_year: int
    semester: Optional[str] = None
    file_name: str
    total_records: int
    success_count: int
    failed_count: int
    error_summary: Optional[Dict[str, Any]] = None
    import_status: str
    created_at: datetime
    created_applications: Optional[List[int]] = Field(default=[])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/tests/test_renewal_import_schema.py -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/renewal_import.py backend/app/tests/test_renewal_import_schema.py
git commit -m "feat: add renewal-import schemas"
```

---

### Task 3: `RenewalImportService` — parser + row filter

**Files:**
- Create: `backend/app/services/renewal_import_service.py`
- Test: `backend/app/tests/test_renewal_import_service.py`

**Interfaces:**
- Produces: `RenewalImportService(db: AsyncSession, student_service=None)`; module consts `RENEWAL_SUB_TYPE_LABELS`, `PASS_MARK`, `APPLIED_YES`; `async def parse_renewal_excel(file_content, scholarship_type_id, academic_year, semester) -> Tuple[List[dict], List[dict], List[dict]]` returning `(parsed_rows, skipped_rows, errors)`. Each parsed row dict has keys `student_id, student_name, sub_type, postal_account, advisor_nycu_id, advisor_name, row_number`.
- Consumes: `RenewalDataRow` (Task 2), `_normalize_identifier`/`_normalize_optional` from `batch_import_service`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_renewal_import_service.py`:

```python
import io

import pandas as pd
import pytest
from unittest.mock import Mock

from app.models.scholarship import ScholarshipType
from app.services.renewal_import_service import RenewalImportService


def _xlsx_bytes(rows):
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="續領")
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def service(db):
    return RenewalImportService(db)


@pytest.fixture
def mock_scholarship():
    s = Mock(spec=ScholarshipType)
    s.id = 1
    s.name = "PhD Scholarship"
    s.code = "phd"
    s.sub_type_list = ["nstc", "moe_1w"]
    return s


@pytest.mark.asyncio
async def test_parse_keeps_only_passed_rows(service, mock_scholarship):
    content = _xlsx_bytes([
        {"學號": "413271002", "學生姓名": "曾美麗", "獎學金類別": "國科會",
         "學生是否申請續領": "是", "續領審核結果": "通過", "郵局帳號": "1234567890123",
         "指導教授本校人事編號": "P001"},
        {"學號": "413271003", "學生姓名": "王大明", "獎學金類別": "教育部",
         "學生是否申請續領": "否", "續領審核結果": "領獎期滿，無續領", "郵局帳號": "",
         "指導教授本校人事編號": ""},
    ])
    service.db.get = Mock(return_value=mock_scholarship)

    async def _get(*a, **k):
        return mock_scholarship

    service.db.get = _get
    parsed, skipped, errors = await service.parse_renewal_excel(
        content, scholarship_type_id=1, academic_year=114, semester="first"
    )
    assert [r["student_id"] for r in parsed] == ["413271002"]
    assert parsed[0]["sub_type"] == "nstc"
    assert len(skipped) == 1
    assert errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_parse_keeps_only_passed_rows -p no:cacheprovider`
Expected: FAIL (module missing).

- [ ] **Step 3: Write the parser**

Create `backend/app/services/renewal_import_service.py`:

```python
"""Renewal-import service: parse a renewal-candidates sheet, keep the
renewal-passed rows, and create approved renewal applications for 造冊."""

import io
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.models.application import Application, ApplicationStatus
from app.models.application_sequence import ApplicationSequence
from app.models.batch_import import BatchImport
from app.models.enums import BatchImportStatus, ReviewStage, Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.renewal_import import RenewalDataRow
from app.services.batch_import_service import _normalize_identifier, _normalize_optional
from app.services.student_service import StudentService

logger = logging.getLogger(__name__)

# 獎學金類別 label -> configuration sub-type code. Extend as new labels appear.
RENEWAL_SUB_TYPE_LABELS = {"國科會": "nstc", "教育部": "moe_1w", "教育部配合款2萬": "moe_2w"}
APPLIED_YES = "是"
PASS_MARK = "通過"


class RenewalImportService:
    def __init__(self, db: AsyncSession, student_service: Optional[StudentService] = None):
        self.db = db
        self.student_service = student_service or StudentService()

    async def parse_renewal_excel(
        self, file_content: bytes, scholarship_type_id: int, academic_year: int, semester: Optional[str]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return (parsed_rows, skipped_rows, errors). Only rows with
        學生是否申請續領=是 AND 續領審核結果=通過 land in parsed_rows."""
        errors: List[Dict[str, Any]] = []
        parsed: List[Dict[str, Any]] = []
        skipped: List[Dict[str, Any]] = []

        try:
            df = pd.read_excel(io.BytesIO(file_content))
        except Exception:
            try:
                df = pd.read_csv(io.BytesIO(file_content))
            except Exception as e:
                errors.append({"row_number": 0, "student_id": None, "field": "file",
                               "error_type": "parse_error", "message": f"無法解析檔案: {str(e)}"})
                return [], [], errors

        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            errors.append({"row_number": 0, "student_id": None, "field": "scholarship_type",
                           "error_type": "not_found", "message": f"獎學金類型 ID {scholarship_type_id} 不存在"})
            return [], [], errors

        real_sub_types = {st.lower() for st in (scholarship.sub_type_list or []) if st}
        df_columns = set(df.columns)
        required = ["學號", "學生姓名", "獎學金類別", "學生是否申請續領", "續領審核結果"]
        missing = [c for c in required if c not in df_columns]
        if missing:
            errors.append({"row_number": 0, "student_id": None, "field": "columns",
                           "error_type": "missing_columns", "message": f"缺少必要欄位: {', '.join(missing)}"})
            return [], [], errors

        seen: set = set()
        for idx, row in df.iterrows():
            row_number = idx + 2
            student_id = _normalize_identifier(row.get("學號", ""))
            if not student_id:
                continue

            applied = _normalize_identifier(row.get("學生是否申請續領", ""))
            result = _normalize_identifier(row.get("續領審核結果", ""))
            base = {"row_number": row_number, "student_id": student_id,
                    "student_name": _normalize_identifier(row.get("學生姓名", "")),
                    "applied_for_renewal": applied, "review_result": result}

            # Filter: only 是 + 通過 rows are imported.
            if applied != APPLIED_YES or result != PASS_MARK:
                base["skip_reason"] = f"未通過 (申請續領={applied or '空'}, 審核結果={result or '空'})"
                skipped.append(base)
                continue

            if student_id in seen:
                errors.append({"row_number": row_number, "student_id": student_id, "field": "student_id",
                               "error_type": "duplicate_in_file", "message": f"學號 {student_id} 在檔案中重複"})
                continue
            seen.add(student_id)

            label = _normalize_identifier(row.get("獎學金類別", ""))
            sub_type = RENEWAL_SUB_TYPE_LABELS.get(label, label.lower())
            if sub_type not in real_sub_types:
                errors.append({"row_number": row_number, "student_id": student_id, "field": "獎學金類別",
                               "error_type": "invalid_sub_type",
                               "message": f"獎學金類別「{label}」無法對應到有效子類型（{'、'.join(sorted(real_sub_types))}）"})
                continue

            data_row = {
                "student_id": student_id,
                "student_name": base["student_name"],
                "sub_type": sub_type,
                "postal_account": _normalize_optional(row.get("郵局帳號")),
                "advisor_nycu_id": _normalize_optional(row.get("指導教授本校人事編號")),
                "advisor_name": _normalize_optional(row.get("指導教授姓名")),
            }
            try:
                normalized = RenewalDataRow(**data_row).model_dump()
                normalized["row_number"] = row_number
                parsed.append(normalized)
            except Exception as e:  # noqa: BLE001 - surface row validation errors
                errors.append({"row_number": row_number, "student_id": student_id, "field": "row_data",
                               "error_type": "validation_error", "message": f"資料驗證失敗: {str(e)}"})

        return parsed, skipped, errors
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_parse_keeps_only_passed_rows -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/renewal_import_service.py backend/app/tests/test_renewal_import_service.py
git commit -m "feat: renewal-import parser keeps only 是+通過 rows"
```

---

### Task 4: `RenewalImportService` — SIS validation, duplicate + quota-warning preview

**Files:**
- Modify: `backend/app/services/renewal_import_service.py`
- Test: `backend/app/tests/test_renewal_import_service.py`

**Interfaces:**
- Produces: `async def validate_and_preview(parsed_rows, college_code, scholarship_type_id, academic_year, semester) -> Tuple[List[dict], List[dict]]` returning `(errors, warnings)`. Errors: `sis_not_found`, `duplicate_renewal`. Warnings: `missing_postal_account`, `over_quota`.
- Consumes: `student_service.get_student_basic_info`, `ManualDistributionService.consumers_count`.

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_renewal_import_service.py`:

```python
from unittest.mock import AsyncMock


@pytest.mark.asyncio
async def test_validate_flags_sis_not_found_as_error(service):
    service.student_service = Mock()
    service.student_service.api_enabled = True
    service.student_service.get_student_basic_info = AsyncMock(return_value=None)
    parsed = [{"student_id": "999", "student_name": "x", "sub_type": "nstc",
               "postal_account": None, "advisor_nycu_id": None, "advisor_name": None, "row_number": 2}]

    errors, warnings = await service.validate_and_preview(
        parsed, college_code="A", scholarship_type_id=1, academic_year=114, semester="first"
    )
    assert any(e["error_type"] == "sis_not_found" for e in errors)
    assert any(w["warning_type"] == "missing_postal_account" for w in warnings)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_validate_flags_sis_not_found_as_error -p no:cacheprovider`
Expected: FAIL (`validate_and_preview` not defined).

- [ ] **Step 3: Implement `validate_and_preview`**

Append to `RenewalImportService` in `renewal_import_service.py`:

```python
    async def validate_and_preview(
        self, parsed_rows: List[Dict[str, Any]], college_code: str,
        scholarship_type_id: int, academic_year: int, semester: Optional[str],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Per-row SIS existence + duplicate-renewal errors, and postal/quota warnings."""
        errors: List[Dict[str, Any]] = []
        warnings: List[Dict[str, Any]] = []
        if not parsed_rows:
            return errors, warnings

        student_ids = [r["student_id"] for r in parsed_rows]

        # SIS existence check (real recipients must resolve to a snapshot at 造冊 time).
        if getattr(self.student_service, "api_enabled", False):
            for r in parsed_rows:
                sid = r["student_id"]
                try:
                    info = await self.student_service.get_student_basic_info(sid)
                except ServiceUnavailableError:
                    warnings.append({"row_number": r["row_number"], "student_id": sid, "field": "學號",
                                     "warning_type": "student_api_unavailable", "message": "學籍系統暫時不可用，請稍後重試。"})
                    break
                except Exception:
                    logger.warning("SIS error for %s", sid, exc_info=True)
                    continue
                if not info:
                    errors.append({"row_number": r["row_number"], "student_id": sid, "field": "學號",
                                   "error_type": "sis_not_found",
                                   "message": f"學籍系統查無學號 {sid}，無法建立可造冊的續領。"})

        # Missing postal account -> excluded from roster Excel (warn only).
        for r in parsed_rows:
            if not r.get("postal_account"):
                warnings.append({"row_number": r["row_number"], "student_id": r["student_id"], "field": "郵局帳號",
                                 "warning_type": "missing_postal_account",
                                 "message": f"學號 {r['student_id']} 缺少郵局帳號，造冊時將被排除。"})

        # Duplicate approved/renewal check + over-quota warning.
        semester_enum = _to_semester_enum(semester)
        users_stmt = select(User).where(User.nycu_id.in_(student_ids))
        users = (await self.db.execute(users_stmt)).scalars().all()
        user_by_nycu = {u.nycu_id: u for u in users}
        if user_by_nycu:
            dup_stmt = select(Application).where(
                Application.user_id.in_([u.id for u in users]),
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
            )
            dup_stmt = (dup_stmt.where(Application.semester.is_(None))
                        if semester_enum is None else dup_stmt.where(Application.semester == semester_enum))
            existing = {a.user_id for a in (await self.db.execute(dup_stmt)).scalars().all()}
            for r in parsed_rows:
                u = user_by_nycu.get(r["student_id"])
                if u and u.id in existing:
                    errors.append({"row_number": r["row_number"], "student_id": r["student_id"], "field": "duplicate",
                                   "error_type": "duplicate_renewal",
                                   "message": f"學號 {r['student_id']} 已有此獎學金 {academic_year} 學年度的續領申請。"})

        await self._append_quota_warnings(parsed_rows, scholarship_type_id, academic_year, semester_enum, warnings)
        return errors, warnings

    async def _append_quota_warnings(self, parsed_rows, scholarship_type_id, academic_year, semester_enum, warnings):
        from app.services.manual_distribution_service import ManualDistributionService

        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
        )
        config_stmt = (config_stmt.where(ScholarshipConfiguration.semester.is_(None))
                       if semester_enum in (None, Semester.yearly) else config_stmt.where(ScholarshipConfiguration.semester == semester_enum))
        config = (await self.db.execute(config_stmt)).scalar_one_or_none()
        if not config or not config.quotas:
            return
        md = ManualDistributionService(self.db)
        counts: Dict[str, int] = {}
        for r in parsed_rows:
            counts[r["sub_type"]] = counts.get(r["sub_type"], 0) + 1
        for sub_type, incoming in counts.items():
            quota_map = config.quotas.get(sub_type) or {}
            total_quota = sum(int(v) for v in quota_map.values()) if isinstance(quota_map, dict) else int(quota_map or 0)
            current = await md.consumers_count(config.id, sub_type)
            if total_quota and current + incoming > total_quota:
                warnings.append({"row_number": None, "student_id": None, "field": sub_type,
                                 "warning_type": "over_quota",
                                 "message": f"子類型 {sub_type} 匯入後將達 {current + incoming} 人，超過配額 {total_quota} 人。"})
```

Add the module-level helper near the top of `renewal_import_service.py` (after the constants):

```python
def _to_semester_enum(semester: Optional[str]) -> Optional[Semester]:
    """Map a raw semester string to the enum; yearly/annual/None -> None."""
    if semester in (None, "", "yearly", "annual"):
        return None
    try:
        return Semester(semester)
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_validate_flags_sis_not_found_as_error -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/renewal_import_service.py backend/app/tests/test_renewal_import_service.py
git commit -m "feat: renewal-import preview validation (SIS, duplicate, quota warning)"
```

---

### Task 5: `RenewalImportService` — create approved renewals + import record

**Files:**
- Modify: `backend/app/services/renewal_import_service.py`
- Test: `backend/app/tests/test_renewal_import_service.py`

**Interfaces:**
- Produces:
  - `async def create_renewal_import_record(importer_id, college_code, scholarship_type_id, academic_year, semester, file_name, total_records) -> BatchImport` (sets `import_type="renewal"`).
  - `async def create_renewals_from_batch(batch_import, parsed_rows, scholarship_type_id, academic_year, semester) -> Tuple[List[int], List[dict]]`.
- Consumes: `_get_or_create_users_bulk` from `BatchImportService`, `student_service.get_student_snapshot`, `ApplicationSequence.format_app_id`.

- [ ] **Step 1: Write the failing test**

Append to `backend/app/tests/test_renewal_import_service.py`:

```python
from app.models.batch_import import BatchImport
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration


@pytest.mark.asyncio
async def test_create_renewals_sets_approved_fields(service):
    scholarship = Mock(spec=ScholarshipType)
    scholarship.id = 1
    scholarship.name = "PhD"
    scholarship.sub_type_selection_mode = "single"

    config = Mock(spec=ScholarshipConfiguration)
    config.id = 7
    config.amount = 40000

    batch = Mock(spec=BatchImport)
    batch.id = 3
    batch.importer_id = 10

    user = Mock(spec=User)
    user.id = 99
    user.nycu_id = "413271002"

    parsed = [{"student_id": "413271002", "student_name": "曾美麗", "sub_type": "nstc",
               "postal_account": "1234567890123", "advisor_nycu_id": "P001", "advisor_name": "張教授",
               "row_number": 2}]

    from unittest.mock import AsyncMock, patch
    captured = []

    async def _get(model, _id):
        return scholarship

    service.db.get = _get
    with (
        patch.object(service, "_get_or_create_users_bulk", new=AsyncMock(return_value={"413271002": user})),
        patch.object(service.student_service, "get_student_snapshot", new=AsyncMock(
            return_value={"std_stdcode": "413271002", "std_cname": "曾美麗", "std_pid": "A123456789"})),
        patch.object(service.db, "add", side_effect=lambda o: captured.append(o)),
        patch.object(service.db, "flush", new=AsyncMock()),
        patch.object(service.db, "execute", new=AsyncMock()),
    ):
        # config lookup + ApplicationSequence lookup both via execute
        cfg_res, seq_res = Mock(), Mock()
        cfg_res.scalar_one_or_none.return_value = config
        seq_res.scalar_one_or_none.return_value = None
        service.db.execute.side_effect = [cfg_res, seq_res]

        created_ids, errors = await service.create_renewals_from_batch(
            batch_import=batch, parsed_rows=parsed, scholarship_type_id=1, academic_year=114, semester="first")

    apps = [o for o in captured if isinstance(o, Application)]
    assert len(apps) == 1
    app = apps[0]
    assert app.is_renewal is True
    assert app.status == ApplicationStatus.approved.value
    assert app.review_stage == ReviewStage.quota_distributed.value
    assert app.sub_scholarship_type == "nstc"
    assert app.allocation_config_id == 7
    assert app.amount == 40000
    assert app.import_source == "renewal_import"
    assert app.app_id.endswith("R")
    assert app.submitted_form_data["postal_account"] == "1234567890123"
    assert errors == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_create_renewals_sets_approved_fields -p no:cacheprovider`
Expected: FAIL (`create_renewals_from_batch` not defined).

- [ ] **Step 3: Implement record creation + create loop**

Append to `RenewalImportService` in `renewal_import_service.py`:

```python
    async def create_renewal_import_record(
        self, importer_id: int, college_code: str, scholarship_type_id: int,
        academic_year: int, semester: Optional[str], file_name: str, total_records: int,
    ) -> BatchImport:
        batch_import = BatchImport(
            importer_id=importer_id,
            college_code=college_code,
            scholarship_type_id=scholarship_type_id,
            academic_year=academic_year,
            semester=semester,
            file_name=file_name,
            total_records=total_records,
            import_status=BatchImportStatus.pending.value,
            import_type="renewal",
            data_expires_at=datetime.now(timezone.utc) + timedelta(days=7),
        )
        self.db.add(batch_import)
        await self.db.flush()
        return batch_import

    async def create_renewals_from_batch(
        self, batch_import: BatchImport, parsed_rows: List[Dict[str, Any]],
        scholarship_type_id: int, academic_year: int, semester: Optional[str],
    ) -> Tuple[List[int], List[Dict[str, Any]]]:
        """Create approved renewal Applications (all-or-nothing) shaped so 造冊 includes them."""
        from app.core.exceptions import BatchImportError
        from app.services.batch_import_service import BatchImportService

        created_ids: List[int] = []
        errors: List[Dict[str, Any]] = []

        scholarship = await self.db.get(ScholarshipType, scholarship_type_id)
        if not scholarship:
            raise BatchImportError(message=f"獎學金類型 ID {scholarship_type_id} 不存在", batch_id=batch_import.id)

        semester_enum = _to_semester_enum(semester)
        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
        )
        config_stmt = (config_stmt.where(ScholarshipConfiguration.semester.is_(None))
                       if semester_enum in (None, Semester.yearly) else config_stmt.where(ScholarshipConfiguration.semester == semester_enum))
        config = (await self.db.execute(config_stmt)).scalar_one_or_none()
        if not config:
            raise BatchImportError(message=f"找不到 {academic_year} 學年度的獎學金配置，請先建立配置。", batch_id=batch_import.id)

        seq_semester = semester if semester is not None else "yearly"
        current_row = 0
        applications: List[Application] = []
        try:
            user_map = await BatchImportService(self.db, self.student_service)._get_or_create_users_bulk(
                [{"student_id": r["student_id"], "student_name": r["student_name"]} for r in parsed_rows]
            )
            for idx, row in enumerate(parsed_rows):
                current_row = row.get("row_number", idx + 2)
                user = user_map[row["student_id"]]

                # Inline sequential app_id with 'R' (renewal) suffix — same lock pattern as batch import.
                seq_stmt = (select(ApplicationSequence).where(and_(
                    ApplicationSequence.academic_year == academic_year,
                    ApplicationSequence.semester == seq_semester)).with_for_update())
                seq_record = (await self.db.execute(seq_stmt)).scalar_one_or_none()
                if not seq_record:
                    seq_record = ApplicationSequence(academic_year=academic_year, semester=seq_semester, last_sequence=0)
                    self.db.add(seq_record)
                    await self.db.flush()
                seq_record.last_sequence += 1
                app_id = f"{ApplicationSequence.format_app_id(academic_year, seq_semester, seq_record.last_sequence)}R"

                student_data = None
                try:
                    student_data = await self.student_service.get_student_snapshot(
                        row["student_id"], academic_year=str(academic_year), semester=semester)
                except (NotFoundError, ServiceUnavailableError):
                    logger.warning("SIS snapshot unavailable for %s", row["student_id"], exc_info=True)

                now = datetime.now(timezone.utc)
                application = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=scholarship_type_id,
                    scholarship_configuration_id=config.id,
                    allocation_config_id=config.id,
                    scholarship_name=scholarship.name,
                    amount=config.amount,
                    sub_scholarship_type=row["sub_type"],
                    scholarship_subtype_list=[row["sub_type"]],
                    sub_type_selection_mode=scholarship.sub_type_selection_mode,
                    academic_year=academic_year,
                    semester=semester,
                    is_renewal=True,
                    renewal_year=academic_year,
                    status=ApplicationStatus.approved.value,
                    review_stage=ReviewStage.quota_distributed.value,
                    quota_allocation_status="allocated",
                    approved_at=now,
                    submitted_at=now,
                    imported_by_id=batch_import.importer_id,
                    batch_import_id=batch_import.id,
                    import_source="renewal_import",
                    document_status="complete",
                    student_data=student_data,
                    submitted_form_data={
                        "postal_account": row.get("postal_account"),
                        "advisor_name": row.get("advisor_name"),
                        "advisor_nycu_id": row.get("advisor_nycu_id"),
                        "custom_fields": {},
                    },
                )
                self.db.add(application)
                applications.append(application)

            await self.db.flush()
            created_ids = [app.id for app in applications]
        except Exception as e:  # noqa: BLE001 - convert to BatchImportError after rollback
            await self.db.rollback()
            batch_import.import_status = BatchImportStatus.failed.value
            batch_import.error_summary = {"failed_at_row": current_row, "message": str(e)}
            await self.db.commit()
            raise BatchImportError(message=f"續領匯入失敗於第 {current_row} 行: {str(e)}", batch_id=batch_import.id) from e

        return created_ids, errors
```

> Implementer note: ids are read after `flush()` from the local `applications` list (same pattern as `create_applications_from_batch`). The initial `created_ids: List[int] = []` is reassigned once ids exist. `document_status="complete"` (not `"pending_documents"`) because renewal imports carry no per-application documents.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest app/tests/test_renewal_import_service.py::test_create_renewals_sets_approved_fields -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Format + lint the service**

Run:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/renewal_import_service.py
flake8 app --select=B904,B014 --max-line-length=120
```
Expected: no B904/B014 findings (note the `raise ... from e`).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/renewal_import_service.py backend/app/tests/test_renewal_import_service.py
git commit -m "feat: create approved renewal applications from import"
```

---

### Task 6: Extend the roster generator to include approved renewals

**Files:**
- Modify: `backend/app/services/roster_service.py` — `generate_rosters_from_distribution` (1478) and `_create_roster_item` (795); add helper `_build_application_semester_filter`.
- Test: `backend/app/tests/test_roster_renewal_inclusion.py`

**Interfaces:**
- Consumes: `Application` renewal rows created in Task 5 (`is_renewal=True`, `status="approved"`, `allocation_config_id`, `sub_scholarship_type`).
- Produces: rosters that contain approved renewals grouped by `(allocation_config_id, sub_scholarship_type)`, including renewal-only groups.

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_roster_renewal_inclusion.py`. This test uses the **sync** test session (`db_sync`) with real rows because `RosterService` is synchronous.

```python
import pytest

from app.models.application import Application, ApplicationStatus
from app.models.enums import ReviewStage
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.services.roster_service import RosterService


def _mk_common(db_sync):
    st = ScholarshipType(name="PhD", code="phd", sub_type_list=["nstc"], sub_type_selection_mode="single")
    db_sync.add(st)
    db_sync.flush()
    cfg = ScholarshipConfiguration(scholarship_type_id=st.id, academic_year=114, semester=None,
                                   config_name="phd-114", config_code="phd_114", amount=40000)
    db_sync.add(cfg)
    db_sync.flush()
    user = User(nycu_id="413271002", name="曾美麗", user_type="student", role="student")
    db_sync.add(user)
    db_sync.flush()
    return st, cfg, user


@pytest.mark.integration
def test_renewal_only_generates_roster(db_sync):
    st, cfg, user = _mk_common(db_sync)
    app = Application(
        app_id="APP-114-0-00001R", user_id=user.id, scholarship_type_id=st.id,
        scholarship_configuration_id=cfg.id, allocation_config_id=cfg.id, scholarship_name="PhD",
        amount=40000, sub_scholarship_type="nstc", scholarship_subtype_list=["nstc"],
        academic_year=114, semester=None, is_renewal=True, renewal_year=114,
        status=ApplicationStatus.approved.value, review_stage=ReviewStage.quota_distributed.value,
        student_data={"std_stdcode": "413271002", "std_cname": "曾美麗", "std_pid": "A123456789"},
        submitted_form_data={"postal_account": "1234567890123"},
    )
    db_sync.add(app)
    db_sync.commit()

    service = RosterService(db_sync)
    result = service.generate_rosters_from_distribution(
        scholarship_type_id=st.id, academic_year=114, semester="yearly",
        created_by_user_id=user.id, student_verification_enabled=False)

    assert len(result.created) == 1
    roster = result.created[0]
    assert roster.sub_type == "nstc"
    assert roster.total_applications == 1
    item = roster.items[0]
    assert item.application_identity == "114續領"
    assert item.allocated_sub_type == "nstc"
```

> If the sync fixture in this repo is named differently (check `app/tests/conftest.py` / an existing `test_roster_service*.py` for the exact sync-session fixture and any `RosterService` construction helper), use that name; the assertions stay the same.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest app/tests/test_roster_renewal_inclusion.py -p no:cacheprovider`
Expected: FAIL — currently raises `ValueError("找不到已完成分發的排名…")` because there are no rankings.

- [ ] **Step 3: Add the Application semester-filter helper**

In `roster_service.py`, next to `_build_semester_filter` (1461), add:

```python
    def _build_application_semester_filter(self, semester: Optional[str]):
        """Semester predicate on Application.semester, mirroring _build_semester_filter."""
        from app.models.application import Application

        if semester in (None, "", "annual", "yearly"):
            return or_(Application.semester.is_(None), Application.semester == "annual",
                       Application.semester == "yearly")
        return Application.semester == semester
```

(Ensure `or_` is imported — it is already used in `roster_service.py`.)

- [ ] **Step 4: Extend `generate_rosters_from_distribution`**

Replace the region from the rankings guard through the `consumed_configs` preload (currently ~lines 1529-1591) with the version below. This: (a) always looks up `scholarship_config`; (b) queries approved renewals; (c) relaxes the "no rankings / no allocated items" guards to also consider renewals; (d) merges renewal application-ids into the group keys.

```python
        ranking_ids = [r.id for r in rankings]

        scholarship_config = (
            self.db.query(ScholarshipConfiguration)
            .filter(and_(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                ScholarshipConfiguration.academic_year == academic_year,
            ))
            .first()
        )
        if not scholarship_config:
            raise ValueError(
                f"找不到對應的獎學金配置：scholarship_type_id={scholarship_type_id}, academic_year={academic_year}"
            )

        # Approved renewals never win a CollegeRankingItem (是 renewals are excluded
        # from allocation), so the distribution roster path can't see them. Pull them
        # directly and merge by (allocation_config_id, sub_scholarship_type) — the same
        # key ManualDistributionService._renewal_filters uses for quota consumption.
        renewal_apps = (
            self.db.query(Application)
            .filter(and_(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal.is_(True),
                Application.status == "approved",
                Application.deleted_at.is_(None),
                self._build_application_semester_filter(semester),
            ))
            .all()
        )

        allocated_items = (
            self.db.query(CollegeRankingItem)
            .filter(and_(
                CollegeRankingItem.ranking_id.in_(ranking_ids),
                CollegeRankingItem.is_allocated.is_(True),
            ))
            .all()
            if ranking_ids else []
        )

        if not allocated_items and not renewal_apps:
            raise ValueError(
                "沒有可造冊的資料：找不到已分配的排名學生，也沒有已核准的續領。"
                "請先完成矩陣分發，或先匯入續領通過名單。"
            )

        # 分組：{(allocation_config_id, sub_type): [ranking_item, ...]}
        groups: Dict[tuple, List] = {}
        for item in allocated_items:
            alloc_config_id = item.allocation_config_id or scholarship_config.id
            sub_type = item.allocated_sub_type or "general"
            groups.setdefault((alloc_config_id, sub_type), []).append(item)

        # Merge approved renewals into (possibly new) groups; collect their ids per key.
        renewal_ids_by_key: Dict[tuple, set] = {}
        for app in renewal_apps:
            key = (app.allocation_config_id or scholarship_config.id, app.sub_scholarship_type or "general")
            renewal_ids_by_key.setdefault(key, set()).add(app.id)
            groups.setdefault(key, [])

        # Preload each group's consumed config.
        consumed_configs: Dict[int, ScholarshipConfiguration] = {scholarship_config.id: scholarship_config}
        for alloc_config_id, _sub_type in groups:
            if alloc_config_id not in consumed_configs:
                consumed = self.db.get(ScholarshipConfiguration, alloc_config_id)
                if consumed is None:
                    raise ValueError(f"找不到消耗配置 scholarship_configuration_id={alloc_config_id}")
                consumed_configs[alloc_config_id] = consumed
```

Then update the group loop's `application_ids_in_group` line (currently ~1599) to add the renewal ids:

```python
        for (alloc_config_id, sub_type), group_items in groups.items():
            application_ids_in_group = {item.application_id for item in group_items}
            application_ids_in_group |= renewal_ids_by_key.get((alloc_config_id, sub_type), set())
            consumed_config = consumed_configs[alloc_config_id]
```

Also **delete** the now-obsolete early guard `if not rankings: raise ValueError("找不到已完成分發的排名…")` (the combined guard above replaces it) and the old standalone `if not allocated_items: raise ValueError(...)`.

- [ ] **Step 5: Fix `_create_roster_item` for renewals (no ranking item)**

In `_create_roster_item` (795), make two edits:

1. Sub-type fallback — after the `if not allocated_sub_type:` block (ends ~892), add:

```python
        # Renewals carry no CollegeRankingItem; take the sub-type from the application.
        if not allocated_sub_type and application.is_renewal:
            allocated_sub_type = application.sub_scholarship_type
```

2. Identity label (line ~906) — change:

```python
        if application.is_renewal and application.previous_application_id:
```
to:
```python
        if application.is_renewal:
```

- [ ] **Step 6: Run test to verify it passes**

Run: `python -m pytest app/tests/test_roster_renewal_inclusion.py -p no:cacheprovider`
Expected: PASS. Also run the existing roster suite to confirm no regression:
`python -m pytest app/tests/test_roster_service*.py -p no:cacheprovider` — Expected: PASS (non-renewal roster behaviour unchanged; renewals were previously invisible).

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_renewal_inclusion.py
git commit -m "feat: include approved renewals in matrix roster generation"
```

---

### Task 7: Renewal-import API endpoints + router registration

**Files:**
- Create: `backend/app/api/v1/endpoints/renewal_import.py`
- Modify: `backend/app/api/v1/api.py` (import + `include_router`)
- Test: `backend/app/tests/test_renewal_import_endpoints.py`

**Interfaces:**
- Produces routes under `/college-review/renewal-import`: `POST /upload`, `POST /{batch_id}/confirm`, `GET /history`, `GET /{batch_id}/details`, `GET /template`. All guarded by `require_college_role`. Standard `{success, message, data}` envelope.
- Consumes: `RenewalImportService` (Tasks 3-5), `RenewalImport*` schemas (Task 2).

- [ ] **Step 1: Write the endpoints**

Create `backend/app/api/v1/endpoints/renewal_import.py`. Mirror `batch_import.py`'s upload/confirm/template structure (MIME/size validation via `magic` + `settings.max_file_size`; MinIO store to `settings.minio_bucket` at `renewal-imports/{id}/{filename}`; `AuditLog` writes; `{success,message,data}` envelope), with these renewal-specific differences:

```python
"""Renewal-students import endpoints (approved renewals for 造冊)."""

import logging
from io import BytesIO
from typing import Any, Dict, List, Optional

import magic
import pandas as pd
from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import BatchImportError
from app.models.audit_log import AuditAction, AuditLog
from app.models.batch_import import BatchImport, BatchImportStatus
from app.models.enums import UserRole
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User
from app.schemas.renewal_import import (
    RenewalImportConfirmRequest,
    RenewalImportConfirmResponse,
    RenewalImportUploadResponse,
)
from app.services.renewal_import_service import RenewalImportService, _to_semester_enum
from app.api.deps import get_current_user  # adjust to the same import batch_import.py uses

logger = logging.getLogger(__name__)
router = APIRouter()


def require_college_role(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in [UserRole.college, UserRole.admin, UserRole.super_admin]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="此功能僅限學院或管理員角色使用")
    return current_user


async def _load_config_in_renewal_period(db, scholarship_type_id, academic_year, semester):
    semester_enum = _to_semester_enum(semester)
    stmt = select(ScholarshipConfiguration).where(
        ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
        ScholarshipConfiguration.academic_year == academic_year,
    )
    from app.models.enums import Semester
    stmt = (stmt.where(ScholarshipConfiguration.semester.is_(None))
            if semester_enum in (None, Semester.yearly) else stmt.where(ScholarshipConfiguration.semester == semester_enum))
    config = (await db.execute(stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"找不到 {academic_year} 學年度的獎學金配置")
    if not config.is_renewal_application_period:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="此獎學金配置目前不在續領期間，無法匯入續領生")
    return config


@router.post("/upload")
async def upload_renewal_import(
    file: UploadFile = File(...),
    scholarship_type: str = Query(..., pattern=r"^[a-z_]{1,50}$"),
    academic_year: int = Query(..., ge=100, le=200),
    semester: Optional[str] = Query(None, pattern=r"^(first|second|yearly)$"),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ScholarshipType).where(ScholarshipType.code == scholarship_type)
    scholarship = (await db.execute(stmt)).scalar_one_or_none()
    if not scholarship:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"獎學金類型 {scholarship_type} 不存在")

    normalized_semester = (semester.strip() if isinstance(semester, str) else semester) or None
    await _load_config_in_renewal_period(db, scholarship.id, academic_year, normalized_semester)

    college_code = current_user.college_code
    file_content = await file.read()
    if len(file_content) > settings.max_file_size:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="檔案過大")
    mime_type = magic.from_buffer(file_content, mime=True)
    allowed = {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               "application/vnd.ms-excel", "application/x-ole-storage", "text/csv",
               "text/plain", "application/csv"}
    if mime_type not in allowed:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"不支援的檔案格式 ({mime_type})")

    service = RenewalImportService(db)
    parsed, skipped, errors = await service.parse_renewal_excel(
        file_content, scholarship.id, academic_year, normalized_semester)
    val_errors, warnings = await service.validate_and_preview(
        parsed, college_code or "", scholarship.id, academic_year, normalized_semester)
    errors = list(errors) + list(val_errors)

    batch = await service.create_renewal_import_record(
        importer_id=current_user.id, college_code=college_code or "admin",
        scholarship_type_id=scholarship.id, academic_year=academic_year,
        semester=normalized_semester, file_name=file.filename, total_records=len(parsed))

    # MinIO store (best-effort) — mirror batch_import.py: object 'renewal-imports/{id}/{filename}'.
    try:
        from app.services.minio_service import MinIOService
        MinIOService().client.put_object(
            bucket_name=settings.minio_bucket,
            object_name=f"renewal-imports/{batch.id}/{file.filename}",
            data=BytesIO(file_content), length=len(file_content), content_type=mime_type)
        batch.file_path = f"renewal-imports/{batch.id}/{file.filename}"
    except Exception:
        logger.warning("Failed to upload renewal import file to MinIO", exc_info=True)

    batch.parsed_data = {"data": parsed, "skipped": skipped, "errors": errors, "warnings": warnings}
    db.add(AuditLog.create_log(
        user_id=current_user.id, action=AuditAction.create.value, resource_type="renewal_import",
        resource_id=str(batch.id), resource_name=file.filename,
        description=f"renewal import upload: {file.filename} ({len(parsed)} passed / {len(skipped)} skipped)"))
    await db.commit()

    resp = RenewalImportUploadResponse(
        batch_id=batch.id, file_name=file.filename, total_records=len(parsed),
        skipped_records=len(skipped), preview_data=parsed,
        validation_summary={"valid_count": len(parsed) - len({e["student_id"] for e in errors if e.get("student_id")}),
                            "invalid_count": len(errors), "skipped_count": len(skipped),
                            "errors": errors[:50], "warnings": warnings[:50]})
    return {"success": True, "message": f"上傳成功：{len(parsed)} 筆通過、{len(skipped)} 筆跳過、{len(errors)} 筆錯誤",
            "data": resp.model_dump()}


@router.post("/{batch_id}/confirm")
async def confirm_renewal_import(
    batch_id: int,
    request: RenewalImportConfirmRequest | None = Body(None),
    current_user: User = Depends(require_college_role),
    db: AsyncSession = Depends(get_db),
):
    batch = await db.get(BatchImport, batch_id)
    if not batch or batch.import_type != "renewal":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"續領匯入記錄 {batch_id} 不存在")
    if batch.importer_id != current_user.id and current_user.role != UserRole.super_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="僅能確認自己上傳的匯入")
    if batch.import_status not in (BatchImportStatus.pending, BatchImportStatus.pending.value,
                                   BatchImportStatus.failed, BatchImportStatus.failed.value):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"此批次狀態為 {batch.import_status}")

    if request is not None and not request.confirm:
        batch.import_status = BatchImportStatus.cancelled.value
        await db.commit()
        return {"success": True, "message": "匯入已取消",
                "data": RenewalImportConfirmResponse(batch_id=batch_id, success_count=0, failed_count=0).model_dump()}

    if not batch.parsed_data or "data" not in batch.parsed_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="匯入資料已過期，請重新上傳")

    error_ids = {e["student_id"] for e in (batch.parsed_data.get("errors") or []) if e.get("student_id")}
    clean = [r for r in batch.parsed_data["data"] if r["student_id"] not in error_ids]
    if not clean:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="沒有可匯入的資料（皆有錯誤）")

    batch.import_status = BatchImportStatus.processing.value
    await db.commit()

    service = RenewalImportService(db)
    try:
        normalized_semester = (batch.semester.strip() if isinstance(batch.semester, str) else batch.semester) or None
        created_ids, creation_errors = await service.create_renewals_from_batch(
            batch_import=batch, parsed_rows=clean, scholarship_type_id=batch.scholarship_type_id,
            academic_year=batch.academic_year, semester=normalized_semester)
        batch.success_count = len(created_ids)
        batch.failed_count = len(creation_errors)
        batch.import_status = BatchImportStatus.completed.value if not creation_errors else BatchImportStatus.partial.value
        for cid in created_ids:
            db.add(AuditLog.create_log(
                user_id=current_user.id, action=AuditAction.import_.value, resource_type="application",
                resource_id=str(cid), description=f"approved renewal created via renewal import {batch_id}",
                meta_data={"batch_id": batch_id}))
        await db.commit()
        return {"success": True, "message": f"匯入完成：建立 {len(created_ids)} 筆續領",
                "data": RenewalImportConfirmResponse(batch_id=batch_id, success_count=len(created_ids),
                        failed_count=len(creation_errors), created_application_ids=created_ids).model_dump()}
    except BatchImportError as e:
        logger.exception("Renewal import confirm failed", extra={"batch_id": batch_id})
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=e.message) from e
```

Add `GET /history`, `GET /{batch_id}/details`, and `GET /template` by mirroring `batch_import.py`'s equivalents, with two changes: (a) `history` filters `BatchImport.import_type == "renewal"`; (b) `template` builds the fixed renewal columns `["編號","學院","系所","學生姓名","學號","學生年級","學生是否申請續領","續領審核結果","獎學金類別","郵局帳號","指導教授本校人事編號"]` with one 範例 row (`否` / `領獎期滿，無續領` per the sample) and one 通過 row, and a note that 獎學金類別 accepts `國科會`/`教育部`. Use the same `pd.ExcelWriter(engine="openpyxl")` + `StreamingResponse` pattern.

> Import note: match `batch_import.py`'s actual import of `get_current_user` and `get_db` (it uses the same deps); copy those import lines verbatim rather than guessing the module path.

- [ ] **Step 2: Register the router**

In `backend/app/api/v1/api.py`, add the import alongside the others (near line 12/26):

```python
from app.api.v1.endpoints import renewal_import
```

and register it right after the batch-import line (after line 70):

```python
api_router.include_router(renewal_import.router, prefix="/college-review/renewal-import", tags=["Renewal Import"])
```

- [ ] **Step 3: Write an endpoint test (renewal-period gate + upload happy path)**

Create `backend/app/tests/test_renewal_import_endpoints.py` using the app's async test client + auth fixtures (mirror an existing `test_*_endpoints.py`). Minimum assertions:
- `POST /college-review/renewal-import/upload` with a config **not** in its renewal window → `400` with detail containing `續領期間`.
- With a config in its renewal window + a 2-row sheet (one 通過, one 否) → `200`, `data.total_records == 1`, `data.skipped_records == 1`.

```python
import pytest


@pytest.mark.asyncio
async def test_upload_rejects_outside_renewal_period(client, admin_auth_headers, phd_config_closed_renewal):
    files = {"file": ("r.xlsx", b"...", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post(
        "/api/v1/college-review/renewal-import/upload",
        params={"scholarship_type": "phd", "academic_year": 114, "semester": "first"},
        files=files, headers=admin_auth_headers)
    assert resp.status_code == 400
    assert "續領期間" in resp.json()["detail"]
```

> Reuse whatever config/auth fixtures the existing endpoint tests provide; if none matches `phd_config_closed_renewal`, build a `ScholarshipConfiguration` with `renewal_application_start_date/end_date` in the past.

- [ ] **Step 4: Run tests + start the app to smoke the routes**

Run: `python -m pytest app/tests/test_renewal_import_endpoints.py -p no:cacheprovider`
Expected: PASS. Then start the dev stack and confirm `/api/v1/college-review/renewal-import/upload` appears in `/openapi.json`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/renewal_import.py backend/app/api/v1/api.py backend/app/tests/test_renewal_import_endpoints.py
git commit -m "feat: renewal-import API endpoints"
```

---

### Task 8: Frontend API module + client getter

**Files:**
- Create: `frontend/lib/api/modules/renewal-import.ts`
- Modify: `frontend/lib/api/index.ts` (import + private field + lazy getter)

**Interfaces:**
- Produces: `apiClient.renewalImport` with `uploadData(file, scholarshipCode, academicYear, semester)`, `confirm(batchId, confirm=true)`, `getHistory(params?)`, `getDetails(batchId)`, `downloadTemplate(scholarshipCode)`.
- Consumes: the Task 7 routes.

- [ ] **Step 1: Write the API module**

Create `frontend/lib/api/modules/renewal-import.ts` mirroring `batch-import.ts` (same `typedClient.raw.<METHOD>` + `toApiResponse` pattern; copy the `resolveAuthToken` helper for `downloadTemplate`). Point paths at `/api/v1/college-review/renewal-import/...`. Result types:

```typescript
export interface RenewalUploadResult {
  batch_id: number;
  file_name: string;
  total_records: number;
  skipped_records: number;
  preview_data: Array<Record<string, unknown>>;
  validation_summary: {
    valid_count: number;
    invalid_count: number;
    skipped_count: number;
    errors: Array<Record<string, unknown>>;
    warnings: Array<Record<string, unknown>>;
  };
}

export interface RenewalConfirmResult {
  batch_id: number;
  success_count: number;
  failed_count: number;
  created_application_ids: number[];
}
```

`uploadData`/`confirm`/`downloadTemplate` bodies are identical in shape to `batch-import.ts` (verbatim), only the URL path differs (`.../renewal-import/upload`, `.../renewal-import/{batch_id}/confirm`, `.../renewal-import/template`). `uploadData` posts to `/api/v1/college-review/renewal-import/upload` with query `{scholarship_type, academic_year, semester}` and the multipart file body.

- [ ] **Step 2: Expose it on `apiClient`**

In `frontend/lib/api/index.ts`: add `import { createRenewalImportApi } from './modules/renewal-import';` (near line 30), a private field `private _renewalImport?: ReturnType<typeof createRenewalImportApi>;` (near line 157), and a lazy getter mirroring `batchImport`:

```typescript
  get renewalImport(): ReturnType<typeof createRenewalImportApi> {
    if (!this._renewalImport) this._renewalImport = createRenewalImportApi();
    return this._renewalImport;
  }
```

- [ ] **Step 3: Type-check**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors from the new module.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/modules/renewal-import.ts frontend/lib/api/index.ts
git commit -m "feat: frontend renewal-import API module"
```

---

### Task 9: Frontend panel + i18n + tab mount

**Files:**
- Create: `frontend/components/renewal-import-panel.tsx`
- Modify: `frontend/lib/i18n.ts` (add `renewal_import.field_labels` in zh + en)
- Modify: `frontend/app/page.tsx` (import + `TabsTrigger` + `TabsContent`)

**Interfaces:**
- Consumes: `apiClient.renewalImport` (Task 8), `apiClient.admin.getMyScholarships()`, `apiClient.referenceData.getScholarshipPeriods()`.

- [ ] **Step 1: Add i18n field labels**

In `frontend/lib/i18n.ts`, add a sibling namespace to `batch_import` in **both** locale objects (zh ~334, en ~851):

```javascript
    renewal_import: {
      field_labels: {
        student_id: "學號",
        student_name: "姓名",
        sub_type: "獎學金類別",
        postal_account: "郵局帳號",
        advisor_nycu_id: "指導教授本校人事編號",
        advisor_name: "指導教授姓名",
        row_number: "行號",
      },
    },
```

(English block: `Student ID` / `Name` / `Scholarship Category` / `Postal Account` / `Advisor NYCU ID` / `Advisor Name` / `Row Number`.)

- [ ] **Step 2: Build the panel**

Create `frontend/components/renewal-import-panel.tsx` as a simplified twin of `batch-import-panel.tsx` (no document-upload step). Reuse verbatim: the `Scholarship`/`PeriodOption` interfaces, the selector grid, `handleDownloadTemplate`/`handleUpload`/`handleConfirm`, and `renderPreviewTable`, with these changes:
- `apiClient.batchImport.*` → `apiClient.renewalImport.*`.
- `UploadedBatch` gains `skipped_records: number` and `validation_summary.skipped_count`.
- Preview `getFieldLabel` uses the `renewal_import.field_labels.*` namespace.
- Show a summary line: `通過 {total_records} 筆 · 跳過 {skipped_records} 筆 · 錯誤 {invalid_count} 筆`, and render the `warnings` list (postal/quota).
- Confirm button copy → `確認匯入續領` and disabled when `invalid_count > 0`.
- Component export: `export function RenewalImportPanel({ locale = "zh" }: { locale?: "zh" | "en" })`.

- [ ] **Step 3: Mount the tab**

In `frontend/app/page.tsx`: add `import { RenewalImportPanel } from "@/components/renewal-import-panel";` (near line 37); add a `<TabsTrigger value="renewal-import">` next to the batch-import trigger in the `TabsList`; and add, next to the batch-import `TabsContent` (line ~545), role-gated for `college`/`admin`/`super_admin`:

```tsx
          {(user.role === "college" || user.role === "admin" || user.role === "super_admin") && (
            <TabsContent value="renewal-import" className="space-y-4">
              <RenewalImportPanel locale={locale} />
            </TabsContent>
          )}
```

- [ ] **Step 4: Type-check + build**

Run: `cd frontend && npx tsc --noEmit && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/renewal-import-panel.tsx frontend/lib/i18n.ts frontend/app/page.tsx
git commit -m "feat: renewal-import admin panel + tab"
```

---

### Task 10: OpenAPI sync, lint gates, and end-to-end verification

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (regenerated)

- [ ] **Step 1: Regenerate OpenAPI types**

With the backend running on `:8000`:
```bash
cd frontend && npm run api:generate
git add lib/api/generated/schema.d.ts
```
Expected: the new `/college-review/renewal-import/*` paths appear in the generated schema.

- [ ] **Step 2: Backend lint gates (hard)**

Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
flake8 app --select=B904,B014 --max-line-length=120
```
Expected: clean. Fix any B904 (`raise ... from`) / B014 in the new files.

- [ ] **Step 3: Run the touched backend tests**

Run:
```bash
python -m pytest app/tests/test_renewal_import_schema.py app/tests/test_renewal_import_service.py \
  app/tests/test_roster_renewal_inclusion.py app/tests/test_renewal_import_endpoints.py \
  app/tests/test_batch_import_type_migration.py -p no:cacheprovider
```
Expected: all PASS.

- [ ] **Step 4: Regression — existing roster + batch-import suites**

Run:
```bash
python -m pytest app/tests/test_roster_service*.py app/tests/test_batch_import*.py -p no:cacheprovider
```
Expected: PASS (batch-import history now scoped to `import_type="application"`; roster behaviour unchanged for non-renewals).

- [ ] **Step 5: Manual end-to-end smoke (dev stack)**

1. Start `docker compose -f docker-compose.dev.yml up`.
2. As admin, open the 匯入續領生 tab; pick the PhD scholarship + a year whose config is in its renewal window.
3. Download the template, fill 2 rows (one 是/通過 國科會, one 否), upload → preview shows 1 imported / 1 skipped.
4. Confirm → an approved renewal `Application` (`is_renewal=True`, `status=approved`, `app_id` ending `R`) is created.
5. Run 生成造冊 for that scholarship+year → the roster includes the renewal with `application_identity="{year}續領"` and the postal account populated.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore: regenerate OpenAPI types for renewal-import"
```

---

## Self-Review Notes (author)

- **Spec coverage:** §5.1 → Task 1; §5.2 template → Task 7 (template) + §5.3 filter → Task 3; §5.3 validation/warnings → Task 4; §5.4 create contract → Task 5; §5.5 roster bridge + `_create_roster_item` fixes → Task 6; §5.6 endpoints/schemas → Tasks 2,7; §5.7 frontend → Tasks 8,9; §6 edge cases (renewal-only roster, duplicate index, non-null amount) → Tasks 5,6; §7 testing → each task + Task 10; §8 migration/OpenAPI → Tasks 1,10.
- **Amount** is `config.amount` (verified non-null Integer) — Task 5, satisfies the roster NOT NULL amount.
- **No professor auto-assign / no UserProfile upsert** — matches real `create_applications_from_batch`; advisor data lives in `submitted_form_data`.
- **`app_id` suffix `"R"`** distinguishes renewal imports from batch (`"U"`) and online.
