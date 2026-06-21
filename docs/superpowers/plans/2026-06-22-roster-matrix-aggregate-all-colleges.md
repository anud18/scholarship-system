# Matrix Roster — Include All Colleges Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When an admin generates a payment roster for a multi-college matrix scholarship without choosing a specific ranking, include **all** colleges' allocated students in one roster (instead of only the latest-finalized college), and make the preview match what gets generated.

**Architecture:** The defect is in `RosterService._get_eligible_applications` (backend service layer): in matrix mode with no `ranking_id` it picks a single `CollegeRanking` via `.order_by(finalized_at.desc()).first()`. Fix: aggregate **all** `is_finalized + distribution_executed` rankings for the (type, year) and select every `is_allocated` item via `.in_(ranking_ids)`. The per-item sub_type/amount derivation in `_create_roster_item` already works per-application when `roster.ranking_id` is NULL, so a single mixed-sub_type roster is correct. Separately, `preview_roster_students` (endpoint layer) has its own divergent single-ranking auto-detect — remove it so the preview delegates to the same selector.

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy (sync `Session`), pytest (in-memory SQLite via `app/tests/conftest.py`).

## Global Constraints

- **Decision B1:** one roster containing all colleges, mixed sub_type (uses existing `STD_UP_MIXLISTA` Excel template). Do NOT split per sub_type in this path.
- **Roster contains only allocated students:** keep the `CollegeRankingItem.is_allocated.is_(True)` filter. Do not add un-allocated / backup students.
- **Explicit `ranking_id` unchanged:** when a caller passes a specific `ranking_id`, still scope to that single ranking.
- **Do NOT change:** `generate_rosters_from_distribution` (the 獎學金分發 path), `RosterCreateRequest` schema, frontend, semester filtering, borrowed-quota per-item snapshots, `backup_info`.
- **Tests assert on observable I/O only** (`PaymentRoster.total_applications`, `PaymentRosterItem` rows / source text) — never on the private helper signature. Follows the leaf-node-containment philosophy already documented in `test_roster_service_generation.py`.
- **Running backend tests (host, from the worktree).** The dev container mounts `main`, not this worktree, and lacks pytest. Run on the host from the worktree `backend/` dir, supplying dummy settings env vars (conftest swaps in SQLite at import) and disabling the 20% coverage gate for focused runs:

  ```bash
  cd backend && \
  DATABASE_URL='sqlite:///:memory:' DATABASE_URL_SYNC='sqlite:///:memory:' \
  SECRET_KEY='test-secret-key-at-least-32-characters-long-xx' \
  MINIO_ACCESS_KEY='test' MINIO_SECRET_KEY='test' ENVIRONMENT='test' \
  python3 -m pytest <target> -q --no-cov
  ```

  This is referenced below as **[TEST CMD]** `<target>`.

---

## File Structure

- **Modify** `backend/app/services/roster_service.py` — `_get_eligible_applications` (lines 674–712): aggregate all rankings when `ranking_id is None`.
- **Modify** `backend/app/api/v1/endpoints/payment_rosters.py` — `preview_roster_students` (lines 591–606): delete the self-contained single-ranking auto-detect; delegate to the service.
- **Create** `backend/app/tests/test_roster_matrix_aggregate_all_colleges.py` — behavioural tests for the service change.
- **Create** `backend/app/tests/test_roster_preview_ranking_consistency.py` — source-invariant test for the endpoint change.

---

## Task 1: Aggregate all colleges in `_get_eligible_applications`

**Files:**
- Modify: `backend/app/services/roster_service.py:674-712`
- Test: `backend/app/tests/test_roster_matrix_aggregate_all_colleges.py`

**Interfaces:**
- Consumes: `RosterService.generate_roster(scholarship_configuration_id:int, period_label:str, roster_cycle:RosterCycle, academic_year:int, created_by_user_id:int, trigger_type, student_verification_enabled:bool, ranking_id:Optional[int])` → `PaymentRoster` (PROCESSING, not committed). Each eligible application yields one `PaymentRosterItem`; `roster.total_applications == len(eligible applications)`.
- Produces: behaviour relied on by Task 2 — `_get_eligible_applications(config_id, period_label, academic_year, ranking_id=None)` returns **all** colleges' allocated `Application`s.

- [ ] **Step 1: Write the failing tests**

Create `backend/app/tests/test_roster_matrix_aggregate_all_colleges.py`:

```python
"""
Regression + contract tests: matrix-mode roster generation must include ALL
colleges' allocated students, not just the latest-finalized ranking.

Root cause was RosterService._get_eligible_applications: matrix mode with no
ranking_id picked ONE ranking via .order_by(finalized_at.desc()).first(), so a
multi-college distribution (one CollegeRanking per college) produced a roster
covering only the last-finalized college.

Assertions are on observable I/O (PaymentRoster.total_applications,
PaymentRosterItem rows) per the leaf-node-containment philosophy in
test_roster_service_generation.py. A yearly (semester=None) matrix config is
used so the period-based semester filter is skipped, isolating the
multi-college ranking aggregation under test.
"""

from decimal import Decimal
from unittest.mock import patch

import pytest

from app.core.exceptions import RosterGenerationError
from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import QuotaManagementMode
from app.models.payment_roster import PaymentRosterItem, RosterCycle, RosterTriggerType
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType, SubTypeSelectionMode
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService

pytestmark = pytest.mark.integration

YEAR = 114
PERIOD = "114"  # yearly period label → no semester filter


@pytest.fixture
def patch_dependencies():
    """Patch RosterService collaborators so tests stay in-process (mirrors
    test_roster_service_generation.py). verify_student is never called because
    student_verification_enabled=False, but RosterService.__init__ constructs
    StudentVerificationService, and audit_service is invoked during generation."""
    with (
        patch("app.services.roster_service.StudentVerificationService") as svs,
        patch("app.services.roster_service.audit_service"),
    ):
        svs.return_value.verify_student.return_value = {"status": "verified", "verified": True, "data": {}}
        yield


def _admin(db_sync) -> User:
    u = User(nycu_id="matrix_admin", email="matrix_admin@nycu.edu.tw", name="Matrix Admin",
             role=UserRole.admin, user_type=UserType.employee)
    db_sync.add(u); db_sync.commit(); db_sync.refresh(u)
    return u


def _scholarship(db_sync) -> ScholarshipType:
    s = ScholarshipType(code="matrix_sch", name="Matrix Scholarship", description="x")
    db_sync.add(s); db_sync.commit(); db_sync.refresh(s)
    return s


def _matrix_config(db_sync, scholarship) -> ScholarshipConfiguration:
    # semester=None ⇒ yearly ⇒ period-based semester filter skipped.
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id, config_code="MX-114-1", config_name="Matrix Config",
        academic_year=YEAR, semester=None, quota_management_mode=QuotaManagementMode.matrix_based,
        has_quota_limit=False, amount=50000,
    )
    db_sync.add(c); db_sync.commit(); db_sync.refresh(c)
    return c


def _approved_app(db_sync, user, scholarship, config, *, std_code, sub_type) -> Application:
    a = Application(
        user_id=user.id, app_id=f"APP-{std_code}", scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id, academic_year=YEAR, semester=None, status="approved",
        sub_type_selection_mode=SubTypeSelectionMode.single, scholarship_subtype_list=[],
        sub_scholarship_type=sub_type,
        student_data={"std_stdcode": std_code, "std_pid": f"A{std_code}", "std_cname": f"學生{std_code}"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        agree_terms=True, amount=Decimal("50000"),
    )
    db_sync.add(a); db_sync.commit(); db_sync.refresh(a)
    return a


def _ranking(db_sync, scholarship, college_code, *, finalized=True, executed=True) -> CollegeRanking:
    r = CollegeRanking(
        scholarship_type_id=scholarship.id, college_code=college_code, sub_type_code="default",
        academic_year=YEAR, semester=None, ranking_name=f"R-{college_code}",
        is_finalized=finalized, ranking_status="finalized" if finalized else "draft",
        distribution_executed=executed,
    )
    db_sync.add(r); db_sync.commit(); db_sync.refresh(r)
    return r


def _alloc_item(db_sync, ranking, application, *, sub_type, allocated=True):
    it = CollegeRankingItem(
        ranking_id=ranking.id, application_id=application.id, rank_position=1,
        is_allocated=allocated, allocated_sub_type=sub_type if allocated else None,
        allocation_config_id=None, status="allocated" if allocated else "ranked",
    )
    db_sync.add(it); db_sync.commit()
    return it


def _generate(db_sync, config, admin, *, ranking_id=None, period=PERIOD):
    return RosterService(db_sync).generate_roster(
        scholarship_configuration_id=config.id, period_label=period, roster_cycle=RosterCycle.YEARLY,
        academic_year=YEAR, created_by_user_id=admin.id, trigger_type=RosterTriggerType.MANUAL,
        student_verification_enabled=False, ranking_id=ranking_id,
    )


def _item_numbers(db_sync, roster):
    rows = db_sync.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).all()
    return rows


def test_no_ranking_id_aggregates_all_colleges(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A"); rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rA, a2, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin)

    assert roster.total_applications == 3
    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001", "A002", "B001"}


def test_unallocated_students_excluded(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc", allocated=True)
    _alloc_item(db_sync, rA, a2, sub_type="nstc", allocated=False)

    roster = _generate(db_sync, cfg, admin)

    assert roster.total_applications == 1
    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001"}


def test_explicit_ranking_id_scopes_to_that_ranking(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A"); rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin, ranking_id=rA.id)

    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001"}


def test_single_ranking_unchanged(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    a2 = _approved_app(db_sync, admin, sch, cfg, std_code="A002", sub_type="nstc")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rA, a2, sub_type="nstc")

    roster = _generate(db_sync, cfg, admin)

    nums = {i.student_number for i in _item_numbers(db_sync, roster)}
    assert nums == {"A001", "A002"}


def test_aggregation_preserves_per_student_subtype(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    rA = _ranking(db_sync, sch, "A"); rB = _ranking(db_sync, sch, "B")
    a1 = _approved_app(db_sync, admin, sch, cfg, std_code="A001", sub_type="nstc")
    b1 = _approved_app(db_sync, admin, sch, cfg, std_code="B001", sub_type="moe_1w")
    _alloc_item(db_sync, rA, a1, sub_type="nstc")
    _alloc_item(db_sync, rB, b1, sub_type="moe_1w")

    roster = _generate(db_sync, cfg, admin)

    by_num = {i.student_number: i for i in _item_numbers(db_sync, roster)}
    assert by_num["A001"].scholarship_subtype == "nstc"
    assert by_num["B001"].scholarship_subtype == "moe_1w"


def test_no_executed_ranking_raises(db_sync, patch_dependencies):
    admin = _admin(db_sync); sch = _scholarship(db_sync); cfg = _matrix_config(db_sync, sch)
    # No rankings created at all.
    with pytest.raises(RosterGenerationError, match="找不到已執行分發的排名"):
        _generate(db_sync, cfg, admin)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run **[TEST CMD]** `app/tests/test_roster_matrix_aggregate_all_colleges.py`

Expected: `test_no_ranking_id_aggregates_all_colleges` and `test_aggregation_preserves_per_student_subtype` FAIL (current code picks one ranking → only college A appears, so `total_applications == 2` and `B001` missing). The single-ranking / explicit-ranking / 0-ranking tests may already pass. At least the two multi-college tests must fail for the right reason (only one college selected).

- [ ] **Step 3: Implement the aggregation**

In `backend/app/services/roster_service.py`, replace the block at lines 674–712 (the `# 如果沒有提供 ranking_id，自動偵測...` comment through the closing `)` of the single-ranking `query = query.join(...)`):

Replace this existing code:

```python
            # 如果沒有提供 ranking_id，自動偵測最新的已執行分發的 ranking
            if ranking_id is None:
                # 從 period_label 推導學期
                semester = self._extract_semester_from_period(period_label)

                # 查詢最新的已完成分發的 ranking
                ranking = (
                    self.db.query(CollegeRanking)
                    .filter(
                        and_(
                            CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                            CollegeRanking.academic_year == academic_year,
                            CollegeRanking.is_finalized.is_(True),  # 必須已完成
                            CollegeRanking.distribution_executed.is_(True),  # 必須已執行分發
                        )
                    )
                    .order_by(CollegeRanking.finalized_at.desc())
                    .first()
                )

                if not ranking:
                    raise ValueError(
                        f"找不到已執行分發的排名。Matrix 模式獎學金必須先執行矩陣分發才能產生造冊。"
                        f"獎學金類型ID: {config.scholarship_type_id}, 學年度: {academic_year}"
                    )

                ranking_id = ranking.id
                logger.info(
                    f"Auto-detected ranking ID {ranking_id} "
                    f"(finalized at {ranking.finalized_at}, {ranking.allocated_count} students allocated)"
                )

            # 只選取該 ranking 中已分配(正取)的申請
            query = query.join(CollegeRankingItem, CollegeRankingItem.application_id == Application.id).filter(
                and_(
                    CollegeRankingItem.ranking_id == ranking_id,
                    CollegeRankingItem.is_allocated.is_(True),  # 只選正取學生
                )
            )
```

With:

```python
            # 未指定 ranking_id：聚合「所有」已執行分發的排名 → 多學院全院納入。
            # matrix 分發下每個學院各有一份 CollegeRanking；過去只取最新一份
            # (.order_by(finalized_at.desc()).first()) 會讓造冊只含最後鎖定的那一院。
            if ranking_id is None:
                rankings = (
                    self.db.query(CollegeRanking)
                    .filter(
                        and_(
                            CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                            CollegeRanking.academic_year == academic_year,
                            CollegeRanking.is_finalized.is_(True),
                            CollegeRanking.distribution_executed.is_(True),
                        )
                    )
                    .all()
                )

                if not rankings:
                    raise ValueError(
                        f"找不到已執行分發的排名。Matrix 模式獎學金必須先執行矩陣分發才能產生造冊。"
                        f"獎學金類型ID: {config.scholarship_type_id}, 學年度: {academic_year}"
                    )

                ranking_ids = [r.id for r in rankings]
                logger.info(
                    f"Aggregating {len(ranking_ids)} executed ranking(s) {ranking_ids} for "
                    f"all-college roster (type {config.scholarship_type_id}, year {academic_year})"
                )

                # 聚合所有排名的正取申請。一個申請最多屬於一份排名，故 .in_() 不會重複。
                query = query.join(
                    CollegeRankingItem, CollegeRankingItem.application_id == Application.id
                ).filter(
                    and_(
                        CollegeRankingItem.ranking_id.in_(ranking_ids),
                        CollegeRankingItem.is_allocated.is_(True),
                    )
                )
            else:
                # 明確指定排名：僅該排名的正取申請（管理員刻意選擇單一排名）。
                query = query.join(
                    CollegeRankingItem, CollegeRankingItem.application_id == Application.id
                ).filter(
                    and_(
                        CollegeRankingItem.ranking_id == ranking_id,
                        CollegeRankingItem.is_allocated.is_(True),
                    )
                )
```

(The now-unused `semester = self._extract_semester_from_period(period_label)` line is intentionally dropped — that local was computed but never used in this block; semester filtering happens later in the function and is unchanged.)

- [ ] **Step 4: Run the tests to verify they pass**

Run **[TEST CMD]** `app/tests/test_roster_matrix_aggregate_all_colleges.py`

Expected: `6 passed`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_matrix_aggregate_all_colleges.py
git commit -m "fix(roster): aggregate all colleges when generating matrix roster without ranking_id"
```

---

## Task 2: Preview delegates ranking resolution (preview == generate)

**Files:**
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py:591-606`
- Test: `backend/app/tests/test_roster_preview_ranking_consistency.py`

**Interfaces:**
- Consumes: Task 1's aggregating `RosterService._get_eligible_applications(config_id, period_label, academic_year, ranking_id=None)`.
- Produces: nothing downstream; this is the final task.

**Why a source-invariant test:** `preview_roster_students` opens its own `SessionLocal()` (payment_rosters.py:539) instead of the DI-injected test session, so it cannot be driven through the async test client against the in-memory DB. The codebase already guards this endpoint at the source level — see `test_payment_roster_allocation_map.py`. Behavioural coverage of the shared aggregation comes from Task 1.

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_roster_preview_ranking_consistency.py`:

```python
"""Source-invariant guard: preview_roster_students must NOT self-select a single
ranking. It must defer ranking resolution to
RosterService._get_eligible_applications, which (after the all-college fix)
aggregates ALL executed rankings — so the preview matches what generate_roster
produces. Same technique as test_payment_roster_allocation_map.py, used because
preview_roster_students opens its own SessionLocal and is awkward to drive
through the DI test client. Behavioural coverage lives in
test_roster_matrix_aggregate_all_colleges.py."""

from pathlib import Path

ENDPOINT = Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "endpoints" / "payment_rosters.py"


def test_preview_does_not_self_select_single_ranking():
    source = ENDPOINT.read_text(encoding="utf-8")
    # The divergent single-ranking auto-detect (ordered by created_at) must be gone.
    assert "CollegeRanking.created_at.desc()" not in source


def test_preview_delegates_ranking_resolution_to_service():
    source = ENDPOINT.read_text(encoding="utf-8")
    # preview still hands ranking_id (None when unspecified) to the shared selector.
    assert "_get_eligible_applications(" in source
```

- [ ] **Step 2: Run the test to verify it fails**

Run **[TEST CMD]** `app/tests/test_roster_preview_ranking_consistency.py`

Expected: `test_preview_does_not_self_select_single_ranking` FAILS (the string `CollegeRanking.created_at.desc()` is still present at line 601). `test_preview_delegates_ranking_resolution_to_service` PASSES already.

- [ ] **Step 3: Remove the divergent auto-detect**

In `backend/app/api/v1/endpoints/payment_rosters.py`, replace the block at lines 591–606:

Replace this existing code:

```python
        # Auto-detect ranking_id if needed
        if has_matrix_distribution and not ranking_id:
            ranking = (
                db.query(CollegeRanking)
                .filter(
                    and_(
                        CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                        CollegeRanking.distribution_executed.is_(True),
                    )
                )
                .order_by(CollegeRanking.created_at.desc())
                .first()
            )
            if ranking:
                ranking_id = ranking.id
                logger.info(f"Auto-detected ranking_id: {ranking_id}")
```

With:

```python
        # NOTE: 不在此處自挑單一排名。ranking_id 為 None 時交由
        # roster_service._get_eligible_applications 聚合「所有」已執行分發的排名
        # （= 全院），與 generate_roster 走同一條路 → 預覽與產生保證一致。
        # 明確指定 ranking_id 時則只預覽該排名。
```

(`has_matrix_distribution` is still computed above and returned in the response payload; only the single-ranking auto-detect is removed. `ranking_id` flows unchanged into `_get_eligible_applications` at the call site below.)

- [ ] **Step 4: Run the test to verify it passes, then run the full roster suite**

Run **[TEST CMD]** `app/tests/test_roster_preview_ranking_consistency.py`
Expected: `2 passed`.

Then regression-check the roster suites together (omit `--no-cov` here so the coverage gate is satisfied by the larger run):

```bash
cd backend && \
DATABASE_URL='sqlite:///:memory:' DATABASE_URL_SYNC='sqlite:///:memory:' \
SECRET_KEY='test-secret-key-at-least-32-characters-long-xx' \
MINIO_ACCESS_KEY='test' MINIO_SECRET_KEY='test' ENVIRONMENT='test' \
python3 -m pytest app/tests/ -q -k "roster" --no-cov
```

Expected: all selected tests pass (in particular `test_roster_service_generation.py`, `test_roster_distribution_reconcile_*`, `test_payment_roster_allocation_map.py`, and the two new files).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/payment_rosters.py backend/app/tests/test_roster_preview_ranking_consistency.py
git commit -m "fix(roster): preview defers ranking resolution to service so preview matches generation"
```

---

## Post-implementation verification (manual, optional)

The dev container serves `main`, not this worktree, so end-to-end verification against the live app requires re-pointing the container at the worktree (or doing it after merge). To confirm against the existing dev data (4 colleges, 9 allocated), after the fix is live, force-regenerate the 2-person monthly roster and expect 9 items across colleges A/B/C/E:

```bash
docker exec -u root scholarship_backend_dev python -c "REGENERATE roster 15 (period 114-09) with force_regenerate=True"
# then: SELECT count(*) FROM payment_roster_items WHERE roster_id=15;  -- expect 9, not 2
```

The end-to-end script `.claude/skills/playwright-test-and-debug/scripts/verify-multi-college-distribution.js` already exercises ranking→distribution→roster; extend its final assertion from `payment_rosters` batch count to "roster items cover every college's allocated count".

---

## Self-Review

- **Spec coverage:** §4.1 core fix → Task 1. §4.2 per-item sub_type (no change) → asserted by `test_aggregation_preserves_per_student_subtype`. §4.3 preview consistency → Task 2. §3 "only allocated" → `test_unallocated_students_excluded`. §5 behaviour matrix rows → Task 1 tests (0 / 1 / ≥2 rankings, explicit ranking_id). §7 test plan → Tasks 1–2 + post-impl note. §6 deferred items (semester / backup_info / borrowed-quota) → explicitly untouched per Global Constraints.
- **Placeholders:** none — every code/test block is concrete; the post-impl shell line is marked optional/manual.
- **Type consistency:** `_get_eligible_applications(config_id, period_label, academic_year, ranking_id)`, `generate_roster(..., ranking_id=None)`, `PaymentRosterItem.student_number` / `.scholarship_subtype`, `RosterGenerationError`, `RosterCycle.YEARLY` used consistently across tasks and match the source files read during planning.
