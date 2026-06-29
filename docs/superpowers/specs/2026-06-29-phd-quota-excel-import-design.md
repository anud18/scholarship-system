# Spec: PhD Quota Excel Import (博士配額 Excel 匯入)

- **Date**: 2026-06-29
- **Status**: Approved design (revised after code-verification workflow)
- **Scope owner**: Admin / 系統管理 → 獎學金配置 → 配額管理模式
- **Worktree / branch**: dir `phd-quota-excel-import` / branch `worktree-phd-quota-excel-import`

> All `file:line` references below were verified against the worktree checkout on
> 2026-06-29. Line numbers are still point-in-time — verify before editing.

## 1. Summary

Add **Excel import** for the PhD scholarship quota matrix, integrated into the
existing **"配額設定 (JSON 格式)"** field in the scholarship-configuration
create/edit dialogs. The import parses a matrix-shaped `.xlsx` in the browser,
converts it to the existing `{sub_type: {college_code: int}}` JSON shape, shows a
preview/diff, and on confirm populates the same `formData.quotas` state that the
JSON textarea already drives. The existing create/update save path then persists it.

Two backend defects surfaced during verification and are fixed as part of this work:
1. **Create silently drops quotas** — `POST /configurations` never writes the quota
   fields, so a brand-new config's matrix is lost.
2. **No server-side quota validation** — both create and update accept a free-form
   dict and trust whatever quota structure the client sends.

Backend approach (**Option 1**, chosen): fix create + add a **shared structural
validator** called by both write paths. **No new endpoint**; the frontend keeps using
the existing create/update calls.

This is the only NEW user-facing capability. The matrix table, the mode selector, and
the "配額設定 (JSON 格式)" textarea already exist; the request reads as a UI path plus
one action item: *support Excel import*.

## 2. Background & current state (verified)

- **Model** `ScholarshipConfiguration` — `backend/app/models/scholarship.py:504`.
  Quota columns: `has_quota_limit` (Boolean, `:532`), `has_college_quota`
  (Boolean, `:533`), `quota_management_mode` (Enum, `:534`), `total_quota`
  (Integer, `:541`), `quotas` (JSON, `:542`; shape comment `:544`).
- **Matrix shape**: `quotas` is nested `{sub_type: {college_code: int}}`, e.g.
  `{"nstc": {"EE": 5, "EN": 4}, "moe_1w": {"EE": 6, "EN": 5}}`. Rows = sub_type,
  columns = college code. Read/written via model helpers `get_matrix_quota` (`:678`),
  `set_matrix_quota` (`:686`), `get_matrix_quota_summary` (`:714`) — all assume this
  nesting. (A flat `{college: int}` shape exists for `simple`/`college_based` via
  `get_quota_for_college` `:672`, out of scope.)
- **Enum** `QuotaManagementMode` — `backend/app/models/enums.py:113`:
  `none`/`simple`/`college_based`/`matrix_based`. PhD uses `matrix_based`.
- **Single-cell write** `PUT /scholarship-configurations/matrix-quota` —
  `backend/app/api/v1/endpoints/scholarship_configurations.py:427`. Recomputes
  `total_quota = sum(all cells)` (`:508-511`), `flag_modified(config, "quotas")`
  (`:515`), invalidates caches via `invalidate("refdata:")` / `invalidate("formconfig:")`
  / `invalidate("quota:")` from `app.core.cache` (`:522-524`). Validates: sub_type ∈
  `phd.sub_type_list or ["nstc","moe_1w","moe_2w"]` (`:486-491`), value ≥ 0 (`:438`),
  value ≤ 1000 → 400 (`:441-442`). It does **not** validate the college code.
- **Reference data**: colleges = the `Academy` table, served by
  `GET /api/v1/reference-data/academies` (`backend/app/api/v1/endpoints/reference_data.py:92`,
  returns `{id, code, name}`), consumed via `frontend/hooks/use-reference-data.ts`
  (`academies` `:20/:98`, `subTypeTranslations` `:34-37/:101`). The existing matrix
  table sources its columns from these academy codes
  (`frontend/components/quota/matrix-quota-table.tsx:54/:64/:76`), **not**
  `college_mappings.py`. Sub-types = `ScholarshipType.sub_type_list`
  (`backend/app/models/scholarship.py:61`), labels via `ScholarshipSubTypeConfig`
  (`:301`) surfaced as `sub_type_translations`.
- **Frontend "配額設定 (JSON 格式)"** — `frontend/components/admin-configuration-management.tsx`.
  The quota form block is **duplicated (copy-pasted, not shared)** across the create and
  edit dialogs with different element ids:
  - Create dialog (block ~`:1776-1889`): mode `<Select>` (`:1781-1801`, always shown);
    `total_quota <Input id="total_quota">` gated on `mode === "simple"` (`:1804-1821`);
    `quotas <Textarea id="quotas">` (label `:1826`) gated on
    `mode === "college_based" || mode === "matrix_based"` (`:1823-1872`), bound via
    `JSON.stringify(formData.quotas)` (`:1851`) / `JSON.parse` (`:1857`) →
    `setFormData(prev => ({ ...prev, quotas: parsed }))` (`:1859`).
  - Edit dialog (block ~`:2260-2375`): same, ids `edit_quota_management_mode` /
    `edit_total_quota` / `edit_quotas` (label `:2312`, textarea `:2309-2358`).
  - `handleCreateConfig` (`:435`) and `handleUpdateConfig` (`:469`) send
    `processedData = { ...formData, has_quota_limit: mode !== "none", has_college_quota:
    mode === "college_based" || mode === "matrix_based" }` (so `quotas` is included,
    plus two derived booleans) to `api.admin.createScholarshipConfiguration`
    (`frontend/lib/api/modules/admin.ts:803`) / `updateScholarshipConfiguration` (`:814`).
- **Existing CSV export (untouched)**: `frontend/components/quota-management.tsx`
  `handleExport` (`:187`) → `apiClient.quota.exportQuotaData(selectedPeriod, "csv")`.
- **Excel parse pattern to mirror**: `frontend/lib/ranking/parse-ranking-sheet.ts` is a
  **pure** function over pre-parsed rows (`:39`) with a `__tests__` sibling; its consumer
  `frontend/components/college-ranking-table.tsx` does the lazy
  `const XLSX = await import("xlsx")` (`:610`) + `XLSX.utils.sheet_to_json` (`:618`) and
  calls the pure parser (`:622`). This split (pure parser ← lazy-xlsx consumer) is the pattern.

### The two corrected truths (this drives the whole design)

| Path | What the spec originally assumed | What the code actually does |
|------|----------------------------------|-----------------------------|
| **Create** `POST /configurations` (`:774`) | persists quotas (via `ScholarshipConfigurationCreate`) | **Drops quotas.** Body is free-form `Dict[str, Any]`; the `ScholarshipConfiguration(...)` constructor (`:814-847`) omits `quotas`/`total_quota`/`quota_management_mode`/`has_*`. (Test note documents the free-form body: `test_scholarship_configuration_endpoints.py:148`.) |
| **Edit** `PUT /configurations/{id}` (`:973`) | drops quotas (docstring says "excluding quota fields") | **Persists quotas.** The docstring (`:980`) is **stale**; the handler assigns `quota_management_mode` (`:1068-1082`), `has_quota_limit` (`:1085`), `has_college_quota` (`:1087`), `total_quota` (`:1089`), `config.quotas` + `flag_modified` (`:1090-1092`). |

Neither write path does any structural validation of the quota matrix — both take a
free-form dict (`ScholarshipConfigurationUpdate` at `schemas/scholarship_configuration.py:147`
is a standalone `BaseModel` with **no** `validate_quotas` validator; the validator lives
only on `Base`/`Create`, which the handlers don't use).

So: the real latent bug is on **create**, edit already works but **unvalidated**, and the
quota textarea (and therefore Excel import) silently fails to persist **only when creating
a new config**.

## 3. Goals & non-goals

### Goals
- Import a matrix-shaped `.xlsx` into the PhD quota matrix from the config dialog.
- Convert Excel → the existing `{sub_type: {college: int}}` JSON; reuse the existing
  `formData.quotas` data flow ("Excel → JSON → existing save path").
- Preview/diff before applying, including a **warning when the import will zero/remove a
  cell that currently holds a quota**.
- Provide a **template download** pre-filled with the current quotas (matrix layout;
  doubles as the round-trip export).
- **Fix create** so the quota matrix persists on create (latent bug).
- **Add server-side structural validation** of the quota matrix on both write paths, so
  client input is never trusted.

### Non-goals (out of scope)
- Generalising beyond PhD / `matrix_based`.
- The separate single-cell matrix-management page (`quota-management.tsx`).
- The existing CSV export button.
- A standalone Excel **export** button (the pre-filled template covers round-trip).
- A new bulk quota endpoint (Option 2 was rejected).
- Reconciling `college_mappings.py` vs `Academy` (Academy is authoritative here, §6).
- Editing `quota_management_mode` via import (PhD stays `matrix_based`).
- Blocking import based on in-flight allocations (see §10 hazard — preview only warns).

## 4. Design decisions (resolved with stakeholder)

| # | Decision | Choice |
|---|----------|--------|
| 1 | Applicability scope | **PhD only** (`matrix_based`); no generalisation |
| 2 | "配額設定 (JSON 格式)" | Existing JSON textarea; the integration target, not a new build |
| 3 | Excel sheet layout | **Matrix** (rows = sub_type, columns = college); mirrors screen/template; round-trippable |
| 4 | Apply semantics | **Full replace, blank = 0**, with a mandatory pre-apply preview/diff |
| 5 | Template / export | **Import + template download (pre-filled with current quotas)**; CSV export untouched |
| 6 | Validation strictness | **Structural errors block** (unknown college/sub_type, negative/non-integer, > 1000, duplicate → red, apply disabled). **No over-quota check** — in `matrix_based` mode `total_quota` is derived as the sum of cells, so it can never be exceeded. |
| 7 | Backend approach | **Option 1**: fix `POST` to persist quotas + a **shared `validate_quota_matrix()`** called inline by both `POST` and `PUT`; recompute `total_quota = sum` for matrix mode. **No new endpoint**; frontend save flow unchanged. |
| 8 | Authoritative college list | The **`Academy`** reference-data (`use-reference-data.ts` / `GET /reference-data/academies`), used **identically** by the frontend parser/template and the backend validator. |

## 5. Architecture (Option 1)

```
下載範本 ──▶ build matrix .xlsx pre-filled with current formData.quotas
                  │ (admin edits in Excel)
匯入 Excel ──▶ pick file ─▶ lazy import xlsx ─▶ pure parser parseQuotaSheet()
                  │            (map headers→Academy college codes, rows→sub_types,
                  │             cells→int 0..1000; blank/absent=0; structural validation)
                  ▼
        QuotaImportDialog (preview matrix + diff vs current;
                            errors red [apply disabled], warnings yellow
                            [cells being zeroed/removed])
                  │ confirm
                  ▼
        setFormData(prev => ({ ...prev, quotas: parsedQuotas }))   // full replace
                  │ (JSON textarea re-renders to match)
                  ▼ admin clicks 建立 / 更新  (UNCHANGED handlers, already send quotas)
   create:  POST /configurations   ── FIX: constructor now writes quota fields
   edit:    PUT  /configurations/{id} ── already writes quota fields
                  ▼  (both call the SHARED validator first)
        validate_quota_matrix(quotas, sub_type_list, academy_codes)
          → 422 unless every sub_type ∈ list, every college ∈ Academy, every value int 0..1000
        → set quotas, flag_modified, total_quota = sum(cells) [matrix mode], invalidate caches
                  ▼
        separate matrix-management page reflects new numbers
```

### Why Option 1
- Honours "reference the existing JSON way and just add Excel; convert Excel to JSON":
  Excel import only fills `formData.quotas`; the existing create/update path persists it.
- Minimal churn: no new endpoint, no new api-client method, no change to the save handlers.
- Fixes the real bug (create) and closes the validation hole on **both** paths in one
  shared, unit-testable helper (never trust client input — project rule).

## 6. Detailed design

### 6.1 Excel sheet format (matrix)

- Row 1 = header: first cell a label (e.g. `子類型 \ 學院`), remaining cells = **college
  identifiers** — accept the Academy **code** (`C`, `A`, …) or **name** (中/英). Mapped to
  canonical Academy codes by the parser.
- Each later row: first cell = **sub_type identifier** — accept the sub_type **code**
  (`nstc`, …) or its display label; remaining cells = integer quotas.
- **Blank cell ⇒ 0.** **Absent column/row** (a college in the Academy list or a sub_type in
  `sub_type_list` with no matching column/row in the sheet) ⇒ written as **0** (consistent
  with full-replace), and each such omission is surfaced as a **preview warning**.
- The template builder emits exactly this shape, pre-filled, so download → edit → import is
  loss-free.

### 6.2 Frontend

**New — shared issue type** (in `frontend/lib/quota/parse-quota-sheet.ts`):
```
type QuotaParseIssue = {
  kind: 'college' | 'subType' | 'cell' | 'duplicate' | 'zeroed';
  severity: 'error' | 'warning';
  row?: number;          // 1-based sheet row
  col?: number;          // 1-based sheet column
  message: string;       // human-readable, zh
};
```

**New — pure parser** `frontend/lib/quota/parse-quota-sheet.ts` (mirrors
`frontend/lib/ranking/parse-ranking-sheet.ts`; **no `xlsx` import inside**):
```
parseQuotaSheet(
  rows: unknown[][],                  // XLSX.utils.sheet_to_json(ws, { header: 1 })
  knownColleges: { code: string; name: string; nameEn?: string }[],   // from Academy
  knownSubTypes: { code: string; label?: string }[],                  // from sub_type_list
  currentQuotas: Record<string, Record<string, number>>,              // for the zeroed-cell diff
): {
  quotas: Record<string, Record<string, number>>;   // canonical codes, full matrix (absent ⇒ 0)
  errors: QuotaParseIssue[];     // block apply
  warnings: QuotaParseIssue[];   // zeroed/removed cells — allow apply
}
```
- Header cell → canonical Academy code (code match first, then name/nameEn, case/space-insensitive);
  unknown ⇒ **error** (`kind:'college'`, with `col`).
- Row label → canonical sub_type code (code first, then label); unknown ⇒ **error**
  (`kind:'subType'`, with `row`). Import cannot invent sub_types.
- Cell value: empty ⇒ 0; otherwise must be an integer in `0..1000` — negative / fractional /
  non-numeric / > 1000 ⇒ **error** (`kind:'cell'`, `(row,col)`).
- Duplicate college column or sub_type row ⇒ **error** (`kind:'duplicate'`).
- After building the full matrix (filling absent colleges/sub_types with 0), any cell where
  `currentQuotas[sub][col] > 0` and the new value is `0` ⇒ **warning** (`kind:'zeroed'`).
- Pure & deterministic → unit-testable.

**New — template builder** `frontend/lib/quota/build-quota-template.ts`
- Lazy `import("xlsx")`. Builds the matrix workbook pre-filled from current `formData.quotas`
  (sub_type rows in `sub_type_list` order; college columns = Academy codes). Downloads as
  `quota-template-${config_code || "new"}.xlsx` (on the create path `config_code` may be
  unset → `"new"`). Used by both dialogs.

**New — preview dialog** `frontend/components/admin/quota-import/QuotaImportDialog.tsx`
- Props: parsed `quotas`, `errors`, `warnings`, `currentQuotas` (for the diff), `onConfirm(quotas)`.
  Renders the matrix with `old→new` diffs; lists errors (red) and warnings (yellow, e.g.
  "此匯入會將 nstc/EE 由 5 歸零"). `[確認套用]` disabled when `errors.length > 0`.

**Modified — config dialog** `frontend/components/admin-configuration-management.tsx`
- Add **「匯入 Excel」** + **「下載範本」** buttons next to the quota textarea in **BOTH** the
  create block (`~:1823-1872`) and the edit block (`~:2309-2358`) — the block is duplicated,
  so the buttons go in two places. Gate the buttons on `quota_management_mode === "matrix_based"`
  (PhD-only). NOTE: the textarea itself renders for `college_based || matrix_based`, so the
  buttons intentionally appear in only the `matrix_based` subset.
- 「匯入 Excel」: file input → lazy `xlsx` → `parseQuotaSheet(...)` → open `QuotaImportDialog`.
  On confirm: `setFormData(prev => ({ ...prev, quotas }))` (full replace). The existing
  `handleCreateConfig` / `handleUpdateConfig` are **unchanged** — they already send `quotas`.
- `knownColleges` from `useReferenceData().academies`; `knownSubTypes` from the selected
  scholarship type's `sub_type_list` (fallback `["nstc","moe_1w","moe_2w"]`) + `subTypeTranslations`.
- **No new api-client method** — persistence reuses `createScholarshipConfiguration` /
  `updateScholarshipConfiguration`.

### 6.3 Backend (Option 1 — no new endpoint)

**Fix — create** `POST /configurations` (`scholarship_configurations.py:774`, constructor `:814-847`):
add the omitted quota fields so a new config persists its matrix —
`quotas`, `total_quota`, `quota_management_mode`, `has_quota_limit`, `has_college_quota`
(assign in/after the constructor; `flag_modified(config, "quotas")` if assigned post-construct).
Keep the existing cache-invalidation trio (`:853-855`).

**New — shared validator** `validate_quota_matrix(quotas, allowed_sub_types, allowed_college_codes) -> list[str]`
(pure helper, e.g. `backend/app/utils/quota_validation.py`; unit-tested). Returns a list of
error messages; **all checks are NEW** (none are in `validate_quota_config`, `scholarship.py:753`,
which only checks presence + `college_total ≤ total_quota`):
- every sub_type key ∈ `allowed_sub_types` (the config's `sub_type_list`, fallback
  `["nstc","moe_1w","moe_2w"]`);
- every college key ∈ `allowed_college_codes` (resolved server-side from
  `select(Academy.code)` — **not** `college_mappings.py`);
- every value is an `int` in `0..1000` (mirrors the single-cell endpoint's `≤ 1000` cap).

**Wire it into both write paths**: in `POST` (create) and `PUT` (`:973`, update), when
`quota_management_mode == "matrix_based"` and `quotas` is present, call `validate_quota_matrix`;
if it returns errors, raise `HTTPException(422, detail=...)` (raise — never swallow). Then for
matrix mode set `total_quota = sum(sum(cells))` (ignore any `total_quota` in the body, matching
the single-cell endpoint and avoiding drift). Do **not** rely on
`validate_quota_config`'s `college_total > total_quota` check — it is vacuous once `total_quota`
is the sum. The bulk replace does **not** touch `has_quota_limit` / `has_college_quota` /
`quota_management_mode` (the frontend already derives those; mode is unchanged).

## 7. Error handling & validation

| Layer | Condition | Result |
|-------|-----------|--------|
| File | not `.xlsx` / unreadable / no usable sheet | block; clear toast |
| Parser (FE) | unknown college column | error (red), apply disabled |
| Parser (FE) | unknown sub_type row | error (red), apply disabled |
| Parser (FE) | negative / fractional / non-numeric / > 1000 cell | error (red) with `(row,col)` |
| Parser (FE) | duplicate college col / sub_type row | error (red) |
| Parser (FE) | cell currently > 0 being set to 0 (incl. absent col/row) | **warning** (yellow), apply allowed |
| Backend | `validate_quota_matrix` violation on create OR edit | `422`, raise (no silent accept) |

## 8. Testing strategy

**Frontend unit** `frontend/lib/quota/__tests__/parse-quota-sheet.test.ts`: valid matrix;
blank ⇒ 0; absent college column / sub_type row ⇒ 0 **and** emits a zeroed-cell warning;
unknown college; unknown sub_type; negative; fractional; non-numeric; > 1000; header matched by
code vs by name; duplicate column/row; empty sheet. Template round-trip:
`build → sheet_to_json → parseQuotaSheet` reproduces the input quotas.

**Backend** (flat files in `backend/app/tests/` — `test_scholarship_configuration_endpoints.py`
for async endpoint tests via `@pytest.mark.asyncio`; `test_scholarship_configuration_pure_helpers.py`
or a sibling for the sync `validate_quota_matrix` unit tests):
- `validate_quota_matrix` unit: each rejection (bad sub_type / bad college / negative / > 1000)
  and an all-valid pass.
- **create regression**: creating a config now persists `quotas` + `total_quota` (was dropped).
- **edit**: updating quotas persists (already worked) and now 422s on a structural violation.
- `total_quota` recomputed as sum on both paths; cache trio invalidated; `require_admin` enforced.
- Follow the CI split (async ⇒ integration). Lint gate: black `--line-length=120`,
  `flake8 --select=B904,B014`.

**E2E (optional, Playwright)**: download template → modify → import → preview → apply (create
*and* edit) → separate matrix page reflects the new numbers.

## 9. Files touched

**New**
- `frontend/lib/quota/parse-quota-sheet.ts`
- `frontend/lib/quota/build-quota-template.ts`
- `frontend/lib/quota/__tests__/parse-quota-sheet.test.ts`
- `frontend/components/admin/quota-import/QuotaImportDialog.tsx`
- `backend/app/utils/quota_validation.py` (`validate_quota_matrix`)

**Modified**
- `frontend/components/admin-configuration-management.tsx` (import + template buttons in BOTH the create and edit quota blocks)
- `backend/app/api/v1/endpoints/scholarship_configurations.py` (fix create constructor; wire `validate_quota_matrix` + matrix `total_quota` recompute into create & update; refresh the stale `:980` docstring)
- `backend/app/tests/test_scholarship_configuration_endpoints.py` (+ sync helper test file)

**Not touched**: no new endpoint, no new api-client method, no change to the save handlers
`handleCreateConfig` / `handleUpdateConfig`, the CSV export, or the matrix-management page.

## 10. Risks / notes

- **Silent allocation-pool zeroing (main hazard)**: full-replace is KeyError-safe — all
  consumers guard with `.get`/`or {}`/`isinstance` (`manual_distribution_service.py:178/:196`
  with `_matrix_row` `:188-204`; `quota_service.py:82`; `college_review_service.py:984-992`;
  model helpers `:678-702`) — so it will **not crash**. But dropping/zeroing a sub_type/college
  on re-import silently sets its allocation pool to 0 (`manual_distribution_service.pool_total`
  reads these). Mitigation in scope: the **zeroed-cell preview warning** (§6.2/§7). Blocking on
  in-flight allocations is out of scope (§3). (`roster_service` does **not** read `config.quotas`.)
- **`total_quota` drift**: today `PUT` takes `total_quota` straight from the body (`:1089`); for
  matrix mode we now recompute it as the cell-sum, matching `PUT /matrix-quota` (`:508-511`).
- **Validation source-of-truth**: no existing code validates college codes against `Academy`;
  `validate_quota_matrix` is the first, and it must use the same Academy list the frontend
  parser uses, or the FE would accept an import the BE 422-rejects.
- **Duplicated dialog block**: the quota block is copy-pasted across create/edit; the two button
  insertions must stay in sync (consider extracting a small shared sub-component if it grows).
