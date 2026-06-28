# PhD Quota Excel Import — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin import the PhD scholarship quota matrix from a matrix-shaped `.xlsx` (with preview + template download) in the scholarship-configuration dialog, and make quotas persist + validate on every write path.

**Architecture:** Frontend parses the `.xlsx` in the browser into the existing `{sub_type: {college_code: int}}` JSON, previews a diff, and on confirm fills the same `formData.quotas` the JSON textarea already drives — so the existing create/update save path persists it. Backend gains one shared `validate_quota_matrix()` called by both `POST` (create, currently drops quotas — fixed here) and `PUT` (edit, already persists), and recomputes `total_quota` as the cell-sum in matrix mode. No new endpoint, no new API-client method.

**Tech Stack:** FastAPI + SQLAlchemy (async) + Pydantic v2 (backend); Next.js + React + TypeScript + `xlsx` (SheetJS) + jest (frontend). Spec: `docs/superpowers/specs/2026-06-29-phd-quota-excel-import-design.md`.

## Global Constraints

- **Scope: PhD only** (`quota_management_mode === "matrix_based"`). Do not generalise to other modes.
- **Quota matrix shape**: `{sub_type: {college_code: int}}` (rows = sub_type, columns = college).
- **Authoritative college list = the `Academy` table** (`Academy.code`). The frontend parser/template and the backend validator MUST use this same list. `Academy` is `app.models.student.Academy` (columns `code`, `name`, `name_en`).
- **Cell values**: integers in `0..1000` (mirrors the single-cell endpoint's `≤ 1000` cap). Blank/absent cell ⇒ `0`. Import is a **full replace** of the matrix.
- **Sub-type allow-list**: the config's `ScholarshipType.sub_type_list`, fallback `["nstc", "moe_1w", "moe_2w"]`.
- **API envelope**: endpoints return `ApiResponse{success, message, data}`. Both `POST`/`PUT` config endpoints take a free-form `Dict[str, Any]` body (no Pydantic schema) — quota structural validation is added explicitly in the handler, not via a schema.
- **Backend lint gate (hard)**: `black --line-length=120`; `flake8 --select=B904,B014` (a `raise` inside `except` must be `raise ... from e`).
- **Backend tests in this worktree**: run via `./.run-backend-tests.sh app/tests/<file> -v` (ephemeral container mounting THIS worktree; the live `scholarship_backend_dev` container is mounted to a different worktree and will NOT see these files).
- **Frontend tests**: `npm test -- <pathPattern>` (jest). The worktree has **no `frontend/node_modules`** — run frontend tooling from a checkout that has deps installed, or inside the frontend container mounted to this worktree. **NEVER** symlink `frontend/node_modules` (Turbopack panics).
- **Lazy-load `xlsx`**: `const XLSX = await import("xlsx")` inside the handler (never a top-level import).
- **Commits**: conventional-commit messages, English, no attribution footer.

---

## File Structure

**New**
- `backend/app/utils/quota_validation.py` — pure `validate_quota_matrix()`.
- `backend/app/tests/test_quota_validation.py` — sync unit tests for the validator.
- `frontend/lib/quota/parse-quota-sheet.ts` — pure parser + `QuotaParseIssue`/`QuotaMatrix` types.
- `frontend/lib/quota/build-quota-template.ts` — pure `buildQuotaMatrixRows()` + lazy `downloadQuotaTemplate()`.
- `frontend/lib/quota/__tests__/parse-quota-sheet.test.ts`
- `frontend/lib/quota/__tests__/build-quota-template.test.ts`
- `frontend/components/admin/quota-import/QuotaImportDialog.tsx` — presentational preview/diff dialog.
- `frontend/components/admin/quota-import/QuotaExcelButtons.tsx` — import + template buttons; hosts the dialog; lazy `xlsx`.

**Modified**
- `backend/app/api/v1/endpoints/scholarship_configurations.py` — add quota imports + `_resolve_quota_allowlists` + `_apply_quota_fields`; call in create (before `db.add`) and replace the update quota block; refresh the stale `:980` docstring.
- `backend/app/tests/test_scholarship_configuration_endpoints.py` — matrix fixtures + create-persists + 422 tests.
- `frontend/components/admin-configuration-management.tsx` — render `<QuotaExcelButtons>` in both the create (`~:1872`) and edit (`~:2356`) quota blocks.

---

## Task 1: Backend `validate_quota_matrix` helper (pure)

**Files:**
- Create: `backend/app/utils/quota_validation.py`
- Test: `backend/app/tests/test_quota_validation.py`

**Interfaces:**
- Produces: `validate_quota_matrix(quotas: Any, allowed_sub_types: Iterable[str], allowed_college_codes: Iterable[str]) -> list[str]` and module constant `MAX_CELL_QUOTA = 1000`. Returns a (possibly empty) list of zh error strings; empty ⇒ valid.

- [ ] **Step 1: Write the failing test**

```python
# backend/app/tests/test_quota_validation.py
"""Unit tests for the pure quota-matrix validator (sync — runs in the unit suite)."""

from app.utils.quota_validation import MAX_CELL_QUOTA, validate_quota_matrix

ALLOWED_SUB = ["nstc", "moe_1w"]
ALLOWED_COL = ["C", "E"]


def test_valid_matrix_returns_no_errors():
    assert validate_quota_matrix({"nstc": {"C": 5, "E": 4}}, ALLOWED_SUB, ALLOWED_COL) == []


def test_unknown_sub_type_is_error():
    errors = validate_quota_matrix({"ghost": {"C": 1}}, ALLOWED_SUB, ALLOWED_COL)
    assert any("ghost" in e for e in errors)


def test_unknown_college_is_error():
    errors = validate_quota_matrix({"nstc": {"ZZ": 1}}, ALLOWED_SUB, ALLOWED_COL)
    assert any("ZZ" in e for e in errors)


def test_negative_value_is_error():
    assert validate_quota_matrix({"nstc": {"C": -1}}, ALLOWED_SUB, ALLOWED_COL)


def test_value_over_max_is_error():
    assert validate_quota_matrix({"nstc": {"C": MAX_CELL_QUOTA + 1}}, ALLOWED_SUB, ALLOWED_COL)


def test_boolean_is_not_a_valid_int():
    # bool is a subclass of int in Python; it must be rejected.
    assert validate_quota_matrix({"nstc": {"C": True}}, ALLOWED_SUB, ALLOWED_COL)


def test_non_dict_quotas_is_error():
    assert validate_quota_matrix([], ALLOWED_SUB, ALLOWED_COL)
    assert validate_quota_matrix({"nstc": 5}, ALLOWED_SUB, ALLOWED_COL)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `./.run-backend-tests.sh app/tests/test_quota_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.utils.quota_validation'`.

- [ ] **Step 3: Write the minimal implementation**

```python
# backend/app/utils/quota_validation.py
"""Pure structural validation for the quota matrix {sub_type: {college_code: int}}.

Shared by the create and update scholarship-configuration endpoints so the rules
cannot drift between write paths. Returns a list of human-readable (zh) error
strings; an empty list means the matrix is structurally valid.
"""

from typing import Any, Iterable, List

MAX_CELL_QUOTA = 1000


def validate_quota_matrix(
    quotas: Any,
    allowed_sub_types: Iterable[str],
    allowed_college_codes: Iterable[str],
) -> List[str]:
    errors: List[str] = []
    allowed_sub = set(allowed_sub_types)
    allowed_col = set(allowed_college_codes)

    if not isinstance(quotas, dict):
        return ["配額格式錯誤：必須為物件 {子類型: {學院代碼: 數量}}"]

    for sub_type, row in quotas.items():
        if sub_type not in allowed_sub:
            errors.append(f"未知的子類型：{sub_type}")
            continue
        if not isinstance(row, dict):
            errors.append(f"子類型 {sub_type} 的配額格式錯誤：必須為 {{學院代碼: 數量}}")
            continue
        for college, value in row.items():
            if college not in allowed_col:
                errors.append(f"未知的學院代碼：{college}（子類型 {sub_type}）")
            if isinstance(value, bool) or not isinstance(value, int):
                errors.append(f"配額必須為整數：{sub_type}/{college} = {value!r}")
            elif value < 0 or value > MAX_CELL_QUOTA:
                errors.append(f"配額需介於 0 與 {MAX_CELL_QUOTA} 之間：{sub_type}/{college} = {value}")

    return errors
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `./.run-backend-tests.sh app/tests/test_quota_validation.py -v`
Expected: PASS — 7 passed.

- [ ] **Step 5: Lint**

Run: `cd backend && uvx --from "black==26.3.1" black --line-length=120 app/utils/quota_validation.py app/tests/test_quota_validation.py && flake8 app/utils/quota_validation.py --select=B904,B014 --max-line-length=120`
Expected: no output (clean).

- [ ] **Step 6: Commit**

```bash
git add backend/app/utils/quota_validation.py backend/app/tests/test_quota_validation.py
git commit -m "feat(quota): add pure validate_quota_matrix helper"
```

---

## Task 2: Backend — persist + validate quotas on create and update

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py` (imports ~`:24-27`; new helpers near `:104`; create call before `db.add` at `:849`; replace update quota block `:1068-1092`; refresh docstring `:980`)
- Test: `backend/app/tests/test_scholarship_configuration_endpoints.py`

**Interfaces:**
- Consumes: `validate_quota_matrix` (Task 1).
- Produces: create now persists `quotas`/`total_quota`/`quota_management_mode`/`has_*`; both paths 422 on a structurally-invalid matrix in `matrix_based` mode; `total_quota` recomputed as the cell-sum in matrix mode.

- [ ] **Step 1: Write the failing tests** (append to `test_scholarship_configuration_endpoints.py`)

```python
# --- PhD matrix quota import: persistence + validation ----------------------- #

from app.models.student import Academy  # add with the other model imports at the top


@pytest_asyncio.fixture
async def matrix_reference_data(db: AsyncSession, test_scholarship_type):
    """Give the test scholarship type a matrix sub_type_list and seed the
    Academy rows the validator resolves college codes from."""
    test_scholarship_type.sub_type_list = ["nstc", "moe_1w"]
    db.add(test_scholarship_type)
    db.add_all([Academy(code="C", name="資訊"), Academy(code="E", name="電機")])
    await db.commit()
    return test_scholarship_type


class TestScholarshipConfigurationQuotaImport:
    @pytest.mark.asyncio
    async def test_create_persists_matrix_quotas(
        self, authenticated_admin_client, valid_config_payload, matrix_reference_data
    ):
        payload = {
            **valid_config_payload,
            "config_code": "MATRIX-PERSIST-113-1",
            "quota_management_mode": "matrix_based",
            "quotas": {"nstc": {"C": 5, "E": 4}, "moe_1w": {"C": 3}},
        }
        resp = await authenticated_admin_client.post(BASE, json=payload)
        assert resp.status_code == 200
        config_id = resp.json()["data"]["id"]

        # Read back through the API (the proven pattern in test_create_configuration_success).
        got = (await authenticated_admin_client.get(f"{BASE}/{config_id}")).json()["data"]
        assert got["quotas"] == {"nstc": {"C": 5, "E": 4}, "moe_1w": {"C": 3}}
        assert got["total_quota"] == 12  # 5 + 4 + 3, recomputed as the cell-sum

    @pytest.mark.asyncio
    async def test_create_rejects_unknown_college(
        self, authenticated_admin_client, valid_config_payload, matrix_reference_data
    ):
        payload = {
            **valid_config_payload,
            "config_code": "MATRIX-BADCOL-113-1",
            "quota_management_mode": "matrix_based",
            "quotas": {"nstc": {"ZZ": 5}},
        }
        resp = await authenticated_admin_client.post(BASE, json=payload)
        assert resp.status_code == 422
```

Add `from app.models.student import Academy` to the test's model imports (top of the file, near the other `from app.models...` lines).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `./.run-backend-tests.sh app/tests/test_scholarship_configuration_endpoints.py::TestScholarshipConfigurationQuotaImport -v`
Expected: FAIL — `test_create_persists_matrix_quotas` fails (`got["quotas"]` is `None`/missing — create drops quotas); `test_create_rejects_unknown_college` fails (returns 200, not 422).

- [ ] **Step 3: Add imports** (top of `scholarship_configurations.py`)

Add to the model imports (after `:27`):

```python
from app.models.enums import QuotaManagementMode, Semester  # extend the existing Semester import (:25)
from app.models.student import Academy
from app.utils.quota_validation import validate_quota_matrix
```

(Remove the now-redundant inline `from app.models.enums import QuotaManagementMode` at the old `:1069`.)

- [ ] **Step 4: Add the shared helpers** (place near `get_user_accessible_scholarship_ids`, ~`:104`)

```python
DEFAULT_PHD_SUB_TYPES = ["nstc", "moe_1w", "moe_2w"]


async def _resolve_quota_allowlists(db: AsyncSession, scholarship_type_id: int):
    """Return (allowed_sub_types, allowed_college_codes) for matrix validation."""
    sub_result = await db.execute(
        select(ScholarshipType.sub_type_list).where(ScholarshipType.id == scholarship_type_id)
    )
    sub_types = sub_result.scalar_one_or_none() or DEFAULT_PHD_SUB_TYPES
    col_result = await db.execute(select(Academy.code))
    college_codes = list(col_result.scalars().all())
    return sub_types, college_codes


async def _apply_quota_fields(db: AsyncSession, config, config_data, *, scholarship_type_id: int):
    """Assign quota fields from config_data onto config, validating the matrix.

    Shared by create and update so the rules cannot drift. In matrix_based mode the
    matrix is structurally re-validated (422 on violation) and total_quota is
    recomputed as the sum of all cells (the body's total_quota is ignored).
    """
    if "quota_management_mode" in config_data:
        mode_value = config_data["quota_management_mode"]
        mode_enum = QuotaManagementMode.none
        if mode_value:
            for mode in QuotaManagementMode:
                if mode.value == mode_value:
                    mode_enum = mode
                    break
        config.quota_management_mode = mode_enum
    if "has_quota_limit" in config_data:
        config.has_quota_limit = config_data["has_quota_limit"]
    if "has_college_quota" in config_data:
        config.has_college_quota = config_data["has_college_quota"]

    if "quotas" in config_data and config_data["quotas"] is not None:
        quotas = config_data["quotas"]
        if config.quota_management_mode == QuotaManagementMode.matrix_based:
            sub_types, college_codes = await _resolve_quota_allowlists(db, scholarship_type_id)
            errors = validate_quota_matrix(quotas, sub_types, college_codes)
            if errors:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="；".join(errors)
                )
            config.total_quota = sum(
                sum(row.values()) for row in quotas.values() if isinstance(row, dict)
            )
        elif "total_quota" in config_data:
            config.total_quota = config_data["total_quota"]
        config.quotas = quotas
        flag_modified(config, "quotas")
    elif "total_quota" in config_data:
        config.total_quota = config_data["total_quota"]
```

- [ ] **Step 5: Call the helper in create** (insert in `create_scholarship_configuration` between `:847` `)` end of constructor and `:849` `db.add(new_config)`)

```python
        # Persist + validate quota fields (create previously dropped them).
        await _apply_quota_fields(
            db, new_config, config_data, scholarship_type_id=scholarship_type_id
        )

        db.add(new_config)
```

- [ ] **Step 6: Replace the update quota block** (`update_scholarship_configuration`, current `:1067-1092`)

Replace these lines:

```python
        # Update quota management settings
        if "quota_management_mode" in config_data:
            from app.models.enums import QuotaManagementMode
            ...
        if "quotas" in config_data:
            config.quotas = config_data["quotas"]
            flag_modified(config, "quotas")
```

with:

```python
        # Update quota management settings (validated; matrix mode recomputes total).
        await _apply_quota_fields(
            db, config, config_data, scholarship_type_id=config.scholarship_type_id
        )
```

Leave the following `project_numbers` / `shared_quota_sources` blocks (current `:1093-1103`) unchanged. Also update the stale docstring at `:980` from `"""Update a scholarship configuration (excluding quota fields)"""` to `"""Update a scholarship configuration (quota fields included; matrix validated)."""`.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `./.run-backend-tests.sh app/tests/test_scholarship_configuration_endpoints.py -v`
Expected: PASS — the two new tests pass and the existing config-endpoint tests still pass.

- [ ] **Step 8: Lint**

Run: `cd backend && uvx --from "black==26.3.1" black --line-length=120 app/api/v1/endpoints/scholarship_configurations.py app/tests/test_scholarship_configuration_endpoints.py && flake8 app/api/v1/endpoints/scholarship_configurations.py --select=B904,B014 --max-line-length=120`
Expected: no output (note the `raise HTTPException(...)` in `_apply_quota_fields` is NOT inside an `except`, so B904 does not apply).

- [ ] **Step 9: Commit**

```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
git commit -m "fix(quota): persist and validate matrix quotas on create and update"
```

---

## Task 3: Frontend quota-sheet parser (pure) + types

**Files:**
- Create: `frontend/lib/quota/parse-quota-sheet.ts`
- Test: `frontend/lib/quota/__tests__/parse-quota-sheet.test.ts`

**Interfaces:**
- Produces: types `QuotaMatrix`, `KnownCollege`, `KnownSubType`, `QuotaParseIssue`, `QuotaParseResult`, and `parseQuotaSheet(rows, knownColleges, knownSubTypes, currentQuotas) -> QuotaParseResult`. The result `quotas` is always a FULL matrix (`knownSubTypes × knownColleges`, absent cells `0`).

- [ ] **Step 1: Write the failing test**

```ts
// frontend/lib/quota/__tests__/parse-quota-sheet.test.ts
import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
} from "@/lib/quota/parse-quota-sheet";

const COLLEGES: KnownCollege[] = [
  { code: "C", name: "資訊" },
  { code: "E", name: "電機", nameEn: "ECE" },
];
const SUBTYPES: KnownSubType[] = [
  { code: "nstc", label: "國科會" },
  { code: "moe_1w", label: "教育部1萬" },
];
const sheet = (...rows: unknown[][]) => rows;

describe("parseQuotaSheet", () => {
  it("parses a valid matrix by college code and sub_type code", () => {
    const { quotas, errors, warnings } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", 5, 4], ["moe_1w", 3, 2]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors).toEqual([]);
    expect(warnings).toEqual([]);
    expect(quotas).toEqual({ nstc: { C: 5, E: 4 }, moe_1w: { C: 3, E: 2 } });
  });

  it("treats blank cells and absent columns/rows as 0", () => {
    const { quotas, errors } = parseQuotaSheet(
      sheet(["", "C"], ["nstc", ""]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors).toEqual([]);
    expect(quotas).toEqual({ nstc: { C: 0, E: 0 }, moe_1w: { C: 0, E: 0 } });
  });

  it("matches headers and rows by name/label as well as code", () => {
    const { quotas } = parseQuotaSheet(
      sheet(["", "資訊", "ECE"], ["國科會", 7, 8]),
      COLLEGES, SUBTYPES, {},
    );
    expect(quotas.nstc).toEqual({ C: 7, E: 8 });
  });

  it("errors on an unknown college column", () => {
    const { errors } = parseQuotaSheet(sheet(["", "ZZ"], ["nstc", 1]), COLLEGES, SUBTYPES, {});
    expect(errors.some(e => e.kind === "college")).toBe(true);
  });

  it("errors on an unknown sub_type row", () => {
    const { errors } = parseQuotaSheet(sheet(["", "C"], ["ghost", 1]), COLLEGES, SUBTYPES, {});
    expect(errors.some(e => e.kind === "subType")).toBe(true);
  });

  it("errors on negative, fractional, non-numeric, and >1000 cells", () => {
    const { errors } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", -1, 2.5], ["moe_1w", "x", 1001]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors.filter(e => e.kind === "cell")).toHaveLength(4);
  });

  it("errors on duplicate college columns and sub_type rows", () => {
    const { errors } = parseQuotaSheet(
      sheet(["", "C", "C"], ["nstc", 1, 2], ["nstc", 3, 4]),
      COLLEGES, SUBTYPES, {},
    );
    expect(errors.some(e => e.kind === "duplicate")).toBe(true);
  });

  it("warns when an import zeroes a cell that currently has a quota", () => {
    const { warnings } = parseQuotaSheet(
      sheet(["", "C", "E"], ["nstc", 0, 4]),
      COLLEGES, SUBTYPES, { nstc: { C: 5, E: 4 } },
    );
    expect(warnings.some(w => w.kind === "zeroed")).toBe(true);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- lib/quota/__tests__/parse-quota-sheet.test.ts`
Expected: FAIL — cannot find module `@/lib/quota/parse-quota-sheet`.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/lib/quota/parse-quota-sheet.ts
export type QuotaMatrix = Record<string, Record<string, number>>;

export interface KnownCollege {
  code: string;
  name: string;
  nameEn?: string;
}

export interface KnownSubType {
  code: string;
  label?: string;
}

export interface QuotaParseIssue {
  kind: "college" | "subType" | "cell" | "duplicate" | "zeroed";
  severity: "error" | "warning";
  row?: number; // 1-based sheet row
  col?: number; // 1-based sheet column
  message: string;
}

export interface QuotaParseResult {
  quotas: QuotaMatrix;
  errors: QuotaParseIssue[];
  warnings: QuotaParseIssue[];
}

const MAX_CELL_QUOTA = 1000;

const norm = (v: unknown): string => String(v ?? "").trim().toLowerCase();

function resolveCollege(header: unknown, colleges: KnownCollege[]): string | null {
  const key = norm(header);
  if (!key) return null;
  for (const c of colleges) {
    if (norm(c.code) === key || norm(c.name) === key || (c.nameEn && norm(c.nameEn) === key)) {
      return c.code;
    }
  }
  return null;
}

function resolveSubType(label: unknown, subTypes: KnownSubType[]): string | null {
  const key = norm(label);
  if (!key) return null;
  for (const s of subTypes) {
    if (norm(s.code) === key || (s.label && norm(s.label) === key)) return s.code;
  }
  return null;
}

export function parseQuotaSheet(
  rows: unknown[][],
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
  currentQuotas: QuotaMatrix,
): QuotaParseResult {
  const errors: QuotaParseIssue[] = [];
  const warnings: QuotaParseIssue[] = [];

  // Start from a full zero matrix so absent rows/columns become 0 (full-replace).
  const quotas: QuotaMatrix = {};
  for (const s of knownSubTypes) {
    quotas[s.code] = {};
    for (const c of knownColleges) quotas[s.code][c.code] = 0;
  }

  // Map sheet column index -> canonical college code.
  const header = rows[0] ?? [];
  const colCode: (string | null)[] = [];
  const seenCols = new Set<string>();
  for (let j = 1; j < header.length; j++) {
    const raw = header[j];
    if (norm(raw) === "") {
      colCode[j] = null;
      continue;
    }
    const code = resolveCollege(raw, knownColleges);
    if (!code) {
      errors.push({ kind: "college", severity: "error", col: j + 1, message: `未知的學院欄位：「${String(raw)}」（第 ${j + 1} 欄）` });
      colCode[j] = null;
      continue;
    }
    if (seenCols.has(code)) {
      errors.push({ kind: "duplicate", severity: "error", col: j + 1, message: `學院欄位重複：${code}` });
      colCode[j] = null;
      continue;
    }
    seenCols.add(code);
    colCode[j] = code;
  }

  const seenRows = new Set<string>();
  for (let i = 1; i < rows.length; i++) {
    const row = rows[i] ?? [];
    if (norm(row[0]) === "") continue; // skip blank rows
    const sub = resolveSubType(row[0], knownSubTypes);
    if (!sub) {
      errors.push({ kind: "subType", severity: "error", row: i + 1, message: `未知的子類型列：「${String(row[0])}」（第 ${i + 1} 列）` });
      continue;
    }
    if (seenRows.has(sub)) {
      errors.push({ kind: "duplicate", severity: "error", row: i + 1, message: `子類型列重複：${sub}` });
      continue;
    }
    seenRows.add(sub);

    for (let j = 1; j < row.length; j++) {
      const code = colCode[j];
      if (!code) continue; // unknown/blank/duplicate column already reported
      const raw = row[j];
      if (raw === undefined || raw === null || String(raw).trim() === "") {
        quotas[sub][code] = 0;
        continue;
      }
      const n = Number(String(raw).trim());
      if (!Number.isInteger(n) || n < 0 || n > MAX_CELL_QUOTA) {
        errors.push({ kind: "cell", severity: "error", row: i + 1, col: j + 1, message: `第 ${i + 1} 列第 ${j + 1} 欄配額無效：「${String(raw)}」（需為 0–${MAX_CELL_QUOTA} 的整數）` });
        continue;
      }
      quotas[sub][code] = n;
    }
  }

  // Zeroed-cell warnings: a cell currently > 0 that the import sets to 0.
  for (const s of knownSubTypes) {
    for (const c of knownColleges) {
      const before = currentQuotas?.[s.code]?.[c.code] ?? 0;
      if (before > 0 && quotas[s.code][c.code] === 0) {
        warnings.push({ kind: "zeroed", severity: "warning", message: `此匯入會將 ${s.code}/${c.code} 由 ${before} 歸零` });
      }
    }
  }

  return { quotas, errors, warnings };
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- lib/quota/__tests__/parse-quota-sheet.test.ts`
Expected: PASS — 8 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/quota/parse-quota-sheet.ts frontend/lib/quota/__tests__/parse-quota-sheet.test.ts
git commit -m "feat(quota): add pure parseQuotaSheet for matrix Excel import"
```

---

## Task 4: Frontend template builder

**Files:**
- Create: `frontend/lib/quota/build-quota-template.ts`
- Test: `frontend/lib/quota/__tests__/build-quota-template.test.ts`

**Interfaces:**
- Consumes: `QuotaMatrix`, `KnownCollege`, `KnownSubType` (Task 3); `parseQuotaSheet` (Task 3, for the round-trip test).
- Produces: `buildQuotaMatrixRows(quotas, knownColleges, knownSubTypes) -> (string|number)[][]` (pure) and `downloadQuotaTemplate(quotas, knownColleges, knownSubTypes, configCode?) -> Promise<void>` (lazy `xlsx`).

- [ ] **Step 1: Write the failing test** (round-trip — pure, no `xlsx` needed)

```ts
// frontend/lib/quota/__tests__/build-quota-template.test.ts
import { buildQuotaMatrixRows } from "@/lib/quota/build-quota-template";
import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
} from "@/lib/quota/parse-quota-sheet";

const COLLEGES: KnownCollege[] = [{ code: "C", name: "資訊" }, { code: "E", name: "電機" }];
const SUBTYPES: KnownSubType[] = [{ code: "nstc" }, { code: "moe_1w" }];

describe("buildQuotaMatrixRows", () => {
  it("round-trips: build → parse reproduces the full matrix", () => {
    const quotas = { nstc: { C: 5, E: 4 }, moe_1w: { C: 3, E: 0 } };
    const rows = buildQuotaMatrixRows(quotas, COLLEGES, SUBTYPES);
    const { quotas: parsed, errors } = parseQuotaSheet(rows, COLLEGES, SUBTYPES, {});
    expect(errors).toEqual([]);
    expect(parsed).toEqual(quotas);
  });

  it("emits a header row of college codes and pre-fills 0 for missing cells", () => {
    const rows = buildQuotaMatrixRows({ nstc: { C: 9 } }, COLLEGES, SUBTYPES);
    expect(rows[0].slice(1)).toEqual(["C", "E"]);
    expect(rows[1]).toEqual(["nstc", 9, 0]);
    expect(rows[2]).toEqual(["moe_1w", 0, 0]);
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- lib/quota/__tests__/build-quota-template.test.ts`
Expected: FAIL — cannot find module `@/lib/quota/build-quota-template`.

- [ ] **Step 3: Write the implementation**

```ts
// frontend/lib/quota/build-quota-template.ts
import type { KnownCollege, KnownSubType, QuotaMatrix } from "@/lib/quota/parse-quota-sheet";

const CORNER_LABEL = "子類型＼學院";

// Pure: the array-of-arrays the .xlsx sheet will contain (header + body rows).
export function buildQuotaMatrixRows(
  quotas: QuotaMatrix,
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
): (string | number)[][] {
  const header: (string | number)[] = [CORNER_LABEL, ...knownColleges.map(c => c.code)];
  const body = knownSubTypes.map(s => [
    s.code,
    ...knownColleges.map(c => quotas?.[s.code]?.[c.code] ?? 0),
  ]);
  return [header, ...body];
}

export async function downloadQuotaTemplate(
  quotas: QuotaMatrix,
  knownColleges: KnownCollege[],
  knownSubTypes: KnownSubType[],
  configCode?: string,
): Promise<void> {
  const XLSX = await import("xlsx");
  const rows = buildQuotaMatrixRows(quotas, knownColleges, knownSubTypes);
  const ws = XLSX.utils.aoa_to_sheet(rows);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "配額");
  XLSX.writeFile(wb, `quota-template-${configCode || "new"}.xlsx`);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- lib/quota/__tests__/build-quota-template.test.ts`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/quota/build-quota-template.ts frontend/lib/quota/__tests__/build-quota-template.test.ts
git commit -m "feat(quota): add matrix template builder (round-trippable)"
```

---

## Task 5: Frontend preview dialog (`QuotaImportDialog`)

**Files:**
- Create: `frontend/components/admin/quota-import/QuotaImportDialog.tsx`
- Test: `frontend/components/admin/quota-import/__tests__/QuotaImportDialog.test.tsx`

**Interfaces:**
- Consumes: `QuotaMatrix`, `KnownCollege`, `KnownSubType`, `QuotaParseResult` (Task 3).
- Produces: `<QuotaImportDialog open onOpenChange result currentQuotas knownColleges knownSubTypes onConfirm />`. `確認套用` is disabled when `result.errors.length > 0`.

- [ ] **Step 1: Write the failing test** (jsdom — default jest config)

```tsx
// frontend/components/admin/quota-import/__tests__/QuotaImportDialog.test.tsx
import { render, screen } from "@testing-library/react";
import { QuotaImportDialog } from "@/components/admin/quota-import/QuotaImportDialog";

const colleges = [{ code: "C", name: "資訊" }];
const subs = [{ code: "nstc" }];

it("disables 確認套用 when there are errors", () => {
  render(
    <QuotaImportDialog
      open
      onOpenChange={() => {}}
      result={{ quotas: { nstc: { C: 0 } }, errors: [{ kind: "cell", severity: "error", message: "bad" }], warnings: [] }}
      currentQuotas={{}}
      knownColleges={colleges}
      knownSubTypes={subs}
      onConfirm={() => {}}
    />,
  );
  expect(screen.getByText("確認套用").closest("button")).toBeDisabled();
});

it("enables 確認套用 with no errors and renders a diff cell", () => {
  render(
    <QuotaImportDialog
      open
      onOpenChange={() => {}}
      result={{ quotas: { nstc: { C: 5 } }, errors: [], warnings: [] }}
      currentQuotas={{ nstc: { C: 2 } }}
      knownColleges={colleges}
      knownSubTypes={subs}
      onConfirm={() => {}}
    />,
  );
  expect(screen.getByText("確認套用").closest("button")).not.toBeDisabled();
  expect(screen.getByText("2→5")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- components/admin/quota-import/__tests__/QuotaImportDialog.test.tsx`
Expected: FAIL — cannot find module `@/components/admin/quota-import/QuotaImportDialog`.

- [ ] **Step 3: Write the component**

```tsx
// frontend/components/admin/quota-import/QuotaImportDialog.tsx
"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import type {
  KnownCollege,
  KnownSubType,
  QuotaMatrix,
  QuotaParseResult,
} from "@/lib/quota/parse-quota-sheet";

interface QuotaImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  result: QuotaParseResult | null;
  currentQuotas: QuotaMatrix;
  knownColleges: KnownCollege[];
  knownSubTypes: KnownSubType[];
  onConfirm: (quotas: QuotaMatrix) => void;
}

export function QuotaImportDialog({
  open,
  onOpenChange,
  result,
  currentQuotas,
  knownColleges,
  knownSubTypes,
  onConfirm,
}: QuotaImportDialogProps) {
  if (!result) return null;
  const hasErrors = result.errors.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>匯入配額預覽</DialogTitle>
        </DialogHeader>

        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr>
                <th className="border p-1 text-left">子類型＼學院</th>
                {knownColleges.map(c => (
                  <th key={c.code} className="border p-1">{c.code}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {knownSubTypes.map(s => (
                <tr key={s.code}>
                  <td className="border p-1 font-medium">{s.label || s.code}</td>
                  {knownColleges.map(c => {
                    const before = currentQuotas?.[s.code]?.[c.code] ?? 0;
                    const after = result.quotas?.[s.code]?.[c.code] ?? 0;
                    const changed = before !== after;
                    return (
                      <td
                        key={c.code}
                        className={cn("border p-1 text-center", changed && "bg-amber-50 font-semibold")}
                      >
                        {changed ? `${before}→${after}` : after}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {result.errors.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm text-red-600">
            {result.errors.map((e, i) => <li key={i}>⛔ {e.message}</li>)}
          </ul>
        )}
        {result.warnings.length > 0 && (
          <ul className="mt-2 space-y-1 text-sm text-amber-600">
            {result.warnings.map((w, i) => <li key={i}>⚠ {w.message}</li>)}
          </ul>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>取消</Button>
          <Button
            disabled={hasErrors}
            onClick={() => {
              onConfirm(result.quotas);
              onOpenChange(false);
            }}
          >
            確認套用
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

> If `@/components/ui/dialog` does not export exactly these names, mirror an existing dialog (e.g. `components/whitelist-management-dialog.tsx`) for the correct imports — do not invent new ones.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- components/admin/quota-import/__tests__/QuotaImportDialog.test.tsx`
Expected: PASS — 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/quota-import/QuotaImportDialog.tsx frontend/components/admin/quota-import/__tests__/QuotaImportDialog.test.tsx
git commit -m "feat(quota): add quota import preview dialog"
```

---

## Task 6: Frontend import/template buttons (`QuotaExcelButtons`)

**Files:**
- Create: `frontend/components/admin/quota-import/QuotaExcelButtons.tsx`
- Test: `frontend/components/admin/quota-import/__tests__/QuotaExcelButtons.test.tsx`

**Interfaces:**
- Consumes: `parseQuotaSheet` (Task 3), `downloadQuotaTemplate` (Task 4), `QuotaImportDialog` (Task 5), `useReferenceData` (`academies`).
- Produces: `<QuotaExcelButtons quotas subTypes configCode? onApply />` — renders 「匯入 Excel」+「下載範本」, lazy-loads `xlsx`, parses to a `QuotaParseResult`, and on confirm calls `onApply(quotas)`.

- [ ] **Step 1: Write the failing test** (mock the reference-data hook)

```tsx
// frontend/components/admin/quota-import/__tests__/QuotaExcelButtons.test.tsx
jest.mock("@/hooks/use-reference-data", () => ({
  useReferenceData: () => ({
    academies: [{ id: 1, code: "C", name: "資訊" }],
    subTypeTranslations: { zh: {}, en: {} },
  }),
}));

import { render, screen } from "@testing-library/react";
import { QuotaExcelButtons } from "@/components/admin/quota-import/QuotaExcelButtons";

it("renders the import and template buttons", () => {
  render(<QuotaExcelButtons quotas={{}} subTypes={[{ code: "nstc" }]} onApply={() => {}} />);
  expect(screen.getByText("匯入 Excel")).toBeInTheDocument();
  expect(screen.getByText("下載範本")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test -- components/admin/quota-import/__tests__/QuotaExcelButtons.test.tsx`
Expected: FAIL — cannot find module `@/components/admin/quota-import/QuotaExcelButtons`.

- [ ] **Step 3: Write the component**

```tsx
// frontend/components/admin/quota-import/QuotaExcelButtons.tsx
"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { Download, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReferenceData } from "@/hooks/use-reference-data";
import {
  parseQuotaSheet,
  type KnownCollege,
  type KnownSubType,
  type QuotaMatrix,
  type QuotaParseResult,
} from "@/lib/quota/parse-quota-sheet";
import { downloadQuotaTemplate } from "@/lib/quota/build-quota-template";
import { QuotaImportDialog } from "@/components/admin/quota-import/QuotaImportDialog";

interface QuotaExcelButtonsProps {
  quotas: QuotaMatrix;
  subTypes: KnownSubType[];
  configCode?: string;
  onApply: (quotas: QuotaMatrix) => void;
}

export function QuotaExcelButtons({ quotas, subTypes, configCode, onApply }: QuotaExcelButtonsProps) {
  const { academies } = useReferenceData();
  const fileRef = useRef<HTMLInputElement>(null);
  const [result, setResult] = useState<QuotaParseResult | null>(null);
  const [open, setOpen] = useState(false);

  const colleges: KnownCollege[] = academies.map(a => ({ code: a.code, name: a.name }));

  const handleFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-selecting the same file
    if (!file) return;
    try {
      const XLSX = await import("xlsx");
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: "array" });
      const ws = wb.Sheets[wb.SheetNames[0]];
      if (!ws) {
        toast.error("Excel 沒有可用的工作表");
        return;
      }
      const rows = XLSX.utils.sheet_to_json<unknown[]>(ws, { header: 1 });
      setResult(parseQuotaSheet(rows, colleges, subTypes, quotas));
      setOpen(true);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "無法讀取 Excel 檔案");
    }
  };

  const handleTemplate = async () => {
    try {
      await downloadQuotaTemplate(quotas, colleges, subTypes, configCode);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "無法下載範本");
    }
  };

  return (
    <div className="mt-2 flex gap-2">
      <input ref={fileRef} type="file" accept=".xlsx" hidden onChange={handleFile} />
      <Button type="button" variant="outline" size="sm" onClick={() => fileRef.current?.click()}>
        <Upload className="h-4 w-4 mr-1" />
        匯入 Excel
      </Button>
      <Button type="button" variant="outline" size="sm" onClick={handleTemplate}>
        <Download className="h-4 w-4 mr-1" />
        下載範本
      </Button>
      <QuotaImportDialog
        open={open}
        onOpenChange={setOpen}
        result={result}
        currentQuotas={quotas}
        knownColleges={colleges}
        knownSubTypes={subTypes}
        onConfirm={onApply}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npm test -- components/admin/quota-import/__tests__/QuotaExcelButtons.test.tsx`
Expected: PASS — 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/quota-import/QuotaExcelButtons.tsx frontend/components/admin/quota-import/__tests__/QuotaExcelButtons.test.tsx
git commit -m "feat(quota): add Excel import + template buttons"
```

---

## Task 7: Wire the buttons into the config dialog (both create and edit)

**Files:**
- Modify: `frontend/components/admin-configuration-management.tsx`

**Interfaces:**
- Consumes: `<QuotaExcelButtons>` (Task 6). Uses existing `formData.quotas`, `formData.config_code`, `formData.quota_management_mode`, and `selectedScholarshipType`.

- [ ] **Step 1: Add the import** (with the other component imports near the top)

```tsx
import { QuotaExcelButtons } from "@/components/admin/quota-import/QuotaExcelButtons";
```

- [ ] **Step 2: Derive the sub-type list** (inside the component body, e.g. just after the `selectedScholarshipType` state at `~:274`)

```tsx
  const quotaSubTypes = (
    (selectedScholarshipType as { sub_type_list?: string[] })?.sub_type_list ??
    ["nstc", "moe_1w", "moe_2w"]
  ).map(code => ({ code }));
```

- [ ] **Step 3: Render the buttons in the CREATE block** — insert immediately after the quotas `<Textarea>` wrapper `</div>` (current `:1872`) and before the `{formData.quota_management_mode === "matrix_based" && (<SharedQuotaSourcesPicker ...` block (current `:1874`):

```tsx
                {formData.quota_management_mode === "matrix_based" && (
                  <QuotaExcelButtons
                    quotas={(typeof formData.quotas === "object" && formData.quotas) || {}}
                    subTypes={quotaSubTypes}
                    configCode={formData.config_code}
                    onApply={next => setFormData(prev => ({ ...prev, quotas: next }))}
                  />
                )}
```

- [ ] **Step 4: Render the buttons in the EDIT block** — insert the identical block immediately after the `edit_quotas` `<Textarea>` wrapper `</div>` (the edit copy; label at `:2312`, textarea `id="edit_quotas"` at `:2334`), before the edit-dialog `SharedQuotaSourcesPicker`:

```tsx
                {formData.quota_management_mode === "matrix_based" && (
                  <QuotaExcelButtons
                    quotas={(typeof formData.quotas === "object" && formData.quotas) || {}}
                    subTypes={quotaSubTypes}
                    configCode={formData.config_code}
                    onApply={next => setFormData(prev => ({ ...prev, quotas: next }))}
                  />
                )}
```

- [ ] **Step 5: Typecheck the change**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors introduced by `admin-configuration-management.tsx` (the file already typechecks; the new block must not add errors).

- [ ] **Step 6: Manual smoke (documented, no automated test for the giant dialog)**

1. Open 系統管理 → 獎學金配置, pick the PhD type, mode = 矩陣配額.
2. 下載範本 → a `quota-template-*.xlsx` downloads pre-filled with current quotas.
3. Edit a cell in Excel, 匯入 Excel → preview shows the `old→new` diff; a bad college column shows a red error and disables 確認套用.
4. 確認套用 → the 配額設定 (JSON 格式) textarea updates; 建立/更新 → reopen and confirm the new numbers persist.

- [ ] **Step 7: Commit**

```bash
git add frontend/components/admin-configuration-management.tsx
git commit -m "feat(quota): wire Excel import buttons into config dialog (create + edit)"
```

---

## Task 8 (optional): Playwright E2E

**Files:**
- Create: `frontend/e2e/quota-excel-import.spec.ts` (follow the existing E2E patterns and the multi-college ranking→distribution→roster flow referenced in the project's playwright-test-and-debug skill).

Cover: login as admin → 獎學金配置 (PhD, 矩陣配額) → 下載範本 → upload a modified fixture `.xlsx` → preview → 確認套用 → save → reopen and assert the matrix-management page reflects the new numbers. Skip if E2E infra isn't being run for this change.

---

## Self-Review — spec coverage

- Excel import (matrix layout, blank/absent ⇒ 0, full replace) → Tasks 3, 6, 7.
- Preview/diff with errors (red, block) + zeroed-cell warnings (yellow) → Tasks 3, 5.
- Template download pre-filled with current quotas (round-trippable) → Tasks 4, 6.
- Create persists quotas (latent bug fix) → Task 2 (`test_create_persists_matrix_quotas`).
- Server-side structural validation on create AND edit (422) → Tasks 1, 2.
- Authoritative college list = `Academy`, used by FE parser/template and BE validator → Tasks 1/2 (`_resolve_quota_allowlists` → `Academy.code`) and Task 6 (`useReferenceData().academies`).
- `total_quota` recomputed as cell-sum in matrix mode → Task 2 (`_apply_quota_fields`).
- Buttons gated on `matrix_based`, added in BOTH duplicated dialog blocks → Task 7.
- No new endpoint / no new API-client method → confirmed (Tasks 2, 7 reuse existing save).
