# College Ranking Excel Export — 學生資料彙整表

**Date:** 2026-05-08
**Status:** Approved
**Reference sample:** `docs/samples/114年博士生獎學金學生資料彙整表.xlsx`

## Goal

Replace the existing frontend-driven 9-column college ranking Excel export with a backend-generated 「學生資料彙整表」 modeled after the sample workbook (`114年博士生獎學金學生資料彙整表.xlsx`). The new export combines hardcoded static columns sourced from `student_data` / `CollegeRankingItem` with admin-configurable dynamic columns sourced from each application's `submitted_form_data`.

Admins gain a new option on dynamic application fields:「顯示於學院匯出 Excel」(plus an optional override label), so columns like 碩士畢業學校 and 學生手機 can be surfaced in the workbook without code changes.

## Non-goals

- Recreating the exact column ordering of the sample file. Static columns are written in a fixed order; dynamic columns are appended at the end ordered by `display_order`.
- Making non-text dynamic fields (NUMBER, SELECT, FILE, …) exportable. Only `field_type='text'` may be flagged.
- Supporting multiple Excel templates per scholarship type. One layout serves all scholarship types.

## Background

- Existing college ranking export lives in `frontend/components/college-ranking-table.tsx:742-808`, generates a 9-column workbook in-browser via `xlsx`, and lacks fields like 碩士畢業學校, 註冊入學日期, 指導教授姓名.
- `ApplicationField` (`backend/app/models/application_field.py:27-77`) drives dynamic fields per scholarship type. It has no flag for inclusion in any export.
- `Application.sub_type_preferences` (JSON ordered list, e.g. `["nstc", "moe_1w"]`) and `sub_type_selection_mode` already encode 志願順序, so the sample's "1./2./3./4." 申請獎學金類別 column can be derived without new data.
- Payment roster export (`backend/app/services/excel_export_service.py`) is the reference pattern for backend Excel generation but serves a different purpose; the new export gets its own service to keep responsibilities clean.

## Data model changes

Add two columns to `application_fields`:

| Column | Type | Default | Notes |
|---|---|---|---|
| `include_in_college_export` | BOOLEAN NOT NULL | `false` | When true, this field appears in the college Excel export. |
| `export_column_label` | VARCHAR(200) NULL | NULL | Optional override for the Excel column header; falls back to `field_label`. |

**Validation rule** (Pydantic `model_validator` on `ApplicationFieldCreate` / `ApplicationFieldUpdate`):
- `include_in_college_export=True` requires `field_type == 'text'`. Any other type raises `ValueError("include_in_college_export 僅支援 field_type='text'")`.

**Migration** — new Alembic revision `add_college_export_flag_to_application_field`. Idempotent guard pattern per CLAUDE.md:

```python
def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    cols = [c['name'] for c in inspector.get_columns('application_fields')]
    if 'include_in_college_export' not in cols:
        op.add_column(
            'application_fields',
            sa.Column('include_in_college_export', sa.Boolean(),
                      nullable=False, server_default='false'),
        )
    if 'export_column_label' not in cols:
        op.add_column(
            'application_fields',
            sa.Column('export_column_label', sa.String(200), nullable=True),
        )

def downgrade():
    op.drop_column('application_fields', 'export_column_label')
    op.drop_column('application_fields', 'include_in_college_export')
```

## Excel structure

**Workbook title:** `{academic_year}學年度{scholarship_name}學生資料彙整表`
(e.g. `114學年度博士生獎學金學生資料彙整表`)

**Sheet name:** `{academic_year}學年`

**Static columns** (hardcoded, in order, applies to every scholarship type):

| # | Header | Source |
|---|---|---|
| 1 | NO. | row index (1-based) |
| 2 | 學院初審會議之學院排序 | `CollegeRankingItem.final_rank` ?? `preliminary_rank` ?? `""` |
| 3 | 申請獎學金類別 | rendered from `application.sub_type_preferences` (see below) |
| 4 | 學院 | `student_data.trm_academyname` |
| 5 | 系所 | `student_data.trm_depname` |
| 6 | 年級 | `((trm_termcount or 0) + 1) // 2`; empty when `trm_termcount` is None |
| 7 | 學生中文姓名 | `student_data.std_cname` |
| 8 | 學生英文姓名 | `student_data.std_ename` |
| 9 | 國籍 | `student_data.std_nation` |
| 10 | 性別 | `1→"男"`, `2→"女"`, otherwise `""` |
| 11 | 註冊入學日期 | `f"{std_enrollyear}.{9 if std_enrollterm==1 else 2}.1"`; empty when `std_enrollyear` is None |
| 12 | 學號 | `student_data.std_stdcode` |
| 13 | 學生身分證字號 | `student_data.std_pid` |
| 14 | 學生 E-mail | `student_data.com_email` |

**Dynamic columns** (appended after column 14):

Filter:
```python
ApplicationField.scholarship_type == ranking.scholarship_type
AND include_in_college_export == True
AND is_active == True
AND field_type == 'text'
```
Order by `display_order ASC`.

- Header text: `field.export_column_label or field.field_label`
- Cell value: `str(submitted_form_data["fields"][field.field_name]["value"] or "")`. Missing key → empty cell. Never raises.

**申請獎學金類別 rendering rule**:

```
prefs = application.sub_type_preferences or []
labels = lookup ScholarshipSubTypeConfig.name for each code in prefs

if len(prefs) == 0:
    fallback = sub_type_label_for(application.sub_scholarship_type) or application.sub_scholarship_type
    return fallback or ""
elif len(prefs) == 1:
    return labels[0]
else:
    return f"{labels[0]}(第一志願)暨{labels[1]}(第二志願)"
```

Sub-type Chinese labels come from `ScholarshipSubTypeConfig.name` keyed by `sub_type_code`. Unknown codes fall back to the raw code string (matches the convention used by `manual_distribution_service._sub_type_to_chinese`).

**Workbook formatting:**
- Header row bold, centred, light-grey fill
- All cells thin border
- Column widths derived from heading text length (min 10, max 30)
- Freeze panes at row 2

## API

`GET /api/v1/college-review/rankings/{ranking_id}/export-excel`

- **Auth:** admin OR a college user whose `college_code` matches the ranking's college (uses the existing dependency that protects other ranking endpoints in `backend/app/api/v1/endpoints/college_review/`).
- **Response:** binary stream with
  - `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `Content-Disposition: attachment; filename*=UTF-8''<url-encoded filename>`
- **Filename:** `{academic_year}學年度{scholarship_name}學生資料彙整表_{college_name}.xlsx`
- **Why this is exempt from ApiResponse standardization:** binary downloads are not JSON. `payment_rosters` already follows this exception pattern.

**Backend flow:**
1. Load `CollegeRanking` + items with `selectinload(application)`.
2. Load `ApplicationField`s matching the filter above, ordered by `display_order`.
3. Load relevant `ScholarshipSubTypeConfig` rows for the ranking's `scholarship_type` to build the sub-type label map.
4. Hand the prepared payload to `CollegeRankingExcelExportService.build_workbook(...)` (new module: `backend/app/services/college_ranking_export_service.py`).
5. Stream `openpyxl` workbook bytes back through FastAPI's `StreamingResponse`.

**Frontend:**

- Replace `handleExport` in `frontend/components/college-ranking-table.tsx` to download the new endpoint via `fetch + blob + URL.createObjectURL` (auth header required, so a plain `<a href>` will not work).
- Add `exportRankingExcel(rankingId)` helper in `frontend/lib/api/modules/college-review.ts`.
- Remove the `xlsx` import from `college-ranking-table.tsx` if no other call sites remain after the migration.
- Run `npm run api:generate` to refresh `lib/api/generated/schema.d.ts`.

## Admin UI

**Edit form** (`frontend/components/application-field-form.tsx`):

- Show `☐ 顯示於學院匯出 Excel` checkbox **only when** `field_type === 'text'`.
- When checked, reveal an optional input `學院匯出顯示名稱` with `maxLength=200`. Placeholder shows the current `field_label`. Empty value is stored as NULL.
- Switching `field_type` to anything other than `text` resets `include_in_college_export` to `false` and clears `export_column_label`. Inline warning: `變更類型會關閉學院匯出設定`.

**List view** (if `application-fields-list.tsx` or equivalent table exists): add a `學院匯出` column showing ✓ / ✗.

**Schema sync:**
- `ApplicationFieldCreate` / `ApplicationFieldUpdate` / `ApplicationFieldResponse` all gain the two new optional fields.
- Pydantic `model_validator` enforces the text-only rule.
- Regenerate OpenAPI types after backend changes land.

## Error handling

- `ranking_id` not found → `HTTPException(404, "找不到該學院排序資料")`.
- Unauthorized college user → `HTTPException(403, "無權限匯出此學院之資料")`.
- Empty ranking (no items) → still produce a valid workbook with header row only. Do NOT 500.
- Missing `submitted_form_data` keys, missing `student_data` fields, None `trm_termcount`, etc. → render empty string in cell. **Never** swallow load-time failures (DB errors still raise per CLAUDE.md guidance).
- Invalid validator combination (e.g. non-text field flagged for export) → 422 from Pydantic.

## Testing

**Backend** (`backend/tests/`):

- `test_college_ranking_export_service.py`
  - 14 static columns map correctly from a fully populated `student_data` snapshot
  - Dynamic field filter respects `include_in_college_export`, `is_active`, `field_type='text'`
  - Dynamic column ordering follows `display_order`
  - `export_column_label` overrides `field_label`
  - `sub_type_preferences` rendering for 0 / 1 / 2 entries and unknown codes
  - Rank precedence: `final_rank` wins over `preliminary_rank`; both None → `""`
  - Gender: `1→男`, `2→女`, `0→""`, `None→""`
  - Grade: `trm_termcount=None→""`, `0→""`, `1→1`, `5→3`, `8→4`
  - Enrollment date: `(110, 1)→"110.9.1"`, `(110, 2)→"110.2.1"`, `(None, _)→""`

- `test_application_field_export_validation.py`
  - `{field_type='number', include_in_college_export=True}` → ValueError
  - `{field_type='text', include_in_college_export=True}` → OK
  - `{field_type='text', include_in_college_export=False, export_column_label='X'}` → OK (no constraint on label without flag)

- `test_college_ranking_export_endpoint.py`
  - 200 + non-empty bytes for happy path
  - 403 for college user from a different college
  - 404 for nonexistent ranking
  - Empty ranking → 200 with workbook containing only header row

**Frontend:**
- Unit test on `application-field-form.tsx`: switching field type clears the export flag and label.
- E2E (Playwright) on the college ranking page: clicking 「下載學院匯出 Excel」 triggers a file download with the expected filename pattern.

## Migration & rollout

1. Alembic migration adds the two columns (idempotent guards in place).
2. Backend service + endpoint shipped; existing frontend export keeps working until the swap.
3. Frontend swap to new endpoint, remove `xlsx`-based logic, regen OpenAPI types.
4. Admin UI changes ship together with the schema changes.
5. No data backfill needed — every field defaults to `include_in_college_export=false`, so the new export starts with only the static 14 columns until admins opt fields in.

## Files changed (anticipated)

**New:**
- `backend/alembic/versions/{hash}_add_college_export_flag_to_application_field.py`
- `backend/app/services/college_ranking_export_service.py`
- `backend/tests/test_college_ranking_export_service.py`
- `backend/tests/test_application_field_export_validation.py`
- `backend/tests/test_college_ranking_export_endpoint.py`

**Modified:**
- `backend/app/models/application_field.py`
- `backend/app/schemas/application_field.py`
- `backend/app/api/v1/endpoints/college_review/ranking_management.py` (add export endpoint)
- `frontend/components/application-field-form.tsx`
- `frontend/components/college-ranking-table.tsx`
- `frontend/lib/api/modules/college-review.ts`
- `frontend/lib/api/generated/schema.d.ts` (regenerated)

## Open questions / decisions deferred

- Whether to also add an `export_column_order` integer was declined (YAGNI; `display_order` suffices for the agreed "appended after static columns" layout).
- Whether the new export should also be reachable from the admin master ranking list (out of scope; the user only asked for the per-college ranking page).
