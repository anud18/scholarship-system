# 學院匯出排名 — PDF Format Support

**Date:** 2026-07-01
**Status:** Approved (design decisions locked via brainstorming)

## Goal

Add a PDF output option to the college ranking export ("學院匯出排名"). Today the
`匯出` button produces only an `.xlsx` 學生資料彙整表 via openpyxl. We add a PDF
variant that mirrors the Excel **exactly** — same columns (including PII), same
rows, same ordering — rendered as a wide **A4-landscape** table.

## Locked decisions

| Decision | Choice |
|---|---|
| Scope | **Ranking export only** (`export-excel` endpoint / the `匯出` button). 申請總表, bulk, and the fill-in template stay Excel-only. |
| PDF layout | **Wide landscape table, full Excel parity** — every static + dynamic column, including PII (身分證字號, 匯款帳號). |
| Page size | **A4 landscape**, small font with cell wrapping; column widths normalized to page width. |
| UI control | **Dropdown** on the existing `匯出` button → `匯出 Excel` / `匯出 PDF`. |

## Current state (verified)

- Button: `frontend/components/college-ranking-table.tsx:901` → `handleExportRanking` → `exportRankingExcel(rankingId)`.
- API module: `frontend/lib/api/modules/college.ts` `exportRankingExcel()` → `GET /api/v1/college-review/rankings/{id}/export-excel`.
- Endpoint: `backend/app/api/v1/endpoints/college_review/ranking_management.py` `export_ranking_excel` (line ~1174). Loads the ranking + items, builds `ExportRow`s, calls the service, writes a `pii_access` `AuditLog` (the sheet carries plaintext `std_pid`), returns a `StreamingResponse`.
- Renderer: `backend/app/services/college_ranking_export_service.py` `CollegeRankingExportService.build_workbook()` (openpyxl). Columns = `STATIC_HEADERS` (18) + dynamic fields. Per-cell value logic lives in pure helpers (`_render_gender`, `_render_direct_phd`, `_compute_grade`, `_render_enrollment_date`, `_render_scholarship_type`, `_extract_dynamic_value`).
- Existing PDF infra: `reportlab==4.4.10` is a dependency; `backend/app/services/export_package_service.py` already registers the WQY CJK font (`/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`) and builds PDFs via `SimpleDocTemplate`/`Table`.

## Architecture

### 1. Shared CJK-font module — `backend/app/services/pdf_fonts.py` (new)

The WQY font registration currently lives privately inside
`export_package_service.py` (`CJK_FONT_PATH`, `_font_registered`, `_ensure_font`).
Extract it into a tiny shared module:

```python
CJK_FONT_NAME = "WQY"
CJK_FONT_PATH = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"

def ensure_cjk_font() -> None:
    """Idempotently register the WQY CJK font for reportlab."""
```

- **Why a new module, not import from `export_package_service`:** that would create
  an import cycle — `export_package_service → export_summary_tables →
  college_ranking_export_service`, and the new `build_pdf` lives in
  `college_ranking_export_service`. A leaf module breaks the cycle and is DRY.
- `export_package_service.py` is refactored to import `ensure_cjk_font` /
  `CJK_FONT_NAME` from this module (its local copies removed). Its one call site
  (`ExportPackageService.__init__`) and PDF styles (`fontName="WQY"`) keep working.

### 2. `CollegeRankingExportService` — add `build_pdf()`

- Refactor the column-value logic into one shared, single-sourced pair:
  - `_headers(sorted_dynamic) -> list[str]` — `STATIC_HEADERS + dynamic labels`.
  - `_row_cells(row, row_index, sub_type_labels, sorted_dynamic) -> list` — the
    ordered list of cell values for one `ExportRow` (NO. + 17 static via the
    existing pure helpers + dynamic values).
- `build_workbook` is refactored to write cells from `_row_cells` / `_headers`
  (same output as today — the pure helpers are unchanged, so
  `test_college_ranking_export_pure_helpers.py` and `test_ranking_export_template.py`
  still pass).
- New `build_pdf(*, rows, dynamic_fields, sub_type_labels, title) -> bytes`:
  - `ensure_cjk_font()`; `SimpleDocTemplate(buf, pagesize=landscape(A4), margins≈10mm)`.
  - Title `Paragraph` (centered, WQY).
  - `Table(data, colWidths=widths, repeatRows=1)` where `data[0]` = header
    `Paragraph`s and each subsequent row = cell `Paragraph`s (WQY, ~6pt, wrap).
  - **Column widths normalized to usable width:** per-column weights (narrow:
    NO./排序/年級/性別/逕博; wide: 中文姓名/英文姓名/E-mail/通訊地址/指導教授/dynamic),
    `width_i = usable_width * weight_i / Σweights`. Guarantees no horizontal
    overflow — content wraps within cells; rows paginate vertically with the
    header repeated each page.
  - `TableStyle`: thin grid, light-grey header fill, `VALIGN TOP`, small padding,
    `FONTNAME WQY` fallback.

### 3. Endpoint `export_ranking_excel`

- Add query param `format: Literal["xlsx", "pdf"] = "xlsx"`.
- Branch on `format`:
  - `xlsx` (default): unchanged — `build_workbook`, xlsx media type, `.xlsx` name.
  - `pdf`: `build_pdf`, `media_type="application/pdf"`, `.pdf` filename.
- Reject `template=true & format=pdf` → HTTP 400 (`範本僅支援 Excel 格式`): a PDF
  cannot be filled in and re-imported, so the combination is meaningless.
- **PII audit unchanged for both formats** — the PDF still contains plaintext
  `std_pid`, so the same `pii_access` `AuditLog` is written;
  `meta_data.export_format` reflects `"pdf"` / `"xlsx"`.

### 4. Frontend — `college.ts`

Generalize:

```ts
export async function exportRankingExcel(
  rankingId: number,
  format: "xlsx" | "pdf" = "xlsx",
): Promise<{ blob: Blob; filename: string }>
```

Add the `format` query param and a format-appropriate fallback filename. Keep the
exported name (callers unchanged except passing a format). `downloadRankingTemplate`
stays xlsx.

### 5. Frontend — `college-ranking-table.tsx`

Replace the single `匯出` Button with the existing shadcn `DropdownMenu`
(`@/components/ui/dropdown-menu`, already used in `payment-roster-list.tsx` etc.):

- Trigger: `匯出 ▾` (outline, size sm, Download icon).
- Items: `匯出 Excel` → `handleExportRanking("xlsx")`, `匯出 PDF` →
  `handleExportRanking("pdf")`.
- `handleExportRanking(format)` passes the format through to `exportRankingExcel`.

### 6. OpenAPI types

Regenerate `frontend/lib/api/generated/schema.d.ts` (new `format` query param),
per CLAUDE.md §8.

## Testing

- **Service (pure/unit):** `build_pdf` returns bytes starting with `%PDF` and of
  non-trivial size; header/`_row_cells` parity with the xlsx path. New file
  `backend/app/tests/test_college_ranking_export_pdf.py`.
- **Endpoint (integration):** mirror `test_ranking_export_template.py`:
  - `format=pdf` → 200, `content-type: application/pdf`, `Content-Disposition`
    filename ends `.pdf`, body starts `%PDF`.
  - audit row present with `meta_data.export_format == "pdf"`.
  - `template=true & format=pdf` → 400.
  - default (no format) still returns xlsx with rank filled (regression).

## Error handling

- Unsupported `format` value → FastAPI 422 (via `Literal`).
- Font file missing at render time → reportlab raises; surfaces as 500 (same as
  the existing export-package PDF path; the font ships in the backend image).
- PDF render must not silently fall back to xlsx — fail loudly per project policy.

## Out of scope

申請總表 (`department-summary-export[-bulk]`), the fill-in template, and any bulk
ZIP export remain Excel-only.
