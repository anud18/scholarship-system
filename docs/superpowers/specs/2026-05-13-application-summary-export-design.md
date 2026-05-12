# Application Summary Excel Export — 系所申請總表

**Date:** 2026-05-13
**Status:** Approved
**Reference:** Builds on `2026-05-08-college-ranking-export-design.md` (學生資料彙整表)
**Worktree:** `.claude/worktrees/application-summary-export` (branch `worktree-application-summary-export`)

## Goal

Add a department-scoped 「申請總表」 Excel export that mirrors the existing 學生資料彙整表 layout (18 static columns + admin-configurable dynamic columns) but with the rank column (`學院初審會議之學院排序`) left blank. The export must be reachable by both college users (limited to departments in their own academy) and administrators (any department), and must support both single-department `.xlsx` download and multi-department `.zip` bundle.

## Non-goals

- Adding new static columns or changing the layout. The new export reuses the existing 18-column template; only the rank cell value changes.
- Filtering applications by `sub_type_code`. All non-deleted applications matching `(scholarship_type, academic_year, semester, department)` are included regardless of sub-type preference.
- Renaming the rank column header. Header stays `學院初審會議之學院排序`; only the cell value is blank.
- Allowing college users to export departments outside their own academy.
- A separate admin page. The export trigger reuses the existing application list UI used by both college users and admins.

## Background

- The college ranking export (`backend/app/services/college_ranking_export_service.py`) already renders the 18-column template. Its `ExportRow.rank_position: int` carries `CollegeRankingItem.rank_position`. Cell rendering is in `_write_static_cells` line 126: `ws.cell(row=excel_row, column=2, value=row.rank_position)`.
- Applications are stored with `Application.student_data` (JSON) carrying SIS snapshot fields including `std_depno` (department code), `std_stdcode` (student ID), and `trm_*` term fields.
- Department model (`backend/app/models/student.py:78-89`) joins `Department.academy_code` → `Academy.code`. `User.college_code` (for college users) holds an Academy code.
- Existing ranking export endpoint pattern (`backend/app/api/v1/endpoints/college_review/ranking_management.py:1093-1247`) is the reference for auth, dynamic-field loading, bulk profile/advisor loading, and StreamingResponse handling.

## Data model changes

**None.** No DB schema migration is required. The export reuses:

- `application_fields.include_in_college_export` (flag added by the prior ranking-export feature) for dynamic columns.
- `application_fields.export_column_label` for optional header overrides.
- Existing `Department`/`Academy` tables for department lookup.

## Excel structure

Identical to 學生資料彙整表 (see prior spec). The only behavioural change:

| # | Header | Value |
|---|---|---|
| 2 | 學院初審會議之學院排序 | **Empty string** (no rank yet) |

All other columns (1, 3-18) and dynamic columns render exactly as in the ranking export.

**Workbook title:** `{academic_year}學年度{scholarship_name}學生資料彙整表 - {department_name}`
(e.g. `114學年度博士生獎學金學生資料彙整表 - 教育研究所`)

**Sheet name:** `{academic_year}學年`

**Sort order:** `student_data.std_stdcode` ASC. Applications without a student code sort last (stable secondary sort by `application.id`).

## API

Both endpoints live in a new module `backend/app/api/v1/endpoints/college_review/application_summary_export.py`, mounted under the existing `/api/v1/college-review` prefix (router include in `college_review/__init__.py`).

### Single-department endpoint

`GET /api/v1/college-review/applications/department-summary-export`

| Query param | Type | Required | Notes |
|---|---|---|---|
| `scholarship_type_id` | int | yes | |
| `academic_year` | int | yes | |
| `semester` | str | no | `first` / `second` / `yearly` / null. `yearly` and null both match rows with `semester IS NULL`. Normalised via `_helpers.normalize_semester_value`. |
| `department_code` | str | yes | Must match `Department.code`. |

**Response:** `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` stream.
**Filename:** `{academic_year}學年度{scholarship_name}學生資料彙整表_{department_name}.xlsx` (RFC 5987 UTF-8 encoded in `Content-Disposition`).

### Bulk (ZIP) endpoint

`GET /api/v1/college-review/applications/department-summary-export-bulk`

| Query param | Type | Required | Notes |
|---|---|---|---|
| `scholarship_type_id` | int | yes | |
| `academic_year` | int | yes | |
| `semester` | str | no | Same semantics. |
| `scope` | str | yes | `college` (本學院全部系所) or `all` (全部系所). |

**Response:** `application/zip` stream containing one `.xlsx` per non-empty department.
**Filename:** `{academic_year}學年度{scholarship_name}學生資料彙整表_{scope_label}.zip` where `scope_label` is `current_user.college_code` for `college` scope (matching the existing ranking-export filename convention) or `全部` for `all`.
**Inner filenames:** Same single-department `.xlsx` pattern, sanitised to remove path separators and other filesystem-unsafe characters (`/`, `\`, `:`, `*`, `?`, `"`, `<`, `>`, `|`).

### Authorization

Both endpoints use `Depends(require_college)` (covers admin + super_admin + college roles). Additional checks:

| Caller role | `department_code` (single) | `scope=college` | `scope=all` |
|---|---|---|---|
| `admin` / `super_admin` | any | requires `current_user.college_code` to be set; otherwise 400 with `管理員需指定學院` | OK |
| College user | dept must satisfy `Department.academy_code == current_user.college_code`; else 403 | OK (current user's academy) | **403** |
| Anyone else | 403 (covered by `require_college`) | 403 | 403 |

Empty result sets are handled per the table in the **Error handling** section: a single-department call with no matches still returns a valid workbook (header row only); a bulk call with no matches returns 404 to avoid silent empty ZIP downloads.

### Backend flow (shared)

1. Validate auth, normalise `semester`, resolve target department code list:
   - Single: `[department_code]` after auth check.
   - Bulk `scope=college`: `select Department.code where academy_code == current_user.college_code` (admins use their own `college_code`; the 400 above guards admins with no `college_code`).
   - Bulk `scope=all`: distinct `std_depno` values present in matching applications.
2. Load applications:
   ```python
   stmt = (
       select(Application)
       .where(
           Application.scholarship_type_id == scholarship_type_id,
           Application.academic_year == academic_year,
           Application.semester == normalised_semester,  # IS NULL when yearly
           Application.status != ApplicationStatus.deleted.value,
           Application.deleted_at.is_(None),
           Application.student_data["std_depno"].astext.in_(department_codes),
       )
   )
   ```
   The JSON path predicate uses SQLAlchemy's `JSON.astext`. PostgreSQL is the only supported DB.
3. Sort in Python by `student_data.get("std_stdcode") or ""` ASC, secondary by `application.id` ASC. (Doing this in Python avoids JSON-collation surprises across PG versions.)
4. Load dynamic fields, sub-type labels, profile account numbers, and advisor names with the same bulk-load pattern as `ranking_management.export_ranking_excel` (lines 1127-1199). Refactor that block into a helper at `backend/app/api/v1/endpoints/college_review/_helpers.py` to avoid duplication. Helper signature:
   ```python
   async def load_export_aux_data(
       db: AsyncSession,
       *,
       scholarship_type: Optional[ScholarshipType],
       applications: list[Application],
   ) -> tuple[
       list[DynamicFieldSpec],
       dict[str, str],          # sub_type_labels
       dict[int, str],          # account_number_by_user
       dict[int, str],          # advisor_string_by_user
   ]: ...
   ```
   `ranking_management.export_ranking_excel` is refactored to call this helper as part of this feature.
5. Build `ExportRow` per application with `rank_position=None`. Apply `service.build_workbook(...)`.
6. Single endpoint: return one `StreamingResponse`. Bulk: wrap workbooks in `zipfile.ZipFile(BytesIO(), 'w', ZIP_DEFLATED)`, then stream.

### Department lookup helper

Add `_load_department_lookup(db, codes)` returning `dict[str, str]` (code → name). Used for filename generation and bulk grouping. Falls back to the raw code when a Department row is missing (does NOT raise; defensive matches the rest of the export pipeline).

## Service change — `CollegeRankingExportService`

Single-field signature change to enable the empty-rank rendering:

```python
@dataclass
class ExportRow:
    rank_position: Optional[int]   # was: int
    application: Any
    bank_account: Optional[str] = None
    advisor_names: Optional[str] = None
```

`_write_static_cells` line 126 becomes:

```python
ws.cell(
    row=excel_row,
    column=2,
    value=(row.rank_position if row.rank_position is not None else ""),
)
```

No other lines change. Existing tests for the ranking export continue to pass because they always set `rank_position` to an integer.

Per [coding-style.md], we do **not** add a new "Optional support" toggle or wrapper service — the field directly accommodates `None`, and the call site decides whether to pass an int.

## Frontend

### ApplicationReviewPanel (college + admin shared)

Reuses `frontend/components/college/review/ApplicationReviewPanel.tsx`. The panel is already mounted in the college management shell for college users; admins reach the same data via the existing admin tools. (Admin access is via the existing role-aware path; we are **not** adding a new admin tab in this iteration.)

**UI additions** (placed near the existing 「下載」 / 「匯出 ZIP」 controls):

1. **Department selector** — `<Select>` with options:
   - For college users: each `Department` under `current_user.college_code`, plus a synthetic option `__college_all__` labelled 「本學院全部 (ZIP)」.
   - For admins: each `Department` (system-wide), plus `__college_all__` ("本學院全部 (ZIP)") only when the admin has a `college_code`, and `__all__` ("全部系所 (ZIP)").
2. **Export button** — 「匯出申請總表」. Disabled until a department option is selected and a scholarship-year-semester combination is locked (already required by the panel).
3. Click handler routes:
   - Specific dept code → call single-department helper → save `.xlsx`.
   - `__college_all__` → bulk helper with `scope=college`.
   - `__all__` → bulk helper with `scope=all`.

### Data sources for the dropdown

Departments come from the existing `useReferenceData()` hook (already used in the same file at line 60). The hook already loads Department + Academy reference data. Filtering for college users:

```ts
const visibleDepartments = useMemo(() => {
  if (user.role === "admin" || user.role === "super_admin") return departments;
  return departments.filter((d) => d.academy_code === user.college_code);
}, [departments, user]);
```

### API helpers

Add to `frontend/lib/api/modules/college.ts` (extends the module that already hosts `exportRankingExcel`):

```ts
export async function exportDepartmentSummary(params: {
  scholarship_type_id: number;
  academic_year: number;
  semester?: string | null;
  department_code: string;
}): Promise<Blob>;

export async function exportDepartmentSummaryBulk(params: {
  scholarship_type_id: number;
  academic_year: number;
  semester?: string | null;
  scope: "college" | "all";
}): Promise<Blob>;
```

Both use `fetch + blob` with the existing auth header pattern (Bearer token). On success, derive the filename from the `Content-Disposition` header (RFC 5987) and trigger a download via `URL.createObjectURL`.

After backend lands, run `cd frontend && npm run api:generate` to refresh `lib/api/generated/schema.d.ts`.

## Error handling

| Condition | HTTP | Detail |
|---|---|---|
| Missing/invalid query params | 422 | FastAPI default validation |
| `department_code` not found | 404 | `找不到系所代碼 {code}` |
| College user requests a dept outside their academy | 403 | `無權限匯出此系所之資料` |
| College user requests `scope=all` | 403 | `學院使用者僅能匯出本學院資料` |
| Admin requests `scope=college` without `college_code` set | 400 | `管理員未設定學院，無法使用本學院範圍` |
| No applications match (single) | 200 | Workbook with header row only (consistent with ranking export) |
| No applications match (bulk) | 404 | `找不到符合條件的申請資料` |
| DB / IO failure | 500 | Logged; never silently swallowed (per CLAUDE.md error-handling standard) |

## Testing

### Backend

`backend/tests/test_college_ranking_export_service.py` (existing file, add cases):
- `rank_position=None` → column 2 of that data row is `""`, header at row 2 unchanged.
- `rank_position=5` (existing test) still passes — regression guard.

New `backend/tests/test_application_summary_export_service.py`:
- Single department: 3 applications across different `sub_type_preferences` → 3 rows with empty rank cells, sorted by `std_stdcode`.
- Sub-type rendering matches existing logic (0 / 1 / 2 prefs).
- Dynamic field flagged for export appears at the correct offset with override label.
- Workbook title contains the department name.

New `backend/tests/test_application_summary_export_endpoint.py`:
- College user happy path: 200 + non-empty `.xlsx`.
- College user requests dept outside academy: 403.
- College user `scope=all`: 403.
- Admin `scope=all` happy path: 200 + ZIP with N files where N = distinct departments with applications.
- Admin `scope=college` without `college_code`: 400.
- Bulk with no matching apps: 404.
- Single with no matching apps: 200 + workbook with header row only.
- Auth bypassed (no token): 401 (handled by `require_college`).

> Note: the prior ranking-export spec deferred endpoint integration tests due to an `aiosqlite`/`httpx.AsyncClient(app=...)` gap in `backend/app/tests/conftest.py`. The implementation plan will first verify whether the gap still applies (run a single endpoint test to confirm). If it does, the conftest fix (ASGITransport migration + `aiosqlite` dev-dep) is sequenced as a precursor task; otherwise, the endpoint tests land directly. Service tests do not depend on the conftest and ship unconditionally.

### Frontend

- `__tests__` on `ApplicationReviewPanel`: department dropdown renders, "本學院全部" routes to bulk helper, single dept routes to single helper, admin sees 「全部系所」.
- E2E (optional): user-flow check that download is triggered (Playwright). Reuse the existing ranking-export Playwright spec as a template.

## Migration & rollout

1. Backend refactor: extract `load_export_aux_data` helper into `college_review/_helpers.py`; update `ranking_management.export_ranking_excel` to use it. (Pure refactor — covered by existing ranking export tests.)
2. Modify `ExportRow.rank_position` to `Optional[int]`; update `_write_static_cells`. (Pure rendering change — covered by new + existing service tests.)
3. Add `application_summary_export.py` endpoint module + register router. Service tests + endpoint tests run.
4. Frontend: add department dropdown + export button + API helpers; regenerate OpenAPI types.
5. Manual smoke in dev: admin export `.xlsx` for one dept, college export `.xlsx`, college 「本學院全部」 `.zip`, admin 「全部系所」 `.zip`.

No database migration. No env var changes. No breaking changes to existing endpoints. Rollback is a clean revert.

## Files changed

**New:**
- `backend/app/api/v1/endpoints/college_review/application_summary_export.py`
- `backend/tests/test_application_summary_export_service.py`
- `backend/tests/test_application_summary_export_endpoint.py`

**Modified:**
- `backend/app/services/college_ranking_export_service.py` — `ExportRow.rank_position: Optional[int]`; conditional cell value.
- `backend/app/api/v1/endpoints/college_review/__init__.py` — include new router.
- `backend/app/api/v1/endpoints/college_review/_helpers.py` — add `load_export_aux_data` helper.
- `backend/app/api/v1/endpoints/college_review/ranking_management.py` — call new helper (remove duplicated load block).
- `backend/tests/test_college_ranking_export_service.py` — regression test for `rank_position=None`.
- `frontend/components/college/review/ApplicationReviewPanel.tsx` — dropdown + button + handler.
- `frontend/lib/api/modules/college.ts` — `exportDepartmentSummary`, `exportDepartmentSummaryBulk` helpers.
- `frontend/lib/api/generated/schema.d.ts` — regenerated.
- (If conftest fix is in scope) `backend/app/tests/conftest.py`, `backend/pyproject.toml` (dev deps).

## Open questions / deferred

- Whether to surface the export from the admin 「歷史申請」 (`HistoryPanel`) tab in a follow-up. Out of scope here.
- Whether to add a "filter by application status" query param. Not requested; YAGNI.
- Whether to allow downloading just one column subset. Not requested; YAGNI.
