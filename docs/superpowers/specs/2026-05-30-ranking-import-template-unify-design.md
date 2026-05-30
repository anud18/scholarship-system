# Ranking Import / Template Unification on the 學生資料彙整表 Format

**Date:** 2026-05-30
**Status:** Approved (design) — pending implementation plan
**Area:** College ranking (學員排名) Excel import + template download

## Problem

The college-ranking screen has three Excel touch-points that currently use **two
different formats**:

| Action | Endpoint / code | Format today |
|---|---|---|
| 匯出 (export) | `GET /college-review/rankings/{id}/export-excel` → `CollegeRankingExportService` | Full **學生資料彙整表**: row 1 merged title, row 2 = 18 static headers + dynamic field columns, rank filled in col 2 |
| 下載範本 (template) | `handleTemplateDownload` (client-side `XLSX.json_to_sheet`) | Slim **4-col** file: `學號 / 姓名 / 系所 / 排名`(blank) |
| 匯入 (import) | `handleFileUpload` parser → `POST /import-excel` | Reads `學號` + `排名` from a single-header sheet |

The user wants **one canonical format** — the 學生資料彙整表 export format — used by
all three. The template is simply the export with the **rank column left blank**
for the college to fill in. The import parser must read that same export format.

## Goal

- **Template** = export-format workbook with col 2 `學院初審會議之學院排序` blank, every
  other column (incl. PII + dynamic fields) filled. Backend-generated so it stays
  in lockstep with the real export columns.
- **Import parser** reads the export format: skip the merged title row, take `學號`
  (match key), `學院初審會議之學院排序` (rank), `學生中文姓名` (display/required).
- Drop the legacy 4-column template + `排名` header parsing (project policy:
  **no backward compatibility**).

## Verified codebase facts (adversarial pass, 2026-05-30)

All seven claims below were independently verified against the worktree:

1. **Auth** — `require_scholarship_manager` (`backend/app/core/security.py:135-139`)
   admits `admin / super_admin / college`. The template reuses `export-excel`, so it
   inherits that dependency plus the endpoint's three inner gates (college_code
   matches ranking creator's college_code; AdminScholarship grant on the
   scholarship_type; active ScholarshipConfiguration for the academic_year). **No
   new auth code.**
2. **Blank rank** — `college_ranking_export_service.py:126-130` is the *sole* writer
   of col 2: `value=(row.rank_position if row.rank_position is not None else "")`.
   `rank_position=None` ⇒ empty string; nothing else derives the rank. (Confirmed by
   the existing `application_summary_export.py`, which already passes
   `rank_position=None` to get a blank ranking column.)
3. **Header strings** (`STATIC_HEADERS`, indices 0-17): index **1** =
   `學院初審會議之學院排序` (rank, col 2), index **7** = `學生中文姓名` (col 8), index
   **12** = `學號` (col 13). These are the join + read columns.
4. **xlsx semantics** — SheetJS `0.20.3` (pinned in `frontend/package.json:96`).
   `XLSX.utils.sheet_to_json(ws, { range: 1 })` ⇒ Excel **row 2** is the header row,
   data from **row 3**. Caveat: **do not** also pass a `header` option, or the
   numeric `range` row is treated as data. (`node_modules/xlsx` is not installed in
   this worktree — tests run in the dev/CI container after `npm install`.)
5. **Single owner** — the 4-col template + `排名` parser live *only* in
   `college-ranking-table.tsx` (`handleTemplateDownload` :728, `handleFileUpload`
   :569), wired only at :960 / :980, consumed only by `RankingManagementPanel`'s
   `handleImportExcel`, which forwards a JSON array. No other consumer.
6. **import-excel stays JSON** — `POST /import-excel` takes
   `List[RankingImportItem]` (JSON body, not multipart); it parses no Excel headers.
   So the frontend parser change does **not** touch the endpoint, and the existing
   `frontend/e2e/specs/college-ranking-import-excel.spec.ts` (which POSTs JSON
   directly) + `college.test.ts` importRankingExcel body-shape test stay green.
7. **`student_name` is required** — `RankingImportItem` (`schemas/college_review.py:140-141`)
   declares `student_id`, `student_name`, `rank_position` all with `Field(...)`.
   The parser **must keep sending `student_name`** → read it from `學生中文姓名`.

The server-side supplementary-import parser
(`supplementary_import_service.py`, `_COL_RANK=2`, `_COL_STUDENT_ID=13`,
`_STATIC_COL_COUNT=18`, "row 1 = title, row 2 = headers, row 3+ = data") already
reads this exact layout — the new frontend parser aligns to it.

## Design

### Backend — `export_ranking_excel` (`ranking_management.py:1123`)

Add a query flag; no new endpoint, no service change.

```python
@router.get("/rankings/{ranking_id}/export-excel")
async def export_ranking_excel(
    ranking_id: int,
    request: Request,
    template: bool = Query(False, description="Render rank column blank as an import template"),
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
    ...
    export_rows = [
        ExportRow(
            rank_position=None if template else item.rank_position,
            application=item.application,
            bank_account=account_number_by_user.get(item.application.user_id),
            advisor_names=advisor_string_by_user.get(item.application.user_id),
        )
        for item in items_sorted
        if item.application is not None
    ]
```

- When `template=True`: every row's `rank_position=None` ⇒ col 2 blank (service
  renders `None` → `""`). All other columns unchanged.
- **Filename** gains a `_範本` suffix:
  `{year}學年度{name}學生資料彙整表_{college}_範本.xlsx`.
- **Audit** — the template still contains plaintext `std_pid` and other PII, so the
  existing `pii_access` audit log is preserved; the description notes it is a
  template download.
- Everything else (auth gates, aux-data loading, `build_workbook`) is untouched.

### Frontend API — `lib/api/modules/college.ts`

New function mirroring `exportRankingExcel`, using the shared
`_fetchBinaryExport(path, params, fallbackFilename, errorFallback)` helper:

```ts
export async function downloadRankingTemplate(
  rankingId: number
): Promise<{ blob: Blob; filename: string }> {
  const params = new URLSearchParams();
  params.set("template", "true");
  return _fetchBinaryExport(
    `/api/v1/college-review/rankings/${rankingId}/export-excel`,
    params,
    `學生資料彙整表_${rankingId}_範本.xlsx`,
    "無法下載範本"
  );
}
```

### Frontend component — `college-ranking-table.tsx`

**`handleTemplateDownload`** — replace the client-side `json_to_sheet` builder with a
backend blob download (mirror `handleExportRanking` at :773):

```ts
const handleTemplateDownload = async () => {
  if (!rankingId) { toast.error("缺少排名 ID，無法下載範本"); return; }
  try {
    const { blob, filename } = await downloadRankingTemplate(rankingId);
    // ...createObjectURL → anchor click → revoke (same as handleExportRanking)
    toast.success(`已下載範本檔案：${filename}`);
  } catch (error) {
    logger.error("Template download error", { error });
    toast.error(error instanceof Error ? error.message : "無法產生範本檔案");
  }
};
```

(The old dept-sort + 4-col `templateData` block and its `!cols` widths are removed.)

**`handleFileUpload`** — parse the 彙整表 layout:

```ts
const jsonData = XLSX.utils.sheet_to_json(worksheet, { range: 1 }); // skip title row; row 2 = header
...
const studentId   = String(row["學號"] || "").trim();
const studentName  = String(row["學生中文姓名"] || "").trim();
const rawRank      = row["學院初審會議之學院排序"];
```

- Drop the legacy `row["排名"] / row["student_id"] / row["姓名"] / row["rank"]`
  fallbacks.
- Empty-`學號` rows are skipped (covers blank trailing rows + the freeze-pane area).
- All existing validation stays: `"N"` (case-insensitive) → rejected;
  positive-integer ranks; no duplicate 學號; no duplicate ranks; consecutive from 1;
  ≥1 valid row.
- `importData` shape `{ student_id, student_name, rank_position }` and the
  `onImportExcel` call are unchanged ⇒ `POST /import-excel` JSON contract intact.

### Data flow

```
下載範本 (export-excel?template=true, rank col blank, PII+dynamic filled)
  → college fills col 2 「學院初審會議之學院排序」 with int / N
  → 匯入 (handleFileUpload: sheet_to_json range:1, read 學號 + rank + 學生中文姓名)
  → onImportExcel → POST /import-excel  [JSON: {student_id, student_name, rank_position}]
  → backend matches std_stdcode (exact set), consecutive ranks, N → college_rejected
```

## Edge cases / non-goals

- **Old 4-col template files stop importing.** They lack `學院初審會議之學院排序`, so
  every row errors "rank empty". Acceptable per no-backward-compat; users
  re-download the new template. (Already acknowledged in the prior review doc.)
- **Re-importing an unmodified export** (ranks pre-filled as integers) works, but
  college-rejected students re-import as ranked because the export prints their
  rejected position as an integer, not `N`. Out of scope — the blank-rank template
  is the intended path; flag only.
- **`None` renders as `""`, not a truly empty cell.** Irrelevant to import (we
  read/skip empty), and visually blank. No action.
- The import-excel endpoint, `RankingImportItem` schema, and supplementary-import
  path are **not** modified.

## Testing

- **Backend** (`backend/app/tests/`): new case on `export_ranking_excel` —
  `template=true` ⇒ col 2 (`學院初審會議之學院排序`) blank for all data rows, row-2
  headers identical to the normal export, filename contains `範本`; `template=false`
  (default) unchanged. Existing `test_college_ranking_export_service.py` header/title
  assertions must stay green (we don't reword headers).
- **Frontend** (new — component currently has zero tests): a parser unit test that
  builds a 彙整表-shaped sheet (title row 1, the 18 headers on row 2, data row 3+)
  and asserts `handleFileUpload` extracts the right `{student_id, student_name,
  rank_position}` for integer ranks, `"N"`, and that blank-rank / empty-學號 rows are
  handled per the validation rules. Add `downloadRankingTemplate` to
  `college.test.ts` (params include `template=true`, filename fallback `_範本`).
- **Unchanged / must stay green:** `college-ranking-import-excel.spec.ts` (JSON
  POST), `college.test.ts` importRankingExcel body-shape, supplementary-import tests.

## Touched files

- `backend/app/api/v1/endpoints/college_review/ranking_management.py` — `template`
  query param + filename/audit tweak on `export_ranking_excel`.
- `frontend/lib/api/modules/college.ts` — add `downloadRankingTemplate`.
- `frontend/components/college-ranking-table.tsx` — rewrite `handleTemplateDownload`
  (backend blob) + `handleFileUpload` (彙整表 parser).
- Tests: backend export-template case; new frontend parser test + `college.test.ts`
  addition.
