# Ranking Import / Template Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the college-ranking 下載範本 (template) and 匯入 (import) both use the 學生資料彙整表 export format — template = export with the rank column blank, import parser reads that same format.

**Architecture:** Backend adds a `template=true` flag to the existing `export-excel` endpoint that renders the rank column blank (the export service already maps `rank_position=None → ""`). Frontend gets a `downloadRankingTemplate` API helper, rewrites the template button to download that backend blob, and replaces the bespoke 4-column Excel parser with one that reads the 彙整表 layout via an extracted, unit-tested pure function.

**Tech Stack:** FastAPI + openpyxl (backend), Next.js/React + SheetJS `xlsx@0.20.3` + Jest (frontend), pytest + httpx AsyncClient (backend tests).

**Spec:** `docs/superpowers/specs/2026-05-30-ranking-import-template-unify-design.md`
**Branch:** `feat/ranking-import-template-unify` (already checked out)

---

## File structure

| File | Responsibility | Change |
|---|---|---|
| `backend/app/api/v1/endpoints/college_review/ranking_management.py` | `export_ranking_excel` endpoint | Add `template: bool` query param → blank rank + `_範本` filename |
| `backend/app/tests/test_ranking_export_template.py` | Integration test for the template flag | **Create** |
| `frontend/lib/ranking/parse-ranking-sheet.ts` | Pure parser: 彙整表 row-objects → `{importData, errors}` + `ExcelRankingImportRow` type | **Create** |
| `frontend/lib/ranking/__tests__/parse-ranking-sheet.test.ts` | Unit tests for the pure parser | **Create** |
| `frontend/lib/api/modules/college.ts` | `downloadRankingTemplate` API helper | Add function |
| `frontend/lib/api/modules/__tests__/college.test.ts` | API helper test | Add test |
| `frontend/components/college-ranking-table.tsx` | Ranking table UI | Rewrite `handleFileUpload` (use parser) + `handleTemplateDownload` (backend blob); import the extracted type |

**Out of scope / DO NOT TOUCH:** `POST /import-excel` endpoint, `RankingImportItem` schema (`student_name` stays **required** — the parser must keep sending it), `CollegeRankingExportService`, the supplementary-import path, `frontend/e2e/specs/college-ranking-import-excel.spec.ts` (posts JSON directly — stays green).

---

## Task 1: Backend `template` query param on `export-excel`

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/ranking_management.py` (`export_ranking_excel`, signature at `:1123-1128`; `export_rows` at `:1174-1183`; filename at `:1199-1200`; audit description at `:1222-1224`)
- Test: `backend/app/tests/test_ranking_export_template.py` (create)

> Note: `Query` is already imported (used at `ranking_management.py:61-62`) — no new import needed.
> The export service already renders `rank_position=None` as `""` (proven by `backend/tests/test_college_ranking_export_service.py::test_rank_position_none_renders_empty_cell`), so this task only wires the flag through the endpoint.

- [ ] **Step 1: Write the failing integration test**

Create `backend/app/tests/test_ranking_export_template.py`:

```python
"""Integration tests for the export-excel `template` flag (blank rank column)."""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_scholarship_manager
from app.main import app
from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import AdminScholarship, User, UserRole, UserType


@pytest_asyncio.fixture
async def admin_user(db: AsyncSession) -> User:
    user = User(
        nycu_id="admin900",
        name="Admin",
        email="admin900@nycu.edu.tw",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def scholarship(db: AsyncSession) -> ScholarshipType:
    s = ScholarshipType(
        code="phd_tmpl_test",
        name="Test Template PhD",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        status="active",
    )
    db.add(s)
    await db.flush()
    return s


@pytest_asyncio.fixture
async def configuration(
    db: AsyncSession, scholarship: ScholarshipType, admin_user: User
) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,  # yearly
        config_name="Test PhD 114",
        config_code="test-tmpl-114",
        amount=40000,
        is_active=True,
    )
    db.add(cfg)
    # Grant admin permission so _check_scholarship_permission passes
    db.add(AdminScholarship(admin_id=admin_user.id, scholarship_id=scholarship.id))
    await db.flush()
    return cfg


@pytest_asyncio.fixture
async def ranking_with_item(
    db: AsyncSession,
    admin_user: User,
    scholarship: ScholarshipType,
    configuration: ScholarshipConfiguration,
) -> CollegeRanking:
    student = User(
        nycu_id="310460099",
        name="王小明",
        email="s99@nycu.edu.tw",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    await db.flush()

    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code="nstc",
        academic_year=114,
        ranking_name="Test",
        created_by=admin_user.id,
        is_finalized=False,
    )
    db.add(r)
    await db.flush()

    app_row = Application(
        app_id="APP-114-0-09999",
        user_id=student.id,
        scholarship_type_id=scholarship.id,
        academic_year=114,
        semester=None,
        status=ApplicationStatus.submitted,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        student_data={"std_stdcode": "310460099", "std_cname": "王小明"},
        sub_type_preferences=["nstc"],
        scholarship_subtype_list=["nstc"],
        submitted_form_data={"fields": {}},
    )
    db.add(app_row)
    await db.flush()

    item = CollegeRankingItem(
        ranking_id=r.id,
        application_id=app_row.id,
        rank_position=1,
        status="ranked",
        college_rejected=False,
        is_allocated=False,
    )
    db.add(item)
    await db.flush()
    return r


@pytest.mark.asyncio
class TestExportTemplateFlag:
    async def test_template_true_blanks_rank_and_marks_filename(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(
                f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel",
                params={"template": "true"},
            )
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 200, resp.text
        # 範本 (U+7BC4 U+672C) url-encoded in Content-Disposition filename*
        assert "%E7%AF%84%E6%9C%AC" in resp.headers["content-disposition"]

        wb = load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        # row1 = title, row2 = headers, row3 = first data row
        assert ws.cell(row=2, column=2).value == "學院初審會議之學院排序"
        assert ws.cell(row=2, column=13).value == "學號"
        assert str(ws.cell(row=3, column=13).value) == "310460099"  # 學號 present
        assert (ws.cell(row=3, column=2).value or "") == ""  # rank BLANK

    async def test_default_keeps_rank_filled(
        self,
        client: AsyncClient,
        db: AsyncSession,
        admin_user: User,
        ranking_with_item: CollegeRanking,
    ):
        app.dependency_overrides[require_scholarship_manager] = lambda: admin_user
        try:
            resp = await client.get(
                f"/api/v1/college-review/rankings/{ranking_with_item.id}/export-excel"
            )
        finally:
            app.dependency_overrides.pop(require_scholarship_manager, None)

        assert resp.status_code == 200, resp.text
        assert "%E7%AF%84%E6%9C%AC" not in resp.headers["content-disposition"]
        wb = load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        assert ws.cell(row=3, column=2).value == 1  # rank present
```

- [ ] **Step 2: Run the test to verify it fails**

Run (inside the backend test env / container):
```bash
cd backend && python -m pytest app/tests/test_ranking_export_template.py -v
```
Expected: `test_template_true_blanks_rank_and_marks_filename` FAILS — `template` is an unknown query param (ignored), so the rank cell holds `1` and the filename has no `範本`.

- [ ] **Step 3: Add the `template` param + blank-rank mapping + filename suffix**

In `export_ranking_excel`, add the param to the signature (after `request: Request,`):

```python
@router.get("/rankings/{ranking_id}/export-excel")
async def export_ranking_excel(
    ranking_id: int,
    request: Request,
    template: bool = Query(
        False, description="Render the rank column blank, as a fill-in import template"
    ),
    current_user: User = Depends(require_scholarship_manager),
    db: AsyncSession = Depends(get_db),
):
```

Change the `export_rows` comprehension (currently `:1174-1183`) so the rank is blanked in template mode:

```python
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

Change the filename (currently `:1199`) to add a `_範本` suffix in template mode:

```python
    template_suffix = "_範本" if template else ""
    base_filename = (
        f"{ranking.academic_year}學年度{scholarship_name}學生資料彙整表_{college_label}{template_suffix}.xlsx"
    )
```

Update the audit description (currently `:1222-1224`) to note template downloads:

```python
            description=(
                f"匯出學生資料彙整表（{'範本，' if template else ''}含身分證字號明文）: "
                f"ranking_id={ranking_id}, records={len(exported_app_ids)}"
            ),
```

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd backend && python -m pytest app/tests/test_ranking_export_template.py -v
```
Expected: both tests PASS.

- [ ] **Step 5: Run the existing export-service tests to confirm no regression**

Run:
```bash
cd backend && python -m pytest backend/tests/test_college_ranking_export_service.py -v
```
Expected: all PASS (headers/title/blank-rank behavior unchanged).

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/ranking_management.py backend/app/tests/test_ranking_export_template.py
git commit -m "feat(ranking): add template flag to export-excel for blank-rank import template"
```

---

## Task 2: Extract the pure ranking-sheet parser

Pull the parsing + validation logic out of the component into a pure, unit-testable function that takes the already-keyed row objects (what `XLSX.utils.sheet_to_json` returns) and returns `{ importData, errors }`. This makes the bug-prone parser testable without a DOM or SheetJS, and aligns the read columns with the 彙整表 export headers.

**Files:**
- Create: `frontend/lib/ranking/parse-ranking-sheet.ts`
- Test: `frontend/lib/ranking/__tests__/parse-ranking-sheet.test.ts`

- [ ] **Step 1: Write the failing tests**

Create `frontend/lib/ranking/__tests__/parse-ranking-sheet.test.ts`:

```ts
import {
  parseRankingSheet,
  type ExcelRankingImportRow,
} from "@/lib/ranking/parse-ranking-sheet";

// Each row mimics XLSX.utils.sheet_to_json(ws, { range: 1 }) output:
// keys are the row-2 headers of the 學生資料彙整表 export.
const rowOf = (id: string, name: string, rank: unknown) => ({
  學號: id,
  學生中文姓名: name,
  學院初審會議之學院排序: rank,
});

describe("parseRankingSheet", () => {
  it("reads 學號 + 學生中文姓名 + 學院初審會議之學院排序 for integer ranks", () => {
    const { importData, errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 2),
    ]);
    expect(errors).toEqual([]);
    expect(importData).toEqual<ExcelRankingImportRow[]>([
      { student_id: "310460099", student_name: "王小明", rank_position: 1 },
      { student_id: "310460100", student_name: "李小華", rank_position: 2 },
    ]);
  });

  it("treats N (any case) as a rejected marker, not a numeric rank", () => {
    const { importData, errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", "n"),
    ]);
    expect(errors).toEqual([]);
    expect(importData[1].rank_position).toBe("N");
  });

  it("skips rows with an empty 學號", () => {
    const { importData } = parseRankingSheet([
      rowOf("", "", ""),
      rowOf("310460099", "王小明", 1),
    ]);
    expect(importData).toHaveLength(1);
    expect(importData[0].student_id).toBe("310460099");
  });

  it("errors when the rank cell is blank (data row = index + 3)", () => {
    const { errors } = parseRankingSheet([rowOf("310460099", "王小明", "")]);
    expect(errors).toEqual([
      "第 3 行排名欄位為空（學號：310460099）",
    ]);
  });

  it("errors on a non-positive-integer rank", () => {
    const { errors } = parseRankingSheet([rowOf("310460099", "王小明", "0")]);
    expect(errors[0]).toContain("排名格式無效");
  });

  it("errors on duplicate 學號", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460099", "王小明", 2),
    ]);
    expect(errors.some(e => e.includes("學號重複"))).toBe(true);
  });

  it("errors on duplicate integer ranks", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 1),
    ]);
    expect(errors.some(e => e.includes("排名 1 重複出現"))).toBe(true);
  });

  it("errors when integer ranks are not consecutive from 1", () => {
    const { errors } = parseRankingSheet([
      rowOf("310460099", "王小明", 1),
      rowOf("310460100", "李小華", 3),
    ]);
    expect(errors.some(e => e.includes("排名不連續"))).toBe(true);
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd frontend && npx jest lib/ranking/__tests__/parse-ranking-sheet.test.ts
```
Expected: FAIL — `Cannot find module '@/lib/ranking/parse-ranking-sheet'`.

- [ ] **Step 3: Implement the pure parser**

Create `frontend/lib/ranking/parse-ranking-sheet.ts`:

```ts
/**
 * Pure parser for the 學生資料彙整表 ranking-import format.
 *
 * Input rows are the objects produced by `XLSX.utils.sheet_to_json(ws, { range: 1 })`
 * — keyed by the export's row-2 headers (the merged title on row 1 is skipped by
 * the caller via `range: 1`). We only read the three columns the backend
 * `POST /import-excel` needs; every other 彙整表 column is ignored.
 *
 * Data rows start at Excel row 3 (row 1 = title, row 2 = headers), so the
 * human-facing row number for error messages is `index + 3`.
 */

// Header strings — must match backend STATIC_HEADERS exactly
// (college_ranking_export_service.py STATIC_HEADERS indices 12 / 7 / 1).
const COL_STUDENT_ID = "學號";
const COL_STUDENT_NAME = "學生中文姓名";
const COL_RANK = "學院初審會議之學院排序";

const FIRST_DATA_EXCEL_ROW = 3;

export interface ExcelRankingImportRow {
  student_id: string;
  student_name: string;
  rank_position: number | string; // integer rank, or "N" for rejected
}

export interface ParseResult {
  importData: ExcelRankingImportRow[];
  errors: string[];
}

export function parseRankingSheet(
  rows: Array<Record<string, unknown>>
): ParseResult {
  const errors: string[] = [];
  const importData: ExcelRankingImportRow[] = [];

  rows.forEach((row, index) => {
    const rowNum = index + FIRST_DATA_EXCEL_ROW;
    const studentId = String(row[COL_STUDENT_ID] ?? "").trim();
    const studentName = String(row[COL_STUDENT_NAME] ?? "").trim();
    const rawRank = row[COL_RANK];

    if (!studentId) return; // skip empty rows

    if (
      rawRank === undefined ||
      rawRank === null ||
      String(rawRank).trim() === ""
    ) {
      errors.push(`第 ${rowNum} 行排名欄位為空（學號：${studentId}）`);
      return;
    }

    const rankStr = String(rawRank).trim();

    if (rankStr.toUpperCase() === "N") {
      importData.push({
        student_id: studentId,
        student_name: studentName,
        rank_position: "N",
      });
      return;
    }

    const rankNum = Number(rankStr);
    if (!Number.isInteger(rankNum) || rankNum < 1) {
      errors.push(
        `第 ${rowNum} 行排名格式無效：'${rankStr}'（學號：${studentId}）`
      );
      return;
    }
    importData.push({
      student_id: studentId,
      student_name: studentName,
      rank_position: rankNum,
    });
  });

  // Duplicate 學號
  const seenStudentIds = new Set<string>();
  const duplicateStudentIds = new Set<string>();
  importData.forEach(item => {
    if (seenStudentIds.has(item.student_id)) {
      duplicateStudentIds.add(item.student_id);
    }
    seenStudentIds.add(item.student_id);
  });
  if (duplicateStudentIds.size > 0) {
    errors.push(`學號重複：${Array.from(duplicateStudentIds).join(", ")}`);
  }

  // Duplicate integer ranks
  const integerRanks = importData
    .filter(item => typeof item.rank_position === "number")
    .map(item => item.rank_position as number);

  const rankCounts = new Map<number, number>();
  integerRanks.forEach(r => rankCounts.set(r, (rankCounts.get(r) || 0) + 1));
  rankCounts.forEach((count, rank) => {
    if (count > 1) {
      errors.push(`排名 ${rank} 重複出現（${count} 次）`);
    }
  });

  // Consecutive from 1 (only when no prior errors, mirroring legacy behavior)
  if (integerRanks.length > 0 && errors.length === 0) {
    const rankSet = new Set(integerRanks);
    const missing: number[] = [];
    for (let i = 1; i <= integerRanks.length; i++) {
      if (!rankSet.has(i)) missing.push(i);
    }
    if (missing.length > 0) {
      errors.push(`排名不連續：缺少第 ${missing.join(", ")} 名`);
    }
  }

  return { importData, errors };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd frontend && npx jest lib/ranking/__tests__/parse-ranking-sheet.test.ts
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/ranking/parse-ranking-sheet.ts frontend/lib/ranking/__tests__/parse-ranking-sheet.test.ts
git commit -m "feat(ranking): extract pure parser for 彙整表-format ranking import"
```

---

## Task 3: Wire the component parser to the 彙整表 format

Replace the inline parse/validation block in `handleFileUpload` with a call to `parseRankingSheet`, reading the export format (skip the title row via `range: 1`). Remove the local `ExcelRankingImportRow` interface and import it from the new module.

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx` (`ExcelRankingImportRow` def at `:151-157`; `handleFileUpload` at `:569-726`)

- [ ] **Step 1: Import the extracted type + parser**

At the top of `college-ranking-table.tsx`, next to the existing `import { exportRankingExcel } from "@/lib/api/modules/college";` (line `:75`), add:

```ts
import {
  parseRankingSheet,
  type ExcelRankingImportRow,
} from "@/lib/ranking/parse-ranking-sheet";
```

- [ ] **Step 2: Delete the now-duplicated local interface**

Remove the local declaration at `:151-157`:

```ts
// DELETE THIS BLOCK (now imported from @/lib/ranking/parse-ranking-sheet):
// Excel import row shape produced by handleFileUpload before being passed up
// via onImportExcel — three columns (學號/姓名/排名) parsed and normalized.
interface ExcelRankingImportRow {
  student_id: string;
  student_name: string;
  rank_position: number | string;
}
```

(`ExcelRankingImportRow` stays referenced by `onImportExcel?: (data: ExcelRankingImportRow[]) => Promise<void>` at `:184` — now satisfied by the import.)

- [ ] **Step 3: Replace the parse/validate body of `handleFileUpload`**

Replace everything inside the `try {` of `handleFileUpload` (from `// Read Excel file` at `:591` down to the end of the `if (onImportExcel) { ... }` block at `:715`) with:

```ts
      // Read Excel file (學生資料彙整表 export format: row1 title, row2 headers,
      // row3+ data). `range: 1` makes row 2 the header row; do NOT also pass a
      // `header` option or the numeric range row is treated as data.
      const data = await file.arrayBuffer();
      const uint8Array = new Uint8Array(data);
      const workbook = XLSX.read(uint8Array, { type: "array" });
      const worksheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData = XLSX.utils.sheet_to_json(worksheet, {
        range: 1,
      }) as Array<Record<string, unknown>>;

      const { importData, errors } = parseRankingSheet(jsonData);

      if (errors.length > 0) {
        toast.error(errors.join("\n"), { duration: 10000 });
        setIsImporting(false);
        event.target.value = "";
        return;
      }

      if (importData.length === 0) {
        toast.error("Excel 檔案中沒有找到有效的排名資料");
        setIsImporting(false);
        event.target.value = "";
        return;
      }

      if (onImportExcel) {
        await onImportExcel(importData);
        const rejectedCount = importData.filter(
          item => item.rank_position === "N"
        ).length;
        const rankedCount = importData.length - rejectedCount;
        toast.success(
          `成功匯入 ${importData.length} 筆排名資料（排名 ${rankedCount} 筆，拒絕 ${rejectedCount} 筆）`
        );
        setIsImportDialogOpen(false);
      }
```

> Keep the surrounding `setIsImporting(true)`, the file-type/size guards above, and the `catch`/`finally` blocks unchanged. The `ExcelRankingImportRow` import now provides the type used by `importData`.

- [ ] **Step 4: Typecheck the frontend**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors referencing `college-ranking-table.tsx` or `ExcelRankingImportRow`.

- [ ] **Step 5: Re-run the parser tests (sanity, no behavior change expected)**

Run:
```bash
cd frontend && npx jest lib/ranking/__tests__/parse-ranking-sheet.test.ts
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/college-ranking-table.tsx
git commit -m "feat(ranking): parse 彙整表-format file on ranking import via shared parser"
```

---

## Task 4: `downloadRankingTemplate` API helper

**Files:**
- Modify: `frontend/lib/api/modules/college.ts` (`_fetchBinaryExport` at `:625-630`; add fn next to `exportRankingExcel` at `:678-687`)
- Test: `frontend/lib/api/modules/__tests__/college.test.ts` (add to the `"module-level export helpers"` describe block at `:416`)

- [ ] **Step 1: Write the failing test**

In `frontend/lib/api/modules/__tests__/college.test.ts`, add `downloadRankingTemplate` to the import list at the top (next to `exportRankingExcel` at `:20`):

```ts
  downloadRankingTemplate,
```

Then add inside the `describe("module-level export helpers", ...)` block:

```ts
  it("downloadRankingTemplate hits export-excel with template=true + 範本 fallback filename", async () => {
    const fetchMock = jest.fn().mockResolvedValue({
      ok: true,
      headers: { get: jest.fn().mockReturnValue("") },
      blob: jest.fn().mockResolvedValue(new Blob()),
    });
    global.fetch = fetchMock as any;

    const result = await downloadRankingTemplate(42);

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/rankings/42/export-excel");
    expect(url).toContain("template=true");
    expect(result.filename).toBe("學生資料彙整表_42_範本.xlsx");
  });
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd frontend && npx jest lib/api/modules/__tests__/college.test.ts -t "downloadRankingTemplate"
```
Expected: FAIL — `downloadRankingTemplate` is not exported.

- [ ] **Step 3: Implement the helper**

In `frontend/lib/api/modules/college.ts`, immediately after `exportRankingExcel` (`:687`), add:

```ts
/**
 * Download the 學生資料彙整表 import TEMPLATE for a college ranking — the same
 * export workbook with the rank column (學院初審會議之學院排序) left blank for the
 * college to fill in and re-import.
 *
 * Endpoint: GET /api/v1/college-review/rankings/{ranking_id}/export-excel?template=true
 */
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

- [ ] **Step 4: Run the test to verify it passes**

Run:
```bash
cd frontend && npx jest lib/api/modules/__tests__/college.test.ts -t "downloadRankingTemplate"
```
Expected: PASS. Also confirm the existing `exportRankingExcel` tests still pass:
```bash
cd frontend && npx jest lib/api/modules/__tests__/college.test.ts -t "exportRankingExcel"
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/college.ts frontend/lib/api/modules/__tests__/college.test.ts
git commit -m "feat(ranking): add downloadRankingTemplate API helper (export-excel?template=true)"
```

---

## Task 5: Rewrite `handleTemplateDownload` to use the backend blob

Replace the client-side 4-column `json_to_sheet` builder with a backend template download, mirroring `handleExportRanking`.

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx` (`handleTemplateDownload` at `:728-771`; import line at `:75`)

- [ ] **Step 1: Add `downloadRankingTemplate` to the college API import**

Update the import at `:75` (it currently imports only `exportRankingExcel`):

```ts
import {
  exportRankingExcel,
  downloadRankingTemplate,
} from "@/lib/api/modules/college";
```

- [ ] **Step 2: Replace the whole `handleTemplateDownload` function**

Replace `handleTemplateDownload` (`:728-771`) with:

```ts
  const handleTemplateDownload = async () => {
    if (!rankingId) {
      toast.error("缺少排名 ID，無法下載範本");
      return;
    }
    try {
      const { blob, filename } = await downloadRankingTemplate(rankingId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success(`已下載範本檔案：${filename}`);
    } catch (error) {
      logger.error("Template download error", { error: error });
      toast.error(error instanceof Error ? error.message : "無法產生範本檔案");
    }
  };
```

> `handleTemplateDownload` is wired at the 下載範本 button (`onClick={handleTemplateDownload}`, `:960`). An async onClick handler is fine; no JSX change needed. The old `subTypeCode`/`academicYear`/`localApplications` references inside this function are gone — if `tsc` flags them as unused elsewhere, leave them (still used by other parts of the component).

- [ ] **Step 3: Typecheck**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no new errors. (If `XLSX` becomes entirely unused after this — it is NOT; `handleFileUpload` still uses `XLSX.read`/`sheet_to_json` — leave the import.)

- [ ] **Step 4: Lint the touched frontend files**

Run:
```bash
cd frontend && npx eslint components/college-ranking-table.tsx lib/api/modules/college.ts lib/ranking/parse-ranking-sheet.ts
```
Expected: clean (fix any unused-var warnings introduced by the rewrite, e.g. a now-unused helper).

- [ ] **Step 5: Commit**

```bash
git add frontend/components/college-ranking-table.tsx
git commit -m "feat(ranking): download 彙整表 template (blank rank) from backend instead of client 4-col build"
```

---

## Task 6: Full verification

- [ ] **Step 1: Run the full backend test slice**

Run:
```bash
cd backend && python -m pytest app/tests/test_ranking_export_template.py backend/tests/test_college_ranking_export_service.py app/tests/test_supplementary_import_endpoints.py -v
```
Expected: all PASS (new template tests + unchanged export-service + supplementary-import tests).

- [ ] **Step 2: Run the full frontend test slice**

Run:
```bash
cd frontend && npx jest lib/ranking lib/api/modules/__tests__/college.test.ts
```
Expected: all PASS, including the existing `importRankingExcel` body-shape test (JSON contract unchanged).

- [ ] **Step 3: Manual smoke test (dev stack)**

Per `playwright-test-and-debug` / manual: log in as a college user (e.g. `cs_college`), open 學院排名 for a ranking, click **下載範本** → confirm the file is the full 學生資料彙整表 with the `學院初審會議之學院排序` column blank and filename ending `_範本.xlsx`. Fill a couple of rank cells (ints + one `N`), then **匯入** the file → confirm the ranks apply and the success toast shows the ranked/rejected counts.

- [ ] **Step 4: Final branch check**

Run:
```bash
git log --oneline feat/ranking-import-template-unify
git status
```
Expected: 6 commits (spec + 5 implementation), clean working tree.

---

## Self-review (completed by plan author)

- **Spec coverage:** Backend `template` flag → Task 1. `downloadRankingTemplate` → Task 4. Template button → Task 5. Parser → Tasks 2-3. `student_name` stays sent (parser reads `學生中文姓名`) → Task 2 impl + test. import-excel JSON contract untouched; e2e + importRankingExcel tests stay green → Task 6 Step 2. New parser + template tests → Tasks 2/4. All spec sections mapped.
- **Placeholder scan:** No TBD/TODO; every code step shows full code; every run step shows exact command + expected output.
- **Type consistency:** `ExcelRankingImportRow` defined once in `parse-ranking-sheet.ts` (Task 2), imported by the component (Task 3) and matches the `onImportExcel` prop signature. `parseRankingSheet` returns `{ importData, errors }` — used identically in Task 3. `downloadRankingTemplate(rankingId: number)` signature matches both its test (Task 4) and caller (Task 5).
- **Known environment caveat:** `node_modules` (incl. `xlsx`) is not installed in this worktree; frontend `jest`/`tsc`/`eslint` commands require `npm install` first (dev container / CI). Backend tests run in the backend test env. Confirm the dev container's mount path (it may mount a different worktree) before relying on `docker compose exec` for tests.
