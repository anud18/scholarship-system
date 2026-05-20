# Post-Distribution Supplementary Import Design

**Date**: 2026-05-14  
**Status**: Approved

## Overview

After admin completes distribution (`distribution_executed = True`), allow colleges to import additional student application data into an existing ranking. Imported students are appended after all existing students and queued for a subsequent admin manual distribution pass.

---

## Feature Summary

- Admin controls a per-configuration toggle (`ScholarshipConfiguration.allow_supplementary_import`) to open/close supplementary imports — one flag per (scholarship_type, academic_year, semester) applies to ALL colleges' rankings under that config
- College users upload an Excel file in the same format as the ranking export (學生資料彙整表)
- System calls NYCU SIS API to fetch `student_data` for each imported student
- Imported students are appended to the existing ranking with `is_supplementary = True`
- Each ranking belongs to one college (via `creator.college_code`); the upload endpoint rejects students whose SIS `std_academyno` doesn't match
- Admin manually assigns `sub_type` / `allocation_year` to new students, then runs finalize again
- Finalize logic is updated: unallocated supplementary students stay as `status = 'ranked'` (not rejected)

---

## Schema Changes

### `scholarship_configurations` table

```python
# Admin toggle, scoped to one (scholarship_type, academic_year, semester) configuration —
# applies to all colleges' rankings under that config.
allow_supplementary_import = Column(Boolean, default=False, nullable=False, server_default="false")
```

### `college_ranking_items` table

```python
# Per-item flag set on rows appended via the supplementary import flow.
is_supplementary = Column(Boolean, default=False, nullable=False, server_default="false")
```

### Migration

`add_supplementary_import_001` adds the two columns above with existence checks, and also drops a legacy `college_rankings.allow_supplementary_import` column if it exists (earlier prototype that stored the flag per-ranking).

---

## Data Flow: Excel Column → Storage

| Excel Column | Content | Stored In |
|---|---|---|
| Col 2 | 學院初審會議之學院排序 | `CollegeRankingItem.rank_position` (offset by max existing) |
| Col 3 | 申請獎學金類別 | `Application.sub_type_preferences` (parsed via label→code map) |
| Col 13 | 學號 → SIS API | `Application.student_data` |
| Col 15 | 學生匯款帳號 | `UserProfile.account_number` |
| Col 18 | 指導教授姓名 | `UserProfile.advisor_name` |
| Col 19+ | Dynamic form fields | `Application.submitted_form_data.fields` |

Columns 4–14, 16–17 (other static fields) are not read from Excel — all come from SIS API response.

---

## `申請獎學金類別` Parsing

The export format serializes `sub_type_preferences` as:

- Single preference: `"XXX"`
- Dual preference: `"XXX(第一志願)暨YYY(第二志願)"`

On import, build a reverse lookup table from `ScholarshipSubTypeConfig`:

```python
label_to_code: Dict[str, str] = {
    config.name: config.sub_type_code
    for config in scholarship_type.sub_type_configs
}
```

Parse column 3 using this map. If any label cannot be mapped to a code, return 422 with the offending rows.

---

## `rank_position` Assignment

```
new_rank_position = max(existing_rank_positions) + excel_col2_value
```

Excel column 2 values must be consecutive positive integers starting from 1 (same validation as existing `import-excel`).

---

## Application & User Creation

For each imported student:

1. Call NYCU SIS API with student ID → `student_data`
2. Query `users` table by student ID; auto-create `User(role=student)` using SIS email if not found
3. Create `Application` with:
   - `status = 'pending'`
   - `scholarship_type_id`, `academic_year`, `semester` from ranking
   - `student_data` from SIS API
   - `sub_type_preferences` parsed from col 3
   - `submitted_form_data.fields` from col 19+
4. Create `UserProfile` with `account_number` (col 15), `advisor_name` (col 18)
5. Create `CollegeRankingItem` with `is_supplementary = True`, `status = 'ranked'`

All operations are batched: full rollback if any step fails.

---

## Validation Rules

| Condition | Response |
|---|---|
| Ranking not found | 404 |
| `allow_supplementary_import = False` | 403 |
| Student already has application for same scholarship/year/semester | 422, list conflicting student IDs |
| SIS API returns no data for student ID | 422, list missing student IDs |
| Duplicate student IDs in import file | 422 |
| Column 2 values not consecutive positive integers | 422 |
| Column 3 value cannot be mapped to a sub_type code | 422, list offending rows |

---

## API Endpoints

### Admin Toggle (per scholarship configuration)

```
PATCH /api/v1/scholarship-configurations/configurations/{configuration_id}/supplementary-import
Auth: require_admin
Body: { "allow": bool }
Response: { "id": int, "allow_supplementary_import": bool }
```

Lives in `backend/app/api/v1/endpoints/scholarship_configurations.py`.

### College Supplementary Import (per ranking)

```
POST /api/v1/college-review/rankings/{ranking_id}/supplementary-import
Auth: require_college (rejects non-college roles)
Content-Type: multipart/form-data (Excel .xlsx file, ≤10 MB)
Guards:
  - Configuration flag `allow_supplementary_import` must be true (403)
  - Ranking creator's college_code must match current_user.college_code (403)
  - Each student's SIS std_academyno must match the ranking's college (422)
  - No duplicate (student × scholarship × academic_year × semester) (422)
Response: {
  "ranking_id": int,
  "imported_count": int,
  "max_existing_rank": int,
  "new_rank_range": str
}
```

Lives in `backend/app/api/v1/endpoints/college_review/ranking_management.py`.

---

## Finalize Logic Change

File: `backend/app/services/manual_distribution_service.py`

Current behavior: unallocated items → `Application.status = 'rejected'`

New behavior:

```python
if item.is_supplementary and not item.is_allocated:
    # Supplementary student not yet allocated — leave as 'ranked', do not reject
    pass
else:
    # Existing logic unchanged
```

This allows admin to run finalize multiple times. Each run approves only the currently-allocated items without rejecting unallocated supplementary students.

---

## Service Module

New file: `backend/app/services/supplementary_import_service.py`

Responsibilities:
1. `parse_excel(file_bytes, ranking, dynamic_fields) → List[RowData] | ValidationErrors`
2. `validate_no_duplicate_applications(rows, scholarship_type_id, academic_year, semester) → errors`
3. `fetch_student_data_bulk(student_ids) → Dict[str, dict] | missing_ids`
4. `find_or_create_users(student_data_map) → Dict[str, User]`
5. `create_applications_and_items(rows, users, ranking) → ImportResult`

---

## Frontend

### Admin Side (`ManualDistributionPanel.tsx` or ranking card)

- Toggle control: `allow_supplementary_import` on/off per ranking
- Calls `PATCH /college-review/rankings/{id}/supplementary-import`
- When enabled: shows hint "學院可匯入新學生，排名將接在現有 N 人之後"

### College Side (`CollegeManagementShell.tsx` ranking detail)

- "補充匯入" button visible only when `allow_supplementary_import = true`
- Upload flow: drag-and-drop Excel → preview parsed rows (student ID, name, rank) → confirm → POST
- Success: "已匯入 N 人，排名 {max+1} ~ {max+N}"
- Error: per-row error display (duplicate, SIS not found, etc.)

### Distribution Panel (Admin)

- `is_supplementary = true` items display a `[補充]` tag
- Visual separator between regular and supplementary students
- All distribution actions (sub_type / allocation_year assignment) identical to regular students

---

## Files Affected

| File | Change |
|---|---|
| `backend/app/models/college_review.py` | Add `allow_supplementary_import`, `is_supplementary` columns |
| `backend/alembic/versions/xxx_add_supplementary_import.py` | New migration |
| `backend/app/services/supplementary_import_service.py` | New service |
| `backend/app/services/manual_distribution_service.py` | Finalize logic patch |
| `backend/app/api/v1/endpoints/college_review/ranking_management.py` | Two new endpoints |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Admin toggle |
| `frontend/components/college/CollegeManagementShell.tsx` | Import button + upload flow |
| `frontend/components/admin/manual-distribution/` (distribution table) | `[補充]` tag + visual separator |
| `frontend/lib/api/modules/college-review.ts` | New API calls |
