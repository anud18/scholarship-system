# College-Viewable Distribution Results (admin-gated) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a College user see their own college's per-student distribution outcomes (正取/備取/未錄取 by sub-type), gated by a per-scholarship admin toggle.

**Architecture:** Mirror the existing `allow_supplementary_import` admin-toggle pattern end-to-end — a new boolean on `ScholarshipConfiguration`, an admin `PATCH` setter, the flag surfaced in read payloads, a new college-scoped `GET` endpoint that enforces the flag, and a new College "分發結果" tab that appears only when the flag is on. No payment PII; no allocation-year labels (outcomes for one sub-type are merged across allocation years).

**Tech Stack:** FastAPI + SQLAlchemy (async) + Alembic + PostgreSQL (backend); Next.js + React + TypeScript + shadcn/ui (frontend); pytest (backend tests, async/integration suite); jest/RTL (frontend component tests); Playwright (e2e).

## Global Constraints

- Backend enums/values lowercase; SQLAlchemy `Enum` columns keep `values_callable`. (CLAUDE.md §4)
- All endpoints return the `ApiResponse` shape `{success, message, data}`; no `response_model=`. (CLAUDE.md §5)
- New Alembic migrations MUST include existence checks before DDL and a working `downgrade`. (CLAUDE.md "Alembic Migration Development Rules")
- Lint gate before every backend commit: `uvx --from "black==26.3.1" black --check --line-length=120 backend/app`; `flake8 app --select=B904,B014 --max-line-length=120`. `raise ... from exc` inside `except` (B904). (CLAUDE.md "Testing, Lint & CI Standards")
- Async backend tests are `@pytest.mark.asyncio` / `async def`; they run in the **integration** suite, use the async `db` + `client` fixtures, and authenticate by overriding the `require_admin` / `require_college` dependency via `app.dependency_overrides`. (mirror `app/tests/test_scholarship_configuration_endpoints.py`)
- Frontend copy is Traditional Chinese (zh-TW).
- After any API/schema change, regenerate OpenAPI types: `cd frontend && npm run api:generate` with the backend running on `localhost:8000`, and commit `frontend/lib/api/generated/schema.d.ts`. (CLAUDE.md §8)
- New flag name: **`allow_college_view_distribution`** (backend column + payload key + TS field). Admin Switch label: **「開放學院查看分發結果」**. College tab label: **「分發結果」**.
- Worktree note: running pytest via `docker compose exec backend` executes the **main** checkout, not this worktree. To exercise worktree code, either run pytest in a local venv with `DATABASE_URL`/`DATABASE_URL_SYNC`/`SECRET_KEY`/`MINIO_*` set inline, or confirm the dev container is bind-mounting this worktree before relying on its output. (memory: backend_local_pytest_env)

---

## File Structure

**Backend**
- `backend/app/models/scholarship.py` — add the `allow_college_view_distribution` column (modify).
- `backend/alembic/versions/<new>.py` — additive migration (create).
- `backend/app/api/v1/endpoints/scholarship_configurations.py` — admin `PATCH` setter + surface flag in config read/update serialization (modify).
- `backend/app/api/v1/endpoints/college_review/distribution.py` — new college `GET /distribution-results` endpoint (modify).
- `backend/app/api/v1/endpoints/college_review/ranking_management.py` — surface flag in the two college rankings payloads (modify).
- `backend/app/tests/test_college_view_distribution.py` — backend tests (create).

**Frontend**
- `frontend/lib/api/types.ts` — add `allow_college_view_distribution?: boolean` (modify).
- `frontend/lib/api/modules/college.ts` — `toggleConfigCollegeViewDistribution` + `getDistributionResults` (modify).
- `frontend/components/admin/config/ConfigToggleSwitch.tsx` — extracted generic toggle (create).
- `frontend/components/admin-configuration-management.tsx` — use the generic toggle for both flags (modify).
- `frontend/components/college/distribution/DistributionResultPanel.tsx` — the new panel (create).
- `frontend/components/college/CollegeManagementShell.tsx` — conditional third tab (modify).
- `frontend/lib/api/generated/schema.d.ts` — regenerated (modify, Task 7).

---

## Task 1: Backend model column + Alembic migration

**Files:**
- Modify: `backend/app/models/scholarship.py:591`
- Create: `backend/alembic/versions/add_college_view_distribution_001.py`

**Interfaces:**
- Produces: `ScholarshipConfiguration.allow_college_view_distribution: bool` (default `False`).

- [ ] **Step 1: Add the column to the model**

In `backend/app/models/scholarship.py`, immediately after line 591 (`allow_supplementary_import = ...`), add:

```python
    # 分發結果查看開關 — admin 控制，是否開放學院查看自己學生的分發結果（正取/備取/未錄取）
    allow_college_view_distribution = Column(
        Boolean, default=False, nullable=False, server_default="false"
    )
```

- [ ] **Step 2: Find the current migration head**

Run (dev container is authoritative — the repo has had multi-head merges):

```bash
docker compose -f docker-compose.dev.yml exec backend alembic heads
```

Expected: one revision id printed (e.g. `xxxxxxxx (head)`). If MORE than one head prints, run `docker compose -f docker-compose.dev.yml exec backend alembic merge -m "merge heads" <head1> <head2>` first (or pick the head that descends the scholarship-config lineage) so there is a single head to branch from. Record the head id — call it `<HEAD>`.

- [ ] **Step 3: Create the migration file**

Create `backend/alembic/versions/add_college_view_distribution_001.py`:

```python
"""add allow_college_view_distribution to scholarship_configurations

Revision ID: add_college_view_distribution_001
Revises: <HEAD>
Create Date: 2026-06-30

Admin-controlled toggle: open/close college visibility of distribution results.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "add_college_view_distribution_001"
down_revision = "<HEAD>"  # ← replace with the id from Step 2
branch_labels = None
depends_on = None

TABLE = "scholarship_configurations"
COLUMN = "allow_college_view_distribution"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN not in columns:
        op.add_column(
            TABLE,
            sa.Column(
                COLUMN,
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns(TABLE)}
    if COLUMN in columns:
        op.drop_column(TABLE, COLUMN)
```

- [ ] **Step 4: Apply the migration and verify the column exists**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U scholarship_user -d scholarship_db -c \
  "SELECT column_name, column_default, is_nullable FROM information_schema.columns WHERE table_name='scholarship_configurations' AND column_name='allow_college_view_distribution';"
```

Expected: one row — `allow_college_view_distribution | false | NO`.

- [ ] **Step 5: Verify a fresh rebuild also has the column**

```bash
./scripts/reset_database.sh
docker compose -f docker-compose.dev.yml exec postgres \
  psql -U scholarship_user -d scholarship_db -c "\d scholarship_configurations" | grep allow_college_view_distribution
```

Expected: the column is listed. (Confirms both the model-driven create path and the migration agree.)

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/scholarship.py backend/alembic/versions/add_college_view_distribution_001.py
git commit -m "feat(model): add allow_college_view_distribution toggle to scholarship config"
```

---

## Task 2: Admin toggle endpoint + surface flag in config serialization

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py` (around 954, 1054-1055, 1132-1165, 1390)
- Test: `backend/app/tests/test_college_view_distribution.py` (create — admin section)

**Interfaces:**
- Consumes: `ScholarshipConfiguration.allow_college_view_distribution` (Task 1).
- Produces: `PATCH /api/v1/scholarship-configurations/configurations/{id}/college-view-distribution`, body `{"allow": bool}`, returns `ApiResponse` with `data={"id": int, "allow_college_view_distribution": bool}`. Config GET payloads now include `allow_college_view_distribution`.

- [ ] **Step 1: Write the failing test (admin toggle flips the flag)**

Create `backend/app/tests/test_college_view_distribution.py`:

```python
"""Tests for the admin toggle + college view of distribution results."""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import require_admin, require_college
from app.main import app
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType
from app.models.user import AdminScholarship, User, UserRole, UserType

CONFIG_BASE = "/api/v1/scholarship-configurations/configurations"


@pytest_asyncio.fixture
async def sch_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="cvd_phd",
        name="CVD PhD Scholarship",
        description="college-view-distribution test",
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
        config_name="CVD 114-1",
        config_code="CVD-114-1",
        academic_year=114,
        semester="first",
        amount=40000,
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


@pytest_asyncio.fixture
async def admin_client(db: AsyncSession, client: AsyncClient, sch_type) -> AsyncClient:
    admin = User(
        nycu_id="cvd_admin",
        email="cvd_admin@university.edu",
        name="CVD Admin",
        user_type=UserType.employee,
        role=UserRole.admin,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    db.add(AdminScholarship(admin_id=admin.id, scholarship_id=sch_type.id))
    await db.commit()

    async def override_admin():
        return admin

    app.dependency_overrides[require_admin] = override_admin
    try:
        yield client
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_admin_can_toggle_college_view_distribution(admin_client, config, db):
    resp = await admin_client.patch(
        f"{CONFIG_BASE}/{config.id}/college-view-distribution", json={"allow": True}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["allow_college_view_distribution"] is True

    await db.refresh(config)
    assert config.allow_college_view_distribution is True
```

- [ ] **Step 2: Run it and watch it fail**

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_college_view_distribution.py::test_admin_can_toggle_college_view_distribution -p no:cacheprovider -v
```

Expected: FAIL with 404 (route not found) or `KeyError: 'allow_college_view_distribution'`.

- [ ] **Step 3: Add the toggle endpoint**

In `backend/app/api/v1/endpoints/scholarship_configurations.py`, directly after the existing `toggle_configuration_supplementary_import` function (ends ~line 1165), add:

```python
class CollegeViewDistributionToggle(BaseModel):
    allow: bool


@router.patch("/configurations/{id}/college-view-distribution")
async def toggle_configuration_college_view_distribution(
    id: int,
    body: CollegeViewDistributionToggle,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Admin toggle: open or close college visibility of distribution results.

    Applies to all colleges' rankings under this (scholarship_type, academic_year, semester).
    """
    accessible_scholarship_ids = await get_user_accessible_scholarship_ids(current_user, db)

    stmt = select(ScholarshipConfiguration).where(
        and_(
            ScholarshipConfiguration.id == id,
            ScholarshipConfiguration.scholarship_type_id.in_(accessible_scholarship_ids),
        )
    )
    result = await db.execute(stmt)
    config = result.scalar_one_or_none()

    if not config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="配置不存在或您沒有存取權限")

    config.allow_college_view_distribution = body.allow
    config.updated_by = current_user.id
    await db.commit()

    return ApiResponse(
        success=True,
        message=f"College view of distribution {'enabled' if body.allow else 'disabled'}",
        data={"id": config.id, "allow_college_view_distribution": body.allow},
    )
```

(`BaseModel`, `select`, `and_`, `require_admin`, `get_user_accessible_scholarship_ids`, `ApiResponse`, `status`, `HTTPException` are already imported in this file — the supplementary-import endpoint above uses them all.)

- [ ] **Step 4: Surface the flag in config read + generic-update serialization**

In the same file, mirror every `allow_supplementary_import` serialization site with a sibling line:

- Line ~954 (config read dict): add `"allow_college_view_distribution": config.allow_college_view_distribution,`
- Line ~1390 (the other config read dict): add `"allow_college_view_distribution": config.allow_college_view_distribution,`
- Lines ~1054-1055 (generic update path): add
  ```python
          if "allow_college_view_distribution" in config_data:
              config.allow_college_view_distribution = bool(config_data["allow_college_view_distribution"])
  ```

- [ ] **Step 5: Run the test and confirm it passes**

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_college_view_distribution.py::test_admin_can_toggle_college_view_distribution -p no:cacheprovider -v
```

Expected: PASS.

- [ ] **Step 6: Lint + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_college_view_distribution.py
flake8 app --select=B904,B014 --max-line-length=120   # run inside backend/ or the container
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_college_view_distribution.py
git commit -m "feat(api): admin toggle for college-view-distribution + surface flag in config payloads"
```

---

## Task 3: College-facing read endpoint + surface flag in rankings payload

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/distribution.py` (add new endpoint)
- Modify: `backend/app/api/v1/endpoints/college_review/ranking_management.py:184,565`
- Test: `backend/app/tests/test_college_view_distribution.py` (append college section)

**Interfaces:**
- Consumes: `ScholarshipConfiguration.allow_college_view_distribution`; `CollegeRanking` (`scholarship_type_id`, `academic_year`, `semester`, `distribution_executed`, `sub_type_code`); `CollegeRankingItem` (`ranking_id`, `application`, `is_allocated`, `allocated_sub_type`, `backup_allocations`, `status`, `college_rejected`, `rank_position`); `User.college_code`.
- Produces:
  `GET /api/v1/college-review/distribution-results?scholarship_type_id=<int>&academic_year=<int>&semester=<str|null>` →
  ```jsonc
  { "success": true, "message": "...", "data": {
      "distribution_executed": true,
      "sub_types": [ { "code": "nstc", "label": "國科會", "label_en": "NSTC",
        "admitted": [ {"student_number":"310460031","student_name":"王小明","rank_position":1} ],
        "backup":   [ {"student_number":"310460052","student_name":"陳小美","backup_position":1} ],
        "rejected": [ {"student_number":"310460088","student_name":"張三"} ] } ] } }
  ```
  Rankings list payload gains `allow_college_view_distribution: bool`.

- [ ] **Step 1: Write the failing tests (403 off, grouping + scoping on, empty when not executed)**

Append to `backend/app/tests/test_college_view_distribution.py`:

```python
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem

DIST_URL = "/api/v1/college-review/distribution-results"


def _student_data(std_code: str, name: str, academy: str) -> dict:
    return {"std_stdcode": std_code, "std_cname": name, "std_academyno": academy}


@pytest_asyncio.fixture
async def college_client_factory(db: AsyncSession, client: AsyncClient):
    """Return a helper that overrides require_college with a college user bound to `academy`."""

    async def _make(academy: str) -> AsyncClient:
        user = User(
            nycu_id=f"cvd_college_{academy}",
            email=f"cvd_college_{academy}@university.edu",
            name=f"College {academy}",
            user_type=UserType.employee,
            role=UserRole.college,
            college_code=academy,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

        async def override_college():
            return user

        app.dependency_overrides[require_college] = override_college
        return client

    yield _make
    app.dependency_overrides.pop(require_college, None)


async def _seed_distribution(db, sch_type, *, executed: bool):
    """One finalized ranking for sub_type 'nstc' with 3 items in college 'A':
    admitted (rank1), backup (pos1), rejected; plus one admitted student in college 'B'."""
    ranking = CollegeRanking(
        scholarship_type_id=sch_type.id,
        sub_type_code="nstc",
        academic_year=114,
        semester="first",
        ranking_name="nstc 114-1",
        total_applications=4,
        is_finalized=True,
        distribution_executed=executed,
        allocated_count=2,
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    def app_row(sid, name, academy, status="approved"):
        return Application(
            user_id=None,
            scholarship_type_id=sch_type.id,
            academic_year=114,
            semester="first",
            status=status,
            student_data=_student_data(sid, name, academy),
        )

    a_admit = app_row("A001", "王小明", "A")
    a_backup = app_row("A002", "陳小美", "A", status="submitted")
    a_reject = app_row("A003", "張三", "A", status="submitted")
    b_admit = app_row("B001", "他校生", "B")
    for a in (a_admit, a_backup, a_reject, b_admit):
        db.add(a)
    await db.commit()
    for a in (a_admit, a_backup, a_reject, b_admit):
        await db.refresh(a)

    db.add_all([
        CollegeRankingItem(ranking_id=ranking.id, application_id=a_admit.id, rank_position=1,
                           is_allocated=True, allocated_sub_type="nstc", status="allocated"),
        CollegeRankingItem(ranking_id=ranking.id, application_id=a_backup.id, rank_position=2,
                           is_allocated=False, status="waitlisted",
                           backup_allocations=[{"sub_type": "nstc", "backup_position": 1}]),
        CollegeRankingItem(ranking_id=ranking.id, application_id=a_reject.id, rank_position=3,
                           is_allocated=False, status="rejected"),
        CollegeRankingItem(ranking_id=ranking.id, application_id=b_admit.id, rank_position=1,
                           is_allocated=True, allocated_sub_type="nstc", status="allocated"),
    ])
    await db.commit()
    return ranking


@pytest.mark.asyncio
async def test_distribution_results_403_when_flag_off(college_client_factory, config, sch_type, db):
    # config.allow_college_view_distribution defaults to False
    cclient = await college_client_factory("A")
    resp = await cclient.get(DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_distribution_results_grouped_and_college_scoped(college_client_factory, config, sch_type, db):
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=True)

    cclient = await college_client_factory("A")
    resp = await cclient.get(DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["distribution_executed"] is True
    nstc = next(g for g in data["sub_types"] if g["code"] == "nstc")

    admitted_numbers = {s["student_number"] for s in nstc["admitted"]}
    backup_numbers = {s["student_number"] for s in nstc["backup"]}
    rejected_numbers = {s["student_number"] for s in nstc["rejected"]}

    assert admitted_numbers == {"A001"}          # B001 (other college) excluded
    assert backup_numbers == {"A002"}
    assert rejected_numbers == {"A003"}
    assert "B001" not in (admitted_numbers | backup_numbers | rejected_numbers)


@pytest.mark.asyncio
async def test_distribution_results_empty_when_not_executed(college_client_factory, config, sch_type, db):
    config.allow_college_view_distribution = True
    await db.commit()
    await _seed_distribution(db, sch_type, executed=False)

    cclient = await college_client_factory("A")
    resp = await cclient.get(DIST_URL, params={"scholarship_type_id": sch_type.id, "academic_year": 114, "semester": "first"})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["distribution_executed"] is False
    assert data["sub_types"] == []
```

- [ ] **Step 2: Run the new tests and watch them fail**

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_college_view_distribution.py -k distribution_results -p no:cacheprovider -v
```

Expected: FAIL with 404 (route not found).

- [ ] **Step 3: Add the college endpoint**

In `backend/app/api/v1/endpoints/college_review/distribution.py`, append a new route (after `get_distribution_details`). The imports it needs — `select`, `and_`, `selectinload`, `Optional`, `Dict`, `ApiResponse`, `require_college`, `get_db`, `HTTPException`, `status`, `normalize_semester_value`, `CollegeRanking`, `CollegeRankingItem`, `ScholarshipConfiguration`, `ScholarshipType` — are already imported by `get_distribution_details`; additionally add at the top of the file if absent:

```python
from sqlalchemy import func as sa_func
from app.models.application import Application
```

Then add:

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

    Gated by ScholarshipConfiguration.allow_college_view_distribution (admin toggle).
    Scoped to the caller's college_code. Allocation outcome only — no payment PII,
    no allocation-year labels (outcomes for one sub-type are merged across years).
    """
    # Permission first, then read the flag (don't leak flag state to a college
    # with no binding) — same ordering discipline as ranking_management.py.
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

    # Sub-type label metadata
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

    # Rankings for this (type, year, semester)
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
        return ApiResponse(
            success=True,
            message="尚未分發",
            data={"distribution_executed": distribution_executed, "sub_types": []},
        )

    items_stmt = (
        select(CollegeRankingItem)
        .options(selectinload(CollegeRankingItem.application))
        .join(Application, CollegeRankingItem.application_id == Application.id)
        .where(
            CollegeRankingItem.ranking_id.in_(ranking_ids),
            sa_func.json_extract_path_text(Application.student_data, "std_academyno") == college_code,
        )
    )
    items = (await db.execute(items_stmt)).scalars().all()

    groups: Dict[str, Dict[str, list]] = {}

    def bucket(code: str) -> Dict[str, list]:
        if code not in groups:
            groups[code] = {"admitted": [], "backup": [], "rejected": []}
        return groups[code]

    for item in items:
        appn = item.application
        if not appn or not appn.student_data:
            continue
        if appn.status == "deleted" or appn.deleted_at is not None:
            continue
        sd = appn.student_data
        student = {
            "student_number": sd.get("std_stdcode") or sd.get("nycu_id") or "N/A",
            "student_name": sd.get("std_cname") or sd.get("name") or "N/A",
        }
        fallback_code = ranking_sub_type.get(item.ranking_id) or "unallocated"

        if item.status == "rejected" or getattr(item, "college_rejected", False):
            bucket(fallback_code)["rejected"].append(student)
            continue

        handled = False
        if item.is_allocated and item.allocated_sub_type:
            bucket(item.allocated_sub_type)["admitted"].append({**student, "rank_position": item.rank_position})
            handled = True
        if item.backup_allocations and isinstance(item.backup_allocations, list):
            for ba in item.backup_allocations:
                if not isinstance(ba, dict):
                    continue
                st_code = ba.get("sub_type")
                if not st_code:
                    continue
                bucket(st_code)["backup"].append({**student, "backup_position": ba.get("backup_position")})
                handled = True
        if not handled:
            bucket(fallback_code)["rejected"].append(student)

    def meta(code: str) -> Dict[str, str]:
        return label_map.get(code, {"label": code, "label_en": code})

    sub_types = []
    for code in sorted(groups.keys()):
        m = meta(code)
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

    return ApiResponse(
        success=True,
        message="分發結果",
        data={"distribution_executed": True, "sub_types": sub_types},
    )
```

- [ ] **Step 4: Surface the flag in the college rankings payload**

In `backend/app/api/v1/endpoints/college_review/ranking_management.py`, add a sibling key next to `allow_supplementary_import` at BOTH serialization sites (line ~184 and ~565):

```python
                    "allow_college_view_distribution": bool(config and config.allow_college_view_distribution),
```

- [ ] **Step 5: Run the college tests and confirm they pass**

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider -v
```

Expected: all tests PASS (admin toggle + the three distribution-results tests).

- [ ] **Step 6: Lint + commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/api/v1/endpoints/college_review/distribution.py backend/app/api/v1/endpoints/college_review/ranking_management.py backend/app/tests/test_college_view_distribution.py
flake8 app --select=B904,B014 --max-line-length=120
git add backend/app/api/v1/endpoints/college_review/distribution.py backend/app/api/v1/endpoints/college_review/ranking_management.py backend/app/tests/test_college_view_distribution.py
git commit -m "feat(api): college-scoped distribution-results endpoint (admin-gated)"
```

---

## Task 4: Frontend API methods + type

**Files:**
- Modify: `frontend/lib/api/types.ts:352`
- Modify: `frontend/lib/api/modules/college.ts` (~233 and ~522)

**Interfaces:**
- Produces:
  - TS field `allow_college_view_distribution?: boolean` on the config type.
  - `api.college.toggleConfigCollegeViewDistribution(configurationId: number, allow: boolean): Promise<ApiResponse<{ id: number; allow_college_view_distribution: boolean }>>`
  - `api.college.getDistributionResults(params: { scholarshipTypeId: number; academicYear: number; semester?: string }): Promise<ApiResponse<DistributionResults>>`
  - exported type `DistributionResults` (and `DistributionSubTypeGroup`).

- [ ] **Step 1: Add the type field**

In `frontend/lib/api/types.ts`, directly after line 352 (`allow_supplementary_import?: boolean;`) add:

```typescript
  allow_college_view_distribution?: boolean;
```

- [ ] **Step 2: Add the response types + API methods**

In `frontend/lib/api/modules/college.ts`, add the exported types near the top of the module (after existing imports):

```typescript
export interface DistributionStudent {
  student_number: string;
  student_name: string;
  rank_position?: number;
  backup_position?: number;
}

export interface DistributionSubTypeGroup {
  code: string;
  label: string;
  label_en: string;
  admitted: DistributionStudent[];
  backup: DistributionStudent[];
  rejected: DistributionStudent[];
}

export interface DistributionResults {
  distribution_executed: boolean;
  sub_types: DistributionSubTypeGroup[];
}
```

Add `getDistributionResults` after the existing `getDistributionDetails` method (~line 233):

```typescript
    /**
     * College: own college's distribution outcomes (正取/備取/未錄取) by sub-type.
     * GET /api/v1/college-review/distribution-results
     * Admin-gated by ScholarshipConfiguration.allow_college_view_distribution (403 when closed).
     */
    getDistributionResults: async (params: {
      scholarshipTypeId: number;
      academicYear: number;
      semester?: string;
    }): Promise<ApiResponse<DistributionResults>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/college-review/distribution-results",
        {
          params: {
            query: {
              scholarship_type_id: params.scholarshipTypeId,
              academic_year: params.academicYear,
              semester: params.semester,
            },
          },
        }
      );
      return toApiResponse<DistributionResults>(response);
    },
```

Add `toggleConfigCollegeViewDistribution` directly after `toggleConfigSupplementaryImport` (~line 545), mirroring it:

```typescript
    /**
     * Admin: toggle college visibility of distribution results for a configuration.
     * PATCH /api/v1/scholarship-configurations/configurations/{id}/college-view-distribution
     */
    toggleConfigCollegeViewDistribution: async (
      configurationId: number,
      allow: boolean
    ): Promise<ApiResponse<{ id: number; allow_college_view_distribution: boolean }>> => {
      const token = typedClient.getToken();
      const resp = await fetch(
        `/api/v1/scholarship-configurations/configurations/${configurationId}/college-view-distribution`,
        {
          method: "PATCH",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ allow }),
        }
      );
      if (!resp.ok) {
        const err = await resp.json().catch(() => null);
        throw new Error(err?.message || err?.detail || "操作失敗");
      }
      return resp.json();
    },
```

- [ ] **Step 3: Type-check**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no new errors from these files. (The `raw.GET` path string resolves fully after Task 7's `npm run api:generate`; if `tsc` complains the path is unknown before regen, proceed — Task 7 regenerates the schema and Step 3 is re-run there.)

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/api/modules/college.ts
git commit -m "feat(api-client): college distribution-results fetch + admin toggle method"
```

---

## Task 5: Admin Switch UI (DRY via a shared toggle component)

**Files:**
- Create: `frontend/components/admin/config/ConfigToggleSwitch.tsx`
- Modify: `frontend/components/admin-configuration-management.tsx` (~78-162 existing toggle, ~949 usage)
- Test: `frontend/components/__tests__/admin-configuration-management.test.tsx` (extend)

**Interfaces:**
- Consumes: `api.college.toggleConfigSupplementaryImport`, `api.college.toggleConfigCollegeViewDistribution` (Task 4).
- Produces: `ConfigToggleSwitch` reusable component.

- [ ] **Step 1: Extract the generic toggle component**

The existing inline supplementary-import toggle (`admin-configuration-management.tsx:78-162`) is a self-contained ~85-line Switch+tooltip. Extract it into a reusable component. Create `frontend/components/admin/config/ConfigToggleSwitch.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Switch } from "@/components/ui/switch";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export interface ConfigToggleSwitchProps {
  initialOpen: boolean;
  onToggle: (next: boolean) => Promise<unknown>;
  ariaLabel: string;
  onLabel?: string; // default 開放中
  offLabel?: string; // default 已關閉
  successOn: string;
  successOff: string;
  tooltipOn: string;
  tooltipOff: string;
  onChange?: (open: boolean) => void;
}

export function ConfigToggleSwitch({
  initialOpen,
  onToggle,
  ariaLabel,
  onLabel = "開放中",
  offLabel = "已關閉",
  successOn,
  successOff,
  tooltipOn,
  tooltipOff,
  onChange,
}: ConfigToggleSwitchProps) {
  const [open, setOpen] = useState(initialOpen);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    setOpen(initialOpen);
  }, [initialOpen]);

  const handleToggle = async (next: boolean) => {
    const prev = open;
    setOpen(next); // optimistic
    setSaving(true);
    try {
      await onToggle(next);
      toast.success(next ? successOn : successOff);
      onChange?.(next);
    } catch (err) {
      setOpen(prev); // rollback
      toast.error(err instanceof Error ? err.message : "操作失敗");
    } finally {
      setSaving(false);
    }
  };

  return (
    <TooltipProvider delayDuration={250}>
      <Tooltip>
        <TooltipTrigger asChild>
          <div className="inline-flex items-center gap-2.5">
            <Switch
              checked={open}
              disabled={saving}
              onCheckedChange={handleToggle}
              aria-label={ariaLabel}
              className={open ? "data-[state=checked]:bg-emerald-600" : undefined}
            />
            <span
              className={[
                "inline-flex items-center gap-1.5 text-xs font-medium tracking-wide tabular-nums transition-colors",
                open ? "text-emerald-700" : "text-muted-foreground",
              ].join(" ")}
            >
              {saving ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <span className="relative inline-flex h-2 w-2">
                  <span
                    className={[
                      "absolute inline-flex h-full w-full rounded-full opacity-60",
                      open ? "animate-ping bg-emerald-400" : "bg-transparent",
                    ].join(" ")}
                  />
                  <span
                    className={[
                      "relative inline-flex h-2 w-2 rounded-full",
                      open ? "bg-emerald-500" : "bg-muted-foreground/40",
                    ].join(" ")}
                  />
                </span>
              )}
              {open ? onLabel : offLabel}
            </span>
          </div>
        </TooltipTrigger>
        <TooltipContent side="top" className="text-xs">
          {open ? tooltipOn : tooltipOff}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
```

- [ ] **Step 2: Replace the bespoke supplementary toggle with the generic one**

In `admin-configuration-management.tsx`, delete the inline toggle component body (lines ~78-162) and import the new one at the top:

```tsx
import { ConfigToggleSwitch } from "@/components/admin/config/ConfigToggleSwitch";
```

At the existing supplementary usage (~line 949), replace the old element with:

```tsx
                              <ConfigToggleSwitch
                                initialOpen={!!config.allow_supplementary_import}
                                ariaLabel="開放/關閉學院補充匯入"
                                successOn="已開放補充匯入"
                                successOff="已關閉補充匯入"
                                tooltipOn="學院可於分發後上傳新申請學生 Excel；排名接續於現有名單之後"
                                tooltipOff="點擊以開放學院上傳補充申請名單（Excel）"
                                onToggle={(next) =>
                                  api.college.toggleConfigSupplementaryImport(config.id, next)
                                }
                              />
```

- [ ] **Step 3: Add the college-view-distribution toggle next to it**

Immediately after the supplementary `ConfigToggleSwitch`, add:

```tsx
                              <ConfigToggleSwitch
                                initialOpen={!!config.allow_college_view_distribution}
                                ariaLabel="開放/關閉學院查看分發結果"
                                successOn="已開放學院查看分發結果"
                                successOff="已關閉學院查看分發結果"
                                tooltipOn="學院可查看自己學生的分發結果（正取／備取／未錄取）"
                                tooltipOff="點擊以開放學院查看分發結果"
                                onToggle={(next) =>
                                  api.college.toggleConfigCollegeViewDistribution(config.id, next)
                                }
                              />
```

Add a short zh-TW label beside it if the surrounding markup labels the supplementary switch (match the existing layout — e.g. a `<span>開放學院查看分發結果</span>` mirroring how 補充匯入 is labelled).

- [ ] **Step 4: Update the existing component test + add one for the new toggle**

In `frontend/components/__tests__/admin-configuration-management.test.tsx`, the mock already stubs `toggleConfigSupplementaryImport` (line ~92,146). Add a sibling mock:

```typescript
      toggleConfigCollegeViewDistribution: (...args: any[]) =>
        mockToggleCollegeView(...args),
```

and define `mockToggleCollegeView = jest.fn().mockResolvedValue({ success: true, data: {} })`. Add a test asserting that toggling the new Switch (find by `aria-label="開放/關閉學院查看分發結果"`) calls `mockToggleCollegeView` with `(configId, true)`. Mirror the existing supplementary-toggle test in the same file.

- [ ] **Step 5: Run the frontend component tests**

```bash
cd frontend && npx jest admin-configuration-management --silent
```

Expected: existing supplementary test still PASSES (behaviour preserved via the generic component) and the new college-view test PASSES.

- [ ] **Step 6: Commit**

```bash
git add frontend/components/admin/config/ConfigToggleSwitch.tsx frontend/components/admin-configuration-management.tsx frontend/components/__tests__/admin-configuration-management.test.tsx
git commit -m "feat(admin-ui): college-view-distribution toggle via shared ConfigToggleSwitch"
```

---

## Task 6: College "分發結果" tab + panel

**Files:**
- Create: `frontend/components/college/distribution/DistributionResultPanel.tsx`
- Modify: `frontend/components/college/CollegeManagementShell.tsx` (~330-365)

**Interfaces:**
- Consumes: `api.college.getDistributionResults` (Task 4); context `selectedAcademicYear`, `selectedSemester`, `filteredRankings` from `useCollegeManagement()`.
- Produces: `DistributionResultPanel` (props `{ user: User; scholarshipType: { id: number; code: string; name: string } }`).

- [ ] **Step 1: Create the panel**

Create `frontend/components/college/distribution/DistributionResultPanel.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { User } from "@/types/user";
import { useCollegeManagement } from "@/contexts/college-management-context";
import type { DistributionResults } from "@/lib/api/modules/college";

interface DistributionResultPanelProps {
  user: User;
  scholarshipType: { id: number; code: string; name: string };
}

export function DistributionResultPanel({ scholarshipType }: DistributionResultPanelProps) {
  const { selectedAcademicYear, selectedSemester } = useCollegeManagement();
  const [data, setData] = useState<DistributionResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const { apiClient } = await import("@/lib/api");
        const resp = await apiClient.college.getDistributionResults({
          scholarshipTypeId: scholarshipType.id,
          academicYear: selectedAcademicYear,
          semester: selectedSemester,
        });
        if (!cancelled) {
          if (resp.success && resp.data) {
            setData(resp.data);
          } else {
            setError(resp.message || "無法載入分發結果");
          }
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "無法載入分發結果");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [scholarshipType.id, selectedAcademicYear, selectedSemester]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12 text-gray-600">
        <Loader2 className="h-6 w-6 animate-spin text-blue-600 mr-2" />
        載入分發結果中...
      </div>
    );
  }

  if (error) {
    return <div className="py-12 text-center text-sm text-gray-500">{error}</div>;
  }

  if (!data || !data.distribution_executed || data.sub_types.length === 0) {
    return <div className="py-12 text-center text-sm text-gray-500">尚未分發，暫無結果</div>;
  }

  return (
    <div className="space-y-6">
      {data.sub_types.map((group) => (
        <div key={group.code} className="rounded-lg border border-gray-200 bg-white p-4">
          <h3 className="mb-3 text-base font-semibold text-gray-800">{group.label}</h3>

          <Section title="正取" tone="emerald">
            {group.admitted.map((s) => (
              <Row key={`a-${s.student_number}`} order={s.rank_position} name={s.student_name} id={s.student_number} />
            ))}
          </Section>

          <Section title="備取" tone="amber">
            {group.backup.map((s) => (
              <Row key={`b-${s.student_number}`} order={s.backup_position} name={s.student_name} id={s.student_number} />
            ))}
          </Section>

          <Section title="未錄取" tone="gray">
            {group.rejected.map((s) => (
              <Row key={`r-${s.student_number}`} name={s.student_name} id={s.student_number} />
            ))}
          </Section>
        </div>
      ))}
    </div>
  );
}

function Section({
  title,
  tone,
  children,
}: {
  title: string;
  tone: "emerald" | "amber" | "gray";
  children: React.ReactNode;
}) {
  const hasItems = Array.isArray(children) ? children.length > 0 : !!children;
  const toneClass =
    tone === "emerald" ? "text-emerald-700" : tone === "amber" ? "text-amber-700" : "text-gray-500";
  return (
    <div className="mb-3 last:mb-0">
      <p className={`mb-1 text-xs font-semibold ${toneClass}`}>{title}</p>
      {hasItems ? <ul className="space-y-0.5">{children}</ul> : <p className="text-xs text-gray-400">—</p>}
    </div>
  );
}

function Row({ order, name, id }: { order?: number; name: string; id: string }) {
  return (
    <li className="flex items-center gap-2 text-sm text-gray-700">
      {typeof order === "number" && <span className="tabular-nums text-gray-400">{order}.</span>}
      <span>{name}</span>
      <span className="text-xs text-gray-400">({id})</span>
    </li>
  );
}
```

- [ ] **Step 2: Wire the conditional tab into the shell**

In `frontend/components/college/CollegeManagementShell.tsx`:

1. Add the lazy import near the other `dynamic(...)` panels (after `RankingManagementPanel`, ~line 38):

```tsx
const DistributionResultPanel = dynamic(
  () => import("./distribution/DistributionResultPanel").then(mod => ({ default: mod.DistributionResultPanel })),
  {
    loading: () => (
      <div className="flex items-center justify-center py-8">
        <div className="flex items-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-blue-600" />
          <span className="text-gray-600">載入分發結果中...</span>
        </div>
      </div>
    )
  }
);
```

2. Add `filteredRankings` to the `useCollegeManagement()` destructure (~line 60-83).

3. Inside the per-scholarship `TabsContent` (the college branch, ~line 328-365), derive tab visibility and render the tab. Replace the college `<Tabs>` block with one that conditionally shows the third tab:

```tsx
              /* college: 申請審核 + 學生排序 (+ 分發結果 when admin opens it) */
              (() => {
                const showDistribution = filteredRankings.some(
                  r => (r as { allow_college_view_distribution?: boolean }).allow_college_view_distribution === true
                );
                return (
                  <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
                    <TabsList className={`grid w-full ${showDistribution ? "grid-cols-3" : "grid-cols-2"}`}>
                      <TabsTrigger value="review" className="flex items-center gap-2">
                        <GraduationCap className="h-4 w-4" />
                        {locale === "zh" ? "申請審核" : "Application Review"}
                      </TabsTrigger>
                      <TabsTrigger value="ranking" className="flex items-center gap-2">
                        <Trophy className="h-4 w-4" />
                        {locale === "zh" ? "學生排序" : "Student Ranking"}
                      </TabsTrigger>
                      {showDistribution && (
                        <TabsTrigger value="distribution" className="flex items-center gap-2">
                          <Award className="h-4 w-4" />
                          {locale === "zh" ? "分發結果" : "Distribution Result"}
                        </TabsTrigger>
                      )}
                    </TabsList>

                    <TabsContent value="review" className="space-y-6">
                      <ApplicationReviewPanel user={user} scholarshipType={scholarshipType} />
                    </TabsContent>

                    <TabsContent value="ranking" className="space-y-6">
                      <RankingManagementPanel user={user} scholarshipType={scholarshipType} />
                    </TabsContent>

                    {showDistribution && (
                      <TabsContent value="distribution" className="space-y-6">
                        <DistributionResultPanel user={user} scholarshipType={scholarshipType} />
                      </TabsContent>
                    )}
                  </Tabs>
                );
              })()
```

Note: if `activeTab` is `"distribution"` and the admin later closes the flag, the trigger disappears; the existing `<Tabs>` simply renders no content — acceptable. (Optional polish: reset `activeTab` to `"review"` when `showDistribution` becomes false.)

- [ ] **Step 3: Type-check + build**

```bash
cd frontend && npx tsc --noEmit && npm run build
```

Expected: compiles with no new errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/college/distribution/DistributionResultPanel.tsx frontend/components/college/CollegeManagementShell.tsx
git commit -m "feat(college-ui): 分發結果 tab showing own-college distribution outcomes"
```

---

## Task 7: OpenAPI regen + full verification gate

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (regenerated)

- [ ] **Step 1: Ensure the backend is running, then regenerate types**

```bash
docker compose -f docker-compose.dev.yml up -d backend
# wait until http://localhost:8000/openapi.json responds
cd frontend && npm run api:generate
```

Expected: `lib/api/generated/schema.d.ts` now contains the `/api/v1/college-review/distribution-results` path and the `/configurations/{id}/college-view-distribution` path.

- [ ] **Step 2: Re-run frontend type-check against the regenerated schema**

```bash
cd frontend && npx tsc --noEmit
```

Expected: the `raw.GET("/api/v1/college-review/distribution-results", …)` call in `college.ts` type-checks against the generated path.

- [ ] **Step 3: Run the full backend test file once more**

```bash
docker compose -f docker-compose.dev.yml exec backend \
  python -m pytest app/tests/test_college_view_distribution.py -p no:cacheprovider -v
```

Expected: all PASS.

- [ ] **Step 4: Backend lint gate (whole touched tree)**

```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120
```

Expected: clean.

- [ ] **Step 5: Manual smoke (Playwright or by hand)**

Use the `playwright-test-and-debug` skill / seeded users. Verify:
1. As `admin`: open a scholarship config, toggle 「開放學院查看分發結果」 ON.
2. As a college user (e.g. `cs_college`) for that scholarship after distribution is executed: the 「分發結果」 tab appears and lists this college's 正取/備取/未錄取 by sub-type.
3. Toggle OFF as admin → reload college → tab is gone (and the endpoint returns 403 if called directly).
4. Confirm a college only sees its OWN students (no other college's names).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(api): regenerate OpenAPI types for college-view-distribution endpoints"
```

---

## Self-Review

**Spec coverage:**
- Admin per-scholarship toggle → Task 1 (column), Task 2 (PATCH + serialization), Task 5 (admin Switch). ✓
- College-scoped read of 正取/備取/未錄取 by sub-type, no PII, no year label → Task 3 (endpoint), Task 6 (panel). ✓
- Tab visible only when flag on → Task 3 (flag in rankings payload), Task 6 (conditional tab). ✓
- College sees only its own students → Task 3 (`std_academyno == college_code` scoping) + test `test_distribution_results_grouped_and_college_scoped`. ✓
- Type sync + tests + lint → Task 2/3 tests, Task 5 frontend test, Task 7 regen + gates. ✓
- Out-of-scope items (no finalize change, existing `distribution-details` untouched, no global setting, no roster PII) → respected; no task touches them. ✓

**Placeholder scan:** The only intentional fill-in is `<HEAD>` in the migration (Task 1 Step 2-3), which is a value discovered by a real command (`alembic heads`) — not a logic placeholder. All code blocks are complete.

**Type consistency:** `allow_college_view_distribution` used identically across model, payloads, TS type, and toggle data. Endpoint response keys (`distribution_executed`, `sub_types[].{code,label,label_en,admitted,backup,rejected}`, student `{student_number, student_name, rank_position?, backup_position?}`) match the `DistributionResults`/`DistributionSubTypeGroup`/`DistributionStudent` TS types (Task 4) consumed by the panel (Task 6). Toggle method name `toggleConfigCollegeViewDistribution` consistent between Task 4 (def) and Task 5 (use). `getDistributionResults` signature consistent between Task 4 (def) and Task 6 (use).
