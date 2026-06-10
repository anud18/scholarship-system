# College Quota Matrix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show per-college remaining quota (including linked prior-year 共用往年 configs) as a college × config matrix on the admin 造冊分發 (manual distribution) page, live-updated against staged allocations.

**Architecture:** Backend extends the existing `GET /api/v1/manual-distribution/quota-status` payload — each `by_config` entry gains `by_college: {college_code: {total, allocated, remaining}} | null`, computed by a new `consumers_by_college` service method that mirrors `consumers_count`'s two-half consumer partition. Frontend adds a `CollegeQuotaMatrix` component fed entirely from data the panel already loads (`quotaStatus`, `subTypeCols`, `students`, `localAllocations`).

**Tech Stack:** FastAPI + SQLAlchemy (async) + pytest-asyncio; Next.js / React / TypeScript + Tailwind.

**Spec:** `docs/superpowers/specs/2026-06-10-college-quota-matrix-design.md`

**Environment notes:**
- Backend tests run inside the dev container: `docker compose -f docker-compose.dev.yml exec backend python -m pytest <path> -p no:cacheprovider`. If the dev stack isn't running, start it first (see `init-dev-env` project skill). When working in a git worktree whose files the container doesn't mount, run pytest with a venv from the worktree or temporarily point the compose mount at the worktree — do NOT silently skip the test runs.
- Lint gates are HARD (project CLAUDE.md): `uvx --from "black==26.3.1" black --check --line-length=120 backend/app` and `flake8 app --select=B904,B014 --max-line-length=120` (run from `backend/`).
- Git commit messages in English.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `backend/app/services/manual_distribution_service.py` | Modify | Add `consumers_by_college`; extend `get_quota_status` with `by_college` |
| `backend/app/tests/test_manual_distribution_pool_math.py` | Modify | `student_data` param on `_make_application`; tests for `consumers_by_college` |
| `backend/app/tests/test_get_quota_status_shared_pool.py` | Modify | Update exact-shape assertion; tests for `by_college` payload |
| `frontend/lib/api/modules/manual-distribution.ts` | Modify | Align `ConfigQuota`/`CollegeQuota` types with the real payload |
| `frontend/components/admin/manual-distribution/CollegeQuotaMatrix.tsx` | Create | The matrix table component (pure render from props) |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Modify | Pull `academies` from `useReferenceData`; render the matrix |

---

### Task 1: Backend — `consumers_by_college`

**Files:**
- Modify: `backend/app/tests/test_manual_distribution_pool_math.py` (builder at `_make_application`, new test section at end of file)
- Modify: `backend/app/services/manual_distribution_service.py` (insert after `consumers_count`, i.e. after line ~226)

- [ ] **Step 1: Extend the `_make_application` builder to accept `student_data`**

In `backend/app/tests/test_manual_distribution_pool_math.py`, change the builder signature and constructor call:

```python
async def _make_application(
    db: AsyncSession,
    *,
    user_id: int,
    scholarship_type_id: int,
    academic_year: int,
    sub_scholarship_type: str,
    is_renewal: bool,
    status: ApplicationStatus,
    app_id: str,
    allocation_config_id: int | None = None,
    student_data: dict | None = None,
) -> Application:
    app = Application(
        app_id=app_id,
        user_id=user_id,
        scholarship_type_id=scholarship_type_id,
        sub_type_selection_mode="single",
        sub_scholarship_type=sub_scholarship_type,
        academic_year=academic_year,
        semester=None,
        status=status,
        is_renewal=is_renewal,
        allocation_config_id=allocation_config_id,
        agree_terms=True,
        student_data=student_data,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app
```

(Only two lines change: the new keyword parameter and `student_data=student_data` in the constructor. Existing callers pass no `student_data` and are unaffected.)

- [ ] **Step 2: Write the failing tests**

Append to `backend/app/tests/test_manual_distribution_pool_math.py`:

```python
# --------------------------------------------------------------------------- #
# 2.4 consumers_by_college — per-college split of consumers_count
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_consumers_by_college_attributes_winner_and_renewal(db: AsyncSession):
    st = await _make_type(db, code="cbc1")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="cbc1_115",
        academic_year=115,
        quotas={"nstc": {"E": 5, "C": 5}},
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)

    u1 = await _make_user(db, nycu_id="cbc1s1")
    winner = await _make_application(
        db,
        user_id=u1.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-10001",
        student_data={"std_academyno": "E"},
    )
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=winner.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )

    u2 = await _make_user(db, nycu_id="cbc1s2")
    await _make_application(
        db,
        user_id=u2.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-10002",
        allocation_config_id=cfg.id,
        student_data={"std_academyno": "C"},
    )

    svc = ManualDistributionService(db)
    assert await svc.consumers_by_college(cfg.id, "nstc") == {"E": 1, "C": 1}


@pytest.mark.asyncio
async def test_consumers_by_college_missing_academyno_lands_in_empty_bucket(db: AsyncSession):
    st = await _make_type(db, code="cbc2")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="cbc2_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    u = await _make_user(db, nycu_id="cbc2s1")
    # student_data omitted entirely (None) — must land in the "" bucket
    winner = await _make_application(
        db,
        user_id=u.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-10003",
    )
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=winner.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )

    svc = ManualDistributionService(db)
    assert await svc.consumers_by_college(cfg.id, "nstc") == {"": 1}


@pytest.mark.asyncio
async def test_consumers_by_college_renewal_with_ranking_item_counted_once(db: AsyncSession):
    """Mirror of the consumers_count is_renewal partition guard: a restored
    renewal has BOTH an approved renewal Application and an allocated
    CollegeRankingItem — it must be attributed exactly once."""
    st = await _make_type(db, code="cbc3")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="cbc3_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    u = await _make_user(db, nycu_id="cbc3s1")
    renewal = await _make_application(
        db,
        user_id=u.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-10004",
        allocation_config_id=cfg.id,
        student_data={"std_academyno": "E"},
    )
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=renewal.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )

    svc = ManualDistributionService(db)
    assert await svc.consumers_by_college(cfg.id, "nstc") == {"E": 1}


@pytest.mark.asyncio
async def test_consumers_by_college_sums_to_consumers_count(db: AsyncSession):
    """Drift tripwire (spec invariant): the per-college split MUST stay
    filter-identical to consumers_count."""
    st = await _make_type(db, code="cbc4")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="cbc4_115",
        academic_year=115,
        quotas={"nstc": {"E": 5, "C": 5}},
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    for i, (college, is_renewal) in enumerate([("E", False), ("C", False), ("E", True)]):
        u = await _make_user(db, nycu_id=f"cbc4s{i}")
        app = await _make_application(
            db,
            user_id=u.id,
            scholarship_type_id=st.id,
            academic_year=115,
            sub_scholarship_type="nstc",
            is_renewal=is_renewal,
            status=ApplicationStatus.approved if is_renewal else ApplicationStatus.submitted,
            app_id=f"APP-115-0-1010{i}",
            allocation_config_id=cfg.id if is_renewal else None,
            student_data={"std_academyno": college},
        )
        if not is_renewal:
            await _make_item(
                db,
                ranking_id=ranking.id,
                application_id=app.id,
                rank=i + 1,
                is_allocated=True,
                allocated_sub_type="nstc",
                allocation_config_id=cfg.id,
            )

    svc = ManualDistributionService(db)
    by_college = await svc.consumers_by_college(cfg.id, "nstc")
    assert by_college == {"E": 2, "C": 1}
    assert sum(by_college.values()) == await svc.consumers_count(cfg.id, "nstc")
```

- [ ] **Step 3: Run the new tests to verify they fail**

Run (from repo root, dev container):
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_manual_distribution_pool_math.py -k consumers_by_college -p no:cacheprovider -q
```
Expected: 4 FAILED with `AttributeError: 'ManualDistributionService' object has no attribute 'consumers_by_college'`.

- [ ] **Step 4: Implement `consumers_by_college`**

In `backend/app/services/manual_distribution_service.py`, insert directly after the `consumers_count` method (after its `return int(winners) + int(renewals)`, before `remaining`):

```python
    async def consumers_by_college(self, config_id: int, sub_type: str) -> dict[str, int]:
        """Per-college split of consumers_count — SAME two-half partition.

        Attribution: application.student_data["std_academyno"]; a missing or
        empty academyno lands in the "" bucket (rendered 未知 in the UI).
        Invariant (tripwire-tested): sum(values) == consumers_count(config_id,
        sub_type) — keep the filters of both methods identical.
        """
        winners_stmt = (
            select(Application.student_data)
            .join(CollegeRankingItem, CollegeRankingItem.application_id == Application.id)
            .where(
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocated_sub_type == sub_type,
                CollegeRankingItem.allocation_config_id == config_id,
                Application.is_renewal.is_(False),
            )
        )
        renewals_stmt = select(Application.student_data).where(
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.approved,
            Application.sub_scholarship_type == sub_type,
            Application.allocation_config_id == config_id,
        )
        counts: dict[str, int] = {}
        for stmt in (winners_stmt, renewals_stmt):
            for (student_data,) in (await self.db.execute(stmt)).all():
                college = (student_data or {}).get("std_academyno", "") or ""
                counts = {**counts, college: counts.get(college, 0) + 1}
        return counts
```

(All names used — `select`, `Application`, `CollegeRankingItem`, `ApplicationStatus` — are already imported at the top of this module.)

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_manual_distribution_pool_math.py -p no:cacheprovider -q
```
Expected: all tests in the file PASS (the 4 new ones plus the pre-existing ones — the builder change must not break them).

- [ ] **Step 6: Lint**

Run from `backend/`:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py
flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean). If black fails, run it without `--check` and re-verify.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py
git commit -m "feat: add consumers_by_college per-college consumer split"
```

---

### Task 2: Backend — `by_college` in `get_quota_status`

**Files:**
- Modify: `backend/app/tests/test_get_quota_status_shared_pool.py`
- Modify: `backend/app/services/manual_distribution_service.py` (`get_quota_status`, lines ~488-557)

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_get_quota_status_shared_pool.py` (the `setup` fixture already provides `own` = phd_115 with `quotas={"nstc": {"A": 3}, "moe_1w": {"A": 4}}` sharing from `prior` = phd_114 with `quotas={"nstc": {"A": 2}}`):

```python
@pytest.mark.asyncio
async def test_quota_status_by_college_matrix_and_linked_config(db: AsyncSession, setup):
    sch, own, prior = setup["sch"], setup["own"], setup["prior"]
    # Approved renewal consuming the LINKED prior config, attributed to college A.
    user = User(
        nycu_id="qs_bc",
        name="BC",
        email="qs_bc@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    ren = Application(
        app_id="APP-115-0-bc",
        user_id=user.id,
        scholarship_type_id=sch.id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=115,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=True,
        allocation_config_id=prior.id,
        agree_terms=True,
        student_data={"std_academyno": "A"},
    )
    db.add(ren)
    await db.commit()

    svc = ManualDistributionService(db)
    status = await svc.get_quota_status(sch.id, 115, "yearly")
    by_cfg = {c["config_id"]: c for c in status["nstc"]["by_config"]}

    # Own config: college A untouched (3/0/3).
    assert by_cfg[own.id]["by_college"] == {"A": {"total": 3, "allocated": 0, "remaining": 3}}
    # Linked prior-year config: its OWN matrix, minus the renewal in college A.
    assert by_cfg[prior.id]["by_college"] == {"A": {"total": 2, "allocated": 1, "remaining": 1}}


@pytest.mark.asyncio
async def test_quota_status_by_college_unknown_college_negative_remaining(db: AsyncSession, setup):
    sch, own = setup["sch"], setup["own"]
    # Consumer whose student_data has no academyno: "" bucket, total 0 → remaining -1.
    user = User(
        nycu_id="qs_uk",
        name="UK",
        email="qs_uk@u.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    ren = Application(
        app_id="APP-115-0-uk",
        user_id=user.id,
        scholarship_type_id=sch.id,
        scholarship_subtype_list=["nstc"],
        sub_type_selection_mode=SubTypeSelectionMode.single,
        sub_scholarship_type="nstc",
        academic_year=115,
        semester=None,
        status=ApplicationStatus.approved,
        review_stage=ReviewStage.quota_distributed,
        is_renewal=True,
        allocation_config_id=own.id,
        agree_terms=True,
        student_data={},
    )
    db.add(ren)
    await db.commit()

    svc = ManualDistributionService(db)
    status = await svc.get_quota_status(sch.id, 115, "yearly")
    by_cfg = {c["config_id"]: c for c in status["nstc"]["by_config"]}
    assert by_cfg[own.id]["by_college"] == {
        "A": {"total": 3, "allocated": 0, "remaining": 3},
        "": {"total": 0, "allocated": 1, "remaining": -1},
    }


@pytest.mark.asyncio
async def test_quota_status_by_college_null_for_non_matrix_config(db: AsyncSession):
    sch = ScholarshipType(code="qs_flat", name="QS Flat", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)
    db.add(
        ScholarshipSubTypeConfig(
            scholarship_type_id=sch.id,
            sub_type_code="nstc",
            name="國科會",
            display_order=1,
            is_active=True,
        )
    )
    cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester=None,
        config_name="flat115",
        config_code="flat_115",
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=False,
        quotas={"nstc": 20},
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    svc = ManualDistributionService(db)
    status = await svc.get_quota_status(sch.id, 115, "yearly")
    (entry,) = status["nstc"]["by_config"]
    assert entry["by_college"] is None
    assert entry["total"] == 20
```

- [ ] **Step 2: Update the existing exact-shape assertion**

In `test_quota_status_keys_by_config_and_subtracts_renewals` (line ~100), the exact-dict assertion will now miss the new key. The renewal in that test is created WITHOUT `student_data`, so it lands in the `""` (unknown) bucket. Change:

```python
    assert by_cfg[own.id] == {
        "config_id": own.id,
        "config_code": "phd_115",
        "academic_year": 115,
        "is_own": True,
        "total": 3,
        "remaining": 2,
    }
```

to:

```python
    assert by_cfg[own.id] == {
        "config_id": own.id,
        "config_code": "phd_115",
        "academic_year": 115,
        "is_own": True,
        "total": 3,
        "remaining": 2,
        "by_college": {
            "A": {"total": 3, "allocated": 0, "remaining": 3},
            "": {"total": 0, "allocated": 1, "remaining": -1},
        },
    }
```

- [ ] **Step 3: Run to verify the new tests fail**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_get_quota_status_shared_pool.py -p no:cacheprovider -q
```
Expected: new tests FAIL with `KeyError: 'by_college'`; the updated existing test also FAILS (payload doesn't have the key yet).

- [ ] **Step 4: Implement `by_college` in `get_quota_status`**

In `backend/app/services/manual_distribution_service.py`, replace the `by_config` building loop inside `get_quota_status` (currently lines ~538-551):

```python
            by_config = []
            for col in await self.distributable_pool(current_config, sub_type):
                cfg = current_config if col["is_own"] else linked_by_code.get(col["config_code"])
                total = self.pool_total(cfg, sub_type) if cfg is not None else 0
                by_config.append(
                    {
                        "config_id": col["config_id"],
                        "config_code": col["config_code"],
                        "academic_year": col["academic_year"],
                        "is_own": col["is_own"],
                        "total": total,
                        "remaining": col["remaining"],
                    }
                )
```

with:

```python
            by_config = []
            for col in await self.distributable_pool(current_config, sub_type):
                cfg = current_config if col["is_own"] else linked_by_code.get(col["config_code"])
                total = self.pool_total(cfg, sub_type) if cfg is not None else 0
                by_config.append(
                    {
                        "config_id": col["config_id"],
                        "config_code": col["config_code"],
                        "academic_year": col["academic_year"],
                        "is_own": col["is_own"],
                        "total": total,
                        "remaining": col["remaining"],
                        "by_college": await self._college_breakdown(cfg, col["config_id"], sub_type),
                    }
                )
```

Then add this helper method directly after `get_quota_status`:

```python
    async def _college_breakdown(
        self,
        cfg: ScholarshipConfiguration | None,
        config_id: int,
        sub_type: str,
    ) -> dict[str, dict[str, int]] | None:
        """Per-college quota grid for one (config, sub_type) column (advisory).

        None for non-matrix configs (no per-college split exists). Colleges
        appear when they have quota > 0 in the matrix OR live consumers;
        remaining is NOT clamped — negative flags over-allocation in the UI.
        The enforced gate stays the global per-(config, sub_type) recount in
        _assert_round_not_oversubscribed.
        """
        if cfg is None or not cfg.has_college_quota:
            return None
        matrix = (cfg.quotas or {}).get(sub_type, {})
        if not isinstance(matrix, dict):
            matrix = {}
        allocated_by_college = await self.consumers_by_college(config_id, sub_type)

        breakdown: dict[str, dict[str, int]] = {}
        for code in sorted(set(matrix) | set(allocated_by_college)):
            try:
                college_total = int(matrix.get(code, 0) or 0)
            except (TypeError, ValueError):
                college_total = 0
            allocated = allocated_by_college.get(code, 0)
            if college_total <= 0 and allocated <= 0:
                continue
            breakdown = {
                **breakdown,
                code: {
                    "total": college_total,
                    "allocated": allocated,
                    "remaining": college_total - allocated,
                },
            }
        return breakdown
```

- [ ] **Step 5: Run the test file to verify it passes**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_get_quota_status_shared_pool.py -p no:cacheprovider -q
```
Expected: ALL tests PASS.

- [ ] **Step 6: Run the wider service test net**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_manual_distribution_pool_math.py app/tests/test_quota_service_status_math.py -p no:cacheprovider -q
```
Expected: PASS (catches any caller of `get_quota_status` asserting the old shape).

- [ ] **Step 7: Lint**

From `backend/`:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 app/services/manual_distribution_service.py app/tests/test_get_quota_status_shared_pool.py
flake8 app/services/manual_distribution_service.py app/tests/test_get_quota_status_shared_pool.py --select=B904,B014 --max-line-length=120
```
Expected: clean.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/manual_distribution_service.py backend/app/tests/test_get_quota_status_shared_pool.py
git commit -m "feat: add per-college quota breakdown to quota-status payload"
```

---

### Task 3: Frontend — types + `CollegeQuotaMatrix` component

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:46-62`
- Create: `frontend/components/admin/manual-distribution/CollegeQuotaMatrix.tsx`

- [ ] **Step 1: Align the API types with the real payload**

In `frontend/lib/api/modules/manual-distribution.ts`, replace the `CollegeQuota` / `ConfigQuota` block (lines 46-62):

```typescript
export interface CollegeQuota {
  total: number;
  allocated: number;
  remaining: number;
}

/** Quota for one distributable config (own or linked source) under a sub_type. */
export interface ConfigQuota {
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  total: number;
  allocated: number;
  remaining: number;
  by_college: Record<string, CollegeQuota>;
}
```

with:

```typescript
export interface CollegeQuota {
  total: number;
  allocated: number;
  /** total − allocated; NOT clamped — negative means over-allocated (advisory). */
  remaining: number;
}

/** Quota for one distributable config (own or linked source) under a sub_type. */
export interface ConfigQuota {
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  total: number;
  remaining: number;
  /** Per-college grid keyed by college code (""=unknown); null for non-matrix configs. */
  by_college: Record<string, CollegeQuota> | null;
}
```

(`allocated` is dropped from `ConfigQuota` — the backend never sent a config-level `allocated`. Verify nothing reads it: `grep -rn "\.allocated" frontend/components frontend/lib --include="*.ts*" | grep -v by_college` and check any hits aren't on a `ConfigQuota`. Expected: no `ConfigQuota.allocated` usages.)

- [ ] **Step 2: Verify the type change compiles**

Run:
```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. (If errors point at `by_college` now being nullable in some consumer, fix that consumer with a null guard.)

- [ ] **Step 3: Create the component**

Create `frontend/components/admin/manual-distribution/CollegeQuotaMatrix.tsx`:

```tsx
"use client";

import { useMemo } from "react";
import { Building2 } from "lucide-react";
import type {
  CollegeQuota,
  DistributionStudent,
  QuotaStatus,
  SubTypeConfigCol,
} from "@/lib/api/modules/manual-distribution";
import { getAcademyName } from "@/hooks/use-reference-data";

interface CollegeQuotaMatrixProps {
  cols: SubTypeConfigCol[];
  quotaStatus: QuotaStatus;
  students: DistributionStudent[];
  /** ranking_item_id → current local allocation (null = unallocated). */
  localAllocations: Map<number, { sub_type: string; config_id: number } | null>;
  academies: Array<{ code: string; name: string }>;
}

const UNKNOWN_COLLEGE_LABEL = "未知";

function cellKey(collegeCode: string, colKey: string) {
  return `${collegeCode}|${colKey}`;
}

/**
 * College × (sub_type × config) remaining-quota matrix (advisory display).
 *
 * liveRemaining = serverRemaining − Δlocal, where Δlocal counts the UNSAVED
 * difference between each student's current local allocation and their
 * server-saved allocation. The delta form avoids double-counting: server
 * `allocated` already includes saved allocations, and `localAllocations` is
 * seeded from them (plus auto-preview suggestions).
 */
export function CollegeQuotaMatrix({
  cols,
  quotaStatus,
  students,
  localAllocations,
  academies,
}: CollegeQuotaMatrixProps) {
  const localDelta = useMemo(() => {
    const delta: Record<string, number> = {};
    const bump = (college: string, colKey: string, amount: number) => {
      const k = cellKey(college, colKey);
      delta[k] = (delta[k] ?? 0) + amount;
    };
    for (const s of students) {
      const college = s.college_code || "";
      if (s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null) {
        bump(college, `${s.allocated_sub_type}:${s.allocation_config_id}`, -1);
      }
      const local = localAllocations.get(s.ranking_item_id);
      if (local) {
        bump(college, `${local.sub_type}:${local.config_id}`, +1);
      }
    }
    return delta;
  }, [students, localAllocations]);

  const collegeRows = useMemo(() => {
    const codes = new Set<string>();
    for (const stData of Object.values(quotaStatus)) {
      for (const cData of Object.values(stData.by_config)) {
        for (const code of Object.keys(cData.by_college ?? {})) {
          codes.add(code);
        }
      }
    }
    return Array.from(codes).sort((a, b) => a.localeCompare(b));
  }, [quotaStatus]);

  const byColKey = useMemo(() => {
    const map: Record<string, Record<string, CollegeQuota> | null> = {};
    for (const [subType, stData] of Object.entries(quotaStatus)) {
      for (const cData of Object.values(stData.by_config)) {
        map[`${subType}:${cData.config_id}`] = cData.by_college ?? null;
      }
    }
    return map;
  }, [quotaStatus]);

  const resolveCollegeName = (code: string): string => {
    if (!code) return UNKNOWN_COLLEGE_LABEL;
    const fromReference = getAcademyName(code, academies);
    if (fromReference !== code && fromReference !== "-") return fromReference;
    return students.find(s => s.college_code === code)?.college_name || code;
  };

  if (cols.length === 0 || collegeRows.length === 0) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm mb-3">
      <div className="px-4 py-2 border-b border-slate-100 flex items-center justify-between">
        <h3 className="font-bold text-sm text-slate-800 flex items-center gap-2">
          <Building2 className="h-4 w-4 text-[#003d7a]" />
          各學院剩餘名額
        </h3>
        <span className="text-[10px] text-slate-400">
          剩餘/總額；已即時扣除未儲存的勾選；超額僅供參考，鎖定時以全域名額檢查為準
        </span>
      </div>
      <div className="p-3 overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500">
              <th className="text-left font-medium py-1.5 pr-3 whitespace-nowrap">
                學院
              </th>
              {cols.map(col => (
                <th
                  key={col.key}
                  className="text-center font-medium py-1.5 px-2 whitespace-nowrap"
                >
                  {col.display_name}
                  {!col.is_own && (
                    <span className="ml-1 text-[9px] bg-amber-100 text-amber-700 px-1 py-0.5 rounded">
                      共用往年
                    </span>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {collegeRows.map(code => (
              <tr key={code || "__unknown__"} className="border-t border-slate-100">
                <td className="py-1.5 pr-3 font-medium text-slate-700 whitespace-nowrap">
                  {resolveCollegeName(code)}
                </td>
                {cols.map(col => {
                  const entry = byColKey[col.key]?.[code];
                  if (!entry) {
                    return (
                      <td key={col.key} className="py-1.5 px-2 text-center text-slate-300">
                        —
                      </td>
                    );
                  }
                  const liveRemaining =
                    entry.remaining - (localDelta[cellKey(code, col.key)] ?? 0);
                  const tone =
                    liveRemaining < 0
                      ? "text-red-600 font-bold"
                      : liveRemaining === 0
                        ? "text-slate-400"
                        : "text-[#003d7a] font-semibold";
                  return (
                    <td
                      key={col.key}
                      className={`py-1.5 px-2 text-center font-mono tabular-nums ${tone}`}
                      title={`總額 ${entry.total}・已儲存核配 ${entry.allocated}`}
                    >
                      {liveRemaining}/{entry.total}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

**Implementation notes for this step (read before coding):**
- Payload subtlety: the backend sends `by_config` as a **JSON array**, while the TS type says `Record<string, ConfigQuota>`. `Object.values(...)` handles both, which is exactly how the existing `subTypeCols` memo in `ManualDistributionPanel.tsx:224-252` consumes it — the memos above use the same pattern.
- `col.key` is `makeColKey(sub_type, config_id)` = `` `${sub_type}:${config_id}` `` (see `ManualDistributionPanel.tsx:85`) — the `byColKey`/`localDelta` keys above are built with the same `${...}:${...}` template so they line up.
- Verify `getAcademyName` is exported from `@/hooks/use-reference-data` (it is, at line 222) and that `DistributionStudent` is exported from the API module (it is, at line 12).

- [ ] **Step 4: Type-check**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/manual-distribution.ts frontend/components/admin/manual-distribution/CollegeQuotaMatrix.tsx
git commit -m "feat: add CollegeQuotaMatrix component and align quota types"
```

---

### Task 4: Frontend — wire the matrix into `ManualDistributionPanel`

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` (import block ~line 6, `useReferenceData` destructure at line ~126, render block at lines ~1162-1165)

- [ ] **Step 1: Import the component and pull `academies`**

Add to the imports near the other manual-distribution imports (top of file):

```tsx
import { CollegeQuotaMatrix } from "@/components/admin/manual-distribution/CollegeQuotaMatrix";
```

Change line ~126 from:

```tsx
  const { departments } = useReferenceData();
```

to:

```tsx
  const { departments, academies } = useReferenceData();
```

- [ ] **Step 2: Render the matrix after `AvailableQuotasBlock`**

At lines ~1162-1165, directly after:

```tsx
        <AvailableQuotasBlock
          state={distributionState}
          isLoading={isLoadingState}
        />
```

insert:

```tsx
        <CollegeQuotaMatrix
          cols={subTypeCols}
          quotaStatus={quotaStatus}
          students={students}
          localAllocations={localAllocations}
          academies={academies}
        />
```

(`subTypeCols`, `quotaStatus`, `students`, `localAllocations` are all existing state/memos in this component — no new fetches or state.)

- [ ] **Step 3: Type-check + build sanity**

```bash
cd frontend && npx tsc --noEmit
```
Expected: no errors. If `localAllocations`'s `Map<number, LocalAlloc | null>` doesn't structurally satisfy the prop type, the prop type in `CollegeQuotaMatrix.tsx` already matches `LocalAlloc`'s shape (`{ sub_type: string; config_id: number }`) — fix any mismatch by adjusting the prop type, not the panel.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat: show per-college remaining quota matrix on manual distribution page"
```

---

### Task 5: Regenerate OpenAPI types + full verification

**Files:**
- Possibly modify: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Regenerate OpenAPI types**

With the dev backend running on `localhost:8000`:

```bash
cd frontend && npm run api:generate
git diff --stat lib/api/generated/schema.d.ts
```
Expected: likely **no diff** — the quota-status endpoint returns an untyped dict (no `response_model`), so the OpenAPI schema doesn't encode `by_college`. If there IS a diff, `git add lib/api/generated/schema.d.ts` and include it in the commit below.

- [ ] **Step 2: Run the full backend test files touched**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_manual_distribution_pool_math.py app/tests/test_get_quota_status_shared_pool.py app/tests/test_quota_service_status_math.py -p no:cacheprovider -q
```
Expected: ALL PASS.

- [ ] **Step 3: Full lint gate**

From `backend/`:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 app
flake8 app --select=B904,B014 --max-line-length=120
```
Expected: clean.

- [ ] **Step 4: Localhost smoke test (manual / playwright skill)**

Using the project's `playwright-test-and-debug` skill (or manually): log in as the seeded `admin` user at `http://localhost:3000`, open the 造冊分發 panel for a matrix-mode scholarship (PhD), and verify:
1. The 「各學院剩餘名額」 table renders with one column per (sub_type × config), 共用往年 badge on linked prior-year columns.
2. Ticking a 核配 checkbox for a student immediately decrements that student's college cell in the matching column (before saving).
3. Un-ticking restores the number; over-allocating turns the cell red.
4. Save, then confirm the server-refreshed numbers equal the live numbers shown before saving.

Capture a screenshot for the record (per `screenshots-in-worktree` skill if in a worktree).

- [ ] **Step 5: Commit any generated-type diff**

```bash
git add -A && git status --short
git commit -m "chore: regenerate OpenAPI types" # only if schema.d.ts changed
```

---

## Out of scope (per spec)

- Per-college enforcement at allocate/finalize (stays global).
- Changes to `AvailableQuotasBlock` / `/state`.
- College-side (學院端) pages.
