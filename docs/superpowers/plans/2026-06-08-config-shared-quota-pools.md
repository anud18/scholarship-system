# Config-Level Shared Quota Pools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace year-list NSTC quota borrowing with config-level shared quota pools — admins link prior configs by code (per sub_type), quota becomes a live global pool, each allocated slot records which config it consumed, and rosters draw 計畫編號 / amount from that consumed config.

**Architecture:** Backend FastAPI + SQLAlchemy (async manual-distribution service, sync roster service) + PostgreSQL; Next.js/React frontend. A new `allocation_config_id` FK replaces the bare `allocation_year` int; a new `shared_quota_sources` config link replaces `prior_quota_years`; a mode-aware live `remaining()/pool()` algorithm with a partition-safe consumer count and a SELECT-FOR-UPDATE quota gate at allocate+finalize; two ordered Alembic migrations (additive+backfill+data-move, then drop). No backward compatibility (project policy).

**Tech Stack:** FastAPI, SQLAlchemy, Alembic, Pydantic v2, PostgreSQL; Next.js / TypeScript / React; pytest (asyncio_mode=auto), Jest; Docker Compose dev (`docker-compose.dev.yml`).

**Source spec:** `docs/superpowers/specs/2026-06-08-config-shared-quota-pools-design.md`

> **Migration ordering (critical):** MIGRATION 1 (Task 1.5) is additive + backfill + project_numbers data-move and must run FIRST. MIGRATION 2 (Task 1.6) drops `college_ranking_items.allocation_year` and `scholarship_configurations.prior_quota_years` and must run LAST — only after every code reader (Phases 3–6) is rewritten. Execute Phase 1 models + MIGRATION 1, then Phases 2–6, then MIGRATION 2.

## Plan reconciliation notes (READ FIRST — these override any contradictory task text)

This plan was drafted by six parallel authors; the following resolves cross-phase overlaps. Where a task body contradicts a note here, **the note wins**.

1. **Pool helpers live ONCE, in Phase 2.** `pool_total`, `consumers_count`, `remaining`, `_resolve_linked_configs`, `_allowed_config_ids`, `distributable_pool`, and `_pick_config` are defined and unit-tested in **Phase 2** and are the single source of truth. **Phase 3 Tasks 3.1–3.3 must NOT redefine them** — skip their "add method" steps; keep only genuinely new code. Canonical contract: `_resolve_linked_configs(config)` and `_allowed_config_ids(requesting_config, sub_type)` are **`async`** (they query the DB to resolve `shared_quota_sources` codes → config rows). **Every Phase 3 call site must `await`** them; do not introduce a sync `_linked_configs` attribute cache.
2. **Delete `_pick_pool` / `_build_remaining_quota` ONCE** — in **Phase 2 Task 2.6**. Phase 3 Task 3.10 must NOT re-delete them (already gone); treat that step as a no-op. Task 3.3's "remove in Task 3.7" cross-reference should read **Task 2.6**.
3. **`SubTypeConfigCol` (TS) is declared ONCE — in Phase 6 Task 6.3**, shape `{config_id, config_code, academic_year, is_own, sub_type, remaining, display_name, total, key}`. **Phase 3 Task 3.11 must NOT declare `SubTypeConfigCol`** — if 3.11 adds a type it adds only the backend `by_config` *response* type (name it `ByConfigQuota`), never the grid column type.
4. **Each §13 backend test file is owned by its Phase 3/4 rewrite task** — `test_distribution_state_endpoint`→3.9, `test_auto_allocate_preview`→3.8, `test_challenge_release_distribution`→4.8, `test_renewal_end_to_end`→4.9, `test_restore_allocation_service`→4.7, `test_roster_distribution_reconcile_service`→4.4. **Task 6.19 is a verification-only gate** (run the whole §13 suite + lint); it does NOT re-edit those files (it may add the small `test_excel_export_*` edit, which no earlier task owns).
5. **Drop the old ORM Column lines with MIGRATION 2.** Tasks 1.1/1.3 keep `allocation_year` / `prior_quota_years` Columns during the additive phase. As the final step of **Task 1.6 (applied LAST, after Phase 6)**, delete `allocation_year = Column(...)` from `college_review.py` and `prior_quota_years = Column(...)` from `scholarship.py` so the ORM matches the post-drop DB.
6. **"Phase 2 migration" / "Phase-2 migration" anywhere is a typo for MIGRATION 2 (Task 1.6).** The destructive drop is Phase 1's second migration file, applied last — never in Phase 2.
7. **Task 1.5 pre-drop audit logs to the alembic migration logger** (a `logger.warning` with orphan counts), NOT an `audit_logs` INSERT (`audit_logs.user_id` is NOT NULL and there is no `details` column — already fixed in the Task 1.5 body).
8. **Concurrency gate (Task 3.5 `_assert_round_not_oversubscribed`):** first line is `await self.db.flush()` (do not rely on autoflush for the recount); lock with a deterministic order — `select(ScholarshipConfiguration).where(ScholarshipConfiguration.id.in_(consumed_ids)).order_by(ScholarshipConfiguration.id).with_for_update()` — to prevent cross-round deadlocks. Add one test that leaves the over-cap write un-flushed.
9. **Approved renewals must never have NULL `allocation_config_id`** (else §6.2 under-counts → over-allocation). `create_renewal_from_previous` (Task 4.6, sole creation path; one non-test caller `renewal.py:183`) sets it with the own-config fallback; additionally, finalize/approval backfills `allocation_config_id = scholarship_configuration_id` for any approved `is_renewal` app found NULL.
10. **Trust quoted source over `:NNN` anchors.** Some line numbers drift ±50 from HEAD (e.g. `roster_service._create_roster_item` is at :764, `_generate_one_sub_type_roster` :1567, `generate_rosters_from_distribution` :1434). Match on the quoted code text.
11. **`renewal.py` needs no code change** (reads `renewal_year` for display only, which stays) — confirm during Phase 4.

---


## Phase 1 — Models + migrations

**Files in this phase:**
- `backend/app/models/college_review.py` — `CollegeRankingItem.allocation_config_id` + relationship (Task 1.1)
- `backend/app/models/application.py` — `Application.allocation_config_id` (Task 1.2)
- `backend/app/models/scholarship.py` — `ScholarshipConfiguration.shared_quota_sources` + `project_numbers` docstring flatten (Task 1.3)
- `backend/app/models/payment_roster.py` — `PaymentRoster.allocation_config_id` + `PaymentRosterItem.allocation_config_id` (Task 1.4)
- `backend/alembic/versions/20260608_shared_quota_pools_add.py` — MIGRATION 1 (additive + backfill, Task 1.5)
- `backend/alembic/versions/20260608_shared_quota_pools_drop.py` — MIGRATION 2 (destructive drops, Task 1.6)
- `backend/tests/test_models_allocation_config.py` — model column unit tests (Tasks 1.1–1.4)
- Smoke: `scripts/reset_database.sh` (Task 1.7)

---

### Task 1.1: Add `allocation_config_id` FK + relationship to `CollegeRankingItem`

**Files:**
- Modify: `backend/app/models/college_review.py:158-180` (matrix distribution fields + relationships block)
- Test: `backend/tests/test_models_allocation_config.py` (Create)

Steps:

- [ ] Write the failing test. Create `backend/tests/test_models_allocation_config.py`:
```python
"""Unit tests for allocation_config_id columns + relationships (shared quota pools, Phase 1).

Pure model-mapper assertions — no DB session needed. Verifies the new FK
columns exist with the contract shape and the CollegeRankingItem.allocation_config
relationship is wired.
"""

from sqlalchemy import inspect as sa_inspect

from app.models.application import Application
from app.models.college_review import CollegeRankingItem
from app.models.payment_roster import PaymentRoster, PaymentRosterItem
from app.models.scholarship import ScholarshipConfiguration


def _column(model, name):
    return sa_inspect(model).columns.get(name)


def test_college_ranking_item_has_allocation_config_id_fk():
    col = _column(CollegeRankingItem, "allocation_config_id")
    assert col is not None, "CollegeRankingItem.allocation_config_id column missing"
    assert col.nullable is True
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "scholarship_configurations"


def test_college_ranking_item_allocation_config_relationship():
    rels = sa_inspect(CollegeRankingItem).relationships
    assert "allocation_config" in rels, "allocation_config relationship missing"
    assert rels["allocation_config"].mapper.class_ is ScholarshipConfiguration
```

- [ ] Run it, expect FAIL. Pure mapper test, no DB needed — run on host:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_college_ranking_item_has_allocation_config_id_fk -p no:cacheprovider -q
```
Expected failure: `AssertionError: CollegeRankingItem.allocation_config_id column missing` (the column does not exist yet).

- [ ] Minimal implementation. In `backend/app/models/college_review.py`, the current matrix-distribution block (lines 158-166) is:
```python
    # Matrix distribution fields
    allocated_sub_type = Column(String(50), nullable=True)  # Sub-type code allocated to (e.g., 'nstc', 'moe_1w')
    allocation_year = Column(
        Integer, nullable=True
    )  # Which academic year's quota was used (e.g., 113 for prior-year supplement)
    backup_position = Column(Integer, nullable=True)  # Backup position (NULL for admitted, 1, 2, 3... for backup)
```
Replace it with (adds `allocation_config_id`; keeps `allocation_year` for now — it is dropped only in MIGRATION 2 / Task 1.6):
```python
    # Matrix distribution fields
    allocated_sub_type = Column(String(50), nullable=True)  # Sub-type code allocated to (e.g., 'nstc', 'moe_1w')
    allocation_year = Column(
        Integer, nullable=True
    )  # DEPRECATED (dropped in shared-quota MIGRATION 2): superseded by allocation_config_id
    allocation_config_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=True
    )  # Which config's quota this slot consumed (NULL only on whole-period sentinel rows)
    backup_position = Column(Integer, nullable=True)  # Backup position (NULL for admitted, 1, 2, 3... for backup)
```

- [ ] Add the relationship. The current relationships block (lines 178-180) is:
```python
    # Relationships using string references to avoid circular imports
    ranking = relationship("CollegeRanking", back_populates="items")
    application = relationship("Application", lazy="select", foreign_keys=[application_id])
```
Replace it with:
```python
    # Relationships using string references to avoid circular imports
    ranking = relationship("CollegeRanking", back_populates="items")
    application = relationship("Application", lazy="select", foreign_keys=[application_id])
    allocation_config = relationship(
        "ScholarshipConfiguration", lazy="select", foreign_keys=[allocation_config_id]
    )
```

- [ ] Run both tests, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest "tests/test_models_allocation_config.py::test_college_ranking_item_has_allocation_config_id_fk" "tests/test_models_allocation_config.py::test_college_ranking_item_allocation_config_relationship" -p no:cacheprovider -q
```
Expected: `2 passed`.

- [ ] Lint the model file:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/app/models/college_review.py && flake8 backend/app/models/college_review.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/app/models/college_review.py backend/tests/test_models_allocation_config.py && git commit -m "feat(model): add CollegeRankingItem.allocation_config_id FK + relationship"
```

---

### Task 1.2: Add `allocation_config_id` FK to `Application`

**Files:**
- Modify: `backend/app/models/application.py:103-106` (renewal fields block)
- Test: `backend/tests/test_models_allocation_config.py` (Modify — append a test)

Steps:

- [ ] Write the failing test. Append to `backend/tests/test_models_allocation_config.py`:
```python
def test_application_has_allocation_config_id_fk():
    col = _column(Application, "allocation_config_id")
    assert col is not None, "Application.allocation_config_id column missing"
    assert col.nullable is True
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "scholarship_configurations"
```

- [ ] Run it, expect FAIL:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_application_has_allocation_config_id_fk -p no:cacheprovider -q
```
Expected failure: `AssertionError: Application.allocation_config_id column missing`.

- [ ] Minimal implementation. In `backend/app/models/application.py`, the current renewal block (lines 103-106) is:
```python
    is_renewal = Column(Boolean, default=False, nullable=False)  # 是否為續領申請
    renewal_year = Column(Integer, nullable=True)  # 續領年份 (e.g. 113)，用於批次匯入時直接指定
    previous_application_id = Column(Integer, ForeignKey("applications.id"))
    challenges_application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
```
Replace it with (adds `allocation_config_id`; `renewal_year` stays — display-only per §9):
```python
    is_renewal = Column(Boolean, default=False, nullable=False)  # 是否為續領申請
    renewal_year = Column(Integer, nullable=True)  # 續領年份 (e.g. 113)，display-only (§9，不再參與配額計算)
    allocation_config_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=True
    )  # Config a renewal consumes (§9); NEVER NULL for an approved renewal
    previous_application_id = Column(Integer, ForeignKey("applications.id"))
    challenges_application_id = Column(Integer, ForeignKey("applications.id"), nullable=True, index=True)
```

- [ ] Run the test, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_application_has_allocation_config_id_fk -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/app/models/application.py && flake8 backend/app/models/application.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/app/models/application.py backend/tests/test_models_allocation_config.py && git commit -m "feat(model): add Application.allocation_config_id FK for renewal consumed config"
```

---

### Task 1.3: Add `shared_quota_sources` to `ScholarshipConfiguration`; reflag `project_numbers` flat (keep `quotas` matrix)

**Files:**
- Modify: `backend/app/models/scholarship.py:546-552` (`project_numbers` + `prior_quota_years` block)
- Test: `backend/tests/test_models_allocation_config.py` (Modify — append a test)

Steps:

- [ ] Write the failing test. Append to `backend/tests/test_models_allocation_config.py`:
```python
def test_scholarship_configuration_has_shared_quota_sources_json():
    col = _column(ScholarshipConfiguration, "shared_quota_sources")
    assert col is not None, "ScholarshipConfiguration.shared_quota_sources column missing"
    assert col.nullable is True
    # quotas matrix stays untouched (per-college matrix is NOT removed)
    assert _column(ScholarshipConfiguration, "quotas") is not None
    # prior_quota_years still present at Phase-1 (dropped in MIGRATION 2)
    assert _column(ScholarshipConfiguration, "prior_quota_years") is not None
```

- [ ] Run it, expect FAIL:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_scholarship_configuration_has_shared_quota_sources_json -p no:cacheprovider -q
```
Expected failure: `AssertionError: ScholarshipConfiguration.shared_quota_sources column missing`.

- [ ] Minimal implementation. In `backend/app/models/scholarship.py`, the current block (lines 546-552) is:
```python
    # 計畫編號設定（矩陣模式）
    project_numbers = Column(
        JSON, nullable=True
    )  # 計畫編號，依子類型及學年度 {"nstc": {"115": "115RXXXXXXX", "114": "114RXXXXXXX"}, "moe_1w": {"115": "115CXXXXXX"}}

    # 各子類型可使用的前年度配額
    prior_quota_years = Column(JSON, nullable=True)  # {"nstc": [113, 112], "moe_1w": []}
```
Replace it with (flat `project_numbers` docstring; add `shared_quota_sources`; `prior_quota_years` retained with a deprecation note — dropped in MIGRATION 2 / Task 1.6; `quotas` matrix is untouched):
```python
    # 計畫編號設定（flat，own-year only）
    project_numbers = Column(
        JSON, nullable=True
    )  # 計畫編號，依子類型 {sub_type: own-year-code} e.g. {"nstc": "114R000001", "moe_1w": "114E000001"}

    # 跨配置共享配額來源（取代 prior_quota_years）— 依 config_code 連結前年度配置，per sub_type，無數量
    shared_quota_sources = Column(
        JSON, nullable=True
    )  # [{"source_config_code": "phd_114", "sub_types": ["nstc"]}, ...]

    # DEPRECATED (dropped in shared-quota MIGRATION 2): superseded by shared_quota_sources
    prior_quota_years = Column(JSON, nullable=True)  # {"nstc": [113, 112], "moe_1w": []}
```

- [ ] Run the test, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_scholarship_configuration_has_shared_quota_sources_json -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/app/models/scholarship.py && flake8 backend/app/models/scholarship.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/app/models/scholarship.py backend/tests/test_models_allocation_config.py && git commit -m "feat(model): add ScholarshipConfiguration.shared_quota_sources; flag project_numbers flat"
```

---

### Task 1.4: Add `allocation_config_id` to `PaymentRoster` and `PaymentRosterItem`

**Files:**
- Modify: `backend/app/models/payment_roster.py:82-85` (`PaymentRoster` matrix fields) and `:208-210` (`PaymentRosterItem` scholarship fields)
- Test: `backend/tests/test_models_allocation_config.py` (Modify — append a test)

Steps:

- [ ] Write the failing test. Append to `backend/tests/test_models_allocation_config.py`:
```python
def test_payment_roster_tables_have_allocation_config_id_fk():
    for model in (PaymentRoster, PaymentRosterItem):
        col = _column(model, "allocation_config_id")
        assert col is not None, f"{model.__name__}.allocation_config_id column missing"
        assert col.nullable is True
        fk = next(iter(col.foreign_keys))
        assert fk.column.table.name == "scholarship_configurations"
        # allocation_year kept as a denormalized display snapshot
        assert _column(model, "allocation_year") is not None
```

- [ ] Run it, expect FAIL:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_payment_roster_tables_have_allocation_config_id_fk -p no:cacheprovider -q
```
Expected failure: `AssertionError: PaymentRoster.allocation_config_id column missing`.

- [ ] Minimal implementation — `PaymentRoster`. The current block (lines 82-85) is:
```python
    # 矩陣分發造冊欄位（多年補發支援）
    sub_type = Column(String(50), nullable=True)  # 獎學金子類型 (e.g. nstc, moe_1w)，非矩陣模式為 NULL
    allocation_year = Column(Integer, nullable=True)  # 消耗配額的學年度，補發時與 academic_year 不同
    project_number = Column(String(100), nullable=True)  # 計畫編號 e.g. 115RXXXXXXX
```
Replace it with (adds `allocation_config_id`; keeps `allocation_year` as display snapshot per §8):
```python
    # 矩陣分發造冊欄位（多年補發支援）
    sub_type = Column(String(50), nullable=True)  # 獎學金子類型 (e.g. nstc, moe_1w)，非矩陣模式為 NULL
    allocation_config_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=True
    )  # 消耗配額的 config (NULL 僅代表 whole-period sentinel)
    allocation_year = Column(
        Integer, nullable=True
    )  # 消耗 config 的 academic_year — 凍結 display snapshot (§8)
    project_number = Column(String(100), nullable=True)  # 計畫編號 e.g. 115RXXXXXXX
```

- [ ] Minimal implementation — `PaymentRosterItem`. The current block (lines 208-210) is:
```python
    allocation_year = Column(Integer, nullable=True)  # 消耗哪一年的配額（補發時不同於 academic_year）
    allocated_sub_type = Column(String(50), nullable=True)  # 分發到的子類型快照 (e.g. nstc, moe_1w)
    application_identity = Column(String(50), nullable=True)  # 申請身分快照 (e.g. "114新申請", "114續領")
```
Replace it with:
```python
    allocation_config_id = Column(
        Integer, ForeignKey("scholarship_configurations.id"), nullable=True
    )  # 消耗配額的 config (NULL 僅代表 whole-period sentinel)
    allocation_year = Column(
        Integer, nullable=True
    )  # 消耗 config 的 academic_year — 凍結 display snapshot (§8)
    allocated_sub_type = Column(String(50), nullable=True)  # 分發到的子類型快照 (e.g. nstc, moe_1w)
    application_identity = Column(String(50), nullable=True)  # 申請身分快照 (e.g. "114新申請", "114續領")
```

- [ ] Update the model-level unique-index comment to reflect the rebuilt index. The current `PaymentRoster.__table_args__` comment block (lines 139-142) is:
```python
    # 唯一約束：每個獎學金配置+期間+子類型+配額學年度只能有一個造冊
    # 實際約束由 migration 建立的 functional unique index 實施：
    # UNIQUE(scholarship_configuration_id, period_label, COALESCE(allocation_year, -1), COALESCE(sub_type, ''))
    __table_args__ = ()
```
Replace it with:
```python
    # 唯一約束：每個獎學金配置+期間+子類型+消耗 config 只能有一個造冊
    # 實際約束由 migration 建立的 functional unique index 實施：
    # UNIQUE(scholarship_configuration_id, period_label, COALESCE(allocation_config_id, -1), COALESCE(sub_type, ''))
    __table_args__ = ()
```

- [ ] Run the test, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py::test_payment_roster_tables_have_allocation_config_id_fk -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Run the full model-test file, expect all PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_models_allocation_config.py -p no:cacheprovider -q
```
Expected: `5 passed`.

- [ ] Lint:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/app/models/payment_roster.py && flake8 backend/app/models/payment_roster.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/app/models/payment_roster.py backend/tests/test_models_allocation_config.py && git commit -m "feat(model): add allocation_config_id to PaymentRoster + PaymentRosterItem"
```

---

### Task 1.5: Alembic MIGRATION 1 — additive columns + backfill + data-move + index rebuild

**Files:**
- Create: `backend/alembic/versions/20260608_shared_quota_pools_add.py`
- Test: `backend/tests/test_migration_shared_quota_pools.py` (Create — pure static assertions on the migration module; full data-path verified by the reset smoke in Task 1.7)

Steps:

- [ ] Write the failing test. Create `backend/tests/test_migration_shared_quota_pools.py`:
```python
"""Static guards for the shared-quota MIGRATION 1 module (Phase 1).

These assert the migration's structural contract without a live DB: correct
down_revision (single verified head), existence-checked DDL, the project_numbers
data-move-BEFORE-flatten ordering, and the rebuilt unique index spec. The full
data backfill is exercised by the reset_database.sh smoke (Task 1.7).
"""

import importlib.util
from pathlib import Path

_MIG = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260608_shared_quota_pools_add.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("mig_shared_quota_add", _MIG)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_migration_file_exists():
    assert _MIG.exists(), f"migration not found: {_MIG}"


def test_down_revision_is_verified_head():
    mod = _load()
    assert mod.down_revision == "20260531_perf_indexes"
    assert mod.revision == "20260608_shared_quota_add"


def test_migration_source_contract():
    src = _MIG.read_text(encoding="utf-8")
    # additive FK columns
    assert "college_ranking_items" in src and "allocation_config_id" in src
    assert "applications" in src
    assert "payment_rosters" in src and "payment_roster_items" in src
    # existence-checked DDL (project convention)
    assert "inspector.get_columns" in src
    # data-move BEFORE flatten ordering marker
    assert src.index("DATA-MOVE") < src.index("FLATTEN")
    # rebuilt unique index keys on allocation_config_id, retains sub_type
    assert "COALESCE(allocation_config_id, -1)" in src
    assert "COALESCE(sub_type, '')" in src
    # 3-way semester normalization helpers are inlined
    assert "'annual'" in src and "'yearly'" in src
    # pre-drop audit log emission
    assert "audit" in src.lower()
```

- [ ] Run it, expect FAIL:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_migration_shared_quota_pools.py::test_migration_file_exists -p no:cacheprovider -q
```
Expected failure: `AssertionError: migration not found: .../20260608_shared_quota_pools_add.py`.

- [ ] Create the migration. Write `backend/alembic/versions/20260608_shared_quota_pools_add.py`:
```python
"""shared quota pools — additive cols + backfill + data-move + index rebuild

Revision ID: 20260608_shared_quota_add
Revises: 20260531_perf_indexes
Create Date: 2026-06-08

MIGRATION 1 of 2 (additive only — destructive drops are in MIGRATION 2,
which runs only AFTER all code stops reading the dropped columns).

Adds allocation_config_id FK to college_ranking_items, applications,
payment_rosters, payment_roster_items, and shared_quota_sources JSON to
scholarship_configurations. Backfills allocation_config_id from the legacy
allocation_year using the same 3-way semester normalization the service uses
(ranking semester {NULL,'annual','yearly'} <-> config semester {NULL,'yearly'}),
tie-breaking ORDER BY id DESC LIMIT 1 (matches get_quota_status). Per-slice
items that fail to resolve are pointed at the requesting config id (never NULL).
Approved renewals backfill from the prior slot's config, falling back to their
own scholarship_configuration_id. Moves prior-year project codes into source
configs BEFORE flattening project_numbers to own-year-only. Converts
prior_quota_years -> shared_quota_sources (dropping links whose target config
does not exist). Re-keys history JSON. Rebuilds the roster unique index.

Existence-checked per project convention; safe to re-run.
"""

from typing import Optional, Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260608_shared_quota_add"
down_revision: Union[str, Sequence[str], None] = "20260531_perf_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- 3-way semester normalization (mirrors manual_distribution_service._*_semester_condition) ---
# ranking/item semester in {NULL, 'annual', 'yearly'}  <->  config semester in {NULL, 'yearly'}
def _config_semester_sql(alias: str) -> str:
    """SQL predicate matching a config row's semester to a yearly/term ranking semester.

    `alias` is the source-row table alias whose .semester we are matching against.
    """
    return (
        f"((cfg.semester IS NULL AND ({alias}.semester IS NULL "
        f"OR {alias}.semester IN ('annual', 'yearly'))) "
        f"OR (cfg.semester = 'yearly' AND ({alias}.semester IS NULL "
        f"OR {alias}.semester IN ('annual', 'yearly'))) "
        f"OR (cfg.semester = {alias}.semester))"
    )


def _add_nullable_fk(inspector, table: str, col: str) -> None:
    cols = [c["name"] for c in inspector.get_columns(table)]
    if col not in cols:
        op.add_column(
            table,
            sa.Column(
                col,
                sa.Integer(),
                sa.ForeignKey("scholarship_configurations.id"),
                nullable=True,
            ),
        )


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ---------- 1. additive FK columns (existence-checked) ----------
    _add_nullable_fk(inspector, "college_ranking_items", "allocation_config_id")
    _add_nullable_fk(inspector, "applications", "allocation_config_id")
    _add_nullable_fk(inspector, "payment_rosters", "allocation_config_id")
    _add_nullable_fk(inspector, "payment_roster_items", "allocation_config_id")

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "shared_quota_sources" not in sc_cols:
        op.add_column(
            "scholarship_configurations",
            sa.Column("shared_quota_sources", sa.JSON(), nullable=True),
        )

    # ---------- 2. backfill college_ranking_items.allocation_config_id ----------
    # Resolve (ranking.scholarship_type_id, academic_year = item.allocation_year, semester)
    # -> ScholarshipConfiguration.id, 3-way semester normalized, tie-break id DESC.
    op.execute(
        f"""
        UPDATE college_ranking_items ri
        SET allocation_config_id = (
            SELECT cfg.id FROM scholarship_configurations cfg
            JOIN college_rankings r ON r.id = ri.ranking_id
            WHERE cfg.scholarship_type_id = r.scholarship_type_id
              AND cfg.academic_year = ri.allocation_year
              AND {_config_semester_sql('r')}
            ORDER BY cfg.id DESC
            LIMIT 1
        )
        FROM college_rankings r2
        WHERE r2.id = ri.ranking_id
          AND ri.allocation_year IS NOT NULL
          AND ri.allocation_config_id IS NULL
        """
    )
    # Per-slice orphans (allocated item with a sub_type but unresolved config) ->
    # requesting config id (the ranking's own-year config); NEVER left NULL.
    op.execute(
        f"""
        UPDATE college_ranking_items ri
        SET allocation_config_id = (
            SELECT cfg.id FROM scholarship_configurations cfg
            JOIN college_rankings r ON r.id = ri.ranking_id
            WHERE cfg.scholarship_type_id = r.scholarship_type_id
              AND cfg.academic_year = r.academic_year
              AND {_config_semester_sql('r')}
            ORDER BY cfg.id DESC
            LIMIT 1
        )
        WHERE ri.allocation_config_id IS NULL
          AND ri.is_allocated = true
          AND ri.allocated_sub_type IS NOT NULL
        """
    )

    # ---------- 3. backfill payment_rosters / payment_roster_items ----------
    for tbl in ("payment_rosters", "payment_roster_items"):
        # roster items resolve via their parent roster's config + period;
        # both tables carry allocation_year + scholarship_configuration_id
        # directly (roster) or via roster_id (item). Resolve through the roster.
        if tbl == "payment_rosters":
            op.execute(
                f"""
                UPDATE payment_rosters pr
                SET allocation_config_id = (
                    SELECT cfg.id FROM scholarship_configurations cfg
                    JOIN scholarship_configurations own ON own.id = pr.scholarship_configuration_id
                    WHERE cfg.scholarship_type_id = own.scholarship_type_id
                      AND cfg.academic_year = pr.allocation_year
                      AND ((cfg.semester IS NULL AND (own.semester IS NULL
                            OR own.semester = 'yearly'))
                        OR (cfg.semester = own.semester))
                    ORDER BY cfg.id DESC
                    LIMIT 1
                )
                WHERE pr.allocation_year IS NOT NULL
                  AND pr.allocation_config_id IS NULL
                """
            )
            # whole-period / unresolved per-slice rosters -> own config (never NULL for sub_type rows)
            op.execute(
                """
                UPDATE payment_rosters pr
                SET allocation_config_id = pr.scholarship_configuration_id
                WHERE pr.allocation_config_id IS NULL
                  AND pr.sub_type IS NOT NULL
                """
            )
        else:
            op.execute(
                """
                UPDATE payment_roster_items pri
                SET allocation_config_id = pr.allocation_config_id,
                    allocation_year = pr.allocation_year
                FROM payment_rosters pr
                WHERE pr.id = pri.roster_id
                  AND pri.allocation_config_id IS NULL
                """
            )

    # ---------- 4. backfill applications.allocation_config_id (renewals) ----------
    # prior slot's config from the previous application's allocated ranking item
    op.execute(
        """
        UPDATE applications a
        SET allocation_config_id = (
            SELECT ri.allocation_config_id
            FROM college_ranking_items ri
            WHERE ri.application_id = a.previous_application_id
              AND ri.allocation_config_id IS NOT NULL
            ORDER BY ri.id DESC
            LIMIT 1
        )
        WHERE a.is_renewal = true
          AND a.allocation_config_id IS NULL
          AND a.previous_application_id IS NOT NULL
        """
    )
    # approved renewals must NEVER be NULL -> fall back to own scholarship_configuration_id
    op.execute(
        """
        UPDATE applications a
        SET allocation_config_id = a.scholarship_configuration_id
        WHERE a.is_renewal = true
          AND a.allocation_config_id IS NULL
          AND a.status = 'approved'
          AND a.scholarship_configuration_id IS NOT NULL
        """
    )

    # ---------- 5. project_numbers DATA-MOVE (before flatten) ----------
    # For every config holding borrowed-year codes
    # (e.g. phd_114.project_numbers["nstc"]["113"] = "113R000001"),
    # push that code into the SOURCE config's own-year entry
    # (phd_113.project_numbers["nstc"] = "113R000001") iff the source config
    # exists and lacks an own-year code. Source configs are matched by same
    # scholarship_type_id + academic_year == the year key. Pure-Python loop so
    # the nested-dict logic is testable and dialect-agnostic.
    configs = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, academic_year, semester, "
                "project_numbers FROM scholarship_configurations"
            )
        ).mappings()
    )
    by_type_year = {(c["scholarship_type_id"], c["academic_year"]): dict(c) for c in configs}
    # working copy of each config's flattened own-year project_numbers
    own_year_pn: dict[int, dict] = {}
    for c in configs:
        pn = c["project_numbers"] or {}
        if isinstance(pn, str):
            import json as _json

            try:
                pn = _json.loads(pn)
            except (ValueError, TypeError):
                pn = {}
        own_year_pn.setdefault(c["id"], {})
        for sub_type, by_year in pn.items():
            if not isinstance(by_year, dict):
                # already flat {sub_type: code} — keep as-is
                if isinstance(by_year, str):
                    own_year_pn[c["id"]][sub_type] = by_year
                continue
            for year_str, code in by_year.items():
                try:
                    year_i = int(year_str)
                except (ValueError, TypeError):
                    continue
                if year_i == c["academic_year"]:
                    # own-year entry -> keep on this config
                    own_year_pn[c["id"]][sub_type] = code
                else:
                    # borrowed-year entry -> push into the source config
                    src = by_type_year.get((c["scholarship_type_id"], year_i))
                    if src is None:
                        continue  # no source config -> code is dropped (logged below)
                    own_year_pn.setdefault(src["id"], {})
                    if not own_year_pn[src["id"]].get(sub_type):
                        own_year_pn[src["id"]][sub_type] = code

    # ---------- 6. FLATTEN: write flattened own-year-only project_numbers ----------
    import json as _json

    for cfg_id, flat in own_year_pn.items():
        bind.execute(
            sa.text("UPDATE scholarship_configurations SET project_numbers = :pn WHERE id = :id"),
            {"pn": _json.dumps(flat) if flat else None, "id": cfg_id},
        )

    # ---------- 7. prior_quota_years -> shared_quota_sources ----------
    dropped_links = 0
    code_by_type_year = {
        (c["scholarship_type_id"], c["academic_year"]): c["config_code"]
        for c in bind.execute(
            sa.text("SELECT scholarship_type_id, academic_year, config_code FROM scholarship_configurations")
        ).mappings()
    }
    pqy_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, prior_quota_years "
                "FROM scholarship_configurations WHERE prior_quota_years IS NOT NULL"
            )
        ).mappings()
    )
    for row in pqy_rows:
        pqy = row["prior_quota_years"]
        if isinstance(pqy, str):
            try:
                pqy = _json.loads(pqy)
            except (ValueError, TypeError):
                pqy = {}
        if not isinstance(pqy, dict):
            continue
        # gather {source_config_code: [sub_types]}
        links: dict[str, list] = {}
        for sub_type, years in pqy.items():
            if not isinstance(years, list):
                continue
            for yr in years:
                code = code_by_type_year.get((row["scholarship_type_id"], yr))
                if code is None:
                    dropped_links += 1  # target config does not exist -> drop link
                    continue
                links.setdefault(code, [])
                if sub_type not in links[code]:
                    links[code].append(sub_type)
        sqs = [{"source_config_code": code, "sub_types": sts} for code, sts in links.items()]
        bind.execute(
            sa.text("UPDATE scholarship_configurations SET shared_quota_sources = :sqs WHERE id = :id"),
            {"sqs": _json.dumps(sqs) if sqs else None, "id": row["id"]},
        )

    # ---------- 8. history JSON re-key allocation_year -> allocation_config_id ----------
    # manual_distribution_history.allocations_snapshot is {ranking_item_id: {sub_type, allocation_year, status}}.
    # Re-key per item using the same (type, year, semester) resolution.
    hist_rows = list(
        bind.execute(
            sa.text(
                "SELECT id, scholarship_type_id, semester, allocations_snapshot "
                "FROM manual_distribution_history WHERE allocations_snapshot IS NOT NULL"
            )
        ).mappings()
    )
    for h in hist_rows:
        snap = h["allocations_snapshot"]
        if isinstance(snap, str):
            try:
                snap = _json.loads(snap)
            except (ValueError, TypeError):
                continue
        if not isinstance(snap, dict):
            continue
        changed = False
        for _item_id, payload in snap.items():
            if not isinstance(payload, dict) or "allocation_year" not in payload:
                continue
            yr = payload.get("allocation_year")
            cfg_id = None
            if yr is not None:
                resolved = bind.execute(
                    sa.text(
                        "SELECT id FROM scholarship_configurations cfg "
                        "WHERE cfg.scholarship_type_id = :stid AND cfg.academic_year = :yr "
                        "AND ((cfg.semester IS NULL AND (:sem IS NULL OR :sem IN ('annual','yearly'))) "
                        "OR (cfg.semester = 'yearly' AND (:sem IS NULL OR :sem IN ('annual','yearly'))) "
                        "OR (cfg.semester = :sem)) "
                        "ORDER BY cfg.id DESC LIMIT 1"
                    ),
                    {"stid": h["scholarship_type_id"], "yr": yr, "sem": h["semester"]},
                ).scalar()
                cfg_id = resolved
            payload["allocation_config_id"] = cfg_id
            payload.pop("allocation_year", None)
            changed = True
        if changed:
            bind.execute(
                sa.text("UPDATE manual_distribution_history SET allocations_snapshot = :s WHERE id = :id"),
                {"s": _json.dumps(snap), "id": h["id"]},
            )

    # ---------- 9. rebuild roster unique index on allocation_config_id ----------
    existing_idx = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
    if "uq_roster_scholarship_period_alloc" in existing_idx:
        op.drop_index("uq_roster_scholarship_period_alloc", table_name="payment_rosters")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_roster_scholarship_period_alloc
        ON payment_rosters (
            scholarship_configuration_id,
            period_label,
            COALESCE(allocation_config_id, -1),
            COALESCE(sub_type, '')
        )
        """
    )

    # ---------- 10. pre-drop audit (fail loud counts; MIGRATION 2 does the drops) ----------
    orphan_items = bind.execute(
        sa.text(
            "SELECT count(*) FROM college_ranking_items "
            "WHERE is_allocated = true AND allocated_sub_type IS NOT NULL "
            "AND allocation_config_id IS NULL"
        )
    ).scalar()
    orphan_renewals = bind.execute(
        sa.text(
            "SELECT count(*) FROM applications "
            "WHERE is_renewal = true AND status = 'approved' AND allocation_config_id IS NULL"
        )
    ).scalar()
    # Pre-drop audit: log orphan counts to the alembic migration logger (crash-proof).
    # NOT an audit_logs INSERT — audit_logs.user_id is NOT NULL and there is no `details`
    # column, so a raw INSERT would abort the migration. See reconciliation note 7.
    import logging as _logging

    _logging.getLogger("alembic.runtime.migration").warning(
        "shared_quota_pools migration audit: orphan_allocated_items=%s "
        "orphan_approved_renewals=%s dropped_shared_quota_links=%s",
        orphan_items,
        orphan_renewals,
        dropped_links,
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_idx = [idx["name"] for idx in inspector.get_indexes("payment_rosters")]
    if "uq_roster_scholarship_period_alloc" in existing_idx:
        op.drop_index("uq_roster_scholarship_period_alloc", table_name="payment_rosters")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_roster_scholarship_period_alloc
        ON payment_rosters (
            scholarship_configuration_id,
            period_label,
            COALESCE(allocation_year, -1),
            COALESCE(sub_type, '')
        )
        """
    )

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "shared_quota_sources" in sc_cols:
        op.drop_column("scholarship_configurations", "shared_quota_sources")

    for table in ("payment_roster_items", "payment_rosters", "applications", "college_ranking_items"):
        cols = [c["name"] for c in inspector.get_columns(table)]
        if "allocation_config_id" in cols:
            op.drop_column(table, "allocation_config_id")


# Section markers referenced by the static migration test (do not remove):
# DATA-MOVE = step 5 (project_numbers move into source configs)
# FLATTEN   = step 6 (project_numbers flattened to own-year only)
```

> Note: the pre-drop audit logs orphan counts via the alembic migration logger (visible in `docker compose -f docker-compose.dev.yml logs backend` during the smoke). It does NOT write to `audit_logs` — that table's `user_id` is NOT NULL and it has no `details` column, so a raw INSERT would abort the migration.

- [ ] Run the static migration tests, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_migration_shared_quota_pools.py -p no:cacheprovider -q
```
Expected: `4 passed`.

- [ ] Lint the migration:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/alembic/versions/20260608_shared_quota_pools_add.py && flake8 backend/alembic/versions/20260608_shared_quota_pools_add.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Verify single linear head (no branch introduced):
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T backend alembic heads
```
Expected: exactly `20260608_shared_quota_add (head)`.

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/alembic/versions/20260608_shared_quota_pools_add.py backend/tests/test_migration_shared_quota_pools.py && git commit -m "feat(migration): MIGRATION 1 — add allocation_config_id + backfill + shared_quota_sources"
```

---

### Task 1.6: Alembic MIGRATION 2 — drop dead columns (`allocation_year`, `prior_quota_years`)

**Files:**
- Create: `backend/alembic/versions/20260608_shared_quota_pools_drop.py`
- Test: `backend/tests/test_migration_shared_quota_pools.py` (Modify — append a static guard)

> ORDERING NOTE (critical): MIGRATION 2 drops `college_ranking_items.allocation_year` and `scholarship_configurations.prior_quota_years`. It is chained after MIGRATION 1 but **must not be applied until ALL code (services/endpoints/seeds/tests in later phases) stops reading those columns**. The migration *file* ships now (so the chain is complete and reviewable); its application is gated by the later phases. The model fields for these two columns are also removed in those later phases — at Phase 1 the model still declares them (Tasks 1.1/1.3 kept them).

Steps:

- [ ] Write the failing test. Append to `backend/tests/test_migration_shared_quota_pools.py`:
```python
_MIG2 = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "20260608_shared_quota_pools_drop.py"
)


def _load2():
    spec = importlib.util.spec_from_file_location("mig_shared_quota_drop", _MIG2)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_drop_migration_chains_after_add():
    assert _MIG2.exists(), f"drop migration not found: {_MIG2}"
    mod = _load2()
    assert mod.down_revision == "20260608_shared_quota_add"
    assert mod.revision == "20260608_shared_quota_drop"
    src = _MIG2.read_text(encoding="utf-8")
    # drops exactly the two dead columns, existence-checked
    assert "college_ranking_items" in src and "allocation_year" in src
    assert "prior_quota_years" in src
    assert "inspector.get_columns" in src
```

- [ ] Run it, expect FAIL:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_migration_shared_quota_pools.py::test_drop_migration_chains_after_add -p no:cacheprovider -q
```
Expected failure: `AssertionError: drop migration not found: .../20260608_shared_quota_pools_drop.py`.

- [ ] Create the migration. Write `backend/alembic/versions/20260608_shared_quota_pools_drop.py`:
```python
"""shared quota pools — DROP dead columns (allocation_year, prior_quota_years)

Revision ID: 20260608_shared_quota_drop
Revises: 20260608_shared_quota_add
Create Date: 2026-06-08

MIGRATION 2 of 2 (destructive). Drops:
  - college_ranking_items.allocation_year   (superseded by allocation_config_id)
  - scholarship_configurations.prior_quota_years (superseded by shared_quota_sources)

ORDERING: this migration's APPLICATION must wait until every service, endpoint,
seed, and test stops reading the two dropped columns (later implementation
phases). The file ships now so the revision chain is complete; do not run it
against an environment whose code still reads allocation_year / prior_quota_years.

payment_rosters.allocation_year and payment_roster_items.allocation_year are
KEPT — repurposed as the denormalized display snapshot (= consumed config's
academic_year). They are intentionally NOT dropped here.

Existence-checked per project convention.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260608_shared_quota_drop"
down_revision: Union[str, Sequence[str], None] = "20260608_shared_quota_add"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cri_cols = [c["name"] for c in inspector.get_columns("college_ranking_items")]
    if "allocation_year" in cri_cols:
        op.drop_column("college_ranking_items", "allocation_year")

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "prior_quota_years" in sc_cols:
        op.drop_column("scholarship_configurations", "prior_quota_years")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    cri_cols = [c["name"] for c in inspector.get_columns("college_ranking_items")]
    if "allocation_year" not in cri_cols:
        op.add_column("college_ranking_items", sa.Column("allocation_year", sa.Integer(), nullable=True))

    sc_cols = [c["name"] for c in inspector.get_columns("scholarship_configurations")]
    if "prior_quota_years" not in sc_cols:
        op.add_column("scholarship_configurations", sa.Column("prior_quota_years", sa.JSON(), nullable=True))
```

- [ ] Run the static test, expect PASS:
```bash
cd /home/howard/scholarship-system/backend && python -m pytest tests/test_migration_shared_quota_pools.py::test_drop_migration_chains_after_add -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint the migration:
```bash
cd /home/howard/scholarship-system && uvx --from "black==26.3.1" black --check --line-length=120 backend/alembic/versions/20260608_shared_quota_pools_drop.py && flake8 backend/alembic/versions/20260608_shared_quota_pools_drop.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean).

- [ ] Verify the chain head advanced to the drop migration:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T backend alembic heads
```
Expected: exactly `20260608_shared_quota_drop (head)`.

- [ ] Commit:
```bash
cd /home/howard/scholarship-system && git add backend/alembic/versions/20260608_shared_quota_pools_drop.py backend/tests/test_migration_shared_quota_pools.py && git commit -m "feat(migration): MIGRATION 2 — drop dead allocation_year + prior_quota_years"
```

---

### Task 1.7: Migration smoke — fresh DB via `reset_database.sh`

> Phase-scope note: the seed scripts still emit `prior_quota_years` + nested `project_numbers` + `CollegeRankingItem(allocation_year=…)` at Phase 1 (the seed rewrite is §11.7, a later phase). Therefore apply MIGRATION 1 only (NOT MIGRATION 2) during this smoke — MIGRATION 1 is additive and backfills, so it must survive a seed that still uses the legacy columns. MIGRATION 2's destructive drops are validated only after the seed/code rewrites land. This task asserts the additive migration upgrades a freshly-seeded DB and the backfill/index/data-move land correctly.

**Files:**
- Modify: none (verification task; uses `scripts/reset_database.sh`)
- Test: manual DB assertions via `psql`

Steps:

- [ ] Pin the smoke to MIGRATION 1 (stop before the destructive drop). Confirm the target revision id:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T backend alembic history | head -5
```
Expected: the top two entries are `20260608_shared_quota_drop` then `20260608_shared_quota_add`.

- [ ] Rebuild the DB volume and run migrations + seed:
```bash
cd /home/howard/scholarship-system && ./scripts/reset_database.sh
```
Expected: completes without error through Alembic upgrade + seed (the additive MIGRATION 1 backfills; if `reset_database.sh` upgrades to head it will also apply MIGRATION 2 — if that fails because the seed still emits `prior_quota_years`, downgrade one step to `20260608_shared_quota_add` with the next command and re-run the seed-independent assertions).

- [ ] If the smoke must stop at MIGRATION 1, pin the revision explicitly after reset:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T backend alembic downgrade 20260608_shared_quota_add && docker compose -f docker-compose.dev.yml exec -T backend alembic current
```
Expected: `current` shows `20260608_shared_quota_add (head)`.

- [ ] Assert the new columns exist on all four tables:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T postgres psql -U scholarship_user -d scholarship_db -c "SELECT table_name, column_name FROM information_schema.columns WHERE column_name='allocation_config_id' ORDER BY table_name;"
```
Expected: rows for `applications`, `college_ranking_items`, `payment_roster_items`, `payment_rosters`.

- [ ] Assert `shared_quota_sources` exists and the rebuilt unique index keys on `allocation_config_id`:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T postgres psql -U scholarship_user -d scholarship_db -c "SELECT 1 FROM information_schema.columns WHERE table_name='scholarship_configurations' AND column_name='shared_quota_sources';" -c "SELECT indexdef FROM pg_indexes WHERE indexname='uq_roster_scholarship_period_alloc';"
```
Expected: `shared_quota_sources` row present; `indexdef` contains `COALESCE(allocation_config_id, '-1'::integer)` and `COALESCE(sub_type, ''::text)`.

- [ ] Assert the project_numbers data-move + flatten preserved `113R000001`/`112R000001` onto the source configs (`phd_113`, `phd_112`) and flattened `phd_114` to own-year only:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T postgres psql -U scholarship_user -d scholarship_db -c "SELECT config_code, project_numbers FROM scholarship_configurations WHERE config_code IN ('phd_112','phd_113','phd_114') ORDER BY config_code;"
```
Expected: `phd_112 → {"nstc":"112R000001"}`, `phd_113 → {"nstc":"113R000001"}`, `phd_114 → {"nstc":"114R000001","moe_1w":"114E000001"}` (no nested year keys remain).

- [ ] Assert `prior_quota_years → shared_quota_sources` converted on `phd_114`, dropping any link whose target config is missing:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T postgres psql -U scholarship_user -d scholarship_db -c "SELECT config_code, shared_quota_sources FROM scholarship_configurations WHERE config_code='phd_114';"
```
Expected: `shared_quota_sources` contains `{"source_config_code":"phd_113","sub_types":["nstc"]}` and `{"source_config_code":"phd_112","sub_types":["nstc"]}` (since the seed creates `phd_112`/`phd_113`); any year with no matching config is absent.

- [ ] Assert the pre-drop audit row was written with sane (zero-or-expected) orphan counts:
```bash
cd /home/howard/scholarship-system && docker compose -f docker-compose.dev.yml exec -T postgres psql -U scholarship_user -d scholarship_db -c "SELECT details FROM audit_logs WHERE action='migration_shared_quota_audit' ORDER BY created_at DESC LIMIT 1;"
```
Expected: a JSON `details` with `orphan_allocated_items`, `orphan_approved_renewals`, `dropped_shared_quota_links` keys; counts are 0 (or a known/expected small number) — investigate the migration backfill if any orphan count is unexpectedly nonzero.

- [ ] No commit (verification only). If any assertion above forced a migration-code fix, re-run the relevant prior task's lint + commit before proceeding.


## Phase 2 — Core pool algorithm

**Files in this phase:**
- Modify: `backend/app/services/manual_distribution_service.py` (add `pool_total`, `consumers_count`, `remaining`, `distributable_pool`, `_allowed_config_ids`, `_pick_config`; delete `_pick_pool`, `_build_remaining_quota`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (new — async pool-math unit tests, `db` fixture)

> Phase prerequisite (from Phase 1, already merged before this phase): `CollegeRankingItem.allocation_config_id`, `Application.allocation_config_id` (both `Integer FK scholarship_configurations.id`, nullable) and `ScholarshipConfiguration.shared_quota_sources` (JSON, nullable) columns exist on the models. Every test below constructs those columns directly.

### Task 2.1: `pool_total` — mode-aware per-(config, sub_type) total

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add `pool_total` method on `ManualDistributionService`, class starts at the `def __init__(self, db: AsyncSession):` at line 199)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Create)

- [ ] Create the test file `backend/app/tests/test_manual_distribution_pool_math.py` with the module header + first failing test for `pool_total`. Write the COMPLETE file:

```python
"""Pool-math unit tests for ManualDistributionService (spec §6.1-6.3).

Covers the live shared-pool helpers: pool_total (matrix vs non-matrix),
consumers_count (the is_renewal partition), remaining (global), and
distributable_pool / _allowed_config_ids / _pick_config (own + linked).

These run under asyncio_mode=auto with the async `db` fixture from conftest.
All models are built directly (no API), so the suite is a focused unit on the
algorithm, not the endpoints.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
from app.models.user import User, UserRole, UserType
from app.services.manual_distribution_service import ManualDistributionService


# --------------------------------------------------------------------------- #
# Builders (return persisted rows; caller commits)
# --------------------------------------------------------------------------- #


async def _make_type(db: AsyncSession, *, code: str) -> ScholarshipType:
    st = ScholarshipType(code=code, name=f"Type {code}", description="t")
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


async def _make_config(
    db: AsyncSession,
    *,
    scholarship_type_id: int,
    config_code: str,
    academic_year: int,
    quotas: dict,
    has_college_quota: bool = True,
    total_quota: int | None = None,
    shared_quota_sources: list | None = None,
) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=None,
        config_name=f"Config {config_code}",
        config_code=config_code,
        amount=30000,
        currency="TWD",
        is_active=True,
        has_college_quota=has_college_quota,
        total_quota=total_quota,
        quotas=quotas,
        shared_quota_sources=shared_quota_sources,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def _make_user(db: AsyncSession, *, nycu_id: str) -> User:
    u = User(
        nycu_id=nycu_id,
        name=f"U {nycu_id}",
        email=f"{nycu_id}@university.edu",
        user_type=UserType.student,
        role=UserRole.student,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


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
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


async def _make_ranking(
    db: AsyncSession, *, scholarship_type_id: int, sub_type_code: str, academic_year: int
) -> CollegeRanking:
    r = CollegeRanking(
        scholarship_type_id=scholarship_type_id,
        sub_type_code=sub_type_code,
        academic_year=academic_year,
        semester=None,
        ranking_name="R",
    )
    db.add(r)
    await db.commit()
    await db.refresh(r)
    return r


async def _make_item(
    db: AsyncSession,
    *,
    ranking_id: int,
    application_id: int,
    rank: int,
    is_allocated: bool,
    allocated_sub_type: str | None,
    allocation_config_id: int | None,
) -> CollegeRankingItem:
    it = CollegeRankingItem(
        ranking_id=ranking_id,
        application_id=application_id,
        rank_position=rank,
        is_allocated=is_allocated,
        allocated_sub_type=allocated_sub_type,
        allocation_config_id=allocation_config_id,
        status="allocated" if is_allocated else "ranked",
    )
    db.add(it)
    await db.commit()
    await db.refresh(it)
    return it


# --------------------------------------------------------------------------- #
# 2.1 pool_total
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pool_total_matrix_sums_colleges(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 15, "C": 12, "A": 8}},
        has_college_quota=True,
    )
    svc = ManualDistributionService(db)
    assert svc.pool_total(cfg, "nstc") == 35


@pytest.mark.asyncio
async def test_pool_total_non_matrix_scalar_then_total_quota(db: AsyncSession):
    st = await _make_type(db, code="simple")
    # scalar quotas[st] wins when present
    scalar_cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="simple_115",
        academic_year=115,
        quotas={"nstc": 20},
        has_college_quota=False,
        total_quota=99,
    )
    # falls back to total_quota when quotas has no scalar for st
    fallback_cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="simple_114",
        academic_year=114,
        quotas={},
        has_college_quota=False,
        total_quota=7,
    )
    svc = ManualDistributionService(db)
    assert svc.pool_total(scalar_cfg, "nstc") == 20
    assert svc.pool_total(fallback_cfg, "nstc") == 7
```

- [ ] Run the test, expect collection-time/attribute FAIL because `pool_total` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_manual_distribution_pool_math.py::test_pool_total_matrix_sums_colleges app/tests/test_manual_distribution_pool_math.py::test_pool_total_non_matrix_scalar_then_total_quota -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute 'pool_total'`

- [ ] Add the `pool_total` method. The current code at `backend/app/models/scholarship.py:694-700` is:

```python
    def get_sub_type_total_quota(self, sub_type: str) -> int:
        """Get total quota for a specific sub-type across all colleges"""
        if not self.has_college_quota or not self.quotas:
            return 0

        sub_type_quotas = self.quotas.get(sub_type, {})
        return sum(sub_type_quotas.values())
```

That helper returns `0` when `has_college_quota` is False, so `pool_total` must NOT call it for the non-matrix branch (spec §6.1 warning). Insert the new method immediately AFTER the `def __init__(self, db: AsyncSession):` block. Read lines 199-210 first to get the exact end of `__init__`, then add directly below it:

```python
    def pool_total(self, config: ScholarshipConfiguration, sub_type: str) -> int:
        """Mode-aware per-(config, sub_type) pool total (spec §6.1).

        matrix_based / college_based (has_college_quota): sum the per-college
        matrix row → same as model.get_sub_type_total_quota.
        simple / none (NOT has_college_quota): quotas[sub_type] is a scalar
        (or fall back to total_quota). get_sub_type_total_quota returns 0 for
        these configs, so we MUST NOT route the non-matrix branch through it —
        a cross-type borrow from such a config would read an empty pool.
        """
        quotas = config.quotas or {}
        if config.has_college_quota:
            sub_type_quotas = quotas.get(sub_type, {})
            if not isinstance(sub_type_quotas, dict):
                return 0
            return sum(sub_type_quotas.values())
        scalar = quotas.get(sub_type, 0)
        try:
            scalar_int = int(scalar)
        except (TypeError, ValueError):
            scalar_int = 0
        return scalar_int or int(config.total_quota or 0)
```

- [ ] Run the two tests, expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_manual_distribution_pool_math.py::test_pool_total_matrix_sums_colleges app/tests/test_manual_distribution_pool_math.py::test_pool_total_non_matrix_scalar_then_total_quota -p no:cacheprovider`
  - Expected: `2 passed`

- [ ] Lint the changed file:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): add pool_total mode-aware helper (spec §6.1)"`

### Task 2.2: `consumers_count` — the is_renewal partition

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add `consumers_count` method directly after `pool_total`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Modify — append tests)

- [ ] Append the consumers partition tests to `backend/app/tests/test_manual_distribution_pool_math.py`:

```python
# --------------------------------------------------------------------------- #
# 2.2 consumers_count — is_renewal partition (spec §6.2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_consumers_general_winner_counted_once(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="s1")
    app = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-00001",
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=app.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
    )
    svc = ManualDistributionService(db)
    assert await svc.consumers_count(cfg.id, "nstc") == 1


@pytest.mark.asyncio
async def test_consumers_renewal_counted_once_via_application_half(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="r1")
    renewal = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-00002",
        allocation_config_id=cfg.id,
    )
    # College builds a ranking item for the renewal too, but is_allocated stays
    # False, so the CollegeRankingItem half must NOT pick it up.
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=renewal.id,
        rank=1,
        is_allocated=False,
        allocated_sub_type=None,
        allocation_config_id=None,
    )
    svc = ManualDistributionService(db)
    assert await svc.consumers_count(cfg.id, "nstc") == 1


@pytest.mark.asyncio
async def test_consumers_revoked_then_restored_renewal_not_double_counted(db: AsyncSession):
    """restore_allocation flips is_allocated=True on any item with an
    allocated_sub_type — including a renewal's item. The is_renewal==False
    guard on the ranking-item half is what keeps this from being counted
    twice (once as a winner, once as the approved-renewal application).
    """
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 10}},
    )
    user = await _make_user(db, nycu_id="r2")
    renewal = await _make_application(
        db,
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-00003",
        allocation_config_id=cfg.id,
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    # Restored renewal item: is_allocated=True with allocated_sub_type set.
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
    # Counted ONCE (via the Application renewal half), not twice.
    assert await svc.consumers_count(cfg.id, "nstc") == 1
```

- [ ] Run the new tests, expect FAIL because `consumers_count` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_consumers_general_winner_counted_once" "app/tests/test_manual_distribution_pool_math.py::test_consumers_renewal_counted_once_via_application_half" "app/tests/test_manual_distribution_pool_math.py::test_consumers_revoked_then_restored_renewal_not_double_counted" -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute 'consumers_count'`

- [ ] Add the `consumers_count` method directly after `pool_total`. For context, `college_review_service.py:636-657` builds a `CollegeRankingItem` for EVERY application including renewals (renewals sorted first) — this is why the ranking-item half needs the explicit `Application.is_renewal.is_(False)` join guard:

```python
    async def consumers_count(self, config_id: int, sub_type: str) -> int:
        """Count every LIVE consumer of (config_id, sub_type) anywhere (spec §6.2).

        Guaranteed two-half partition:
          half 1 — general/manual winners: allocated CollegeRankingItem whose
                   application is NOT a renewal (is_renewal==False guard).
          half 2 — approved renewals: Application(is_renewal, approved).

        The is_renewal==False guard on half 1 is load-bearing:
        college_review_service.py:636-657 creates a CollegeRankingItem for
        every application INCLUDING renewals (sorted first), and
        restore_allocation flips is_allocated=True on any item with an
        allocated_sub_type — so a revoked-then-restored renewal would otherwise
        be counted in BOTH halves.
        """
        winners_stmt = (
            select(func.count(CollegeRankingItem.id))
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocated_sub_type == sub_type,
                CollegeRankingItem.allocation_config_id == config_id,
                Application.is_renewal.is_(False),
            )
        )
        winners = (await self.db.execute(winners_stmt)).scalar_one()

        renewals_stmt = select(func.count(Application.id)).where(
            Application.is_renewal.is_(True),
            Application.status == ApplicationStatus.approved,
            Application.sub_scholarship_type == sub_type,
            Application.allocation_config_id == config_id,
        )
        renewals = (await self.db.execute(renewals_stmt)).scalar_one()

        return int(winners) + int(renewals)
```

- [ ] Run the three tests, expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_consumers_general_winner_counted_once" "app/tests/test_manual_distribution_pool_math.py::test_consumers_renewal_counted_once_via_application_half" "app/tests/test_manual_distribution_pool_math.py::test_consumers_revoked_then_restored_renewal_not_double_counted" -p no:cacheprovider`
  - Expected: `3 passed`

- [ ] Lint:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): add consumers_count is_renewal partition (spec §6.2)"`

### Task 2.3: `remaining` — global live remaining

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add `remaining` method directly after `consumers_count`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Modify — append test)

- [ ] Append the `remaining` test:

```python
# --------------------------------------------------------------------------- #
# 2.3 remaining — global live (spec §6.2)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_remaining_is_pool_total_minus_global_consumers(db: AsyncSession):
    st = await _make_type(db, code="phd")
    cfg = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5, "C": 5}},  # pool_total = 10
    )
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    # 2 general winners
    for i in range(2):
        u = await _make_user(db, nycu_id=f"w{i}")
        a = await _make_application(
            db,
            user_id=u.id,
            scholarship_type_id=st.id,
            academic_year=115,
            sub_scholarship_type="nstc",
            is_renewal=False,
            status=ApplicationStatus.submitted,
            app_id=f"APP-115-0-1000{i}",
        )
        await _make_item(
            db,
            ranking_id=ranking.id,
            application_id=a.id,
            rank=i + 1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=cfg.id,
        )
    # 1 approved renewal
    ru = await _make_user(db, nycu_id="rw")
    await _make_application(
        db,
        user_id=ru.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=True,
        status=ApplicationStatus.approved,
        app_id="APP-115-0-20000",
        allocation_config_id=cfg.id,
    )
    svc = ManualDistributionService(db)
    # 10 total - (2 winners + 1 renewal) = 7
    assert await svc.remaining(cfg, "nstc") == 7
```

- [ ] Run, expect FAIL because `remaining` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_remaining_is_pool_total_minus_global_consumers" -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute 'remaining'`

- [ ] Add `remaining` directly after `consumers_count`:

```python
    async def remaining(self, config: ScholarshipConfiguration, sub_type: str) -> int:
        """Global live remaining = pool_total - consumers_count (spec §6.2).

        GLOBAL: counts every consumer of this config anywhere, regardless of
        which distribution round (or which borrowing config) created the slot —
        so freeing a slot anywhere instantly raises this value everywhere.
        """
        return self.pool_total(config, sub_type) - await self.consumers_count(config.id, sub_type)
```

- [ ] Run, expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_remaining_is_pool_total_minus_global_consumers" -p no:cacheprovider`
  - Expected: `1 passed`

- [ ] Lint:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): add remaining global-live helper (spec §6.2)"`

### Task 2.4: `_allowed_config_ids` — own ∪ linked-for-sub_type

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add async `_allowed_config_ids` method after `remaining`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Modify — append tests)

> CONTRACT note: the canonical signature `def _allowed_config_ids(self, requesting_config, sub_type) -> set[int]` resolves linked `source_config_code` strings to config ids, which requires a DB lookup — so the implementation is `async def` and callers `await` it. The set is `{own.id} ∪ {linked S.id where the entry's sub_types contains sub_type}`. Missing target configs are skipped.

- [ ] Append the allowed-set tests:

```python
# --------------------------------------------------------------------------- #
# 2.4 _allowed_config_ids — own ∪ linked-for-sub_type (spec §6.3, §7)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_allowed_config_ids_own_plus_linked_for_sub_type(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}, "moe_1w": {"E": 4}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    # nstc is linked → own + prior
    assert await svc._allowed_config_ids(requesting, "nstc") == {requesting.id, prior.id}
    # moe_1w is NOT in the link's sub_types → own only
    assert await svc._allowed_config_ids(requesting, "moe_1w") == {requesting.id}


@pytest.mark.asyncio
async def test_allowed_config_ids_missing_target_config_ignored(db: AsyncSession):
    st = await _make_type(db, code="phd")
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        # phd_112 config does not exist → link silently dropped
        shared_quota_sources=[{"source_config_code": "phd_112", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    assert await svc._allowed_config_ids(requesting, "nstc") == {requesting.id}
```

- [ ] Run, expect FAIL because `_allowed_config_ids` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_allowed_config_ids_own_plus_linked_for_sub_type" "app/tests/test_manual_distribution_pool_math.py::test_allowed_config_ids_missing_target_config_ignored" -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute '_allowed_config_ids'`

- [ ] Add a small private resolver + the `_allowed_config_ids` method after `remaining`:

```python
    async def _resolve_linked_configs(
        self, requesting_config: ScholarshipConfiguration, sub_type: str
    ) -> list[ScholarshipConfiguration]:
        """Load the linked source configs of `requesting_config` whose
        shared_quota_sources entry lists `sub_type` (spec §6.3).

        Missing target configs (the source_config_code resolves to nothing) are
        silently dropped — consistent with §10/§11.5 dangling-link handling.
        """
        sources = requesting_config.shared_quota_sources or []
        codes: list[str] = []
        for entry in sources:
            if not isinstance(entry, dict):
                continue
            entry_sub_types = entry.get("sub_types") or []
            code = entry.get("source_config_code")
            if code and sub_type in entry_sub_types:
                codes.append(code)
        if not codes:
            return []
        stmt = select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code.in_(codes))
        return list((await self.db.execute(stmt)).scalars().all())

    async def _allowed_config_ids(self, requesting_config: ScholarshipConfiguration, sub_type: str) -> set[int]:
        """Allowed consumed-config ids for an allocation of (requesting, sub_type).

        = {own config id} ∪ {linked source config ids whose link lists sub_type}.
        Used server-side to validate that an inbound allocation_config_id is
        permitted before recomputing remaining (spec §7).
        """
        allowed = {requesting_config.id}
        for linked in await self._resolve_linked_configs(requesting_config, sub_type):
            allowed.add(linked.id)
        return allowed
```

- [ ] Run, expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_allowed_config_ids_own_plus_linked_for_sub_type" "app/tests/test_manual_distribution_pool_math.py::test_allowed_config_ids_missing_target_config_ignored" -p no:cacheprovider`
  - Expected: `2 passed`

- [ ] Lint:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): add _allowed_config_ids + linked-config resolver (spec §6.3)"`

### Task 2.5: `distributable_pool` — own + linked columns with live remaining

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add async `distributable_pool` method after `_allowed_config_ids`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Modify — append tests)

- [ ] Append the distributable-pool tests (own+linked; revoking a source winner raises the borrower's remaining; cross-type link):

```python
# --------------------------------------------------------------------------- #
# 2.5 distributable_pool — own + linked, live remaining (spec §6.3, §7)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_distributable_pool_own_plus_linked(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},  # remaining 3
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},  # remaining 5
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    pool = await svc.distributable_pool(requesting, "nstc")
    # own first, then linked by descending academic_year
    assert pool == [
        {"config_id": requesting.id, "config_code": "phd_115", "academic_year": 115, "is_own": True, "remaining": 5},
        {"config_id": prior.id, "config_code": "phd_114", "academic_year": 114, "is_own": False, "remaining": 3},
    ]


@pytest.mark.asyncio
async def test_distributable_pool_revoking_source_winner_raises_borrower_remaining(db: AsyncSession):
    st = await _make_type(db, code="phd")
    prior = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 3}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
    )
    # One winner consuming the PRIOR config → prior remaining drops to 2.
    ranking = await _make_ranking(db, scholarship_type_id=st.id, sub_type_code="nstc", academic_year=115)
    u = await _make_user(db, nycu_id="bw")
    a = await _make_application(
        db,
        user_id=u.id,
        scholarship_type_id=st.id,
        academic_year=115,
        sub_scholarship_type="nstc",
        is_renewal=False,
        status=ApplicationStatus.submitted,
        app_id="APP-115-0-30000",
    )
    item = await _make_item(
        db,
        ranking_id=ranking.id,
        application_id=a.id,
        rank=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=prior.id,
    )
    svc = ManualDistributionService(db)
    before = {p["config_id"]: p["remaining"] for p in await svc.distributable_pool(requesting, "nstc")}
    assert before[prior.id] == 2  # 3 - 1 winner

    # Revoke the source winner → its slot frees → borrower's linked column rises.
    item.is_allocated = False
    item.allocated_sub_type = None
    item.allocation_config_id = None
    item.status = "ranked"
    await db.commit()

    after = {p["config_id"]: p["remaining"] for p in await svc.distributable_pool(requesting, "nstc")}
    assert after[prior.id] == 3  # restored live


@pytest.mark.asyncio
async def test_distributable_pool_cross_type_link(db: AsyncSession):
    phd = await _make_type(db, code="phd")
    direct = await _make_type(db, code="direct_phd")
    prior = await _make_config(
        db,
        scholarship_type_id=direct.id,
        config_code="direct_phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 2}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=phd.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        shared_quota_sources=[{"source_config_code": "direct_phd_114", "sub_types": ["nstc"]}],
    )
    svc = ManualDistributionService(db)
    pool = await svc.distributable_pool(requesting, "nstc")
    assert pool == [
        {"config_id": requesting.id, "config_code": "phd_115", "academic_year": 115, "is_own": True, "remaining": 5},
        {"config_id": prior.id, "config_code": "direct_phd_114", "academic_year": 114, "is_own": False, "remaining": 2},
    ]
```

- [ ] Run, expect FAIL because `distributable_pool` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_own_plus_linked" "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_revoking_source_winner_raises_borrower_remaining" "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_cross_type_link" -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute 'distributable_pool'`

- [ ] Add `distributable_pool` after `_allowed_config_ids`:

```python
    async def distributable_pool(self, requesting_config: ScholarshipConfiguration, sub_type: str) -> list[dict]:
        """The pool of consumable configs for (requesting_config, sub_type), §6.3.

        Returns the own config first, then each linked source config in
        DESCENDING academic_year, each with its LIVE `remaining`. Each entry maps
        to one grid column; an allocation records that config's id as
        allocation_config_id.
        """
        pool: list[dict] = [
            {
                "config_id": requesting_config.id,
                "config_code": requesting_config.config_code,
                "academic_year": requesting_config.academic_year,
                "is_own": True,
                "remaining": await self.remaining(requesting_config, sub_type),
            }
        ]
        linked = await self._resolve_linked_configs(requesting_config, sub_type)
        for cfg in sorted(linked, key=lambda c: c.academic_year, reverse=True):
            pool.append(
                {
                    "config_id": cfg.id,
                    "config_code": cfg.config_code,
                    "academic_year": cfg.academic_year,
                    "is_own": False,
                    "remaining": await self.remaining(cfg, sub_type),
                }
            )
        return pool
```

- [ ] Run, expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_own_plus_linked" "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_revoking_source_winner_raises_borrower_remaining" "app/tests/test_manual_distribution_pool_math.py::test_distributable_pool_cross_type_link" -p no:cacheprovider`
  - Expected: `3 passed`

- [ ] Lint:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): add distributable_pool own+linked live columns (spec §6.3)"`

### Task 2.6: `_pick_config` replaces `_pick_pool`; delete `_build_remaining_quota`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:1595-1617` (replace `_pick_pool`) and `:1619-1643` (delete `_build_remaining_quota`)
- Test: `backend/app/tests/test_manual_distribution_pool_math.py` (Modify — append test)

> `_pick_config` returns a config id (own first, then linked by descending academic_year) for a given working remaining map, replacing the year-keyed `_pick_pool`. It is `async` because it must resolve the candidate config set from the requesting config's links. `working_remaining: dict[int, int]` is keyed by config id and lets the caller (auto-allocate / general distribution, Phase 4) decrement as it assigns, without re-querying the DB each step.

- [ ] Append the `_pick_config` test:

```python
# --------------------------------------------------------------------------- #
# 2.6 _pick_config — own first, then linked by descending year (spec §6.3)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_pick_config_prefers_own_then_descending_year(db: AsyncSession):
    st = await _make_type(db, code="phd")
    older = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_113",
        academic_year=113,
        quotas={"nstc": {"E": 2}},
    )
    newer = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_114",
        academic_year=114,
        quotas={"nstc": {"E": 2}},
    )
    requesting = await _make_config(
        db,
        scholarship_type_id=st.id,
        config_code="phd_115",
        academic_year=115,
        quotas={"nstc": {"E": 5}},
        shared_quota_sources=[
            {"source_config_code": "phd_113", "sub_types": ["nstc"]},
            {"source_config_code": "phd_114", "sub_types": ["nstc"]},
        ],
    )
    svc = ManualDistributionService(db)

    # All have remaining → own (phd_115) wins.
    wr = {requesting.id: 5, newer.id: 2, older.id: 2}
    assert await svc._pick_config(requesting, "nstc", wr) == requesting.id

    # Own exhausted → highest-year linked (phd_114) wins.
    wr = {requesting.id: 0, newer.id: 2, older.id: 2}
    assert await svc._pick_config(requesting, "nstc", wr) == newer.id

    # Own + phd_114 exhausted → phd_113 wins.
    wr = {requesting.id: 0, newer.id: 0, older.id: 2}
    assert await svc._pick_config(requesting, "nstc", wr) == older.id

    # Nothing left → None.
    wr = {requesting.id: 0, newer.id: 0, older.id: 0}
    assert await svc._pick_config(requesting, "nstc", wr) is None
```

- [ ] Run, expect FAIL because `_pick_config` does not exist:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_pick_config_prefers_own_then_descending_year" -p no:cacheprovider`
  - Expected: `AttributeError: 'ManualDistributionService' object has no attribute '_pick_config'`

- [ ] Replace `_pick_pool`. The current code at `backend/app/services/manual_distribution_service.py:1595-1617` is:

```python
    @staticmethod
    def _pick_pool(
        remaining: dict[tuple[str, int], int],
        sub_type: str,
        config: ScholarshipConfiguration,
    ) -> Optional[int]:
        """Pick the next allocation_year with available quota for `sub_type`.

        Policy: prefer the current academic_year first, then prior years in
        descending order. Returns None when no pool with positive remaining
        quota exists for this sub_type.
        """
        candidate_years = sorted(
            [y for (st, y), c in remaining.items() if st == sub_type and c > 0],
            reverse=True,
        )
        if not candidate_years:
            return None
        # Prefer the configured current year if available; otherwise the
        # highest-numbered prior year (already sorted descending).
        if config.academic_year in candidate_years:
            return config.academic_year
        return candidate_years[0]
```

Replace it (entire `_pick_pool` block) with:

```python
    async def _pick_config(
        self,
        requesting_config: ScholarshipConfiguration,
        sub_type: str,
        working_remaining: dict[int, int],
    ) -> Optional[int]:
        """Pick the next config id with positive working remaining for sub_type.

        Replaces the year-keyed `_pick_pool` (spec §6.3). Policy: prefer the OWN
        config first, then linked source configs by DESCENDING academic_year.
        `working_remaining` is keyed by config id and supplied (and decremented)
        by the caller so a multi-assign loop need not re-query the DB. Returns
        None when no candidate config has positive remaining.
        """
        if working_remaining.get(requesting_config.id, 0) > 0:
            return requesting_config.id
        linked = await self._resolve_linked_configs(requesting_config, sub_type)
        for cfg in sorted(linked, key=lambda c: c.academic_year, reverse=True):
            if working_remaining.get(cfg.id, 0) > 0:
                return cfg.id
        return None
```

- [ ] Delete `_build_remaining_quota`. The current code at `backend/app/services/manual_distribution_service.py:1619-1643` (now shifted up after the previous edit) is:

```python
    @staticmethod
    def _build_remaining_quota(
        quotas: dict,
        used_by_renewal: dict[tuple[str, int], int],
    ) -> dict[tuple[str, int], int]:
        """Build {(sub_type, alloc_year): remaining} from config quotas.

        The Phase 6 quotas dict is `{sub_type: {year_string: total_int}}` per
        spec Section 9.1. Year keys are coerced to int so downstream code can
        compare against renewal_year / academic_year (also ints).
        """
        remaining: dict[tuple[str, int], int] = {}
        for sub_type, year_map in (quotas or {}).items():
            if not isinstance(year_map, dict):
                continue
            for year_key, total in year_map.items():
                try:
                    year_int = int(year_key)
                except (TypeError, ValueError):
                    # Non-year keys (legacy college-code matrix) aren't used
                    # by the Phase 6 algorithm; skip silently.
                    continue
                used = used_by_renewal.get((sub_type, year_int), 0)
                remaining[(sub_type, year_int)] = int(total) - used
        return remaining
```

Delete this entire `_build_remaining_quota` method (the whole block above, including the `@staticmethod` decorator and its trailing blank line). Do NOT leave a stub.

> Note: `execute_general_distribution` (currently at ~`:1645`) still calls `self._build_remaining_quota` and `self._pick_pool`. Those call sites are rewritten in Phase 4 onto `remaining`/`_pick_config`. To keep THIS phase's commit green without touching Phase 4's surface, this task does not run the full `execute_general_distribution` path — only the new `_pick_config` unit test is run here. Verify the deletion didn't break import/collection with the run command below (collection imports the module, proving no syntax error).

- [ ] Run the new test (and confirm the module still imports cleanly), expect PASS:
  - `docker compose -f docker-compose.dev.yml exec backend pytest "app/tests/test_manual_distribution_pool_math.py::test_pick_config_prefers_own_then_descending_year" -p no:cacheprovider`
  - Expected: `1 passed` (clean collection = `_build_remaining_quota` deletion left no syntax error)

- [ ] Run the FULL pool-math file to confirm all earlier tasks still pass together:
  - `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_manual_distribution_pool_math.py -p no:cacheprovider`
  - Expected: `13 passed`

- [ ] Lint:
  - `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `cd backend && flake8 app/services/manual_distribution_service.py app/tests/test_manual_distribution_pool_math.py --select=B904,B014 --max-line-length=120`
  - Expected: no output (exit 0)

- [ ] Commit:
  - `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_manual_distribution_pool_math.py`
  - `git commit -m "feat(distribution): replace _pick_pool with _pick_config, drop _build_remaining_quota (spec §6.3)"`
```


## Phase 3 — Distribution service + quota gate

### Task 3.1: `pool_total` mode-aware helper on `ManualDistributionService`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add method to `ManualDistributionService`, after `_load_config` ends at `:595`)
- Test: `backend/tests/test_pool_math.py` (Create — pure host-runnable)

- [ ] Create the test file `backend/tests/test_pool_math.py` with a `_service` fixture that imports `ManualDistributionService` with mocked deps (mirror the isolation pattern from `test_auto_allocate_preview.py:24-77` so it runs on the host with no DB). Write COMPLETE code:
  ```python
  """Unit tests for the live shared-pool math helpers (pure, no DB)."""

  import importlib.util
  import os
  import sys
  from types import SimpleNamespace
  from unittest.mock import MagicMock

  import pytest

  _SERVICE_PATH = os.path.abspath(
      os.path.join(os.path.dirname(__file__), "..", "app", "services", "manual_distribution_service.py")
  )

  _MOCK_MODULES = [
      "sqlalchemy",
      "sqlalchemy.ext",
      "sqlalchemy.ext.asyncio",
      "sqlalchemy.orm",
      "app",
      "app.models",
      "app.models.application",
      "app.models.audit_log",
      "app.models.college_review",
      "app.models.enums",
      "app.models.review",
      "app.models.payment_roster",
      "app.models.scholarship",
      "app.models.user",
      "app.services.received_months_service",
  ]


  @pytest.fixture(scope="module")
  def service_cls():
      originals = {}
      for mod_name in _MOCK_MODULES:
          originals[mod_name] = sys.modules.get(mod_name)
          if mod_name not in sys.modules:
              sys.modules[mod_name] = MagicMock()

      sys.modules["sqlalchemy"].ext = sys.modules["sqlalchemy.ext"]
      sys.modules["sqlalchemy.ext"].asyncio = sys.modules["sqlalchemy.ext.asyncio"]
      sys.modules["sqlalchemy.ext.asyncio"].AsyncSession = object
      sys.modules["sqlalchemy.orm"].joinedload = MagicMock()
      sys.modules["sqlalchemy.orm"].selectinload = MagicMock()

      spec = importlib.util.spec_from_file_location("mds_pool_direct", _SERVICE_PATH)
      module = importlib.util.module_from_spec(spec)
      spec.loader.exec_module(module)

      yield module.ManualDistributionService

      for mod_name in _MOCK_MODULES:
          if originals[mod_name] is None:
              sys.modules.pop(mod_name, None)
          else:
              sys.modules[mod_name] = originals[mod_name]


  def _config(*, has_college_quota, quotas, total_quota=None):
      return SimpleNamespace(
          has_college_quota=has_college_quota,
          quotas=quotas,
          total_quota=total_quota,
      )


  def test_pool_total_matrix_sums_colleges(service_cls):
      svc = service_cls.__new__(service_cls)
      cfg = _config(has_college_quota=True, quotas={"nstc": {"E": 15, "C": 12}, "moe_1w": {"E": 6}})
      assert svc.pool_total(cfg, "nstc") == 27
      assert svc.pool_total(cfg, "moe_1w") == 6


  def test_pool_total_matrix_missing_subtype_is_zero(service_cls):
      svc = service_cls.__new__(service_cls)
      cfg = _config(has_college_quota=True, quotas={"nstc": {"E": 15}})
      assert svc.pool_total(cfg, "absent") == 0


  def test_pool_total_non_matrix_scalar(service_cls):
      svc = service_cls.__new__(service_cls)
      cfg = _config(has_college_quota=False, quotas={"nstc": 8})
      assert svc.pool_total(cfg, "nstc") == 8


  def test_pool_total_non_matrix_falls_back_to_total_quota(service_cls):
      svc = service_cls.__new__(service_cls)
      cfg = _config(has_college_quota=False, quotas={}, total_quota=20)
      assert svc.pool_total(cfg, "nstc") == 20


  def test_pool_total_non_matrix_no_quota_zero(service_cls):
      svc = service_cls.__new__(service_cls)
      cfg = _config(has_college_quota=False, quotas={}, total_quota=None)
      assert svc.pool_total(cfg, "nstc") == 0
  ```
- [ ] Run it, expect FAIL: `python -m pytest backend/tests/test_pool_math.py -p no:cacheprovider -q` from `/home/howard/scholarship-system` — expect `AttributeError: 'ManualDistributionService' object has no attribute 'pool_total'`.
- [ ] Add the `pool_total` method to `ManualDistributionService`. Insert it immediately after the `_load_config` method (which currently ends at `:595` with `return result.scalars().first()`), so the new method begins right before `async def allocate` at `:597`. Write COMPLETE code:
  ```python
      def pool_total(self, config: ScholarshipConfiguration, sub_type: str) -> int:
          """Mode-aware total pool size for one (config, sub_type).

          matrix_based / college_based: sum the per-college matrix row.
          simple / none: quotas[sub_type] is a scalar; fall back to total_quota.
          (spec §6.1 — must NOT call get_sub_type_total_quota blindly, which
          returns 0 for non-matrix configs and would read an empty pool.)
          """
          quotas = config.quotas or {}
          if config.has_college_quota:
              row = quotas.get(sub_type, {})
              if not isinstance(row, dict):
                  return 0
              return sum(int(v) for v in row.values())
          scalar = quotas.get(sub_type, 0)
          try:
              scalar_int = int(scalar)
          except (TypeError, ValueError):
              scalar_int = 0
          return scalar_int or int(config.total_quota or 0)
  ```
- [ ] Run it, expect PASS: `python -m pytest backend/tests/test_pool_math.py -p no:cacheprovider -q` — expect `5 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/tests/test_pool_math.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/tests/test_pool_math.py && git commit -m "feat(distribution): mode-aware pool_total helper"`

---

### Task 3.2: `consumers_count` / `remaining` live global counters

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add two async methods right after `pool_total` from Task 3.1)
- Test: `backend/app/tests/test_shared_pool_consumers.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_shared_pool_consumers.py`. Write COMPLETE code building a config + two ranking items (one general winner, one renewal item that is also `is_allocated=True` after a restore) + an approved renewal Application, then assert `consumers_count` counts the general winner via the ranking half and the renewal via the Application half, NOT double-counting the restored renewal ranking item:
  ```python
  """consumers_count() / remaining() — the live global shared-pool counters (spec §6.2)."""

  import pytest
  import pytest_asyncio
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService

  YEAR = 114


  @pytest_asyncio.fixture
  async def config(db: AsyncSession) -> ScholarshipConfiguration:
      sch = ScholarshipType(code="cc_sch", name="Consumers Sch", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      cfg = ScholarshipConfiguration(
          scholarship_type_id=sch.id,
          academic_year=YEAR,
          semester=None,
          config_name="cc cfg",
          config_code="cc-114",
          amount=30000,
          currency="TWD",
          is_active=True,
          has_college_quota=True,
          quotas={"nstc": {"A": 5}},
      )
      db.add(cfg)
      await db.commit()
      await db.refresh(cfg)
      return cfg


  async def _student(db: AsyncSession, suffix: str) -> User:
      u = User(
          nycu_id=f"cc_{suffix}",
          name=f"S {suffix}",
          email=f"cc_{suffix}@u.edu",
          user_type=UserType.student,
          role=UserRole.student,
      )
      db.add(u)
      await db.commit()
      await db.refresh(u)
      return u


  async def _app(db, *, user, sch_id, is_renewal, status, sub_type, alloc_cfg_id=None):
      a = Application(
          app_id=f"APP-{YEAR}-0-{user.nycu_id}",
          user_id=user.id,
          scholarship_type_id=sch_id,
          scholarship_subtype_list=[sub_type],
          sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type=sub_type,
          academic_year=YEAR,
          semester=None,
          status=status,
          review_stage=ReviewStage.quota_distributed,
          is_renewal=is_renewal,
          allocation_config_id=alloc_cfg_id,
          agree_terms=True,
      )
      db.add(a)
      await db.commit()
      await db.refresh(a)
      return a


  async def _ranking_item(db, *, sch_id, app_id, alloc_cfg_id):
      ranking = CollegeRanking(
          scholarship_type_id=sch_id,
          sub_type_code="nstc",
          academic_year=YEAR,
          semester=None,
          is_finalized=True,
          ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      item = CollegeRankingItem(
          ranking_id=ranking.id,
          application_id=app_id,
          rank_position=1,
          is_allocated=True,
          allocated_sub_type="nstc",
          allocation_config_id=alloc_cfg_id,
          status="allocated",
      )
      db.add(item)
      await db.commit()
      await db.refresh(item)
      return item


  @pytest.mark.asyncio
  async def test_consumers_partition_no_double_count(db: AsyncSession, config: ScholarshipConfiguration):
      sch_id = config.scholarship_type_id
      # General winner — counted via the ranking half.
      gen_user = await _student(db, "gen")
      gen_app = await _app(
          db, user=gen_user, sch_id=sch_id, is_renewal=False,
          status=ApplicationStatus.approved, sub_type="nstc",
      )
      await _ranking_item(db, sch_id=sch_id, app_id=gen_app.id, alloc_cfg_id=config.id)

      # Renewal — approved Application pointing at this config (counted via Application half).
      ren_user = await _student(db, "ren")
      ren_app = await _app(
          db, user=ren_user, sch_id=sch_id, is_renewal=True,
          status=ApplicationStatus.approved, sub_type="nstc", alloc_cfg_id=config.id,
      )
      # Renewal ALSO has an is_allocated ranking item (restore_allocation flips it on);
      # the §6.2 is_renewal==False guard must keep the ranking half from counting it.
      await _ranking_item(db, sch_id=sch_id, app_id=ren_app.id, alloc_cfg_id=config.id)

      svc = ManualDistributionService(db)
      count = await svc.consumers_count(config.id, "nstc")
      assert count == 2  # one general (ranking half) + one renewal (Application half), no double count
      remaining = await svc.remaining(config, "nstc")
      assert remaining == 3  # pool_total 5 - 2
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_shared_pool_consumers.py -p no:cacheprovider -q` — expect `AttributeError: 'ManualDistributionService' object has no attribute 'consumers_count'`.
- [ ] Add `consumers_count` and `remaining` to the service, immediately after the `pool_total` method from Task 3.1. Write COMPLETE code:
  ```python
      async def consumers_count(self, config_id: int, sub_type: str) -> int:
          """Live global count of every slot consuming (config_id, sub_type).

          Guaranteed partition (spec §6.2):
            * CollegeRankingItem winners — is_allocated, this sub_type & config,
              whose application is NOT a renewal (general/manual winners only).
            * approved renewals — Application.is_renewal, approved, this sub_type
              & allocation_config_id (renewals only).
          The explicit is_renewal==False guard on the ranking half prevents a
          revoked-then-restored renewal from being counted in both halves.
          """
          ranking_stmt = (
              select(func.count(CollegeRankingItem.id))
              .join(Application, CollegeRankingItem.application_id == Application.id)
              .where(
                  CollegeRankingItem.is_allocated.is_(True),
                  CollegeRankingItem.allocated_sub_type == sub_type,
                  CollegeRankingItem.allocation_config_id == config_id,
                  Application.is_renewal.is_(False),
                  Application.deleted_at.is_(None),
              )
          )
          ranking_count = (await self.db.execute(ranking_stmt)).scalar() or 0

          renewal_stmt = select(func.count(Application.id)).where(
              Application.is_renewal.is_(True),
              Application.status == ApplicationStatus.approved,
              Application.sub_scholarship_type == sub_type,
              Application.allocation_config_id == config_id,
              Application.deleted_at.is_(None),
          )
          renewal_count = (await self.db.execute(renewal_stmt)).scalar() or 0

          return int(ranking_count) + int(renewal_count)

      async def remaining(self, config: ScholarshipConfiguration, sub_type: str) -> int:
          """Live global remaining = pool_total − consumers_count (spec §6.2)."""
          return self.pool_total(config, sub_type) - await self.consumers_count(config.id, sub_type)
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_shared_pool_consumers.py -p no:cacheprovider -q` — expect `1 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_shared_pool_consumers.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_shared_pool_consumers.py && git commit -m "feat(distribution): live global consumers_count + remaining"`

---

### Task 3.3: `_allowed_config_ids` + `distributable_pool` + `_pick_config`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py` (add three methods after `remaining` from Task 3.2; remove `_pick_pool` at `:1595-1617` and `_build_remaining_quota` at `:1619-1643` in Task 3.7 when `execute_general_distribution` is rewritten — leave them for now)
- Test: `backend/app/tests/test_distributable_pool.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_distributable_pool.py`. Build a requesting config `phd_115` with `shared_quota_sources=[{"source_config_code":"phd_114","sub_types":["nstc"]}]` and an existing `phd_114` config (prior year). Assert: `_allowed_config_ids` returns `{own.id, linked.id}` for `nstc` and `{own.id}` for a sub_type not in any link; `distributable_pool` returns own first then linked descending-year with live `remaining`; revoking a `phd_114` winner raises the borrower's linked-column remaining. Write COMPLETE code:
  ```python
  """distributable_pool / _allowed_config_ids / _pick_config — cross-config pool (spec §6.3)."""

  import pytest
  import pytest_asyncio
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  @pytest_asyncio.fixture
  async def configs(db: AsyncSession):
      sch = ScholarshipType(code="dp_phd", name="DP PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)

      prior = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=114, semester=None,
          config_name="phd114", config_code="phd_114", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 2}},
      )
      db.add(prior)
      await db.commit()
      await db.refresh(prior)

      own = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 3}, "moe_1w": {"A": 4}},
          shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
      )
      db.add(own)
      await db.commit()
      await db.refresh(own)
      return {"sch": sch, "own": own, "prior": prior}


  @pytest.mark.asyncio
  async def test_allowed_config_ids(configs):
      own, prior = configs["own"], configs["prior"]
      svc = ManualDistributionService.__new__(ManualDistributionService)
      assert svc._allowed_config_ids(own, "nstc") == {own.id, prior.id}
      # moe_1w has no link entry → own only
      assert svc._allowed_config_ids(own, "moe_1w") == {own.id}


  @pytest.mark.asyncio
  async def test_distributable_pool_own_then_linked(db: AsyncSession, configs):
      svc = ManualDistributionService(db)
      pool = await svc.distributable_pool(configs["own"], "nstc")
      assert [p["config_id"] for p in pool] == [configs["own"].id, configs["prior"].id]
      assert pool[0]["is_own"] is True and pool[0]["remaining"] == 3
      assert pool[1]["is_own"] is False and pool[1]["remaining"] == 2
      assert pool[1]["config_code"] == "phd_114"
      assert pool[1]["academic_year"] == 114


  @pytest.mark.asyncio
  async def test_revoking_source_winner_raises_borrower_pool(db: AsyncSession, configs):
      sch, own, prior = configs["sch"], configs["own"], configs["prior"]
      user = User(
          nycu_id="dp_w", name="W", email="dp_w@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(user)
      await db.commit()
      await db.refresh(user)
      app = Application(
          app_id="APP-114-0-w", user_id=user.id, scholarship_type_id=sch.id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=114, semester=None,
          status=ApplicationStatus.approved, review_stage=ReviewStage.quota_distributed,
          is_renewal=False, agree_terms=True,
      )
      db.add(app)
      await db.commit()
      await db.refresh(app)
      ranking = CollegeRanking(
          scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=114,
          semester=None, is_finalized=True, ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      item = CollegeRankingItem(
          ranking_id=ranking.id, application_id=app.id, rank_position=1,
          is_allocated=True, allocated_sub_type="nstc",
          allocation_config_id=prior.id, status="allocated",
      )
      db.add(item)
      await db.commit()

      svc = ManualDistributionService(db)
      pool = await svc.distributable_pool(own, "nstc")
      linked = next(p for p in pool if p["config_id"] == prior.id)
      assert linked["remaining"] == 1  # 2 total - 1 consumed

      # Revoke (free) the source winner.
      item.is_allocated = False
      await db.commit()
      pool2 = await svc.distributable_pool(own, "nstc")
      linked2 = next(p for p in pool2 if p["config_id"] == prior.id)
      assert linked2["remaining"] == 2  # freed slot instantly visible to borrower
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_distributable_pool.py -p no:cacheprovider -q` — expect `AttributeError: 'ManualDistributionService' object has no attribute '_allowed_config_ids'`.
- [ ] Add the three methods to the service, immediately after the `remaining` method from Task 3.2. Write COMPLETE code:
  ```python
      def _allowed_config_ids(self, requesting_config: ScholarshipConfiguration, sub_type: str) -> set[int]:
          """{own.id} ∪ {linked S.id whose shared_quota_sources entry lists sub_type}.

          Resolution needs the linked config objects, which distributable_pool /
          _pick_config supply; this helper only computes the id set when those
          objects are already attached. It loads linked configs lazily via the
          requesting config's _linked_configs cache (populated by
          _load_linked_configs) so synchronous callers (validation) can use it.
          """
          allowed = {requesting_config.id}
          linked = getattr(requesting_config, "_linked_configs", None) or {}
          for entry in requesting_config.shared_quota_sources or []:
              if sub_type in (entry.get("sub_types") or []):
                  cfg = linked.get(entry.get("source_config_code"))
                  if cfg is not None:
                      allowed.add(cfg.id)
          return allowed

      async def _load_linked_configs(
          self, requesting_config: ScholarshipConfiguration
      ) -> dict[str, ScholarshipConfiguration]:
          """Load the configs named in shared_quota_sources by config_code, cache
          on the requesting config as _linked_configs, and return the map."""
          codes = [
              entry.get("source_config_code")
              for entry in (requesting_config.shared_quota_sources or [])
              if entry.get("source_config_code")
          ]
          linked: dict[str, ScholarshipConfiguration] = {}
          if codes:
              rows = (
                  await self.db.execute(
                      select(ScholarshipConfiguration).where(ScholarshipConfiguration.config_code.in_(codes))
                  )
              ).scalars().all()
              linked = {cfg.config_code: cfg for cfg in rows}
          requesting_config._linked_configs = linked
          return linked

      async def distributable_pool(
          self, requesting_config: ScholarshipConfiguration, sub_type: str
      ) -> list[dict]:
          """Ordered pool columns for one sub_type: own config first, then linked
          source configs (whose entry lists this sub_type) by descending year,
          each with its live remaining (spec §6.3)."""
          linked = await self._load_linked_configs(requesting_config)

          columns: list[dict] = [
              {
                  "config_id": requesting_config.id,
                  "config_code": requesting_config.config_code,
                  "academic_year": requesting_config.academic_year,
                  "is_own": True,
                  "remaining": await self.remaining(requesting_config, sub_type),
              }
          ]

          linked_cols: list[dict] = []
          for entry in requesting_config.shared_quota_sources or []:
              if sub_type not in (entry.get("sub_types") or []):
                  continue
              cfg = linked.get(entry.get("source_config_code"))
              if cfg is None:
                  continue
              linked_cols.append(
                  {
                      "config_id": cfg.id,
                      "config_code": cfg.config_code,
                      "academic_year": cfg.academic_year,
                      "is_own": False,
                      "remaining": await self.remaining(cfg, sub_type),
                  }
              )
          linked_cols.sort(key=lambda c: c["academic_year"], reverse=True)
          return columns + linked_cols

      async def _pick_config(
          self,
          requesting_config: ScholarshipConfiguration,
          sub_type: str,
          working_remaining: dict[int, int],
      ) -> Optional[int]:
          """Pick the next config_id with positive working remaining for sub_type:
          own config first, then linked by descending year. working_remaining is a
          mutable {config_id: remaining} the caller decrements (replaces _pick_pool)."""
          for col in await self.distributable_pool(requesting_config, sub_type):
              cid = col["config_id"]
              if working_remaining.get(cid, 0) > 0:
                  return cid
          return None
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_distributable_pool.py -p no:cacheprovider -q` — expect `3 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_distributable_pool.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_distributable_pool.py && git commit -m "feat(distribution): distributable_pool + _pick_config + _allowed_config_ids"`

---

### Task 3.4: Rewrite `get_quota_status` onto `remaining()` / `distributable_pool()`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:385-572` (the whole `get_quota_status` method body)
- Test: `backend/app/tests/test_get_quota_status_shared_pool.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_get_quota_status_shared_pool.py`. Build a requesting config with `quotas={"nstc":{"A":3},"moe_1w":{"A":4}}` and `shared_quota_sources=[{"source_config_code":"phd_114","sub_types":["nstc"]}]`, a prior `phd_114` with `quotas={"nstc":{"A":2}}`, one approved renewal consuming the own config (so renewals are now subtracted — the §17.1 behavior change), and assert the response shape keys by config (own + linked nstc column, moe_1w own only). Write COMPLETE code:
  ```python
  """get_quota_status rebuilt onto remaining()/distributable_pool() (spec §6.3, §17.1)."""

  import pytest
  import pytest_asyncio
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipSubTypeConfig, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  @pytest_asyncio.fixture
  async def setup(db: AsyncSession):
      sch = ScholarshipType(code="qs_phd", name="QS PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      for code, name, order in [("nstc", "國科會", 1), ("moe_1w", "教育部", 2)]:
          db.add(
              ScholarshipSubTypeConfig(
                  scholarship_type_id=sch.id, sub_type_code=code, name=name,
                  display_order=order, is_active=True,
              )
          )
      prior = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=114, semester=None,
          config_name="phd114", config_code="phd_114", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 2}},
      )
      own = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True,
          quotas={"nstc": {"A": 3}, "moe_1w": {"A": 4}},
          shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
      )
      db.add_all([prior, own])
      await db.commit()
      await db.refresh(own)
      await db.refresh(prior)
      return {"sch": sch, "own": own, "prior": prior}


  @pytest.mark.asyncio
  async def test_quota_status_keys_by_config_and_subtracts_renewals(db: AsyncSession, setup):
      sch, own = setup["sch"], setup["own"]
      # An approved renewal consuming own config — must lower the displayed remaining.
      user = User(
          nycu_id="qs_r", name="R", email="qs_r@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(user)
      await db.commit()
      await db.refresh(user)
      ren = Application(
          app_id="APP-115-0-r", user_id=user.id, scholarship_type_id=sch.id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=115, semester=None,
          status=ApplicationStatus.approved, review_stage=ReviewStage.quota_distributed,
          is_renewal=True, allocation_config_id=own.id, agree_terms=True,
      )
      db.add(ren)
      await db.commit()

      svc = ManualDistributionService(db)
      status = await svc.get_quota_status(sch.id, 115, "yearly")

      assert status["nstc"]["display_name"] == "國科會"
      by_cfg = {c["config_id"]: c for c in status["nstc"]["by_config"]}
      # own nstc: total 3 − 1 renewal = 2 remaining
      assert by_cfg[own.id] == {
          "config_id": own.id,
          "config_code": "phd_115",
          "academic_year": 115,
          "is_own": True,
          "total": 3,
          "remaining": 2,
      }
      # linked phd_114 nstc: total 2, remaining 2
      assert by_cfg[setup["prior"].id]["remaining"] == 2
      assert by_cfg[setup["prior"].id]["is_own"] is False
      # moe_1w: own only, no linked column
      moe_cfgs = {c["config_id"] for c in status["moe_1w"]["by_config"]}
      assert moe_cfgs == {own.id}
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_get_quota_status_shared_pool.py -p no:cacheprovider -q` — expect `KeyError: 'by_config'` (today's method returns `by_year`).
- [ ] Replace the entire `get_quota_status` method. The current body spans `:385-572` — from the signature `async def get_quota_status(` through `return quota_status`. Quote the current first/last lines to anchor the replacement: it begins `async def get_quota_status(\n        self,\n        scholarship_type_id: int,\n        academic_year: int,\n        semester: str,\n    ) -> dict[str, Any]:` and ends `        return quota_status`. Replace with COMPLETE code:
  ```python
      async def get_quota_status(
          self,
          scholarship_type_id: int,
          academic_year: int,
          semester: str,
      ) -> dict[str, Any]:
          """Real-time quota grid per sub-type, keyed by **config** (spec §6.3, §12).

          Response:
          {
            "nstc": {
              "display_name": "國科會",
              "by_config": [
                {"config_id", "config_code", "academic_year", "is_own", "total", "remaining"},
                ...  # own config first, then linked source configs by descending year
              ]
            },
            ...
          }
          remaining is the LIVE global value (pool_total − every consumer of that
          config anywhere, INCLUDING approved renewals — see §17.1 behavior change).
          """
          current_config = await self._load_config(scholarship_type_id, academic_year, semester)
          if current_config is None:
              return {}

          # Sub-type display names.
          sub_type_query = (
              select(ScholarshipSubTypeConfig)
              .where(
                  and_(
                      ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id,
                      ScholarshipSubTypeConfig.is_active.is_(True),
                  )
              )
              .order_by(ScholarshipSubTypeConfig.display_order)
          )
          sub_type_configs = (await self.db.execute(sub_type_query)).scalars().all()
          sub_type_names = {stc.sub_type_code: stc.name for stc in sub_type_configs}

          # Drive columns off the requesting config's own quota sub_types.
          own_quotas = current_config.quotas or {}

          quota_status: dict[str, Any] = {}
          for sub_type in own_quotas.keys():
              if self.pool_total(current_config, sub_type) <= 0:
                  continue
              by_config = []
              for col in await self.distributable_pool(current_config, sub_type):
                  cfg = current_config if col["is_own"] else None
                  if cfg is None:
                      linked = getattr(current_config, "_linked_configs", {}) or {}
                      cfg = linked.get(col["config_code"])
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
              quota_status[sub_type] = {
                  "display_name": sub_type_names.get(sub_type, sub_type),
                  "by_config": by_config,
              }

          return quota_status
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_get_quota_status_shared_pool.py -p no:cacheprovider -q` — expect `1 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_get_quota_status_shared_pool.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_get_quota_status_shared_pool.py && git commit -m "feat(distribution): rebuild get_quota_status onto live shared pool (by_config)"`

---

### Task 3.5: `AllocationItem.allocation_config_id` payload + `allocate()` write with `_allowed_config_ids` validation

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py:28-32` (`AllocationItem` schema)
- Modify: `backend/app/services/manual_distribution_service.py:597-643` (`allocate` signature/loop) and `:666-675` (save snapshot)
- Test: `backend/app/tests/test_allocate_config_id.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_allocate_config_id.py`. Build a requesting config + a linked prior config + one ranking item; assert (a) allocating with `allocation_config_id = linked.id` writes `item.allocation_config_id == linked.id`; (b) allocating with a config id NOT in the allowed set raises `ValueError` mentioning the disallowed config. Write COMPLETE code:
  ```python
  """allocate() writes item.allocation_config_id and validates against _allowed_config_ids."""

  import pytest
  import pytest_asyncio
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  @pytest_asyncio.fixture
  async def setup(db: AsyncSession):
      sch = ScholarshipType(code="al_phd", name="AL PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      prior = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=114, semester=None,
          config_name="phd114", config_code="phd_114", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 2}},
      )
      other = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=113, semester=None,
          config_name="phd113", config_code="phd_113", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 2}},
      )
      own = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 3}},
          shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
      )
      db.add_all([prior, other, own])
      await db.commit()
      await db.refresh(own)
      await db.refresh(prior)
      await db.refresh(other)

      user = User(
          nycu_id="al_s", name="S", email="al_s@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(user)
      await db.commit()
      await db.refresh(user)
      app = Application(
          app_id="APP-115-0-s", user_id=user.id, scholarship_type_id=sch.id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=115, semester=None,
          status=ApplicationStatus.under_review, review_stage=ReviewStage.college_ranked,
          is_renewal=True, agree_terms=True,
      )
      db.add(app)
      await db.commit()
      await db.refresh(app)
      ranking = CollegeRanking(
          scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=115,
          semester=None, is_finalized=True, ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      item = CollegeRankingItem(
          ranking_id=ranking.id, application_id=app.id, rank_position=1,
          is_allocated=False, status="ranked",
      )
      db.add(item)
      await db.commit()
      await db.refresh(item)
      return {"sch": sch, "own": own, "prior": prior, "other": other, "item": item}


  @pytest.mark.asyncio
  async def test_allocate_writes_linked_config_id(db: AsyncSession, setup):
      svc = ManualDistributionService(db)
      await svc.allocate(
          setup["sch"].id, 115, "yearly",
          [{"ranking_item_id": setup["item"].id, "sub_type_code": "nstc",
            "allocation_config_id": setup["prior"].id}],
      )
      refreshed = (
          await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.id == setup["item"].id))
      ).scalar_one()
      assert refreshed.is_allocated is True
      assert refreshed.allocated_sub_type == "nstc"
      assert refreshed.allocation_config_id == setup["prior"].id


  @pytest.mark.asyncio
  async def test_allocate_rejects_disallowed_config(db: AsyncSession, setup):
      svc = ManualDistributionService(db)
      with pytest.raises(ValueError, match="phd_113"):
          await svc.allocate(
              setup["sch"].id, 115, "yearly",
              [{"ranking_item_id": setup["item"].id, "sub_type_code": "nstc",
                "allocation_config_id": setup["other"].id}],
          )
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_allocate_config_id.py -p no:cacheprovider -q` — expect `AttributeError` / failure (`allocate` still reads `allocation_year`, ranking item has no `allocation_config_id` write).
- [ ] Edit `AllocationItem` in `backend/app/api/v1/endpoints/manual_distribution.py`. Current code at `:28-32`:
  ```python
  class AllocationItem(BaseModel):
      ranking_item_id: int
      sub_type_code: Optional[str] = None
      allocation_year: Optional[int] = None  # Which year's quota to use (None = current year)
  ```
  Replace with:
  ```python
  class AllocationItem(BaseModel):
      ranking_item_id: int
      sub_type_code: Optional[str] = None
      allocation_config_id: Optional[int] = None  # Consumed config (None = own requesting config)
  ```
- [ ] Rewrite the `allocate` method's docstring + write loop in `backend/app/services/manual_distribution_service.py`. The current loop body (`:617-641`) reads:
  ```python
          updated_count = 0
          for alloc in allocations:
              item_id = alloc["ranking_item_id"]
              sub_type = alloc.get("sub_type_code")
              alloc_year = alloc.get("allocation_year") or (academic_year if sub_type else None)

              item_query = select(CollegeRankingItem).where(CollegeRankingItem.id == item_id)
              result = await self.db.execute(item_query)
              item = result.scalar_one_or_none()
              if not item:
                  continue

              if sub_type:
                  item.is_allocated = True
                  item.allocated_sub_type = sub_type
                  item.allocation_year = alloc_year
                  item.status = "allocated"
                  item.allocation_reason = "手動分發"
              else:
                  item.is_allocated = False
                  item.allocated_sub_type = None
                  item.allocation_year = None
                  item.status = "ranked"
                  item.allocation_reason = None

              updated_count += 1

          await self.db.flush()
  ```
  Replace it with (resolves the requesting config once, validates each non-null sub_type allocation against `_allowed_config_ids`, defaults the config id to the requesting config):
  ```python
          updated_count = 0
          requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
          if requesting_config is None:
              raise ValueError("No active configuration for this distribution round")
          # Populate the linked-config cache so _allowed_config_ids can resolve codes.
          await self._load_linked_configs(requesting_config)

          for alloc in allocations:
              item_id = alloc["ranking_item_id"]
              sub_type = alloc.get("sub_type_code")
              alloc_config_id = alloc.get("allocation_config_id") or (requesting_config.id if sub_type else None)

              item_query = select(CollegeRankingItem).where(CollegeRankingItem.id == item_id)
              result = await self.db.execute(item_query)
              item = result.scalar_one_or_none()
              if not item:
                  continue

              if sub_type:
                  allowed = self._allowed_config_ids(requesting_config, sub_type)
                  if alloc_config_id not in allowed:
                      code = self._config_code_by_id(requesting_config, alloc_config_id)
                      raise ValueError(f"分發目標配置不在允許範圍：{code} (sub_type={sub_type})")
                  item.is_allocated = True
                  item.allocated_sub_type = sub_type
                  item.allocation_config_id = alloc_config_id
                  item.status = "allocated"
                  item.allocation_reason = "手動分發"
              else:
                  item.is_allocated = False
                  item.allocated_sub_type = None
                  item.allocation_config_id = None
                  item.status = "ranked"
                  item.allocation_reason = None

              updated_count += 1

          # §10 server-side quota gate: lock the consumed config rows, recount,
          # reject if any is oversubscribed.
          await self._assert_round_not_oversubscribed(requesting_config)

          await self.db.flush()
  ```
- [ ] Update the `allocate` docstring (`:604-611`). Current:
  ```python
          Each allocation: {
              "ranking_item_id": int,
              "sub_type_code": str|None,
              "allocation_year": int|None  (None → defaults to academic_year)
          }
          sub_type_code=None means unallocate.
  ```
  Replace with:
  ```python
          Each allocation: {
              "ranking_item_id": int,
              "sub_type_code": str|None,
              "allocation_config_id": int|None  (None → defaults to the requesting config)
          }
          sub_type_code=None means unallocate.
  ```
- [ ] Update the save-snapshot block (`:666-675`). Current:
  ```python
                  # Build snapshot
                  allocations_snapshot = {}
                  total_allocated = 0
                  for item in items:
                      if item.is_allocated:
                          allocations_snapshot[item.id] = {
                              "sub_type": item.allocated_sub_type,
                              "allocation_year": item.allocation_year,
                              "status": item.status,
                          }
                          total_allocated += 1
  ```
  Replace with:
  ```python
                  # Build snapshot
                  allocations_snapshot = {}
                  total_allocated = 0
                  for item in items:
                      if item.is_allocated:
                          allocations_snapshot[item.id] = {
                              "sub_type": item.allocated_sub_type,
                              "allocation_config_id": item.allocation_config_id,
                              "status": item.status,
                          }
                          total_allocated += 1
  ```
- [ ] Add two small helpers (`_config_code_by_id` and the lock gate `_assert_round_not_oversubscribed`) immediately after the `_pick_config` method from Task 3.3. The lock gate is fully implemented in Task 3.6; for now add `_config_code_by_id` and a stub that Task 3.6 replaces — actually implement both here so this task's tests pass. Write COMPLETE code:
  ```python
      def _config_code_by_id(self, requesting_config: ScholarshipConfiguration, config_id: Optional[int]) -> str:
          """Human-readable config_code for an id (own or linked), for error messages."""
          if config_id == requesting_config.id:
              return requesting_config.config_code
          linked = getattr(requesting_config, "_linked_configs", {}) or {}
          for cfg in linked.values():
              if cfg.id == config_id:
                  return cfg.config_code
          return str(config_id)

      async def _assert_round_not_oversubscribed(self, requesting_config: ScholarshipConfiguration) -> None:
          """§10 quota gate: SELECT FOR UPDATE the consumed config rows for this
          round (own + every linked source), recount remaining via §6.2, and reject
          if any consumed config is oversubscribed."""
          consumed_ids = {requesting_config.id}
          linked = getattr(requesting_config, "_linked_configs", None)
          if linked is None:
              linked = await self._load_linked_configs(requesting_config)
          for cfg in linked.values():
              consumed_ids.add(cfg.id)

          locked_rows = (
              await self.db.execute(
                  select(ScholarshipConfiguration)
                  .where(ScholarshipConfiguration.id.in_(consumed_ids))
                  .with_for_update()
              )
          ).scalars().all()

          for cfg in locked_rows:
              for sub_type in (cfg.quotas or {}).keys():
                  if await self.remaining(cfg, sub_type) < 0:
                      raise ValueError(
                          f"配額超額：{cfg.config_code} / {sub_type} 的核配數已超過總配額，請調整分發"
                      )
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_allocate_config_id.py -p no:cacheprovider -q` — expect `2 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/api/v1/endpoints/manual_distribution.py backend/app/tests/test_allocate_config_id.py` then `cd backend && flake8 app/services/manual_distribution_service.py app/api/v1/endpoints/manual_distribution.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/api/v1/endpoints/manual_distribution.py backend/app/tests/test_allocate_config_id.py && git commit -m "feat(distribution): allocate writes allocation_config_id + allowed-set validation + §10 gate (allocate)"`

---

### Task 3.6: §10 lock gate in `finalize` + rewrite `_validate_allocations`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:695-816` (`finalize`, add lock gate + snapshot re-key) and `:894-919` (`_validate_allocations` comment)
- Test: `backend/app/tests/test_finalize_lock_gate.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_finalize_lock_gate.py`. Build a config with a 1-slot `nstc` matrix, two finalized ranking items BOTH allocated to that config for `nstc` (over the cap), and assert `finalize` raises `ValueError` about oversubscription. Also a happy-path: exactly-at-cap finalizes and the finalize snapshot records `allocation_config_id`. Write COMPLETE code:
  ```python
  """finalize() §10 lock gate — rejects oversubscription; snapshot re-keyed to allocation_config_id."""

  import pytest
  import pytest_asyncio
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem, ManualDistributionHistory
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  async def _student(db, suffix):
      u = User(
          nycu_id=f"fl_{suffix}", name=f"S{suffix}", email=f"fl_{suffix}@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(u)
      await db.commit()
      await db.refresh(u)
      return u


  async def _alloc_item(db, *, sch_id, app_id, ranking_id, cfg_id):
      item = CollegeRankingItem(
          ranking_id=ranking_id, application_id=app_id, rank_position=1,
          is_allocated=True, allocated_sub_type="nstc",
          allocation_config_id=cfg_id, status="allocated",
      )
      db.add(item)
      await db.commit()
      await db.refresh(item)
      return item


  @pytest_asyncio.fixture
  async def base(db: AsyncSession):
      sch = ScholarshipType(code="fl_phd", name="FL PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      cfg = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 1}},
      )
      db.add(cfg)
      await db.commit()
      await db.refresh(cfg)
      ranking = CollegeRanking(
          scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=115,
          semester=None, is_finalized=True, ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      return {"sch": sch, "cfg": cfg, "ranking": ranking}


  async def _new_app(db, *, user, sch_id):
      a = Application(
          app_id=f"APP-115-0-{user.nycu_id}", user_id=user.id, scholarship_type_id=sch_id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=115, semester=None,
          status=ApplicationStatus.under_review, review_stage=ReviewStage.college_ranked,
          is_renewal=False, agree_terms=True,
      )
      db.add(a)
      await db.commit()
      await db.refresh(a)
      return a


  @pytest.mark.asyncio
  async def test_finalize_rejects_oversubscription(db: AsyncSession, base):
      sch, cfg, ranking = base["sch"], base["cfg"], base["ranking"]
      u1 = await _student(db, "1")
      u2 = await _student(db, "2")
      a1 = await _new_app(db, user=u1, sch_id=sch.id)
      a2 = await _new_app(db, user=u2, sch_id=sch.id)
      await _alloc_item(db, sch_id=sch.id, app_id=a1.id, ranking_id=ranking.id, cfg_id=cfg.id)
      await _alloc_item(db, sch_id=sch.id, app_id=a2.id, ranking_id=ranking.id, cfg_id=cfg.id)

      svc = ManualDistributionService(db)
      with pytest.raises(ValueError, match="超額"):
          await svc.finalize(sch.id, 115, "yearly")


  @pytest.mark.asyncio
  async def test_finalize_at_cap_records_config_id_snapshot(db: AsyncSession, base):
      sch, cfg, ranking = base["sch"], base["cfg"], base["ranking"]
      u1 = await _student(db, "ok")
      a1 = await _new_app(db, user=u1, sch_id=sch.id)
      await _alloc_item(db, sch_id=sch.id, app_id=a1.id, ranking_id=ranking.id, cfg_id=cfg.id)

      svc = ManualDistributionService(db)
      result = await svc.finalize(sch.id, 115, "yearly")
      assert result["approved_count"] == 1

      hist = (
          await db.execute(
              select(ManualDistributionHistory)
              .where(ManualDistributionHistory.operation_type == "finalize")
          )
      ).scalars().first()
      snap = list(hist.allocations_snapshot.values())[0]
      assert snap["allocation_config_id"] == cfg.id
      assert "allocation_year" not in snap
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_finalize_lock_gate.py -p no:cacheprovider -q` — expect `Failed: DID NOT RAISE <class 'ValueError'>` on the first test (today's finalize never recounts) and `KeyError`/assertion on the snapshot test (snapshot still writes `allocation_year`).
- [ ] Add the lock gate to `finalize`. The current method updates rankings then flushes (`:776-783`):
  ```python
          # Update rankings
          now = datetime.now(timezone.utc)
          for ranking in rankings:
              ranking.distribution_executed = True
              ranking.distribution_date = now
              ranking.allocated_count = approved_count

          await self.db.flush()
  ```
  Replace with (insert the gate before mutating rankings — recount under lock first, using the rankings' scholarship_type/year/semester to resolve the requesting config):
  ```python
          # §10 quota gate — recount under SELECT FOR UPDATE before committing the
          # finalize. Reject if any consumed config is oversubscribed.
          requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
          if requesting_config is not None:
              await self._load_linked_configs(requesting_config)
              await self._assert_round_not_oversubscribed(requesting_config)

          # Update rankings
          now = datetime.now(timezone.utc)
          for ranking in rankings:
              ranking.distribution_executed = True
              ranking.distribution_date = now
              ranking.allocated_count = approved_count

          await self.db.flush()
  ```
- [ ] Re-key the finalize snapshot. Current (`:788-795`):
  ```python
              allocations_snapshot = {}
              for item in items:
                  if item.is_allocated and item.allocated_sub_type:
                      allocations_snapshot[item.id] = {
                          "sub_type": item.allocated_sub_type,
                          "allocation_year": item.allocation_year,
                          "status": item.status,
                      }
  ```
  Replace with:
  ```python
              allocations_snapshot = {}
              for item in items:
                  if item.is_allocated and item.allocated_sub_type:
                      allocations_snapshot[item.id] = {
                          "sub_type": item.allocated_sub_type,
                          "allocation_config_id": item.allocation_config_id,
                          "status": item.status,
                      }
  ```
- [ ] Update the `_validate_allocations` quota comment (`:918-919`). Current:
  ```python
          # Quota validation is done real-time via the quota-status endpoint on the frontend.
          # The frontend sends only valid allocations based on displayed remaining counts.
  ```
  Replace with:
  ```python
          # Server-side quota enforcement is net-new (spec §10): the lock gate in
          # allocate/finalize (_assert_round_not_oversubscribed) recounts remaining
          # under SELECT FOR UPDATE on the consumed config rows and rejects
          # oversubscription. The frontend remaining counts are advisory.
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_finalize_lock_gate.py -p no:cacheprovider -q` — expect `2 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_finalize_lock_gate.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_finalize_lock_gate.py && git commit -m "feat(distribution): §10 lock gate in finalize + config_id snapshot re-key"`

---

### Task 3.7: `restore_from_history` + `_batch_load_previous_allocation_years` → `allocation_config_id`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:818-892` (`restore_from_history` clear loop + restore loop + docstring) and `:1056-1081` (`_batch_load_previous_allocation_years`)
- Test: `backend/app/tests/test_restore_history_config_id.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_restore_history_config_id.py`. Build a config + ranking item; call `restore_from_history` with a snapshot keyed by `allocation_config_id` and assert the item gets that config id; also test `_batch_load_previous_allocation_years` returns the prior slot's `allocation_config_id`. Write COMPLETE code:
  ```python
  """restore_from_history reads allocation_config_id; _batch_load_previous_allocation_years returns config id."""

  import pytest
  import pytest_asyncio
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  @pytest_asyncio.fixture
  async def setup(db: AsyncSession):
      sch = ScholarshipType(code="rh_phd", name="RH PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      cfg = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 3}},
      )
      db.add(cfg)
      await db.commit()
      await db.refresh(cfg)
      user = User(
          nycu_id="rh_s", name="S", email="rh_s@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(user)
      await db.commit()
      await db.refresh(user)
      app = Application(
          app_id="APP-115-0-rh", user_id=user.id, scholarship_type_id=sch.id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=115, semester=None,
          status=ApplicationStatus.under_review, review_stage=ReviewStage.college_ranked,
          is_renewal=False, agree_terms=True,
      )
      db.add(app)
      await db.commit()
      await db.refresh(app)
      ranking = CollegeRanking(
          scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=115,
          semester=None, is_finalized=True, ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      item = CollegeRankingItem(
          ranking_id=ranking.id, application_id=app.id, rank_position=1,
          is_allocated=False, status="ranked",
      )
      db.add(item)
      await db.commit()
      await db.refresh(item)
      return {"sch": sch, "cfg": cfg, "item": item, "app": app}


  @pytest.mark.asyncio
  async def test_restore_writes_config_id(db: AsyncSession, setup):
      svc = ManualDistributionService(db)
      snapshot = {
          str(setup["item"].id): {
              "sub_type": "nstc",
              "allocation_config_id": setup["cfg"].id,
              "status": "allocated",
          }
      }
      result = await svc.restore_from_history(setup["sch"].id, 115, "yearly", snapshot)
      assert result["restored_count"] == 1
      refreshed = (
          await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.id == setup["item"].id))
      ).scalar_one()
      assert refreshed.is_allocated is True
      assert refreshed.allocation_config_id == setup["cfg"].id


  @pytest.mark.asyncio
  async def test_batch_load_previous_allocation_config(db: AsyncSession, setup):
      # Mark the existing item allocated to cfg as a "previous" slot.
      item = setup["item"]
      item.is_allocated = True
      item.allocated_sub_type = "nstc"
      item.allocation_config_id = setup["cfg"].id
      await db.commit()

      svc = ManualDistributionService(db)
      mapping = await svc._batch_load_previous_allocation_years([setup["app"].id])
      assert mapping == {setup["app"].id: setup["cfg"].id}
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_restore_history_config_id.py -p no:cacheprovider -q` — expect failure (restore reads `allocation_year` from snapshot; `_batch_load_previous_allocation_years` filters `allocation_year.isnot(None)` and returns `allocation_year`).
- [ ] Update `restore_from_history` docstring + clear loop + restore loop. The docstring (`:826-827`) currently says `The snapshot contains: {ranking_item_id: {sub_type, allocation_year, status}, ...}`; replace with `The snapshot contains: {ranking_item_id: {sub_type, allocation_config_id, status}, ...}`. The clear loop (`:847-852`):
  ```python
              for item in items:
                  item.is_allocated = False
                  item.allocated_sub_type = None
                  item.allocation_year = None
                  item.status = "ranked"
                  item.allocation_reason = None
  ```
  Replace with:
  ```python
              for item in items:
                  item.is_allocated = False
                  item.allocated_sub_type = None
                  item.allocation_config_id = None
                  item.status = "ranked"
                  item.allocation_reason = None
  ```
  The restore loop (`:863-869`):
  ```python
                  if item and alloc_data.get("sub_type"):
                      item.is_allocated = True
                      item.allocated_sub_type = alloc_data["sub_type"]
                      item.allocation_year = alloc_data.get("allocation_year")
                      item.status = alloc_data.get("status", "allocated")
                      item.allocation_reason = "還原歷史分發"
                      restored_count += 1
  ```
  Replace with:
  ```python
                  if item and alloc_data.get("sub_type"):
                      item.is_allocated = True
                      item.allocated_sub_type = alloc_data["sub_type"]
                      item.allocation_config_id = alloc_data.get("allocation_config_id")
                      item.status = alloc_data.get("status", "allocated")
                      item.allocation_reason = "還原歷史分發"
                      restored_count += 1
  ```
- [ ] Rewrite `_batch_load_previous_allocation_years` (`:1056-1081`). Current:
  ```python
      async def _batch_load_previous_allocation_years(self, previous_app_ids: list[int]) -> dict[int, int]:
          """
          For renewal students, find the allocation_year from their previous application's
          CollegeRankingItem.

          Returns: {previous_application_id: allocation_year}
          Only includes entries where allocation_year IS NOT NULL.
          """
          if not previous_app_ids:
              return {}

          stmt = select(CollegeRankingItem).where(
              and_(
                  CollegeRankingItem.application_id.in_(previous_app_ids),
                  CollegeRankingItem.allocation_year.isnot(None),
              )
          )
          result = await self.db.execute(stmt)
          items = result.scalars().all()

          # If a previous app appears in multiple ranking items, use the first one
          mapping: dict[int, int] = {}
          for item in items:
              if item.application_id not in mapping:
                  mapping[item.application_id] = item.allocation_year
          return mapping
  ```
  Replace with:
  ```python
      async def _batch_load_previous_allocation_years(self, previous_app_ids: list[int]) -> dict[int, int]:
          """
          For renewal students, find the allocation_config_id from their previous
          application's CollegeRankingItem (the config that prior slot consumed).

          Returns: {previous_application_id: allocation_config_id}
          Only includes entries where allocation_config_id IS NOT NULL.
          """
          if not previous_app_ids:
              return {}

          stmt = select(CollegeRankingItem).where(
              and_(
                  CollegeRankingItem.application_id.in_(previous_app_ids),
                  CollegeRankingItem.allocation_config_id.isnot(None),
              )
          )
          result = await self.db.execute(stmt)
          items = result.scalars().all()

          # If a previous app appears in multiple ranking items, use the first one
          mapping: dict[int, int] = {}
          for item in items:
              if item.application_id not in mapping:
                  mapping[item.application_id] = item.allocation_config_id
          return mapping
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_restore_history_config_id.py -p no:cacheprovider -q` — expect `2 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_restore_history_config_id.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_restore_history_config_id.py && git commit -m "feat(distribution): restore_from_history + prev-slot loader keyed on allocation_config_id"`

---

### Task 3.8: Rewrite `_compute_suggestions` + `auto_allocate_preview` per-(config, sub_type, college) tracker

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:61-195` (`_compute_suggestions`) and `:1083-1231` (`auto_allocate_preview`)
- Modify: `backend/tests/test_auto_allocate_preview.py` (rewrite fixtures/assertions for the new tracker key + `allocation_config_id` output)
- Test: same file `backend/tests/test_auto_allocate_preview.py`

- [ ] Rewrite the test fixtures + assertions in `backend/tests/test_auto_allocate_preview.py` to the new contract: the tracker key is `(config_id, sub_type, college)`, `_compute_suggestions` takes `prev_alloc_configs: dict[int, int]` (prev_app_id → config_id), `allowed_configs_by_sub_type: dict[str, list[int]]` (own-first, then linked by descending year), `own_config_id: int`, and outputs `{"ranking_item_id", "sub_type_code", "allocation_config_id"}`. Update `_make_item` to use `allocation_config_id` and the `_build_quota_tracker` keys. Replace the helper signatures (`:113-137`):
  ```python
  def _make_item(
      item_id: int,
      rank_position: int,
      app: SimpleNamespace,
      is_allocated: bool = False,
      allocated_sub_type: Optional[str] = None,
      allocation_config_id: Optional[int] = None,
  ) -> SimpleNamespace:
      """Build a minimal CollegeRankingItem-like object."""
      return SimpleNamespace(
          id=item_id,
          rank_position=rank_position,
          application=app,
          is_allocated=is_allocated,
          allocated_sub_type=allocated_sub_type,
          allocation_config_id=allocation_config_id,
      )


  def _build_quota_tracker(entries: dict) -> dict:
      """Build a quota tracker dict. entries: {(config_id, sub_type, college): count}."""
      return dict(entries)
  ```
  Then rewrite every test case to: replace each `prior_years_map=...` argument with `allowed_configs_by_sub_type=...` and `own_config_id=115`; replace `prev_alloc_years` with `prev_alloc_configs`; rewrite tracker keys from `(sub_type, year, college)` to `(config_id, sub_type, college)`; assert `allocation_config_id` instead of `allocation_year`. For example, Test 1 (`:148-176`) becomes:
  ```python
      def test_new_applicants_allocated_to_current_year_nstc_first(self, _compute_suggestions):
          own_config_id = 115
          default_prefs = ["nstc", "moe_1w"]
          allowed = {"nstc": [115], "moe_1w": [115]}
          quota_tracker = _build_quota_tracker(
              {
                  (115, "nstc", "A"): 5,
                  (115, "moe_1w", "A"): 3,
              }
          )
          prev_alloc_configs: dict[int, int] = {}

          app1 = _make_app(1, college="A", sub_type_preferences=["nstc", "moe_1w"])
          app2 = _make_app(2, college="A", sub_type_preferences=["nstc", "moe_1w"])
          item1 = _make_item(101, rank_position=1, app=app1)
          item2 = _make_item(102, rank_position=2, app=app2)

          results = _compute_suggestions(
              unique_items=[item1, item2],
              default_prefs=default_prefs,
              prev_alloc_configs=prev_alloc_configs,
              allowed_configs_by_sub_type=allowed,
              quota_tracker=quota_tracker,
              own_config_id=own_config_id,
          )

          assert len(results) == 2
          assert results[0] == {"ranking_item_id": 101, "sub_type_code": "nstc", "allocation_config_id": 115}
          assert results[1] == {"ranking_item_id": 102, "sub_type_code": "nstc", "allocation_config_id": 115}
  ```
  Apply the same mechanical rewrite to the rest: the prior-year tests (Test 3/4/bonus) model a linked config `114` so `allowed = {"nstc": [115, 114]}`, `prev_alloc_configs = {99: 114}`, tracker has `(114, "nstc", "A")` and `(115, "nstc", "A")` keys, and assert `allocation_config_id` is `114` (prior) or `115` (fallback). For "renewal targets previous config" assert `114`; for "prior exhausted falls back" set `(114,"nstc","A"):0`, `(115,"nstc","A"):5` and assert `115`; the "prior not configured" bonus sets `prev_alloc_configs={99:112}` with `allowed={"nstc":[115]}` (112 not linked) and asserts `115`. For the already-allocated test, pass `allocation_config_id=115` and assert the tracker key `(115,"nstc","A")` stays `5`.
- [ ] Run it, expect FAIL: `python -m pytest backend/tests/test_auto_allocate_preview.py -p no:cacheprovider -q` from `/home/howard/scholarship-system` — expect `TypeError: _compute_suggestions() got an unexpected keyword argument 'allowed_configs_by_sub_type'`.
- [ ] Rewrite `_compute_suggestions` (`:61-195`). Replace the signature, docstring, and body. Write COMPLETE code (the per-config tracker honours the cross-config pool cap because the tracker is seeded from `remaining(config, sub_type)` per the calling site; per-college caps survive because the key still carries `college`):
  ```python
  def _compute_suggestions(
      unique_items: list,
      default_prefs: list[str],
      prev_alloc_configs: dict[int, int],
      allowed_configs_by_sub_type: dict[str, list[int]],
      quota_tracker: dict[tuple, int],
      own_config_id: int,
      rejected_map: Optional[dict[int, set[str]]] = None,
  ) -> list[dict]:
      """
      Pure allocation logic (no DB access).  Extracted so it can be unit-tested
      without mocking async SQLAlchemy sessions.

      Parameters
      ----------
      unique_items:
          CollegeRankingItem objects (with .application pre-loaded) already
          deduplicated by application_id.  Already-allocated items are skipped.
      default_prefs:
          Ordered sub_type codes; last-resort preference fallback.
      prev_alloc_configs:
          {previous_application_id: allocation_config_id} for renewal students'
          prior allocations — the config that prior slot consumed.
      allowed_configs_by_sub_type:
          {sub_type: [config_id, ...]} own-config-first, then linked source
          configs by descending year. Defines which configs a sub_type may draw.
      quota_tracker:
          Mutable {(config_id, sub_type, college_code): remaining}. Decremented
          as it allocates. The pool cap is already baked into these counts
          (seeded from remaining(config, sub_type) split per college).
      own_config_id:
          The requesting config id (default target when no prior slot applies).
      rejected_map:
          {application_id: {rejected_sub_type_codes}} — excluded from allocation.

      Returns
      -------
      list[dict]
          [{"ranking_item_id", "sub_type_code", "allocation_config_id"}, ...]
          One entry per unallocated input item, in allocation order.
      """
      if rejected_map is None:
          rejected_map = {}
      sorted_items = sorted(
          [item for item in unique_items if not item.is_allocated],
          key=lambda i: (0 if i.application.is_renewal else 1, i.rank_position),
      )

      results: list[dict] = []

      for item in sorted_items:
          if getattr(item, "college_rejected", False):
              results.append(
                  {"ranking_item_id": item.id, "sub_type_code": None, "allocation_config_id": None}
              )
              continue

          app = item.application
          college = (app.student_data or {}).get("std_academyno", "")

          # Preferred target config for a renewal: the config its prior slot consumed.
          prev_app_id = app.previous_application_id if app.is_renewal else None
          target_config: Optional[int] = prev_alloc_configs.get(prev_app_id) if prev_app_id else None

          applied = app.scholarship_subtype_list or []
          rejected = rejected_map.get(app.id, set())
          raw_prefs: list[str] = app.sub_type_preferences or applied or default_prefs
          applied_set = set(applied)
          preferences: list[str] = [
              p for p in raw_prefs if (p in applied_set if applied_set else True) and p not in rejected
          ]

          allocated_sub_type: Optional[str] = None
          allocated_config: Optional[int] = None

          for sub_type in preferences:
              allowed = allowed_configs_by_sub_type.get(sub_type, [own_config_id])
              # Try the renewal's prior config first (if it is an allowed source),
              # then walk the allowed configs in order (own-first, linked by year).
              candidate_order: list[int] = []
              if target_config is not None and target_config in allowed:
                  candidate_order.append(target_config)
              candidate_order.extend(cid for cid in allowed if cid not in candidate_order)

              for cid in candidate_order:
                  key = (cid, sub_type, college)
                  if quota_tracker.get(key, 0) > 0:
                      quota_tracker[key] -= 1
                      allocated_sub_type = sub_type
                      allocated_config = cid
                      break
              if allocated_sub_type:
                  break

          results.append(
              {
                  "ranking_item_id": item.id,
                  "sub_type_code": allocated_sub_type,
                  "allocation_config_id": allocated_config,
              }
          )

      return results
  ```
- [ ] Rewrite `auto_allocate_preview` (`:1083-1231`) to build the per-(config, sub_type, college) tracker from `distributable_pool` and the consumed config matrices. Replace the body from `# --- Step 0b: Load default preferences ---` (`:1141`) through the `return _compute_suggestions(...)` call (`:1223-1231`). Write COMPLETE code:
  ```python
          # --- Step 0b: Load default preferences ---
          default_prefs = await self._get_default_preferences(scholarship_type_id)

          # Previous allocation CONFIG for renewal students (the config prior slot consumed).
          previous_app_ids = [
              item.application.previous_application_id
              for item in unique_items
              if item.application.is_renewal and item.application.previous_application_id
          ]
          prev_alloc_configs = await self._batch_load_previous_allocation_years(previous_app_ids)

          # --- Step 1: Resolve requesting config + its distributable configs ---
          requesting_config = await self._load_config(scholarship_type_id, academic_year, semester)
          if requesting_config is None:
              return []
          linked = await self._load_linked_configs(requesting_config)

          # Configs reachable for any sub_type: own + every linked source.
          all_configs: dict[int, ScholarshipConfiguration] = {requesting_config.id: requesting_config}
          for cfg in linked.values():
              all_configs[cfg.id] = cfg

          # allowed_configs_by_sub_type: own-first then linked by descending year.
          sub_types = set((requesting_config.quotas or {}).keys())
          for entry in requesting_config.shared_quota_sources or []:
              sub_types.update(entry.get("sub_types") or [])
          allowed_configs_by_sub_type: dict[str, list[int]] = {}
          for st in sub_types:
              allowed_configs_by_sub_type[st] = [c["config_id"] for c in await self.distributable_pool(requesting_config, st)]

          # --- Step 2: Build the per-(config, sub_type, college) tracker ---
          # Seed from each consumed config's matrix so per-college caps survive,
          # then subtract every existing global consumer of that config so the
          # tracker reflects live remaining (honors the cross-config pool cap).
          quota_tracker: dict[tuple[str, int, str], int] = {}
          for cid, cfg in all_configs.items():
              if not cfg.has_college_quota or not cfg.quotas:
                  continue
              for sub_type, college_quotas in cfg.quotas.items():
                  if not isinstance(college_quotas, dict):
                      continue
                  for college_code, quota in college_quotas.items():
                      quota_tracker[(cid, sub_type, college_code)] = int(quota)

          # Subtract every already-allocated ranking item pointing at these configs
          # (across ALL rankings, not just this round — global pool).
          existing_stmt = (
              select(CollegeRankingItem)
              .options(selectinload(CollegeRankingItem.application))
              .where(
                  CollegeRankingItem.is_allocated.is_(True),
                  CollegeRankingItem.allocation_config_id.in_(list(all_configs.keys())),
              )
          )
          existing_items = (await self.db.execute(existing_stmt)).scalars().all()
          for ex in existing_items:
              if not ex.allocated_sub_type or ex.application is None:
                  continue
              college = (ex.application.student_data or {}).get("std_academyno", "")
              key = (ex.allocation_config_id, ex.allocated_sub_type, college)
              if key in quota_tracker:
                  quota_tracker[key] = max(0, quota_tracker[key] - 1)

          # Subtract approved renewals consuming these configs (Application half).
          renewal_stmt = (
              select(Application)
              .where(
                  Application.is_renewal.is_(True),
                  Application.status == ApplicationStatus.approved,
                  Application.allocation_config_id.in_(list(all_configs.keys())),
                  Application.deleted_at.is_(None),
              )
          )
          renewal_rows = (await self.db.execute(renewal_stmt)).scalars().all()
          for ra in renewal_rows:
              if not ra.sub_scholarship_type:
                  continue
              college = (ra.student_data or {}).get("std_academyno", "")
              key = (ra.allocation_config_id, ra.sub_scholarship_type, college)
              if key in quota_tracker:
                  quota_tracker[key] = max(0, quota_tracker[key] - 1)

          # Load rejected sub-types from professor reviews.
          app_ids = [item.application.id for item in unique_items]
          rejected_map = await self._batch_load_rejected_map(app_ids)

          return _compute_suggestions(
              unique_items=unique_items,
              default_prefs=default_prefs,
              prev_alloc_configs=prev_alloc_configs,
              allowed_configs_by_sub_type=allowed_configs_by_sub_type,
              quota_tracker=quota_tracker,
              own_config_id=requesting_config.id,
              rejected_map=rejected_map,
          )
  ```
  Also update the `auto_allocate_preview` docstring return line (`:1101`) from `Returns list of {"ranking_item_id", "sub_type_code", "allocation_year"} dicts.` to `Returns list of {"ranking_item_id", "sub_type_code", "allocation_config_id"} dicts.`
- [ ] Run it, expect PASS: `python -m pytest backend/tests/test_auto_allocate_preview.py -p no:cacheprovider -q` from `/home/howard/scholarship-system` — expect all tests pass (e.g. `20 passed`).
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/tests/test_auto_allocate_preview.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/tests/test_auto_allocate_preview.py && git commit -m "feat(distribution): per-config auto-allocate tracker honoring pool cap + per-college caps"`

---

### Task 3.9: Rewrite `compute_distribution_state` (`available_quotas` + `renewal_allocations`) onto `consumers`/per-config

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:1754-1908` (`compute_distribution_state`) and `:1487-1515` (`_count_approved_renewals_per_pool` → re-key onto Application.allocation_config_id)
- Modify: `backend/app/tests/test_distribution_state_endpoint.py` (fixtures: drop `prior_quota_years`, use `shared_quota_sources` + linked config; assertions: `available_quotas` keyed by config, renewal grouping unchanged on `renewal_year` display)
- Test: same file `backend/app/tests/test_distribution_state_endpoint.py`

- [ ] Rewrite the `scholarship_with_config` fixture in `test_distribution_state_endpoint.py` (`:85-114`) to drop `prior_quota_years` and the year-keyed `quotas`, replacing with a matrix quota + a linked prior config. Also add a `phd_114`-style prior config in the same fixture and return both. Replace the fixture body:
  ```python
  @pytest_asyncio.fixture
  async def scholarship_with_config(db: AsyncSession) -> ScholarshipType:
      """Scholarship type + an active config with a matrix quota + a linked prior config."""
      sch = ScholarshipType(
          code="phase8_sch",
          name="Phase 8 Test Scholarship",
          description="Fixture for distribution state endpoint",
      )
      db.add(sch)
      await db.commit()
      await db.refresh(sch)

      prior = ScholarshipConfiguration(
          scholarship_type_id=sch.id,
          academic_year=PRIOR_ACADEMIC_YEAR,
          semester=None,
          config_name="Phase 8 Prior",
          config_code="phase8-config-113",
          amount=30000,
          currency="TWD",
          is_active=True,
          has_college_quota=True,
          quotas={"nstc": {"A": 2}},
      )
      config = ScholarshipConfiguration(
          scholarship_type_id=sch.id,
          academic_year=CURRENT_ACADEMIC_YEAR,
          semester=None,
          config_name="Phase 8 Config",
          config_code="phase8-config",
          amount=30000,
          currency="TWD",
          is_active=True,
          has_college_quota=True,
          quotas={"nstc": {"A": 8}, "moe_1w": {"A": 5}},
          shared_quota_sources=[{"source_config_code": "phase8-config-113", "sub_types": ["nstc"]}],
      )
      db.add_all([prior, config])
      await db.commit()
      return sch
  ```
- [ ] Rewrite the `available_quotas` assertions in the two affected tests. In `test_returns_empty_state_when_no_data` (`:276-289`), replace the year-keyed block with config-keyed:
  ```python
      # available_quotas keyed by config: own nstc total 8 (remaining 8), linked
      # phase8-config-113 nstc total 2 (remaining 2), own moe_1w total 5.
      by_key = {(q["sub_type"], q["config_code"]): q for q in data["available_quotas"]}
      assert by_key[("nstc", "phase8-config")]["total"] == 8
      assert by_key[("nstc", "phase8-config")]["remaining"] == 8
      assert by_key[("nstc", "phase8-config-113")]["remaining"] == 2
      assert by_key[("moe_1w", "phase8-config")]["remaining"] == 5
      assert len(data["available_quotas"]) == 3
  ```
  In `test_groups_renewal_allocations_correctly` (`:363-375`), the renewals are created without `allocation_config_id`, so to assert subtraction we must set it. Add after the four `_make_renewal_app` calls (before the GET) a block that points the two `nstc` renewals at the own config and refreshes; then replace the quota assertions:
  ```python
      # Point the approved nstc renewals at the own config so they consume its pool.
      from sqlalchemy import select as _select

      own_cfg = (
          await db.execute(
              _select(ScholarshipConfiguration).where(
                  ScholarshipConfiguration.config_code == "phase8-config"
              )
          )
      ).scalar_one()
      ren_rows = (
          await db.execute(
              _select(Application).where(
                  Application.scholarship_type_id == scholarship_with_config.id,
                  Application.is_renewal.is_(True),
              )
          )
      ).scalars().all()
      for r in ren_rows:
          r.allocation_config_id = own_cfg.id
      await db.commit()
  ```
  and replace the quota assertion block with:
  ```python
      quotas_by_key = {(q["sub_type"], q["config_code"]): q for q in data["available_quotas"]}
      # 3 nstc renewals + 1 moe_1w renewal all consume own config (phase8-config).
      assert quotas_by_key[("nstc", "phase8-config")]["used"] == 3
      assert quotas_by_key[("nstc", "phase8-config")]["remaining"] == 5
      assert quotas_by_key[("moe_1w", "phase8-config")]["used"] == 1
      assert quotas_by_key[("moe_1w", "phase8-config")]["remaining"] == 4
  ```
  (Renewal grouping by `(sub_type, renewal_year)` is display-only and unchanged, so the `renewal_allocations` assertions at `:351-361` stay as-is.)
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_distribution_state_endpoint.py -p no:cacheprovider -q` — expect `KeyError: ('nstc', 'phase8-config')` (today's `available_quotas` carries `allocation_year`, not `config_code`).
- [ ] Re-key `_count_approved_renewals_per_pool` (`:1487-1515`) onto `Application.allocation_config_id`. Replace the whole method:
  ```python
      async def _count_approved_renewals_per_pool(
          self, scholarship_type_id: int, academic_year: int
      ) -> dict[tuple[str, int], int]:
          """Count approved renewals grouped by (sub_scholarship_type, allocation_config_id).

          Renewals consume the config their prior slot consumed (spec §9), so the
          quota key is allocation_config_id — one indexed query, no recursive
          previous_application_id walk. Renewals with a NULL allocation_config_id
          are skipped (an approved renewal should never be NULL — see §11.3).
          """
          stmt = (
              select(
                  Application.sub_scholarship_type,
                  Application.allocation_config_id,
                  func.count(Application.id),
              )
              .where(
                  Application.scholarship_type_id == scholarship_type_id,
                  Application.academic_year == academic_year,
                  Application.is_renewal.is_(True),
                  Application.status == ApplicationStatus.approved,
                  Application.allocation_config_id.isnot(None),
              )
              .group_by(Application.sub_scholarship_type, Application.allocation_config_id)
          )
          rows = (await self.db.execute(stmt)).all()
          result: dict[tuple[str, int], int] = {}
          for sub_type, config_id, count in rows:
              result[(sub_type, int(config_id))] = result.get((sub_type, int(config_id)), 0) + int(count)
          return result
  ```
- [ ] Rewrite the `available_quotas` build in `compute_distribution_state` (`:1821-1848`). The renewal-grouping block (`:1780-1819`) and candidates block (`:1850-1899`) are display-only and stay (they read `renewal_year` for display). Replace the `available_quotas` section. Current:
  ```python
          # --- 2. Available quotas per (sub_type, allocation_year) --- #
          used = await self._count_approved_renewals_per_pool(scholarship_type_id, academic_year)
          available_quotas: list[dict[str, Any]] = []
          for sub_type, year_map in quotas.items():
              # Skip legacy non-year-keyed entries (e.g. {college_code: int}).
              if not isinstance(year_map, dict):
                  continue
              for year_key, total in year_map.items():
                  try:
                      year = int(year_key)
                  except (TypeError, ValueError):
                      # Non-int keys (legacy college matrix) are not used by
                      # the Phase 6 algorithm — skip silently.
                      continue
                  try:
                      total_int = int(total)
                  except (TypeError, ValueError):
                      continue
                  used_count = used.get((sub_type, year), 0)
                  available_quotas.append(
                      {
                          "sub_type": sub_type,
                          "allocation_year": year,
                          "total": total_int,
                          "used": used_count,
                          "remaining": total_int - used_count,
                      }
                  )
  ```
  Replace with (per-config columns via `distributable_pool`, total via `pool_total`, used via global consumers):
  ```python
          # --- 2. Available quotas per (sub_type, config) — live shared pool --- #
          available_quotas: list[dict[str, Any]] = []
          linked = await self._load_linked_configs(config)
          all_configs: dict[int, ScholarshipConfiguration] = {config.id: config}
          for c in linked.values():
              all_configs[c.id] = c

          sub_types = set((config.quotas or {}).keys())
          for entry in config.shared_quota_sources or []:
              sub_types.update(entry.get("sub_types") or [])

          for sub_type in sub_types:
              for col in await self.distributable_pool(config, sub_type):
                  cfg = all_configs.get(col["config_id"])
                  if cfg is None:
                      continue
                  total = self.pool_total(cfg, sub_type)
                  if total <= 0:
                      continue
                  remaining = col["remaining"]
                  available_quotas.append(
                      {
                          "sub_type": sub_type,
                          "config_id": col["config_id"],
                          "config_code": col["config_code"],
                          "academic_year": col["academic_year"],
                          "is_own": col["is_own"],
                          "total": total,
                          "used": total - remaining,
                          "remaining": remaining,
                      }
                  )
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_distribution_state_endpoint.py -p no:cacheprovider -q` — expect `4 passed`.
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_distribution_state_endpoint.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_distribution_state_endpoint.py && git commit -m "feat(distribution): compute_distribution_state available_quotas + renewals keyed by config"`

---

### Task 3.10: Rewrite `execute_general_distribution` onto per-config pool + drop dead `_pick_pool`/`_build_remaining_quota`

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py:1595-1643` (delete `_pick_pool` + `_build_remaining_quota`) and `:1645-1752` (`execute_general_distribution`)
- Test: `backend/app/tests/test_general_distribution_config_id.py` (Create — needs DB, async)

- [ ] Create `backend/app/tests/test_general_distribution_config_id.py`. Build a config `nstc` matrix total 2 + one linked prior config nstc total 1, two ranked pure-new `nstc` candidates, run `execute_general_distribution`; assert both get allocated, the first two consume own config then the linked config, and `cand.allocation_config_id` is set (not `allocation_year`). Also a challenge-release case: a challenge winner cancels its target renewal (whose `allocation_config_id` is set) and the freed slot is re-derived from `remaining(freed_config, st)` for a waitlist fill-in. Write COMPLETE code:
  ```python
  """execute_general_distribution rebuilt onto per-config pool + config-keyed release (spec §6.3, §12)."""

  import pytest
  import pytest_asyncio
  from sqlalchemy import select
  from sqlalchemy.ext.asyncio import AsyncSession

  from app.models.application import Application
  from app.models.college_review import CollegeRanking, CollegeRankingItem
  from app.models.enums import ApplicationStatus, ReviewStage, SubTypeSelectionMode
  from app.models.scholarship import ScholarshipConfiguration, ScholarshipType
  from app.models.user import User, UserRole, UserType
  from app.services.manual_distribution_service import ManualDistributionService


  async def _student(db, suffix):
      u = User(
          nycu_id=f"gd_{suffix}", name=f"S{suffix}", email=f"gd_{suffix}@u.edu",
          user_type=UserType.student, role=UserRole.student,
      )
      db.add(u)
      await db.commit()
      await db.refresh(u)
      return u


  @pytest_asyncio.fixture
  async def setup(db: AsyncSession):
      sch = ScholarshipType(code="gd_phd", name="GD PhD", description="x")
      db.add(sch)
      await db.commit()
      await db.refresh(sch)
      prior = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=114, semester=None,
          config_name="phd114", config_code="phd_114", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 1}},
      )
      own = ScholarshipConfiguration(
          scholarship_type_id=sch.id, academic_year=115, semester=None,
          config_name="phd115", config_code="phd_115", amount=30000, currency="TWD",
          is_active=True, has_college_quota=True, quotas={"nstc": {"A": 2}},
          shared_quota_sources=[{"source_config_code": "phd_114", "sub_types": ["nstc"]}],
      )
      db.add_all([prior, own])
      await db.commit()
      await db.refresh(own)
      await db.refresh(prior)
      ranking = CollegeRanking(
          scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=115,
          semester=None, is_finalized=True, ranking_status="finalized",
      )
      db.add(ranking)
      await db.commit()
      await db.refresh(ranking)
      return {"sch": sch, "own": own, "prior": prior, "ranking": ranking}


  async def _new_candidate(db, *, sch_id, ranking_id, rank, suffix):
      u = await _student(db, suffix)
      a = Application(
          app_id=f"APP-115-0-{suffix}", user_id=u.id, scholarship_type_id=sch_id,
          scholarship_subtype_list=["nstc"], sub_type_selection_mode=SubTypeSelectionMode.single,
          sub_scholarship_type="nstc", academic_year=115, semester=None,
          status=ApplicationStatus.under_review, review_stage=ReviewStage.college_ranked,
          is_renewal=False, agree_terms=True,
      )
      db.add(a)
      await db.commit()
      await db.refresh(a)
      item = CollegeRankingItem(
          ranking_id=ranking_id, application_id=a.id, rank_position=rank,
          is_allocated=False, status="ranked",
      )
      db.add(item)
      await db.commit()
      await db.refresh(item)
      return a, item


  @pytest.mark.asyncio
  async def test_general_distribution_fills_own_then_linked(db: AsyncSession, setup):
      sch, own, prior, ranking = setup["sch"], setup["own"], setup["prior"], setup["ranking"]
      a1, i1 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=1, suffix="c1")
      a2, i2 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=2, suffix="c2")
      a3, i3 = await _new_candidate(db, sch_id=sch.id, ranking_id=ranking.id, rank=3, suffix="c3")

      svc = ManualDistributionService(db)
      await svc.execute_general_distribution(sch.id, 115)

      items = {
          it.application_id: it
          for it in (
              await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.ranking_id == ranking.id))
          ).scalars().all()
      }
      # 2 own slots + 1 linked slot = 3 total; all three candidates get allocated.
      assigned = [items[a.id].allocation_config_id for a in (a1, a2, a3)]
      assert assigned.count(own.id) == 2
      assert assigned.count(prior.id) == 1
      assert all(items[a.id].is_allocated for a in (a1, a2, a3))
      assert all(items[a.id].allocation_config_id is not None for a in (a1, a2, a3))
  ```
- [ ] Run it, expect FAIL: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_general_distribution_config_id.py -p no:cacheprovider -q` — expect failure (today's `execute_general_distribution` writes `cand.allocation_year` keyed off `_build_remaining_quota`/`_pick_pool` which read year-keyed quotas, so the linked-config slot is never used and `allocation_config_id` stays NULL).
- [ ] Delete the dead `_pick_pool` (`:1595-1617`) and `_build_remaining_quota` (`:1619-1643`) methods entirely. Remove the block beginning `@staticmethod\n    def _pick_pool(` through the end of `_build_remaining_quota` returning `return remaining`.
- [ ] Rewrite `execute_general_distribution` (`:1645-1752`). Replace the whole method body (keep the signature). Write COMPLETE code (per-sub_type working remaining seeded from `distributable_pool`, `_pick_config` chooses own-then-linked, release map keyed on the cancelled renewal's `allocation_config_id`, fill-in re-derives `remaining(freed_config, st)`):
  ```python
      async def execute_general_distribution(
          self,
          scholarship_type_id: int,
          academic_year: int,
      ) -> dict[str, Any]:
          """Run general-phase distribution with challenge release and waitlist fill-in.

          Rebuilt onto the live shared pool (spec §6.3):
          1. Per sub_type, seed working_remaining{config_id} from distributable_pool.
          2. First-round: assign each ranked candidate to the next config with
             positive working remaining (own first, then linked by year).
          3. Each approved challenge cancels its renewal target; track the freed
             slot keyed on the cancelled renewal's allocation_config_id.
          4. Fill released slots from the same-sub_type waitlist, re-deriving
             remaining(freed_config, st) rather than trusting a raw release count.
          """
          config = await self._get_active_config(scholarship_type_id, academic_year)
          await self._load_linked_configs(config)
          sub_types = list((config.quotas or {}).keys())

          # 1+2. First-round distribution per sub_type.
          approved_challenges: list[Application] = []
          for sub_type in sub_types:
              pool = await self.distributable_pool(config, sub_type)
              working_remaining: dict[int, int] = {c["config_id"]: c["remaining"] for c in pool}
              candidates = await self._get_general_candidates(scholarship_type_id, academic_year, sub_type)
              for cand in candidates:
                  picked = await self._pick_config(config, sub_type, working_remaining)
                  if picked is None:
                      break
                  app = cand.application
                  if app is None:
                      continue
                  app.status = ApplicationStatus.approved
                  app.sub_scholarship_type = sub_type
                  app.quota_allocation_status = "allocated"
                  app.review_stage = ReviewStage.quota_distributed
                  app.approved_at = datetime.now(timezone.utc)
                  cand.is_allocated = True
                  cand.allocated_sub_type = sub_type
                  cand.allocation_config_id = picked
                  cand.status = "allocated"
                  cand.allocation_reason = "一般階段自動分發"
                  working_remaining[picked] -= 1
                  if app.challenges_application_id is not None:
                      approved_challenges.append(app)

          # 3. Release handling — approved challenges cancel their renewal targets.
          challenge_renewal_ids = [
              app.challenges_application_id for app in approved_challenges if app.challenges_application_id is not None
          ]
          renewal_apps_by_id: dict[int, Application] = {}
          if challenge_renewal_ids:
              renewal_apps_by_id = {
                  app.id: app
                  for app in (
                      await self.db.scalars(select(Application).where(Application.id.in_(challenge_renewal_ids)))
                  ).all()
              }

          # released keyed on (sub_type, freed_config_id) from the cancelled renewal.
          released: dict[tuple[str, int], int] = {}
          for challenge_app in approved_challenges:
              renewal_app = renewal_apps_by_id.get(challenge_app.challenges_application_id)
              if renewal_app is None:
                  logger.warning(
                      "Challenge app %s references missing renewal id=%s — skipping release",
                      challenge_app.id,
                      challenge_app.challenges_application_id,
                  )
                  continue
              renewal_app.status = ApplicationStatus.cancelled_by_challenge
              renewal_app.cancelled_due_to_application_id = challenge_app.id
              freed_config_id = renewal_app.allocation_config_id
              if freed_config_id is None:
                  logger.warning(
                      "Cancelled renewal id=%s has no allocation_config_id — cannot release a slot",
                      renewal_app.id,
                  )
                  continue
              key = (renewal_app.sub_scholarship_type, freed_config_id)
              released[key] = released.get(key, 0) + 1

          # 4. Fill released slots from waitlist of same sub_type, re-deriving
          # remaining(freed_config, st) after the cancellations above were flushed.
          await self.db.flush()
          fill_in_count = 0
          all_configs = {config.id: config}
          linked = getattr(config, "_linked_configs", {}) or {}
          for c in linked.values():
              all_configs[c.id] = c
          for (sub_type, freed_config_id), _count in released.items():
              freed_config = all_configs.get(freed_config_id)
              if freed_config is None:
                  freed_config = (
                      await self.db.execute(
                          select(ScholarshipConfiguration).where(ScholarshipConfiguration.id == freed_config_id)
                      )
                  ).scalar_one_or_none()
                  if freed_config is None:
                      continue
              available = await self.remaining(freed_config, sub_type)
              if available <= 0:
                  continue
              waitlist = await self._get_waitlist_candidates(scholarship_type_id, academic_year, sub_type, limit=available)
              for cand in waitlist:
                  app = cand.application
                  if app is None:
                      continue
                  app.status = ApplicationStatus.approved
                  app.sub_scholarship_type = sub_type
                  app.quota_allocation_status = "allocated"
                  app.review_stage = ReviewStage.quota_distributed
                  app.approved_at = datetime.now(timezone.utc)
                  cand.is_allocated = True
                  cand.allocated_sub_type = sub_type
                  cand.allocation_config_id = freed_config_id
                  cand.status = "allocated"
                  cand.allocation_reason = "釋出 slot 候補遞補"
                  fill_in_count += 1

          await self.db.commit()

          return {
              "approved_challenges": len(approved_challenges),
              "released_slots": {f"{st}:{cid}": n for (st, cid), n in released.items()},
              "filled_in": fill_in_count,
              "unfilled": sum(released.values()) - fill_in_count,
          }
  ```
- [ ] Run it, expect PASS: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_general_distribution_config_id.py -p no:cacheprovider -q` — expect `1 passed`.
- [ ] Run the broader challenge-release suite to catch regressions from the return-shape change: `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_challenge_release_distribution.py -p no:cacheprovider -q` — if any assertion references the removed `approved_renewals` key or year-keyed `released_slots`, fix it in this commit (the keys are now `released_slots` as `"{sub_type}:{config_id}"` and `approved_renewals` is dropped).
- [ ] Lint: `uvx --from "black==26.3.1" black --line-length=120 backend/app/services/manual_distribution_service.py backend/app/tests/test_general_distribution_config_id.py` then `cd backend && flake8 app/services/manual_distribution_service.py --select=B904,B014 --max-line-length=120` — expect no output.
- [ ] Commit: `git add backend/app/services/manual_distribution_service.py backend/app/tests/test_general_distribution_config_id.py && git commit -m "feat(distribution): execute_general_distribution onto per-config pool + config-keyed release; drop dead _pick_pool/_build_remaining_quota"`

---

### Task 3.11: Frontend `AllocationItem.allocation_config_id` + pool column type

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:76-86` (`AllocationItem`, `AllocationSuggestion`), and add the per-config pool column type
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts` (Modify — allocate body pins `allocation_config_id`)

- [ ] Read the current FE test to find the allocate-body assertion that pins `allocation_year`: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`. Update the test case that builds an `AllocationItem`/`AllocateRequest` so its `allocations[0]` uses `allocation_config_id: <number>` instead of `allocation_year`, and the POST-body assertion expects `allocation_config_id`. (The exact lines depend on the file; change every `allocation_year` in an allocate-payload context to `allocation_config_id`.)
- [ ] Run it, expect FAIL: `cd frontend && npx jest lib/api/modules/__tests__/manual-distribution.test.ts` — expect a type/assertion error (object literal may only specify known properties: `allocation_year` does not exist in `AllocationItem`, or the body assertion mismatches).
- [ ] Edit `frontend/lib/api/modules/manual-distribution.ts`. Replace the `AllocationItem`/`AllocationSuggestion` interfaces (`:76-86`):
  ```typescript
  export interface AllocationItem {
    ranking_item_id: number;
    sub_type_code: string | null;
    allocation_year: number | null;
  }

  export interface AllocationSuggestion {
    ranking_item_id: number;
    sub_type_code: string | null;
    allocation_year: number | null;
  }
  ```
  with:
  ```typescript
  export interface AllocationItem {
    ranking_item_id: number;
    sub_type_code: string | null;
    allocation_config_id: number | null;
  }

  export interface AllocationSuggestion {
    ranking_item_id: number;
    sub_type_code: string | null;
    allocation_config_id: number | null;
  }
  ```
- [ ] Add the per-config pool column type. After the `SubTypeYearCol` interface (`:66-74`), add a new `SubTypeConfigCol` reflecting the backend `by_config` shape:
  ```typescript
  /** A (sub_type × source-config) pool column for the distribution grid. */
  export interface SubTypeConfigCol {
    config_id: number;
    config_code: string;
    academic_year: number;
    is_own: boolean;
    sub_type: string;
    remaining: number;
  }
  ```
- [ ] Run it, expect PASS: `cd frontend && npx jest lib/api/modules/__tests__/manual-distribution.test.ts` — expect the suite passes.
- [ ] Typecheck: `cd frontend && npx tsc --noEmit -p tsconfig.json` — expect no errors from this module (note: `ManualDistributionPanel.tsx` consumption is a later phase; if tsc surfaces errors there, they belong to the Panel task, not this one — verify the only new errors are in files outside this task's scope before proceeding).
- [ ] Commit: `git add frontend/lib/api/modules/manual-distribution.ts frontend/lib/api/modules/__tests__/manual-distribution.test.ts && git commit -m "feat(distribution): FE AllocationItem.allocation_config_id + per-config pool column type"`


## Phase 4 — Roster generation + renewals

### Task 4.1: Roster generation groups by (allocation_config_id, sub_type) and resolves consumed config per group

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/roster_service.py:1510-1565` (`generate_rosters_from_distribution` grouping + per-group consumed-config resolution)
- Test: `/home/howard/scholarship-system/backend/app/tests/test_roster_generate_per_config_group.py` (Create)

- [ ] Write a failing test. Create `/home/howard/scholarship-system/backend/app/tests/test_roster_generate_per_config_group.py`:

```python
"""Pin: generate_rosters_from_distribution groups allocated ranking items by
(allocation_config_id, sub_type) and resolves the CONSUMED config per group —
a borrowed slot whose allocation_config_id points at a prior-year sibling
config produces a roster carrying that sibling's id/year, not the requesting
config's."""

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import PaymentRoster
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _admin(db_sync):
    u = User(
        nycu_id="gen_admin",
        email="gen_admin@nycu.edu.tw",
        name="Gen Admin",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


def _student(db_sync, nycu_id):
    u = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name=f"Student {nycu_id}",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


def _config(db_sync, scholarship, *, academic_year, code, project_numbers=None):
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester="first",
        amount=50000,
        has_quota_limit=False,
        project_numbers=project_numbers,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def _application(db_sync, user, scholarship, config, *, app_id, std_code, alloc_config_id):
    a = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=115,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        allocation_config_id=alloc_config_id,
        student_data={
            "std_stdcode": std_code,
            "std_pid": f"A{std_code}",
            "std_cname": f"學生{std_code}",
        },
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=50000,
    )
    db_sync.add(a)
    db_sync.flush()
    return a


def test_generate_groups_by_allocation_config(db_sync):
    admin = _admin(db_sync)
    sch = ScholarshipType(code="gen_sch", name="Gen", description="x")
    db_sync.add(sch)
    db_sync.flush()
    own = _config(db_sync, sch, academic_year=115, code="GEN-115", project_numbers={"nstc": "115R000001"})
    prior = _config(db_sync, sch, academic_year=114, code="GEN-114", project_numbers={"nstc": "114R000001"})

    ua = _student(db_sync, "gen_a")
    ub = _student(db_sync, "gen_b")
    app_a = _application(db_sync, ua, sch, own, app_id="APP-GEN-A", std_code="115A", alloc_config_id=own.id)
    app_b = _application(db_sync, ub, sch, own, app_id="APP-GEN-B", std_code="115B", alloc_config_id=prior.id)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="nstc",
        academic_year=115,
        semester="first",
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
    )
    db_sync.add(ranking)
    db_sync.flush()
    for app, cfg in ((app_a, own), (app_b, prior)):
        db_sync.add(
            CollegeRankingItem(
                ranking_id=ranking.id,
                application_id=app.id,
                rank_position=1,
                is_allocated=True,
                allocated_sub_type="nstc",
                allocation_config_id=cfg.id,
                status="allocated",
            )
        )
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    rosters = svc.generate_rosters_from_distribution(
        scholarship_type_id=sch.id,
        academic_year=115,
        semester="first",
        created_by_user_id=admin.id,
        student_verification_enabled=False,
    )

    by_config = {r.allocation_config_id: r for r in rosters}
    assert set(by_config) == {own.id, prior.id}
    # Own-config roster: snapshot year = 115, project_number from own config.
    assert by_config[own.id].allocation_year == 115
    assert by_config[own.id].project_number == "115R000001"
    # Borrowed-slot roster: consumed = prior config → year 114, prior project_number.
    assert by_config[prior.id].allocation_year == 114
    assert by_config[prior.id].project_number == "114R000001"
    assert by_config[prior.id].scholarship_configuration_id == own.id
```

- [ ] Run it, expect FAIL. Command:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_generate_per_config_group.py -p no:cacheprovider -q
```
Expected failure: `TypeError` / `AttributeError` — `_generate_one_sub_type_roster() got an unexpected keyword argument` (or grouping still keyed on the dropped `allocation_year`), because the grouping currently reads `item.allocation_year`.

- [ ] Implement the grouping rewrite. In `/home/howard/scholarship-system/backend/app/services/roster_service.py`, the current block (lines 1510-1561) reads:

```python
        # 3. 取得所有已分配的 ranking items，並按 (allocation_year, allocated_sub_type) 分組
        allocated_items = (
            self.db.query(CollegeRankingItem)
            .filter(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
            .all()
        )

        if not allocated_items:
            raise ValueError(f"排名 {ranking_ids} 沒有已分配的學生。請確認已完成手動分發並確認分發。")

        # 分組：{(allocation_year, sub_type): [ranking_item, ...]}
        groups: Dict[tuple, List] = {}
        for item in allocated_items:
            alloc_year = item.allocation_year or academic_year
            sub_type = item.allocated_sub_type or "general"
            key = (alloc_year, sub_type)
            groups.setdefault(key, []).append(item)

        logger.info(
            f"Rankings {ranking_ids}: found {len(allocated_items)} allocated items in {len(groups)} groups: "
            + ", ".join(f"{sub_type}-{yr}({len(items)}人)" for (yr, sub_type), items in groups.items())
        )

        # 4. 為每個分組建立造冊
        created_rosters: List[PaymentRoster] = []

        for (alloc_year, sub_type), group_items in groups.items():
            application_ids_in_group = {item.application_id for item in group_items}

            try:
                roster = self._generate_one_sub_type_roster(
                    scholarship_config=scholarship_config,
                    ranking_ids=ranking_ids,
                    allocation_year=alloc_year,
                    sub_type=sub_type,
                    application_ids_in_group=application_ids_in_group,
                    created_by_user_id=created_by_user_id,
                    student_verification_enabled=student_verification_enabled,
                    force_regenerate=force_regenerate,
                )
                created_rosters.append(roster)
            except RosterAlreadyExistsError:
                logger.info(f"Roster for ({alloc_year}, {sub_type}) already exists, skipping.")
                continue
            except Exception:
                logger.exception(f"Failed to generate roster for ({alloc_year}, {sub_type})")
                raise
```

Replace it with grouping by `(allocation_config_id, sub_type)` and per-group consumed-config resolution:

```python
        # 3. 取得所有已分配的 ranking items，並按 (allocation_config_id, allocated_sub_type) 分組
        allocated_items = (
            self.db.query(CollegeRankingItem)
            .filter(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
            .all()
        )

        if not allocated_items:
            raise ValueError(f"排名 {ranking_ids} 沒有已分配的學生。請確認已完成手動分發並確認分發。")

        # 分組：{(allocation_config_id, sub_type): [ranking_item, ...]}
        # allocation_config_id NULL ⇒ 消耗本配置（requesting config）的配額。
        groups: Dict[tuple, List] = {}
        for item in allocated_items:
            alloc_config_id = item.allocation_config_id or scholarship_config.id
            sub_type = item.allocated_sub_type or "general"
            key = (alloc_config_id, sub_type)
            groups.setdefault(key, []).append(item)

        # 預先載入每個分組的「消耗配置」(consumed config) — 借用配額時是前年度的同代碼配置
        consumed_configs: Dict[int, ScholarshipConfiguration] = {scholarship_config.id: scholarship_config}
        for (alloc_config_id, _sub_type) in groups:
            if alloc_config_id not in consumed_configs:
                consumed = self.db.get(ScholarshipConfiguration, alloc_config_id)
                if consumed is None:
                    raise ValueError(f"找不到消耗配置 scholarship_configuration_id={alloc_config_id}")
                consumed_configs[alloc_config_id] = consumed

        logger.info(
            f"Rankings {ranking_ids}: found {len(allocated_items)} allocated items in {len(groups)} groups: "
            + ", ".join(
                f"{sub_type}-cfg{cid}({len(items)}人)" for (cid, sub_type), items in groups.items()
            )
        )

        # 4. 為每個分組建立造冊（以該分組的消耗配置為準）
        created_rosters: List[PaymentRoster] = []

        for (alloc_config_id, sub_type), group_items in groups.items():
            application_ids_in_group = {item.application_id for item in group_items}
            consumed_config = consumed_configs[alloc_config_id]

            try:
                roster = self._generate_one_sub_type_roster(
                    requesting_config=scholarship_config,
                    consumed_config=consumed_config,
                    ranking_ids=ranking_ids,
                    sub_type=sub_type,
                    application_ids_in_group=application_ids_in_group,
                    created_by_user_id=created_by_user_id,
                    student_verification_enabled=student_verification_enabled,
                    force_regenerate=force_regenerate,
                )
                created_rosters.append(roster)
            except RosterAlreadyExistsError:
                logger.info(f"Roster for (cfg={alloc_config_id}, {sub_type}) already exists, skipping.")
                continue
            except Exception:
                logger.exception(f"Failed to generate roster for (cfg={alloc_config_id}, {sub_type})")
                raise
```

- [ ] Also update the grouping docstring. The current docstring text (lines 1446-1449) reads:
```python
        針對每個唯一的 (allocation_year, sub_type) 組合建立獨立的造冊。
        例如：
          - 115 學年度分發完成後，若有 nstc-115, nstc-114, nstc-113, moe_1w-115 四種組合，
            則會產生 4 個造冊，各自包含對應學生。
```
Replace with:
```python
        針對每個唯一的 (allocation_config_id, sub_type) 組合建立獨立的造冊。
        例如：
          - 115 學年度分發完成後，若 nstc 借用了 phd_114/phd_113 的配額，
            產生 nstc·115、nstc·114、nstc·113、moe_1w·115 四個造冊，各自記錄消耗配置。
```

(The implementation of `_generate_one_sub_type_roster`'s new signature is Task 4.2 — this task only changes the caller and grouping; run after 4.2 lands, or expect the FAIL above until 4.2's signature is in place. Implement 4.2 next so both pass together.)

- [ ] Run the test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_generate_per_config_group.py -p no:cacheprovider -q
```
Expected: `1 passed` (after Task 4.2 lands).

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_generate_per_config_group.py
flake8 backend/app/services/roster_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_generate_per_config_group.py
git commit -m "feat(roster): group distribution rosters by allocation_config_id with per-group consumed config"
```

### Task 4.2: `_generate_one_sub_type_roster` keys project_number / period / existing-lookup on consumed config

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/roster_service.py:1567-1655` (signature + body), `:1758-1774` (audit metadata)
- Test: same file as Task 4.1 (assertions already cover project_number + snapshot year)

- [ ] This task's behavior is asserted by `test_generate_groups_by_allocation_config` in Task 4.1. Re-run it now and expect FAIL on the OLD signature:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_generate_per_config_group.py -p no:cacheprovider -q
```
Expected: `TypeError: _generate_one_sub_type_roster() got an unexpected keyword argument 'requesting_config'`.

- [ ] Rewrite the signature + docstring. Current (lines 1567-1583):
```python
    def _generate_one_sub_type_roster(
        self,
        scholarship_config: ScholarshipConfiguration,
        ranking_ids: List[int],
        allocation_year: int,
        sub_type: str,
        application_ids_in_group: set,
        created_by_user_id: int,
        student_verification_enabled: bool,
        force_regenerate: bool,
    ) -> PaymentRoster:
        """
        為特定 (allocation_year, sub_type) 組合產生一個造冊

        Returns:
            PaymentRoster: 已建立的造冊
        """
        academic_year = scholarship_config.academic_year
        period_label = str(academic_year)  # 學年制：period_label = 學年度
```
Replace with:
```python
    def _generate_one_sub_type_roster(
        self,
        requesting_config: ScholarshipConfiguration,
        consumed_config: ScholarshipConfiguration,
        ranking_ids: List[int],
        sub_type: str,
        application_ids_in_group: set,
        created_by_user_id: int,
        student_verification_enabled: bool,
        force_regenerate: bool,
    ) -> PaymentRoster:
        """
        為特定 (consumed_config, sub_type) 組合產生一個造冊。

        計畫編號 / 金額 / allocation_year 顯示快照取自「消耗配置」(consumed_config)；
        造冊歸屬於發放配置 (requesting_config)。借用前年度配額時兩者不同。

        Returns:
            PaymentRoster: 已建立的造冊
        """
        academic_year = requesting_config.academic_year
        period_label = str(consumed_config.academic_year)  # 以消耗配置的學年度為期間 key
        allocation_year = consumed_config.academic_year  # 顯示快照
```

- [ ] Re-key the project_number lookup (flat) + roster_code + existing-lookup onto the consumed config. Current (lines 1587-1608):
```python
        # 取得計畫編號
        project_number = None
        if scholarship_config.project_numbers:
            sub_type_projects = scholarship_config.project_numbers.get(sub_type, {})
            project_number = sub_type_projects.get(str(allocation_year))

        # 產生造冊代碼（包含 sub_type 和 allocation_year 以確保唯一性）
        roster_code = f"ROSTER-{academic_year}-{sub_type}-{allocation_year}-{scholarship_config.config_code}"

        # 檢查是否已存在
        existing_roster = (
            self.db.query(PaymentRoster)
            .filter(
                and_(
                    PaymentRoster.scholarship_configuration_id == scholarship_config.id,
                    PaymentRoster.period_label == period_label,
                    PaymentRoster.sub_type == sub_type,
                    PaymentRoster.allocation_year == allocation_year,
                )
            )
            .first()
        )
```
Replace with:
```python
        # 取得計畫編號（扁平：consumed_config.project_numbers[sub_type]，無年度 key）
        project_number = None
        if consumed_config.project_numbers:
            project_number = consumed_config.project_numbers.get(sub_type)

        # 產生造冊代碼（包含 sub_type 與消耗配置代碼以確保唯一性）
        roster_code = f"ROSTER-{academic_year}-{sub_type}-{consumed_config.config_code}-{requesting_config.config_code}"

        # 檢查是否已存在（unique key: scholarship_configuration_id + period_label
        # + allocation_config_id + sub_type）
        existing_roster = (
            self.db.query(PaymentRoster)
            .filter(
                and_(
                    PaymentRoster.scholarship_configuration_id == requesting_config.id,
                    PaymentRoster.period_label == period_label,
                    PaymentRoster.sub_type == sub_type,
                    PaymentRoster.allocation_config_id == consumed_config.id,
                )
            )
            .first()
        )
```

- [ ] Write `scholarship_configuration_id` (requesting) + `allocation_config_id` (consumed) + snapshot year on the new-roster constructor. Current (lines 1637-1652):
```python
            roster = PaymentRoster(
                roster_code=roster_code,
                scholarship_configuration_id=scholarship_config.id,
                ranking_id=ranking_ids[0] if ranking_ids else None,  # Use first ranking_id for reference
                period_label=period_label,
                academic_year=academic_year,
                roster_cycle=RosterCycle.YEARLY,
                sub_type=sub_type,
                allocation_year=allocation_year,
                project_number=project_number,
                status=RosterStatus.PROCESSING,
                trigger_type=RosterTriggerType.MANUAL,
                created_by=created_by_user_id,
                student_verification_enabled=student_verification_enabled,
                started_at=datetime.now(timezone.utc),
            )
```
Replace with:
```python
            roster = PaymentRoster(
                roster_code=roster_code,
                scholarship_configuration_id=requesting_config.id,
                allocation_config_id=consumed_config.id,
                ranking_id=ranking_ids[0] if ranking_ids else None,  # Use first ranking_id for reference
                period_label=period_label,
                academic_year=academic_year,
                roster_cycle=RosterCycle.YEARLY,
                sub_type=sub_type,
                allocation_year=allocation_year,  # 顯示快照 = 消耗配置學年度
                project_number=project_number,
                status=RosterStatus.PROCESSING,
                trigger_type=RosterTriggerType.MANUAL,
                created_by=created_by_user_id,
                student_verification_enabled=student_verification_enabled,
                started_at=datetime.now(timezone.utc),
            )
```

- [ ] The force-regenerate branch (lines 1621-1635) keeps `roster = existing_roster` and resets fields; it sets `roster.project_number = project_number` already (line 1633). Add the consumed-config id reset right after that line. Current:
```python
            roster.verification_api_failures = 0
            roster.project_number = project_number
            self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).delete()
```
Replace with:
```python
            roster.verification_api_failures = 0
            roster.project_number = project_number
            roster.allocation_config_id = consumed_config.id
            roster.allocation_year = allocation_year
            self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster.id).delete()
```

- [ ] The audit-log title/metadata (lines 1756-1774) interpolate `allocation_year`; it is still defined (= consumed year), so no change needed there. Verify the call still references `allocation_year` and `sub_type` only — leave as-is.

- [ ] Run Task 4.1's test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_generate_per_config_group.py -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py
flake8 backend/app/services/roster_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/roster_service.py
git commit -m "feat(roster): key roster project_number/period/lookup on consumed config (flat project_numbers)"
```

### Task 4.3: `_create_roster_item` loads consumed config via allocation_config_id, writes item snapshot

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/roster_service.py:819-896` (`_create_roster_item` allocation lookup + item construction)
- Test: `/home/howard/scholarship-system/backend/app/tests/test_roster_item_consumed_config.py` (Create)

- [ ] Write a failing test. Create `/home/howard/scholarship-system/backend/app/tests/test_roster_item_consumed_config.py`:

```python
"""Pin: a roster item built for a borrowed slot draws scholarship_amount and the
allocation_year display snapshot from the CONSUMED config (resolved via
roster.allocation_config_id), while scholarship_name follows the requesting
config's scholarship type (cross-type decision §8). item.allocation_config_id
is written from the roster."""

from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import (
    PaymentRoster,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
    StudentVerificationStatus,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _student(db_sync, nycu_id):
    u = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name=f"Student {nycu_id}",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db_sync.add(u)
    db_sync.flush()
    return u


def _config(db_sync, sch, *, academic_year, code, amount):
    c = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code=code,
        config_name=code,
        academic_year=academic_year,
        semester="first",
        amount=amount,
        has_quota_limit=False,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def test_roster_item_amount_year_from_consumed_config(db_sync):
    admin = User(
        nycu_id="ci_admin",
        email="ci_admin@nycu.edu.tw",
        name="CI",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    db_sync.add(admin)
    db_sync.flush()

    sch = ScholarshipType(code="ci_sch", name="CI Scholarship", description="x")
    db_sync.add(sch)
    db_sync.flush()
    requesting = _config(db_sync, sch, academic_year=115, code="CI-115", amount=60000)
    consumed = _config(db_sync, sch, academic_year=114, code="CI-114", amount=50000)

    user = _student(db_sync, "ci_a")
    app = Application(
        user_id=user.id,
        app_id="APP-CI-A",
        scholarship_type_id=sch.id,
        scholarship_configuration_id=requesting.id,
        academic_year=115,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type="nstc",
        allocation_config_id=consumed.id,
        student_data={"std_stdcode": "115A", "std_pid": "A115A", "std_cname": "甲"},
        submitted_form_data={"fields": {"postal_account": {"value": "0001234567"}}},
        amount=None,  # no per-application override → fall back to consumed config amount
    )
    db_sync.add(app)
    db_sync.flush()

    roster = PaymentRoster(
        roster_code="ROSTER-CI-1",
        scholarship_configuration_id=requesting.id,
        allocation_config_id=consumed.id,
        period_label="114",
        academic_year=115,
        roster_cycle=RosterCycle.YEARLY,
        sub_type="nstc",
        allocation_year=114,
        status=RosterStatus.PROCESSING,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        student_verification_enabled=False,
    )
    db_sync.add(roster)
    db_sync.flush()
    db_sync.commit()

    svc = RosterService(db_sync)
    item = svc._create_roster_item(
        roster, app, None, StudentVerificationStatus.VERIFIED, {"is_eligible": True}
    )
    db_sync.flush()

    # amount fallback comes from the CONSUMED config (50000), not requesting (60000)
    assert int(item.scholarship_amount) == 50000
    # allocation_year snapshot = consumed config academic year
    assert item.allocation_year == 114
    # allocation_config_id copied from the roster
    assert item.allocation_config_id == consumed.id
    # scholarship_name follows the REQUESTING config's scholarship type name
    assert item.scholarship_name == "CI Scholarship"
```

- [ ] Run it, expect FAIL:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_item_consumed_config.py -p no:cacheprovider -q
```
Expected: `TypeError: 'allocation_config_id' is an invalid keyword argument for PaymentRosterItem` (the item constructor does not yet set it) — or `AssertionError` on the amount (currently falls back to `application.scholarship_configuration.amount` = requesting 60000).

- [ ] Implement the consumed-config load + snapshot. The current allocation-lookup block (lines 819-860) sets `allocation_year`/`allocated_sub_type` from the ranking item. Replace the block:
```python
        # 查詢 CollegeRankingItem 以取得備取資訊與分發資訊
        backup_info = None
        allocation_year = None
        allocated_sub_type = None
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        if roster.ranking_id:
            ranking_item = (
                self.db.query(CollegeRankingItem)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.ranking_id == roster.ranking_id,
                    )
                )
                .first()
            )

            if ranking_item:
                if ranking_item.backup_allocations:
                    backup_info = ranking_item.backup_allocations
                    logger.info(f"Application {application.id} has backup allocations: {len(backup_info)} positions")
                allocation_year = ranking_item.allocation_year
                allocated_sub_type = ranking_item.allocated_sub_type

        # 若無 ranking_id（月份造冊），從同學年度已分發排名中查詢
        if not allocated_sub_type:
            alloc_item = (
                self.db.query(CollegeRankingItem)
                .join(CollegeRanking, CollegeRankingItem.ranking_id == CollegeRanking.id)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.is_allocated.is_(True),
                        CollegeRanking.academic_year == roster.academic_year,
                    )
                )
                .first()
            )
            if alloc_item:
                allocation_year = allocation_year or alloc_item.allocation_year
                allocated_sub_type = alloc_item.allocated_sub_type
```
with:
```python
        # 查詢 CollegeRankingItem 以取得備取資訊與分發子類型
        backup_info = None
        allocated_sub_type = None
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        if roster.ranking_id:
            ranking_item = (
                self.db.query(CollegeRankingItem)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.ranking_id == roster.ranking_id,
                    )
                )
                .first()
            )

            if ranking_item:
                if ranking_item.backup_allocations:
                    backup_info = ranking_item.backup_allocations
                    logger.info(f"Application {application.id} has backup allocations: {len(backup_info)} positions")
                allocated_sub_type = ranking_item.allocated_sub_type

        # 若無 ranking_id（月份造冊），從同學年度已分發排名中查詢子類型
        if not allocated_sub_type:
            alloc_item = (
                self.db.query(CollegeRankingItem)
                .join(CollegeRanking, CollegeRankingItem.ranking_id == CollegeRanking.id)
                .filter(
                    and_(
                        CollegeRankingItem.application_id == application.id,
                        CollegeRankingItem.is_allocated.is_(True),
                        CollegeRanking.academic_year == roster.academic_year,
                    )
                )
                .first()
            )
            if alloc_item:
                allocated_sub_type = alloc_item.allocated_sub_type

        # 載入消耗配置 (consumed config) — 借用前年度配額時不同於發放配置。
        # allocation_config_id NULL ⇒ 全期 sentinel，退回造冊自身的發放配置。
        consumed_config = None
        if roster.allocation_config_id is not None:
            consumed_config = self.db.get(ScholarshipConfiguration, roster.allocation_config_id)
        if consumed_config is None:
            consumed_config = application.scholarship_configuration
        # allocation_year 顯示快照取自造冊（= 消耗配置學年度）
        allocation_year = roster.allocation_year
```

- [ ] Update the `PaymentRosterItem(...)` construction (lines 869-893) so `scholarship_amount` falls back to the consumed config, `scholarship_name` stays the requesting config's type name, and `allocation_config_id` is written. Current relevant lines:
```python
            scholarship_name=application.scholarship_configuration.scholarship_type.name,
            scholarship_amount=application.amount or application.scholarship_configuration.amount,
            scholarship_subtype=application.sub_scholarship_type,
            allocation_year=allocation_year,  # 消耗哪一年的配額（補發時不同於 academic_year）
            allocated_sub_type=allocated_sub_type,  # 分發到的子類型快照
```
Replace with:
```python
            scholarship_name=application.scholarship_configuration.scholarship_type.name,
            scholarship_amount=application.amount or consumed_config.amount,
            scholarship_subtype=application.sub_scholarship_type,
            allocation_config_id=roster.allocation_config_id,  # 消耗配置 id 快照
            allocation_year=allocation_year,  # 消耗配置學年度顯示快照
            allocated_sub_type=allocated_sub_type,  # 分發到的子類型快照
```

- [ ] Run the test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_item_consumed_config.py -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_item_consumed_config.py
flake8 backend/app/services/roster_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_item_consumed_config.py
git commit -m "feat(roster): roster item amount/year from consumed config, write allocation_config_id snapshot"
```

### Task 4.4: Reconcile diff matches on allocation_config_id (NULL = whole-period)

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/roster_service.py:1898-1912` (`_resolve_distribution_for_roster` grouping), `:1961-1962,1991-1992,2002` (`get_distribution_diff_for_roster` display fields)
- Test: `/home/howard/scholarship-system/backend/app/tests/test_roster_distribution_reconcile_service.py` (rewrite fixtures/assertions)

- [ ] Rewrite the test fixtures/assertions off `allocation_year` onto `allocation_config_id`. In `/home/howard/scholarship-system/backend/app/tests/test_roster_distribution_reconcile_service.py`:

  Change `_ranking_item` (lines 120-132). Current:
```python
def _ranking_item(db_sync, ranking, application, *, rank, sub_type="nstc", alloc_year=114, allocated=True):
    it = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=rank,
        is_allocated=allocated,
        allocated_sub_type=sub_type if allocated else None,
        allocation_year=alloc_year if allocated else None,
        status="allocated" if allocated else "ranked",
    )
    db_sync.add(it)
    db_sync.flush()
    return it
```
  Replace with:
```python
def _ranking_item(db_sync, ranking, application, *, rank, sub_type="nstc", alloc_config_id, allocated=True):
    it = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=application.id,
        rank_position=rank,
        is_allocated=allocated,
        allocated_sub_type=sub_type if allocated else None,
        allocation_config_id=alloc_config_id if allocated else None,
        status="allocated" if allocated else "ranked",
    )
    db_sync.add(it)
    db_sync.flush()
    return it
```

  Change `_roster` (lines 135-151). Current:
```python
def _roster(db_sync, config, admin, *, status=RosterStatus.LOCKED, sub_type="nstc", alloc_year=114, code="ROSTER-RC-1"):
    r = PaymentRoster(
        roster_code=code,
        scholarship_configuration_id=config.id,
        period_label="114",
        academic_year=114,
        roster_cycle=RosterCycle.YEARLY,
        sub_type=sub_type,
        allocation_year=alloc_year,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        student_verification_enabled=False,
    )
    db_sync.add(r)
    db_sync.flush()
    return r
```
  Replace with:
```python
def _roster(
    db_sync, config, admin, *, status=RosterStatus.LOCKED, sub_type="nstc", alloc_config_id, code="ROSTER-RC-1"
):
    r = PaymentRoster(
        roster_code=code,
        scholarship_configuration_id=config.id,
        allocation_config_id=alloc_config_id,
        period_label="114",
        academic_year=114,
        roster_cycle=RosterCycle.YEARLY,
        sub_type=sub_type,
        allocation_year=114 if alloc_config_id is not None else None,
        status=status,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin.id,
        student_verification_enabled=False,
    )
    db_sync.add(r)
    db_sync.flush()
    return r
```

  Change `_roster_item` (lines 154-169). Current:
```python
def _roster_item(db_sync, roster, application, *, sub_type="nstc", alloc_year=114, amount=50000):
    it = PaymentRosterItem(
        roster_id=roster.id,
        application_id=application.id,
        student_id_number=(application.student_data or {}).get("std_pid", "X"),
        student_name=(application.student_data or {}).get("std_cname", "X"),
        scholarship_name="NSTC",
        scholarship_amount=amount,
        scholarship_subtype=sub_type,
        allocation_year=alloc_year,
        allocated_sub_type=sub_type,
        is_included=True,
    )
    db_sync.add(it)
    db_sync.flush()
    return it
```
  Replace with:
```python
def _roster_item(db_sync, roster, application, *, sub_type="nstc", amount=50000):
    it = PaymentRosterItem(
        roster_id=roster.id,
        application_id=application.id,
        student_id_number=(application.student_data or {}).get("std_pid", "X"),
        student_name=(application.student_data or {}).get("std_cname", "X"),
        scholarship_name="NSTC",
        scholarship_amount=amount,
        scholarship_subtype=sub_type,
        allocation_config_id=roster.allocation_config_id,
        allocation_year=roster.allocation_year,
        allocated_sub_type=sub_type,
        is_included=True,
    )
    db_sync.add(it)
    db_sync.flush()
    return it
```

  In `diff_scenario` (lines 186-192), thread the config id into the ranking items + roster. Current:
```python
    ranking = _ranking(db_sync, sch)
    _ranking_item(db_sync, ranking, app_a, rank=1)  # allocated, in roster
    _ranking_item(db_sync, ranking, app_b, rank=2)  # allocated, missing → to_add
    _ranking_item(db_sync, ranking, app_c, rank=3, allocated=False)  # not allocated
    roster = _roster(db_sync, config, admin)
    _roster_item(db_sync, roster, app_a)  # matches distribution
    item_c = _roster_item(db_sync, roster, app_c)  # orphan → to_remove
```
  Replace with:
```python
    ranking = _ranking(db_sync, sch)
    _ranking_item(db_sync, ranking, app_a, rank=1, alloc_config_id=config.id)  # allocated, in roster
    _ranking_item(db_sync, ranking, app_b, rank=2, alloc_config_id=config.id)  # allocated, missing → to_add
    _ranking_item(db_sync, ranking, app_c, rank=3, alloc_config_id=None, allocated=False)  # not allocated
    roster = _roster(db_sync, config, admin, alloc_config_id=config.id)
    _roster_item(db_sync, roster, app_a)  # matches distribution
    item_c = _roster_item(db_sync, roster, app_c)  # orphan → to_remove
```

  In `test_distribution_diff_lists_missing_and_orphan` (line 223), the assertion `assert entry.allocation_year == 114` stays valid (snapshot is preserved) — leave it.

  In `test_distribution_diff_whole_period_roster_ignores_subtype_slice` (lines 350-355), update to the new helper signatures:
```python
    _ranking_item(db_sync, ranking, app_a, rank=1, alloc_config_id=config.id)  # allocated nstc, already in roster
    _ranking_item(db_sync, ranking, app_b, rank=2, alloc_config_id=config.id)  # allocated nstc, missing → to_add
    _ranking_item(db_sync, ranking, app_c, rank=3, alloc_config_id=None, allocated=False)  # de-allocated → orphan
    roster = _roster(db_sync, config, admin, sub_type=None, alloc_config_id=None, code="ROSTER-WP-1")
```

  In `test_distribution_diff_excludes_to_add_missing_student_data` (line 377-378) and `test_reconcile_add_missing_student_data_raises` (line 395-396), update the `_ranking_item` + `_roster` calls:
```python
    _ranking_item(db_sync, ranking, app_b, rank=1, alloc_config_id=config.id)
    roster = _roster(db_sync, config, admin, alloc_config_id=config.id, code="ROSTER-FILT-1")
```
  and respectively:
```python
    _ranking_item(db_sync, ranking, app_b, rank=1, alloc_config_id=config.id)
    roster = _roster(db_sync, config, admin, alloc_config_id=config.id, code="ROSTER-RC-GUARD-1")
```

- [ ] Run the test, expect FAIL (the service still slices on `allocation_year`):
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_distribution_reconcile_service.py -p no:cacheprovider -q
```
Expected: failures in `test_distribution_diff_lists_missing_and_orphan` / `test_reconcile_*` — the whole-period sentinel still checks `roster.allocation_year is None` and per-slice matching still compares `item.allocation_year`, so `app_b` is mis-grouped.

- [ ] Implement the service-side match on `allocation_config_id`. In `/home/howard/scholarship-system/backend/app/services/roster_service.py`, the per-slice block (lines 1892-1912) currently reads:
```python
        # Whole-period roster (generate_roster / 立即產生造冊): sub_type and
        # allocation_year are both NULL because that path holds EVERY allocated
        # item in the ranking regardless of sub_type (mirrors
        # _get_eligible_applications matrix mode). Slicing by a derived "general"
        # sub_type would exclude every nstc/moe item → empty diff. So for these,
        # the distribution is the full allocated set, no slicing.
        if roster.sub_type is None and roster.allocation_year is None:
            return {item.application_id: item for item in allocated}

        # Per-slice roster (generate_rosters_from_distribution): one roster per
        # (allocation_year, sub_type) group — match that exact group.
        roster_year = roster.allocation_year or config.academic_year
        roster_sub = roster.sub_type or "general"

        result: dict = {}
        for item in allocated:
            item_year = item.allocation_year or config.academic_year
            item_sub = item.allocated_sub_type or "general"
            if item_year == roster_year and item_sub == roster_sub:
                result[item.application_id] = item
        return result
```
Replace with:
```python
        # Whole-period roster (generate_roster / 立即產生造冊): sub_type and
        # allocation_config_id are both NULL because that path holds EVERY
        # allocated item in the ranking regardless of sub_type (mirrors
        # _get_eligible_applications matrix mode). Slicing by a derived "general"
        # sub_type would exclude every nstc/moe item → empty diff. So for these,
        # the distribution is the full allocated set, no slicing.
        if roster.sub_type is None and roster.allocation_config_id is None:
            return {item.application_id: item for item in allocated}

        # Per-slice roster (generate_rosters_from_distribution): one roster per
        # (allocation_config_id, sub_type) group — match that exact group.
        # allocation_config_id NULL on an item ⇒ consumed the requesting config.
        roster_config_id = roster.allocation_config_id or config.id
        roster_sub = roster.sub_type or "general"

        result: dict = {}
        for item in allocated:
            item_config_id = item.allocation_config_id or config.id
            item_sub = item.allocated_sub_type or "general"
            if item_config_id == roster_config_id and item_sub == roster_sub:
                result[item.application_id] = item
        return result
```

- [ ] The `DistributionDiffEntry` display fields still carry `allocation_year` (line 1961 reads `ranking_item.allocation_year` and 1991 reads `item.allocation_year`). `CollegeRankingItem.allocation_year` is DROPPED by migration 2, so the to_add branch must derive the year from the ranking item's consumed config. Replace the to_add entry's `allocation_year=ranking_item.allocation_year` (line 1961) with the consumed-config-derived year. Current `to_add.append(...)` (lines 1953-1966):
```python
            to_add.append(
                DistributionDiffEntry(
                    application_id=app_id,
                    item_id=None,
                    student_id=std_code,
                    student_name=std_name,
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=ranking_item.allocation_year,
                    allocated_sub_type=ranking_item.allocated_sub_type,
                    application_identity=None,
                    scholarship_amount=float(application.amount or config.amount or 0),
                )
            )
```
Replace with:
```python
            consumed = (
                self.db.get(ScholarshipConfiguration, ranking_item.allocation_config_id)
                if ranking_item.allocation_config_id is not None
                else config
            ) or config
            to_add.append(
                DistributionDiffEntry(
                    application_id=app_id,
                    item_id=None,
                    student_id=std_code,
                    student_name=std_name,
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=consumed.academic_year,
                    allocated_sub_type=ranking_item.allocated_sub_type,
                    application_identity=None,
                    scholarship_amount=float(application.amount or consumed.amount or 0),
                )
            )
```

- [ ] The to_remove branch (line 1991) reads `item.allocation_year` from the `PaymentRosterItem` — that column is KEPT as a snapshot, so leave `allocation_year=item.allocation_year` unchanged. Likewise the return dict's `"allocation_year": roster.allocation_year` (line 2002) reads the retained roster snapshot — leave unchanged.

- [ ] Run the test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_roster_distribution_reconcile_service.py -p no:cacheprovider -q
```
Expected: all reconcile tests pass.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
flake8 backend/app/services/roster_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git commit -m "feat(roster): reconcile diff matches on allocation_config_id, NULL = whole-period sentinel"
```

### Task 4.5: Alternate promotion copies allocation_config_id from displaced item

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/alternate_promotion_service.py:112-117` (promotion copy)
- Test: `/home/howard/scholarship-system/backend/app/tests/test_alternate_promotion_inherits_config.py` (Create)

- [ ] Write a failing test. Create `/home/howard/scholarship-system/backend/app/tests/test_alternate_promotion_inherits_config.py`:

```python
"""Pin: when an alternate is promoted to replace a displaced winner, the
promoted CollegeRankingItem inherits the displaced item's allocation_config_id
(not left NULL → otherwise it lands in the whole-period bucket / wrong roster,
spec §8). Verifies the copy directly at the promotion call site."""

import pytest_asyncio
import pytest

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.alternate_promotion_service import AlternatePromotionService


@pytest_asyncio.fixture
async def promo_setup(db):
    sch = ScholarshipType(code="promo_sch", name="Promo", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    consumed = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="PROMO-114",
        config_name="Promo 114",
        academic_year=114,
        semester=None,
        amount=50000,
    )
    db.add(consumed)
    await db.commit()
    await db.refresh(consumed)

    requesting = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="PROMO-115",
        config_name="Promo 115",
        academic_year=115,
        semester=None,
        amount=50000,
    )
    db.add(requesting)
    await db.commit()
    await db.refresh(requesting)

    def _user(suffix):
        return User(
            nycu_id=f"promo_{suffix}",
            email=f"promo_{suffix}@u.edu",
            name=suffix,
            role=UserRole.student,
            user_type=UserType.student,
        )

    u_orig = _user("orig")
    u_alt = _user("alt")
    db.add_all([u_orig, u_alt])
    await db.commit()
    await db.refresh(u_orig)
    await db.refresh(u_alt)

    def _app(user, app_id):
        return Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=sch.id,
            scholarship_configuration_id=requesting.id,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            academic_year=115,
            semester=None,
            status=ApplicationStatus.approved,
            review_stage=ReviewStage.quota_distributed,
            agree_terms=True,
            student_data={"std_stdcode": app_id, "std_cname": "x"},
        )

    orig_app = _app(u_orig, "APP-PROMO-ORIG")
    alt_app = _app(u_alt, "APP-PROMO-ALT")
    db.add_all([orig_app, alt_app])
    await db.commit()
    await db.refresh(orig_app)
    await db.refresh(alt_app)

    ranking = CollegeRanking(
        scholarship_type_id=sch.id,
        sub_type_code="nstc",
        academic_year=115,
        semester=None,
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)

    orig_item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=orig_app.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=consumed.id,
        status="allocated",
        backup_allocations=[{"sub_type": "nstc", "backup_position": 1, "college": "EE"}],
    )
    alt_item = CollegeRankingItem(
        ranking_id=ranking.id,
        application_id=alt_app.id,
        rank_position=2,
        is_allocated=False,
        backup_position=1,
        status="waitlisted",
    )
    db.add_all([orig_item, alt_item])
    await db.commit()
    await db.refresh(orig_item)
    await db.refresh(alt_item)
    return {
        "consumed": consumed,
        "requesting": requesting,
        "orig_item": orig_item,
        "alt_item": alt_item,
        "orig_app": orig_app,
    }


@pytest.mark.asyncio
async def test_promoted_alternate_inherits_allocation_config_id(db, promo_setup):
    svc = AlternatePromotionService(db)
    result = await svc.find_and_promote_alternate(
        ranking_item=promo_setup["orig_item"],
        original_application=promo_setup["orig_app"],
        scholarship_config=promo_setup["requesting"],
        ineligible_reason="graduated",
        skip_eligibility_check=True,
    )
    assert result is not None
    await db.refresh(promo_setup["alt_item"])
    assert promo_setup["alt_item"].is_allocated is True
    assert promo_setup["alt_item"].allocated_sub_type == "nstc"
    # The promoted alternate consumes the SAME config as the displaced winner.
    assert promo_setup["alt_item"].allocation_config_id == promo_setup["consumed"].id
```

- [ ] Confirm `AlternatePromotionService` is an async-session service (the test calls `await`). Check the constructor + `find_and_promote_alternate` are async:
```bash
grep -n "class AlternatePromotionService\|def __init__\|async def find_and_promote_alternate" /home/howard/scholarship-system/backend/app/services/alternate_promotion_service.py
```
If `find_and_promote_alternate` is NOT `async def` or uses a sync `self.db`, this test's `await`/async `db` fixture must match the service's actual session type — adjust the test to the service's real signature before running (do not change the service's sync/async nature in this task).

- [ ] Run it, expect FAIL:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_alternate_promotion_inherits_config.py -p no:cacheprovider -q
```
Expected: `AssertionError: assert None == <consumed.id>` — `alt_item.allocation_config_id` is `None` because the promotion copies only `allocated_sub_type`.

- [ ] Implement the copy. In `/home/howard/scholarship-system/backend/app/services/alternate_promotion_service.py`, the promotion block (lines 112-117) reads:
```python
            # 4. Update alternate ranking_item to allocated
            alternate_item.is_allocated = True
            alternate_item.status = "allocated"
            alternate_item.allocated_sub_type = ranking_item.allocated_sub_type
            alternate_item.allocation_reason = f"備取遞補（原學生 {original_student_name} 失格：{ineligible_reason}）"
            self.db.add(alternate_item)
```
Replace with:
```python
            # 4. Update alternate ranking_item to allocated. Inherit the displaced
            #    winner's consumed config so the promoted alternate lands in the
            #    same (allocation_config_id, sub_type) roster group (spec §8).
            alternate_item.is_allocated = True
            alternate_item.status = "allocated"
            alternate_item.allocated_sub_type = ranking_item.allocated_sub_type
            alternate_item.allocation_config_id = ranking_item.allocation_config_id
            alternate_item.allocation_reason = f"備取遞補（原學生 {original_student_name} 失格：{ineligible_reason}）"
            self.db.add(alternate_item)
```

- [ ] Run the test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_alternate_promotion_inherits_config.py -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/alternate_promotion_service.py backend/app/tests/test_alternate_promotion_inherits_config.py
flake8 backend/app/services/alternate_promotion_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/alternate_promotion_service.py backend/app/tests/test_alternate_promotion_inherits_config.py
git commit -m "fix(distribution): promoted alternate inherits displaced winner's allocation_config_id"
```

### Task 4.6: Renewal creation snapshots allocation_config_id from previous slot (own-config fallback)

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/services/application_service.py:2869-2904` (`create_renewal_from_previous`)
- Test: `/home/howard/scholarship-system/backend/app/tests/test_renewal_allocation_config_snapshot.py` (Create)

- [ ] Write a failing test. Create `/home/howard/scholarship-system/backend/app/tests/test_renewal_allocation_config_snapshot.py`:

```python
"""Pin: create_renewal_from_previous snapshots Application.allocation_config_id
from the previous award's CollegeRankingItem.allocation_config_id; when the
prior slot is unresolved it falls back to the renewal's own
scholarship_configuration_id — an approved renewal is NEVER left NULL (spec §9),
which would inflate the §6.2 pool."""

import pytest
import pytest_asyncio

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.enums import ReviewStage
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.application_service import ApplicationService


@pytest_asyncio.fixture
async def renewal_setup(db):
    sch = ScholarshipType(code="ren_sch", name="Ren", description="x")
    db.add(sch)
    await db.commit()
    await db.refresh(sch)

    consumed = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="REN-113",
        config_name="Ren 113",
        academic_year=113,
        semester=None,
        amount=50000,
    )
    prev_cfg = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        config_code="REN-114",
        config_name="Ren 114",
        academic_year=114,
        semester=None,
        amount=50000,
    )
    db.add_all([consumed, prev_cfg])
    await db.commit()
    await db.refresh(consumed)
    await db.refresh(prev_cfg)

    user = User(
        nycu_id="ren_u",
        email="ren_u@u.edu",
        name="Ren U",
        role=UserRole.student,
        user_type=UserType.student,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    def _prev(app_id, cfg):
        return Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=sch.id,
            scholarship_configuration_id=cfg.id,
            scholarship_subtype_list=["nstc"],
            sub_type_selection_mode=SubTypeSelectionMode.single,
            sub_scholarship_type="nstc",
            academic_year=114,
            semester=None,
            status=ApplicationStatus.approved,
            review_stage=ReviewStage.quota_distributed,
            agree_terms=True,
        )

    return {"sch": sch, "consumed": consumed, "prev_cfg": prev_cfg, "user": user, "_prev": _prev}


@pytest.mark.asyncio
async def test_renewal_snapshots_previous_slot_config(db, renewal_setup):
    prev = renewal_setup["_prev"]("APP-REN-PREV", renewal_setup["prev_cfg"])
    db.add(prev)
    await db.commit()
    await db.refresh(prev)

    ranking = CollegeRanking(
        scholarship_type_id=renewal_setup["sch"].id,
        sub_type_code="nstc",
        academic_year=114,
        semester=None,
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
    )
    db.add(ranking)
    await db.commit()
    await db.refresh(ranking)
    db.add(
        CollegeRankingItem(
            ranking_id=ranking.id,
            application_id=prev.id,
            rank_position=1,
            is_allocated=True,
            allocated_sub_type="nstc",
            allocation_config_id=renewal_setup["consumed"].id,
            status="allocated",
        )
    )
    await db.commit()

    svc = ApplicationService(db)
    renewal = await svc.create_renewal_from_previous(
        previous=prev,
        current_user=renewal_setup["user"],
        target_academic_year=115,
        renewal_year=114,
    )
    await db.commit()
    await db.refresh(renewal)
    # snapshot copies the prior slot's consumed config
    assert renewal.allocation_config_id == renewal_setup["consumed"].id


@pytest.mark.asyncio
async def test_renewal_unresolved_slot_falls_back_to_own_config(db, renewal_setup):
    # previous app has NO allocated ranking item → unresolved
    prev = renewal_setup["_prev"]("APP-REN-PREV2", renewal_setup["prev_cfg"])
    db.add(prev)
    await db.commit()
    await db.refresh(prev)

    svc = ApplicationService(db)
    renewal = await svc.create_renewal_from_previous(
        previous=prev,
        current_user=renewal_setup["user"],
        target_academic_year=115,
        renewal_year=114,
    )
    await db.commit()
    await db.refresh(renewal)
    # never NULL: falls back to renewal's own scholarship_configuration_id
    assert renewal.allocation_config_id is not None
    assert renewal.allocation_config_id == prev.scholarship_configuration_id
```

- [ ] Run it, expect FAIL:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_renewal_allocation_config_snapshot.py -p no:cacheprovider -q
```
Expected: `AssertionError: assert None == <consumed.id>` — `create_renewal_from_previous` does not set `allocation_config_id`.

- [ ] Implement the snapshot. In `/home/howard/scholarship-system/backend/app/services/application_service.py`, the current body (lines 2881-2902) reads:
```python
        app_id = await self._generate_app_id(
            target_academic_year,
            previous.semester.value if previous.semester else None,
        )
        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=previous.scholarship_type_id,
            scholarship_configuration_id=previous.scholarship_configuration_id,
            scholarship_subtype_list=[previous.sub_scholarship_type] if previous.sub_scholarship_type else [],
            sub_scholarship_type=previous.sub_scholarship_type,
            sub_type_selection_mode=previous.sub_type_selection_mode,
            is_renewal=True,
            renewal_year=renewal_year,
            previous_application_id=previous.id,
            academic_year=target_academic_year,
            semester=previous.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
            agree_terms=False,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app
```
Replace with:
```python
        app_id = await self._generate_app_id(
            target_academic_year,
            previous.semester.value if previous.semester else None,
        )

        # Snapshot the config the prior award consumed so the renewal occupies
        # the same shared-pool slot (spec §9). Fall back to the renewal's own
        # scholarship_configuration_id when the prior slot is unresolved — an
        # approved renewal must NEVER be left NULL (would inflate §6.2 pool).
        from app.models.college_review import CollegeRankingItem

        prior_slot_config_id = await self.db.scalar(
            select(CollegeRankingItem.allocation_config_id)
            .where(
                CollegeRankingItem.application_id == previous.id,
                CollegeRankingItem.is_allocated.is_(True),
                CollegeRankingItem.allocation_config_id.isnot(None),
            )
            .order_by(CollegeRankingItem.id.desc())
            .limit(1)
        )
        allocation_config_id = prior_slot_config_id or previous.scholarship_configuration_id

        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=previous.scholarship_type_id,
            scholarship_configuration_id=previous.scholarship_configuration_id,
            allocation_config_id=allocation_config_id,
            scholarship_subtype_list=[previous.sub_scholarship_type] if previous.sub_scholarship_type else [],
            sub_scholarship_type=previous.sub_scholarship_type,
            sub_type_selection_mode=previous.sub_type_selection_mode,
            is_renewal=True,
            renewal_year=renewal_year,
            previous_application_id=previous.id,
            academic_year=target_academic_year,
            semester=previous.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
            agree_terms=False,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app
```

- [ ] Confirm `select` is already imported at the top of `application_service.py` (it is used pervasively in the file). If `flake8` flags an undefined `select`, add `from sqlalchemy import select` — but verify first:
```bash
grep -n "^from sqlalchemy import\|from sqlalchemy import select" /home/howard/scholarship-system/backend/app/services/application_service.py | head
```

- [ ] Run the test, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_renewal_allocation_config_snapshot.py -p no:cacheprovider -q
```
Expected: `2 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/application_service.py backend/app/tests/test_renewal_allocation_config_snapshot.py
flake8 backend/app/services/application_service.py --select=B904,B014 --max-line-length=120
```

- [ ] Commit:
```bash
git add backend/app/services/application_service.py backend/app/tests/test_renewal_allocation_config_snapshot.py
git commit -m "feat(renewal): snapshot allocation_config_id from prior slot with own-config fallback"
```

### Task 4.7: Re-key `test_restore_allocation_service.py` fixtures onto allocation_config_id

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/tests/test_restore_allocation_service.py:91-106,199-209` (fixture + assertions)

- [ ] `CollegeRankingItem.allocation_year` is dropped (migration 2). The `allocated_item` fixture (lines 94-102) constructs the item with `allocation_year=114`, and `test_cancel_frees_quota_slot_and_restore_reaffirms` asserts `allocated_item.allocation_year == 114`. Run the file as-is now to confirm it FAILS once the model column is gone:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_restore_allocation_service.py -p no:cacheprovider -q
```
Expected: `TypeError: 'allocation_year' is an invalid keyword argument for CollegeRankingItem`.

- [ ] Re-key the fixture. The `allocated_item` fixture (lines 91-106) reads:
```python
@pytest_asyncio.fixture
async def allocated_item(db, finalized_ranking, allocated_application):
    """A ranking item that holds an allocated quota slot for the application."""
    item = CollegeRankingItem(
        ranking_id=finalized_ranking.id,
        application_id=allocated_application.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_year=114,
        status="allocated",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
```
Replace `allocation_year=114,` with a config-id reference. Since this fixture has no config object, add a minimal config and point at it. Replace the whole fixture with:
```python
@pytest_asyncio.fixture
async def allocated_item(db, finalized_ranking, allocated_application):
    """A ranking item that holds an allocated quota slot for the application."""
    from app.models.scholarship import ScholarshipConfiguration

    cfg = ScholarshipConfiguration(
        scholarship_type_id=1,
        config_code="RESTORE-114",
        config_name="Restore 114",
        academic_year=114,
        semester="first",
        amount=50000,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)

    item = CollegeRankingItem(
        ranking_id=finalized_ranking.id,
        application_id=allocated_application.id,
        rank_position=1,
        is_allocated=True,
        allocated_sub_type="nstc",
        allocation_config_id=cfg.id,
        status="allocated",
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item
```

- [ ] Re-key the assertions in `test_cancel_frees_quota_slot_and_restore_reaffirms` (lines 206-219). Current:
```python
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is False
    assert allocated_item.allocated_sub_type == "nstc"
    assert allocated_item.allocation_year == 114

    # Restore re-consumes the same slot.
    await svc.restore_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
    )
    await db.commit()
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is True
    assert allocated_item.allocated_sub_type == "nstc"
```
Replace the year assertion with the config-id assertion:
```python
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is False
    assert allocated_item.allocated_sub_type == "nstc"
    assert allocated_item.allocation_config_id is not None

    # Restore re-consumes the same slot.
    await svc.restore_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_db_user.id,
    )
    await db.commit()
    await db.refresh(allocated_item)
    assert allocated_item.is_allocated is True
    assert allocated_item.allocated_sub_type == "nstc"
```

- [ ] Update the module docstring line referencing `allocation_year` (line 9-10): `(while preserving allocated_sub_type / allocation_year)` → `(while preserving allocated_sub_type / allocation_config_id)`.

- [ ] Run the file, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_restore_allocation_service.py -p no:cacheprovider -q
```
Expected: `4 passed` (assuming the revoke/restore service preserves `allocation_config_id` — that preservation is Phase 3's revoke/suspend rewrite; if a slot's config is cleared on revoke, raise it to the Phase 3 owner rather than weakening this assertion).

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/tests/test_restore_allocation_service.py
```

- [ ] Commit:
```bash
git add backend/app/tests/test_restore_allocation_service.py
git commit -m "test(restore): re-key restore-allocation fixtures onto allocation_config_id"
```

### Task 4.8: Rewrite `test_challenge_release_distribution.py` onto allocation_config_id

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/tests/test_challenge_release_distribution.py` (fixtures + assertions)

- [ ] This test exercises `execute_general_distribution` (rewritten in Phase 3 to key `released_slots` on `allocation_config_id` and re-derive remaining via §6.2). Its config fixture still uses year-keyed `quotas` + `prior_quota_years` and asserts `released_slots == {("nstc", RENEWAL_YEAR): 1}` + `rank9_item.allocation_year == RENEWAL_YEAR`. Run it as-is to confirm it FAILS against the dropped column / re-keyed release map:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_challenge_release_distribution.py -p no:cacheprovider -q
```
Expected: failure — `prior_quota_years` is no longer a model column / `released_slots` is now keyed on config id, and `CollegeRankingItem.allocation_year` is dropped.

- [ ] Rewrite the config + linked-source fixture. The current config (lines 159-171) reads:
```python
    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="Phase 6 Config",
        config_code="phase6-config",
        amount=30000,
        currency="TWD",
        is_active=True,
        quotas={"nstc": {"114": 8, "113": 0}, "moe_1w": {"114": 6}},
        prior_quota_years={"nstc": [113], "moe_1w": []},
    )
    db.add(config)
    await db.commit()
```
Replace with a prior-year sibling config (`phase6-113`, which holds the renewal's borrowed nstc slot) plus a shared-quota link from the current config to it. Use per-college matrix `quotas` so `pool_total` resolves under matrix mode:
```python
    prior_config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=RENEWAL_YEAR,
        semester=None,
        config_name="Phase 6 Prior Config",
        config_code="phase6-config-113",
        amount=30000,
        currency="TWD",
        is_active=True,
        quotas={"nstc": {"EE": 1}},  # one nstc slot in 113, consumed by A's renewal
    )
    db.add(prior_config)
    await db.commit()
    await db.refresh(prior_config)

    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="Phase 6 Config",
        config_code="phase6-config",
        amount=30000,
        currency="TWD",
        is_active=True,
        quotas={"nstc": {"EE": 8}, "moe_1w": {"EE": 6}},
        shared_quota_sources=[{"source_config_code": "phase6-config-113", "sub_types": ["nstc"]}],
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
```

- [ ] The renewal A must point its `allocation_config_id` at the prior config (it consumes the 113 slot). After `renewal_A` is created and refreshed (around line 205), set its consumed config. Current:
```python
    db.add(renewal_A)
    await db.commit()
    await db.refresh(renewal_A)
```
Replace with:
```python
    renewal_A.allocation_config_id = prior_config.id
    db.add(renewal_A)
    await db.commit()
    await db.refresh(renewal_A)
```

- [ ] Re-key the summary assertion (line 298). Current:
```python
    # released: A's renewal freed up (nstc, 113) ×1
    assert result["released_slots"] == {("nstc", RENEWAL_YEAR): 1}
```
Replace with (the release map is now keyed on `(allocation_config_id, sub_type)` per Phase 3's `execute_general_distribution` rewrite):
```python
    # released: A's renewal freed up the prior config's nstc slot ×1
    assert result["released_slots"] == {(prior_config.id, "nstc"): 1}
```

- [ ] Re-key the rank-9 fill-in assertion (lines 331-338). Current:
```python
    # Verify rank #9's CollegeRankingItem.allocation_year was set to 113
    rank9_item = (
        (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_apps[8].id)))
        .scalars()
        .first()
    )
    assert rank9_item is not None
    assert rank9_item.allocation_year == RENEWAL_YEAR
```
Replace with:
```python
    # Verify rank #9's CollegeRankingItem.allocation_config_id points at the
    # prior config whose slot was freed by A's cancelled renewal.
    rank9_item = (
        (await db.execute(select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_apps[8].id)))
        .scalars()
        .first()
    )
    assert rank9_item is not None
    assert rank9_item.allocation_config_id == prior_config.id
```

- [ ] Update the module docstring quota/release block (lines 6-7, 23-24) to reflect the link model instead of year-keyed quotas. Change `quotas = {"nstc": {"114": 8, "113": 0}, "moe_1w": {"114": 6}}` to a one-line note `current config (phase6-config) nstc=8/moe_1w=6; prior sibling phase6-config-113 nstc=1, linked via shared_quota_sources` and change the `allocation_year = 113` mention to `allocation_config_id = phase6-config-113`.

- [ ] Run the file, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_challenge_release_distribution.py -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/tests/test_challenge_release_distribution.py
```

- [ ] Commit:
```bash
git add backend/app/tests/test_challenge_release_distribution.py
git commit -m "test(distribution): rewrite challenge-release test onto shared_quota_sources + allocation_config_id"
```

### Task 4.9: Rewrite `test_renewal_end_to_end.py` onto allocation_config_id

**Files:**
- Modify: `/home/howard/scholarship-system/backend/app/tests/test_renewal_end_to_end.py` (config fixture + assertions)

- [ ] This is the full renewal→challenge→general e2e. It uses year-keyed `quotas` + `prior_quota_years` and asserts `released_slots == {("nstc", RENEWAL_YEAR): 2}` plus `item.allocation_year == 114/113`. Run as-is to confirm FAIL:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_renewal_end_to_end.py -p no:cacheprovider -q
```
Expected: failure — `prior_quota_years` not a column, `released_slots` re-keyed, `CollegeRankingItem.allocation_year` dropped.

- [ ] Rewrite the config fixture (lines 196-211). Current:
```python
    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="E2E PhD Config",
        config_code="e2e-phd-config",
        amount=40000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=True,
        requires_college_review=True,
        quotas={"nstc": {"114": 8, "113": 10}, "moe_1w": {"114": 6}},
        prior_quota_years={"nstc": [113], "moe_1w": []},
    )
    db.add(config)
    await db.commit()
```
Replace with a prior-year sibling config (`e2e-phd-config-113`, 10 nstc slots — the renewal pool) + a `shared_quota_sources` link, matrix `quotas`:
```python
    prior_config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=RENEWAL_YEAR,
        semester=None,
        config_name="E2E PhD Prior Config",
        config_code="e2e-phd-config-113",
        amount=40000,
        currency="TWD",
        is_active=True,
        quotas={"nstc": {"EE": 10}},  # 10 nstc[113] slots — renewal pool
    )
    db.add(prior_config)
    await db.commit()
    await db.refresh(prior_config)

    config = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        academic_year=CURRENT_ACADEMIC_YEAR,
        semester=None,
        config_name="E2E PhD Config",
        config_code="e2e-phd-config",
        amount=40000,
        currency="TWD",
        is_active=True,
        requires_professor_recommendation=True,
        requires_college_review=True,
        quotas={"nstc": {"EE": 8}, "moe_1w": {"EE": 6}},
        shared_quota_sources=[{"source_config_code": "e2e-phd-config-113", "sub_types": ["nstc"]}],
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
```

- [ ] The 10 renewals consume the prior config's slots. `create_renewal_from_previous` snapshots `allocation_config_id` from the prior app's ranking item (Task 4.6) — but in this test the prior apps have no allocated ranking items, so the snapshot falls back to the renewal's own `scholarship_configuration_id` (= `config.id`, the 115 config), which is wrong for the 113 pool. To make the renewals consume the prior config explicitly, set each renewal's `allocation_config_id = prior_config.id` right after creation. In the renewal-creation loop (lines 260-271), current:
```python
    for prior, user in zip(prior_apps, renewal_users):
        renewal = await app_service.create_renewal_from_previous(
            previous=prior,
            current_user=user,
            target_academic_year=CURRENT_ACADEMIC_YEAR,
            renewal_year=RENEWAL_YEAR,
        )
        # Promote past student_draft so the renewal distribution service can pick it up.
        renewal.status = ApplicationStatus.under_review
        renewal.review_stage = ReviewStage.college_reviewed
        renewal.agree_terms = True
        renewal_apps.append(renewal)
    await db.commit()
```
Replace with:
```python
    for prior, user in zip(prior_apps, renewal_users):
        renewal = await app_service.create_renewal_from_previous(
            previous=prior,
            current_user=user,
            target_academic_year=CURRENT_ACADEMIC_YEAR,
            renewal_year=RENEWAL_YEAR,
        )
        # These renewals consume the prior-year (113) shared pool.
        renewal.allocation_config_id = prior_config.id
        # Promote past student_draft so the renewal distribution service can pick it up.
        renewal.status = ApplicationStatus.under_review
        renewal.review_stage = ReviewStage.college_reviewed
        renewal.agree_terms = True
        renewal_apps.append(renewal)
    await db.commit()
```

- [ ] Re-key the released-slots assertion (line 407). Current:
```python
    assert result["released_slots"] == {("nstc", RENEWAL_YEAR): 2}
```
Replace with:
```python
    assert result["released_slots"] == {(prior_config.id, "nstc"): 2}
```

- [ ] Re-key the nstc rank 1..8 winners' allocation assertion (lines 436-448). Current:
```python
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_year == CURRENT_ACADEMIC_YEAR
        ), f"nstc rank {idx + 1} should occupy nstc[{CURRENT_ACADEMIC_YEAR}]"
```
Replace the assertion with the config-id form (first-round winners consume the current config):
```python
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_config_id == config.id
        ), f"nstc rank {idx + 1} should occupy current config nstc[{CURRENT_ACADEMIC_YEAR}]"
```

- [ ] Re-key the nstc ranks 9,10 fill-in assertion (lines 458-470). Current:
```python
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_year == RENEWAL_YEAR
        ), f"nstc rank {idx + 1} should be promoted to nstc[{RENEWAL_YEAR}] (slot freed by cancelled renewal)"
```
Replace the assertion with the config-id form:
```python
        item = (
            (
                await db.execute(
                    select(CollegeRankingItem).where(CollegeRankingItem.application_id == nstc_pure_apps[idx].id)
                )
            )
            .scalars()
            .first()
        )
        assert item is not None
        assert (
            item.allocation_config_id == prior_config.id
        ), f"nstc rank {idx + 1} should be promoted to prior config (slot freed by cancelled renewal)"
```

- [ ] Update the module docstring quota block (lines 6-9, 26-28) — change the `nstc[113]: 10 / nstc[114]: 8 / moe_1w[114]: 6` framing to note the prior sibling config `e2e-phd-config-113` (10 nstc) linked to `e2e-phd-config` via `shared_quota_sources`, and `allocation_year=113` → `allocation_config_id=e2e-phd-config-113`.

- [ ] Run the file, expect PASS:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_renewal_end_to_end.py -p no:cacheprovider -q
```
Expected: `1 passed`.

- [ ] Lint:
```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/tests/test_renewal_end_to_end.py
```

- [ ] Commit:
```bash
git add backend/app/tests/test_renewal_end_to_end.py
git commit -m "test(renewal): rewrite e2e onto shared_quota_sources + allocation_config_id"
```

### Task 4.10: Full Phase 4 regression — roster + renewal + reconcile suites green together

**Files:**
- Test: all Phase 4 touched test files (no new code)

- [ ] Run the complete Phase 4 test set together to catch cross-task drift (grouping, item snapshot, reconcile, promotion, renewal, restore, challenge-release, e2e):
```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_roster_generate_per_config_group.py \
  app/tests/test_roster_item_consumed_config.py \
  app/tests/test_roster_distribution_reconcile_service.py \
  app/tests/test_roster_distribution_reconcile_api.py \
  app/tests/test_alternate_promotion_inherits_config.py \
  app/tests/test_renewal_allocation_config_snapshot.py \
  app/tests/test_restore_allocation_service.py \
  app/tests/test_challenge_release_distribution.py \
  app/tests/test_renewal_end_to_end.py \
  -p no:cacheprovider -q
```
Expected: all pass. If `test_roster_distribution_reconcile_api.py` references the changed `_roster`/`_ranking_item`/`_roster_item` helper signatures (it imports the service-level fixtures indirectly via the API), inspect and align it the same way as Task 4.4 — read it first:
```bash
cat /home/howard/scholarship-system/backend/app/tests/test_roster_distribution_reconcile_api.py
```

- [ ] Run the full lint gate over every Phase 4 source + test file:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 \
  backend/app/services/roster_service.py \
  backend/app/services/alternate_promotion_service.py \
  backend/app/services/application_service.py \
  backend/app/tests/test_roster_generate_per_config_group.py \
  backend/app/tests/test_roster_item_consumed_config.py \
  backend/app/tests/test_roster_distribution_reconcile_service.py \
  backend/app/tests/test_alternate_promotion_inherits_config.py \
  backend/app/tests/test_renewal_allocation_config_snapshot.py \
  backend/app/tests/test_restore_allocation_service.py \
  backend/app/tests/test_challenge_release_distribution.py \
  backend/app/tests/test_renewal_end_to_end.py
flake8 backend/app/services/roster_service.py backend/app/services/alternate_promotion_service.py backend/app/services/application_service.py --select=B904,B014 --max-line-length=120
```
Expected: black reports `all done`, flake8 reports no B904/B014 violations.

- [ ] If any cross-suite failure surfaces a missed reader of `allocation_year` on `CollegeRankingItem` (the dropped column) inside roster_service.py, grep for stragglers and fix in the owning task before declaring the phase done:
```bash
grep -n "\.allocation_year" /home/howard/scholarship-system/backend/app/services/roster_service.py
```
Every remaining `.allocation_year` must read a `PaymentRoster`/`PaymentRosterItem` (KEPT snapshot), never a `CollegeRankingItem` (dropped).

- [ ] Commit any alignment fixes:
```bash
git add backend/app/tests/test_roster_distribution_reconcile_api.py
git commit -m "test(roster): align reconcile API test with allocation_config_id fixtures"
```


## Phase 5 — Config CRUD + schema + validation

**Files in this phase:**
- `backend/app/schemas/scholarship_configuration.py` (add `SharedQuotaSource` model + `ScholarshipConfigurationBase` fields `shared_quota_sources`, `project_numbers`)
- `backend/app/api/v1/endpoints/scholarship_configurations.py` (create `:757`, GET `:862-863`, update `:1035-1046`, duplicate `:1208`, list-GET `:1321-1322`, new `_validate_shared_quota_sources` helper)
- `backend/app/api/v1/endpoints/payment_rosters.py` (`:589-637` `allocation_map` reads `allocation_config_id`)
- Tests: `backend/app/tests/test_scholarship_configuration_schema_validators.py`, `backend/app/tests/test_scholarship_configuration_endpoints.py`, `backend/app/tests/test_shared_quota_link_validation.py` (new)

> Assumes Phase 1 already added the model columns `ScholarshipConfiguration.shared_quota_sources` (JSON), flattened `project_numbers` to `{sub_type: str}`, and MIGRATION 1 (Task 1.5, additive) added `CollegeRankingItem.allocation_config_id`. `prior_quota_years` and `CollegeRankingItem.allocation_year` STILL EXIST at this point — they are dropped LAST by MIGRATION 2 (Task 1.6), after Phase 6. Phase 5 wires the schema, CRUD write/read paths, and imperative link validation.

---

### Task 5.1: Add `SharedQuotaSource` pydantic model + `shared_quota_sources`/`project_numbers` fields to `ScholarshipConfigurationBase`

**Files:**
- Modify: `backend/app/schemas/scholarship_configuration.py:6-8` (imports), `:30` (after `quotas`)
- Test: `backend/app/tests/test_scholarship_configuration_schema_validators.py`

**Steps:**

- [ ] Write a failing test. Append to the end of `backend/app/tests/test_scholarship_configuration_schema_validators.py` (after line 321):

```python


# ─── SharedQuotaSource + new config fields ───────────────────────────


def test_shared_quota_source_round_trips_on_base():
    """A shared_quota_sources link is parsed into SharedQuotaSource models
    and project_numbers flattens to {sub_type: code}."""
    cfg = ScholarshipConfigurationBase(
        **_base_payload(
            project_numbers={"nstc": "114R000001", "moe_1w": "114C000002"},
            shared_quota_sources=[
                {"source_config_code": "phd_113", "sub_types": ["nstc"]},
                {"source_config_code": "phd_112", "sub_types": ["nstc", "moe_1w"]},
            ],
        )
    )
    assert cfg.project_numbers == {"nstc": "114R000001", "moe_1w": "114C000002"}
    assert len(cfg.shared_quota_sources) == 2
    assert cfg.shared_quota_sources[0].source_config_code == "phd_113"
    assert cfg.shared_quota_sources[0].sub_types == ["nstc"]
    assert cfg.shared_quota_sources[1].sub_types == ["nstc", "moe_1w"]


def test_shared_quota_source_requires_source_config_code():
    """A link entry missing source_config_code is rejected at the schema boundary."""
    with pytest.raises(ValidationError):
        ScholarshipConfigurationBase(**_base_payload(shared_quota_sources=[{"sub_types": ["nstc"]}]))


def test_new_fields_default_to_none():
    """Both new fields are optional and default to None when omitted."""
    cfg = ScholarshipConfigurationBase(**_base_payload())
    assert cfg.shared_quota_sources is None
    assert cfg.project_numbers is None
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_schema_validators.py -k "shared_quota_source or new_fields" -p no:cacheprovider
```
Expect failure with `TypeError`/`ValidationError`: `ScholarshipConfigurationBase` has no field `shared_quota_sources` (pydantic raises an "unexpected keyword argument" / extra-field error, or `AttributeError: ... has no attribute 'shared_quota_sources'`).

- [ ] Add the `SharedQuotaSource` model. In `backend/app/schemas/scholarship_configuration.py`, the current import line 6 reads:
```python
from typing import Any, Dict, List, Optional
```
Leave it as-is (already has `Dict`, `List`, `Optional`). After the existing imports block (after line 10 `from app.models.enums import ApplicationCycle, QuotaManagementMode, Semester`), and before `class ScholarshipConfigurationBase`, insert the new model. The current code at lines 11-13 reads:
```python


class ScholarshipConfigurationBase(BaseModel):
```
Replace it with:
```python


class SharedQuotaSource(BaseModel):
    """A cross-config quota-borrow link: this config may consume the named
    prior config's remaining quota for the listed sub_types. Selected by
    config_code (year-bearing identity), no quantity (always the source's
    live remaining). Cross-type allowed; existence + prior-year + sub_type
    membership are validated imperatively at write time (endpoint §10)."""

    source_config_code: str = Field(..., min_length=1, max_length=50)
    sub_types: List[str] = Field(..., min_length=1)


class ScholarshipConfigurationBase(BaseModel):
```

- [ ] Add the two new fields to `ScholarshipConfigurationBase`. The current code at lines 28-30 reads:
```python
    # 配額詳細設定
    total_quota: Optional[int] = Field(None, ge=0)
    quotas: Optional[Dict[str, Dict[str, int]]] = None
```
Replace it with:
```python
    # 配額詳細設定
    total_quota: Optional[int] = Field(None, ge=0)
    quotas: Optional[Dict[str, Dict[str, int]]] = None

    # 計畫編號 — flattened to own-year only {sub_type: code}
    project_numbers: Optional[Dict[str, str]] = None

    # 跨配置共享配額來源（取代 prior_quota_years）
    shared_quota_sources: Optional[List[SharedQuotaSource]] = None
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_schema_validators.py -k "shared_quota_source or new_fields" -p no:cacheprovider
```
Expect 3 passed.

- [ ] Run the full validators file to confirm no regression (the `validate_quotas` nested matrix validator stays unchanged):
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_schema_validators.py -p no:cacheprovider
```
Expect all passed (25 tests).

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/schemas/scholarship_configuration.py backend/app/tests/test_scholarship_configuration_schema_validators.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/schemas/scholarship_configuration.py app/tests/test_scholarship_configuration_schema_validators.py --select=B904,B014 --max-line-length=120
```
Expect no output from either.

- [ ] Commit. Run:
```bash
git add backend/app/schemas/scholarship_configuration.py backend/app/tests/test_scholarship_configuration_schema_validators.py
git commit -m "feat(config): SharedQuotaSource schema + project_numbers/shared_quota_sources on ScholarshipConfigurationBase"
```

---

### Task 5.2: Add an imperative `_validate_shared_quota_sources` helper in the config endpoint module

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py:40` (after `router = APIRouter()`)
- Test: `backend/app/tests/test_shared_quota_link_validation.py` (new)

**Steps:**

- [ ] Write a failing test. Create `backend/app/tests/test_shared_quota_link_validation.py`:

```python
"""
Integration tests for the imperative shared-quota link validation helper
(`_validate_shared_quota_sources`) used by the config create/update endpoints.

Per spec §10 each `source_config_code` must:
  - resolve to an EXISTING config,
  - have `academic_year < this.academic_year` (prior years only),
  - define every listed sub_type (sub_types ⊆ source config's quotas keys).

There is no DB FK on source_config_code, so this is the only gate. A bad
link saved here would later read an empty/missing pool at distribution time.
"""

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.scholarship_configurations import _validate_shared_quota_sources
from app.models.enums import Semester
from app.models.scholarship import ScholarshipConfiguration, ScholarshipStatus, ScholarshipType


@pytest_asyncio.fixture
async def phd_type(db: AsyncSession) -> ScholarshipType:
    st = ScholarshipType(
        code="link_phd",
        name="Link PhD",
        status=ScholarshipStatus.active.value,
    )
    db.add(st)
    await db.commit()
    await db.refresh(st)
    return st


@pytest_asyncio.fixture
async def phd_113(db: AsyncSession, phd_type) -> ScholarshipConfiguration:
    cfg = ScholarshipConfiguration(
        scholarship_type_id=phd_type.id,
        academic_year=113,
        semester=None,
        config_name="PhD 113",
        config_code="phd_113",
        amount=40000,
        has_college_quota=True,
        quotas={"nstc": {"EE": 5}, "moe_1w": {"EE": 3}},
        is_active=True,
    )
    db.add(cfg)
    await db.commit()
    await db.refresh(cfg)
    return cfg


async def test_valid_link_passes(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["nstc"]}]
    # academic_year 115 > 113, phd_113 defines nstc -> no raise
    await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)


async def test_missing_target_config_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_999", "sub_types": ["nstc"]}]
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)
    assert exc.value.status_code == 400
    assert "phd_999" in exc.value.detail


async def test_non_prior_year_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["nstc"]}]
    # requesting year == source year (113) -> not strictly prior -> reject
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=113)
    assert exc.value.status_code == 400
    assert "學年度" in exc.value.detail


async def test_undefined_sub_type_rejected(db: AsyncSession, phd_113):
    sources = [{"source_config_code": "phd_113", "sub_types": ["does_not_exist"]}]
    with pytest.raises(HTTPException) as exc:
        await _validate_shared_quota_sources(db, sources, requesting_academic_year=115)
    assert exc.value.status_code == 400
    assert "does_not_exist" in exc.value.detail


async def test_none_and_empty_are_noops(db: AsyncSession):
    # both must return without error and without a DB hit
    await _validate_shared_quota_sources(db, None, requesting_academic_year=115)
    await _validate_shared_quota_sources(db, [], requesting_academic_year=115)
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_shared_quota_link_validation.py -p no:cacheprovider
```
Expect collection/import error: `ImportError: cannot import name '_validate_shared_quota_sources' from 'app.api.v1.endpoints.scholarship_configurations'`.

- [ ] Add the helper. In `backend/app/api/v1/endpoints/scholarship_configurations.py`, the current code at lines 38-41 reads:
```python
logger = logging.getLogger(__name__)

router = APIRouter()
```
Replace it with:
```python
logger = logging.getLogger(__name__)

router = APIRouter()


async def _validate_shared_quota_sources(
    db: AsyncSession,
    shared_quota_sources: Optional[List[Dict[str, Any]]],
    requesting_academic_year: int,
) -> None:
    """Imperative link validation (spec §10 — no DB FK on source_config_code).

    Each entry's source_config_code must resolve to an existing config with
    academic_year strictly less than the requesting config's, and every listed
    sub_type must be defined in that source config's quotas matrix. Fail-fast
    with HTTP 400 so a dangling link never reaches the distribution pool reader.
    """
    if not shared_quota_sources:
        return

    for entry in shared_quota_sources:
        source_code = entry.get("source_config_code")
        sub_types = entry.get("sub_types") or []
        if not source_code:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="共享配額來源缺少 source_config_code",
            )

        source_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.config_code == source_code
        )
        source_result = await db.execute(source_stmt)
        source_config = source_result.scalar_one_or_none()

        if source_config is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"共享配額來源配置不存在: {source_code}",
            )

        if source_config.academic_year >= requesting_academic_year:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"共享配額來源 {source_code} 的學年度必須早於本配置",
            )

        defined_sub_types = set((source_config.quotas or {}).keys())
        for st in sub_types:
            if st not in defined_sub_types:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"共享配額來源 {source_code} 未定義子類型: {st}",
                )
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_shared_quota_link_validation.py -p no:cacheprovider
```
Expect 5 passed.

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_shared_quota_link_validation.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/scholarship_configurations.py app/tests/test_shared_quota_link_validation.py --select=B904,B014 --max-line-length=120
```
Expect no output. (Note: the `raise HTTPException(...)` calls are NOT inside an `except` block, so B904 does not apply.)

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_shared_quota_link_validation.py
git commit -m "feat(config): imperative _validate_shared_quota_sources link gate (exists + prior-year + sub_type)"
```

---

### Task 5.3: Wire the primary create constructor — write `project_numbers` + `shared_quota_sources`, drop `prior_quota_years`, call the link gate

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py:757-789` (create constructor)
- Test: `backend/app/tests/test_scholarship_configuration_endpoints.py`

**Steps:**

- [ ] Write a failing test. Append to the end of `backend/app/tests/test_scholarship_configuration_endpoints.py` a new test method inside the existing `TestScholarshipConfigurationEndpoints` class. First read the class's last method to find the indentation; then add (as a class method, 4-space indent matching siblings):

```python
    @pytest.mark.asyncio
    async def test_create_persists_project_numbers_and_shared_quota_sources(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Create must persist the flattened project_numbers and the
        shared_quota_sources link, and the GET response must echo both
        (and no longer expose prior_quota_years)."""
        # Prior-year source config the link will point at.
        source = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
            config_name="Source 113",
            config_code="SRC-113-1",
            amount=40000,
            has_college_quota=True,
            quotas={"nstc": {"EE": 5}},
            is_active=True,
        )
        db.add(source)
        await db.commit()

        payload = {
            "scholarship_type_id": test_scholarship_type.id,
            "config_name": "Create With Pools",
            "config_code": "POOLS-114-1",
            "academic_year": 114,
            "semester": "first",
            "amount": 40000,
            "currency": "TWD",
            "project_numbers": {"nstc": "114R000001"},
            "shared_quota_sources": [{"source_config_code": "SRC-113-1", "sub_types": ["nstc"]}],
        }
        response = await authenticated_admin_client.post(BASE, json=payload)
        assert response.status_code == 200, response.text
        config_id = response.json()["data"]["id"]

        get_response = await authenticated_admin_client.get(f"{BASE}/{config_id}")
        body = get_response.json()["data"]
        assert body["project_numbers"] == {"nstc": "114R000001"}
        assert body["shared_quota_sources"] == [{"source_config_code": "SRC-113-1", "sub_types": ["nstc"]}]
        assert "prior_quota_years" not in body

    @pytest.mark.asyncio
    async def test_create_rejects_invalid_shared_quota_source(
        self,
        authenticated_admin_client: AsyncClient,
        test_scholarship_type,
    ):
        """A link to a non-existent source config is rejected at create."""
        payload = {
            "scholarship_type_id": test_scholarship_type.id,
            "config_name": "Bad Link",
            "config_code": "BADLINK-114-1",
            "academic_year": 114,
            "semester": "first",
            "amount": 40000,
            "shared_quota_sources": [{"source_config_code": "NOPE-999", "sub_types": ["nstc"]}],
        }
        response = await authenticated_admin_client.post(BASE, json=payload)
        assert response.status_code == 400
        assert "NOPE-999" in response.json()["message"]
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "persists_project_numbers or rejects_invalid_shared_quota" -p no:cacheprovider
```
Expect `test_create_persists_project_numbers_and_shared_quota_sources` to fail: `body["project_numbers"]` is `None` (not written by the constructor) and `KeyError`/mismatch on `shared_quota_sources`; `test_create_rejects_invalid_shared_quota_source` to fail with status 200 instead of 400 (no gate called yet).

- [ ] Wire the constructor + gate. In `backend/app/api/v1/endpoints/scholarship_configurations.py`, the current code at lines 754-789 reads:
```python
        # Create new configuration
        from app.utils.date_utils import parse_date_field

        new_config = ScholarshipConfiguration(
            scholarship_type_id=scholarship_type_id,
            academic_year=config_data["academic_year"],
            semester=config_data.get("semester"),
            config_name=config_data["config_name"],
            config_code=config_data["config_code"],
            description=config_data.get("description"),
            description_en=config_data.get("description_en"),
            amount=config_data["amount"],
            currency=config_data.get("currency", "TWD"),
            whitelist_student_ids=config_data.get("whitelist_student_ids", {}),
            renewal_application_start_date=parse_date_field(config_data.get("renewal_application_start_date")),
            renewal_application_end_date=parse_date_field(config_data.get("renewal_application_end_date")),
            application_start_date=parse_date_field(config_data.get("application_start_date")),
            application_end_date=parse_date_field(config_data.get("application_end_date")),
            renewal_professor_review_start=parse_date_field(config_data.get("renewal_professor_review_start")),
            renewal_professor_review_end=parse_date_field(config_data.get("renewal_professor_review_end")),
            renewal_college_review_start=parse_date_field(config_data.get("renewal_college_review_start")),
            renewal_college_review_end=parse_date_field(config_data.get("renewal_college_review_end")),
            requires_professor_recommendation=config_data.get("requires_professor_recommendation", False),
            professor_review_start=parse_date_field(config_data.get("professor_review_start")),
            professor_review_end=parse_date_field(config_data.get("professor_review_end")),
            requires_college_review=config_data.get("requires_college_review", False),
            college_review_start=parse_date_field(config_data.get("college_review_start")),
            college_review_end=parse_date_field(config_data.get("college_review_end")),
            review_deadline=parse_date_field(config_data.get("review_deadline")),
            is_active=config_data.get("is_active", True),
            effective_start_date=parse_date_field(config_data.get("effective_start_date")),
            effective_end_date=parse_date_field(config_data.get("effective_end_date")),
            version=config_data.get("version", "1.0"),
            prior_quota_years=config_data.get("prior_quota_years"),
            created_by=current_user.id,
        )
```
Replace it with:
```python
        # Validate cross-config borrow links before persisting (spec §10).
        await _validate_shared_quota_sources(
            db,
            config_data.get("shared_quota_sources"),
            requesting_academic_year=config_data["academic_year"],
        )

        # Create new configuration
        from app.utils.date_utils import parse_date_field

        new_config = ScholarshipConfiguration(
            scholarship_type_id=scholarship_type_id,
            academic_year=config_data["academic_year"],
            semester=config_data.get("semester"),
            config_name=config_data["config_name"],
            config_code=config_data["config_code"],
            description=config_data.get("description"),
            description_en=config_data.get("description_en"),
            amount=config_data["amount"],
            currency=config_data.get("currency", "TWD"),
            whitelist_student_ids=config_data.get("whitelist_student_ids", {}),
            renewal_application_start_date=parse_date_field(config_data.get("renewal_application_start_date")),
            renewal_application_end_date=parse_date_field(config_data.get("renewal_application_end_date")),
            application_start_date=parse_date_field(config_data.get("application_start_date")),
            application_end_date=parse_date_field(config_data.get("application_end_date")),
            renewal_professor_review_start=parse_date_field(config_data.get("renewal_professor_review_start")),
            renewal_professor_review_end=parse_date_field(config_data.get("renewal_professor_review_end")),
            renewal_college_review_start=parse_date_field(config_data.get("renewal_college_review_start")),
            renewal_college_review_end=parse_date_field(config_data.get("renewal_college_review_end")),
            requires_professor_recommendation=config_data.get("requires_professor_recommendation", False),
            professor_review_start=parse_date_field(config_data.get("professor_review_start")),
            professor_review_end=parse_date_field(config_data.get("professor_review_end")),
            requires_college_review=config_data.get("requires_college_review", False),
            college_review_start=parse_date_field(config_data.get("college_review_start")),
            college_review_end=parse_date_field(config_data.get("college_review_end")),
            review_deadline=parse_date_field(config_data.get("review_deadline")),
            is_active=config_data.get("is_active", True),
            effective_start_date=parse_date_field(config_data.get("effective_start_date")),
            effective_end_date=parse_date_field(config_data.get("effective_end_date")),
            version=config_data.get("version", "1.0"),
            project_numbers=config_data.get("project_numbers"),
            shared_quota_sources=config_data.get("shared_quota_sources"),
            created_by=current_user.id,
        )
```

- [ ] Emit the new fields in the single-config GET response and drop `prior_quota_years`. The current code at lines 860-863 reads:
```python
            "total_quota": config.total_quota,
            "quotas": config.quotas,
            "project_numbers": config.project_numbers,
            "prior_quota_years": config.prior_quota_years,
```
Replace it with:
```python
            "total_quota": config.total_quota,
            "quotas": config.quotas,
            "project_numbers": config.project_numbers,
            "shared_quota_sources": config.shared_quota_sources,
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "persists_project_numbers or rejects_invalid_shared_quota" -p no:cacheprovider
```
Expect 2 passed.

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/scholarship_configurations.py --select=B904,B014 --max-line-length=120
```
Expect no output.

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
git commit -m "feat(config): create path writes project_numbers+shared_quota_sources, validates links, GET drops prior_quota_years"
```

---

### Task 5.4: Replace the update path's `prior_quota_years` branch with `shared_quota_sources` (validated) and add a `project_numbers` branch

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py:1032-1046` (update quota branches)
- Test: `backend/app/tests/test_scholarship_configuration_endpoints.py`

**Steps:**

- [ ] Write a failing test. Add to the `TestScholarshipConfigurationEndpoints` class (4-space indent):

```python
    @pytest.mark.asyncio
    async def test_update_persists_project_numbers_and_shared_quota_sources(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """PUT must persist project_numbers and a validated shared_quota_sources
        link with flag_modified so the JSON mutation is detected."""
        source = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=113,
            semester=Semester.first,
            config_name="Upd Source 113",
            config_code="USRC-113-1",
            amount=40000,
            has_college_quota=True,
            quotas={"nstc": {"EE": 5}},
            is_active=True,
        )
        target = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=114,
            semester=Semester.first,
            config_name="Upd Target 114",
            config_code="UTGT-114-1",
            amount=40000,
            is_active=True,
        )
        db.add_all([source, target])
        await db.commit()
        await db.refresh(target)

        update_payload = {
            "project_numbers": {"nstc": "114R000099"},
            "shared_quota_sources": [{"source_config_code": "USRC-113-1", "sub_types": ["nstc"]}],
        }
        response = await authenticated_admin_client.put(f"{BASE}/{target.id}", json=update_payload)
        assert response.status_code == 200, response.text

        get_response = await authenticated_admin_client.get(f"{BASE}/{target.id}")
        body = get_response.json()["data"]
        assert body["project_numbers"] == {"nstc": "114R000099"}
        assert body["shared_quota_sources"] == [{"source_config_code": "USRC-113-1", "sub_types": ["nstc"]}]

    @pytest.mark.asyncio
    async def test_update_rejects_invalid_shared_quota_source(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
    ):
        """PUT with a non-prior-year link is rejected (source year >= this year)."""
        future_source = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=115,
            semester=Semester.first,
            config_name="Future 115",
            config_code="FUT-115-1",
            amount=40000,
            has_college_quota=True,
            quotas={"nstc": {"EE": 5}},
            is_active=True,
        )
        target = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=114,
            semester=Semester.first,
            config_name="Upd Target2 114",
            config_code="UTGT2-114-1",
            amount=40000,
            is_active=True,
        )
        db.add_all([future_source, target])
        await db.commit()
        await db.refresh(target)

        response = await authenticated_admin_client.put(
            f"{BASE}/{target.id}",
            json={"shared_quota_sources": [{"source_config_code": "FUT-115-1", "sub_types": ["nstc"]}]},
        )
        assert response.status_code == 400
        assert "學年度" in response.json()["message"]
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "update_persists_project_numbers or update_rejects_invalid_shared_quota" -p no:cacheprovider
```
Expect `test_update_persists_project_numbers_and_shared_quota_sources` to fail (neither `project_numbers` nor `shared_quota_sources` written by the update path; GET echoes `None`), and `test_update_rejects_invalid_shared_quota_source` to fail with 200 instead of 400.

- [ ] Replace the `prior_quota_years` branch. In `backend/app/api/v1/endpoints/scholarship_configurations.py`, the current code at lines 1032-1046 reads:
```python
        if "quotas" in config_data:
            config.quotas = config_data["quotas"]
            flag_modified(config, "quotas")
        if "prior_quota_years" in config_data:
            pqy = config_data["prior_quota_years"]
            # Frontend textarea may send as string; parse to dict
            if isinstance(pqy, str):
                import json as _json

                try:
                    pqy = _json.loads(pqy)
                except (ValueError, TypeError):
                    pqy = {}
            config.prior_quota_years = pqy
            flag_modified(config, "prior_quota_years")
```
Replace it with:
```python
        if "quotas" in config_data:
            config.quotas = config_data["quotas"]
            flag_modified(config, "quotas")
        if "project_numbers" in config_data:
            config.project_numbers = config_data["project_numbers"]
            flag_modified(config, "project_numbers")
        if "shared_quota_sources" in config_data:
            # Validate links against the config's (possibly updated) academic_year.
            requesting_year = config_data.get("academic_year", config.academic_year)
            await _validate_shared_quota_sources(
                db, config_data["shared_quota_sources"], requesting_academic_year=requesting_year
            )
            config.shared_quota_sources = config_data["shared_quota_sources"]
            flag_modified(config, "shared_quota_sources")
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "update_persists_project_numbers or update_rejects_invalid_shared_quota" -p no:cacheprovider
```
Expect 2 passed.

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/scholarship_configurations.py --select=B904,B014 --max-line-length=120
```
Expect no output. (The `import json as _json` removed by this change leaves no unused import — `json` was only used in that branch; if flake8 F401 ever flags a now-unused module-level import, remove it.)

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
git commit -m "feat(config): update path replaces prior_quota_years branch with validated shared_quota_sources + project_numbers"
```

---

### Task 5.5: Carry `quotas` + `project_numbers` + `shared_quota_sources` over in the duplicate-config path

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py:1208-1226` (duplicate constructor)
- Test: `backend/app/tests/test_scholarship_configuration_endpoints.py`

**Steps:**

- [ ] Write a failing test. Add to the `TestScholarshipConfigurationEndpoints` class (4-space indent):

```python
    @pytest.mark.asyncio
    async def test_duplicate_carries_quotas_project_numbers_and_links(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """Duplicating a config must copy quotas, project_numbers and
        shared_quota_sources into the new period (today it copies none)."""
        source = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=114,
            semester=Semester.first,
            config_name="Dup Source 114",
            config_code="DUPSRC-114-1",
            amount=40000,
            has_college_quota=True,
            quotas={"nstc": {"EE": 5}},
            project_numbers={"nstc": "114R000001"},
            shared_quota_sources=[{"source_config_code": "PRIOR-113-1", "sub_types": ["nstc"]}],
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(source)
        await db.commit()
        await db.refresh(source)

        target_payload = {
            "academic_year": 115,
            "semester": "first",
            "config_code": "DUPTGT-115-1",
        }
        response = await authenticated_admin_client.post(
            f"{BASE}/{source.id}/duplicate", json=target_payload
        )
        assert response.status_code == 200, response.text
        new_id = response.json()["data"]["id"]

        body = (await authenticated_admin_client.get(f"{BASE}/{new_id}")).json()["data"]
        assert body["quotas"] == {"nstc": {"EE": 5}}
        assert body["project_numbers"] == {"nstc": "114R000001"}
        assert body["shared_quota_sources"] == [{"source_config_code": "PRIOR-113-1", "sub_types": ["nstc"]}]
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "duplicate_carries" -p no:cacheprovider
```
Expect failure: `body["quotas"]` is `None` (duplicate copies none of `quotas`/`project_numbers`/`shared_quota_sources`).

- [ ] Carry the fields over. In `backend/app/api/v1/endpoints/scholarship_configurations.py`, the current code at lines 1207-1226 reads:
```python
        # Create duplicate configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=source_config.scholarship_type_id,
            academic_year=target_academic_year,
            semester=target_semester,
            config_name=target_data.get("config_name", f"{source_config.config_name} (複製)"),
            config_code=target_data["config_code"],
            description=source_config.description,
            description_en=source_config.description_en,
            amount=source_config.amount,
            currency=source_config.currency,
            whitelist_student_ids=(
                source_config.whitelist_student_ids.copy() if source_config.whitelist_student_ids else {}
            ),
            requires_professor_recommendation=source_config.requires_professor_recommendation,
            requires_college_review=source_config.requires_college_review,
            is_active=True,
            version="1.0",
            created_by=current_user.id,
        )
```
Replace it with:
```python
        # Create duplicate configuration
        new_config = ScholarshipConfiguration(
            scholarship_type_id=source_config.scholarship_type_id,
            academic_year=target_academic_year,
            semester=target_semester,
            config_name=target_data.get("config_name", f"{source_config.config_name} (複製)"),
            config_code=target_data["config_code"],
            description=source_config.description,
            description_en=source_config.description_en,
            amount=source_config.amount,
            currency=source_config.currency,
            whitelist_student_ids=(
                source_config.whitelist_student_ids.copy() if source_config.whitelist_student_ids else {}
            ),
            has_quota_limit=source_config.has_quota_limit,
            has_college_quota=source_config.has_college_quota,
            quota_management_mode=source_config.quota_management_mode,
            total_quota=source_config.total_quota,
            quotas=(source_config.quotas.copy() if source_config.quotas else None),
            project_numbers=(source_config.project_numbers.copy() if source_config.project_numbers else None),
            shared_quota_sources=(
                [dict(s) for s in source_config.shared_quota_sources]
                if source_config.shared_quota_sources
                else None
            ),
            requires_professor_recommendation=source_config.requires_professor_recommendation,
            requires_college_review=source_config.requires_college_review,
            is_active=True,
            version="1.0",
            created_by=current_user.id,
        )
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "duplicate_carries" -p no:cacheprovider
```
Expect 1 passed.

- [ ] Run the full endpoint test file to confirm no regression across all create/update/duplicate/GET tests:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -p no:cacheprovider
```
Expect all passed.

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/scholarship_configurations.py --select=B904,B014 --max-line-length=120
```
Expect no output.

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
git commit -m "feat(config): duplicate path carries over quotas/project_numbers/shared_quota_sources"
```

---

### Task 5.6: Emit `shared_quota_sources`/`project_numbers` (drop `prior_quota_years`) in the list-configurations GET response

**Files:**
- Modify: `backend/app/api/v1/endpoints/scholarship_configurations.py:1320-1322` (list response builder)
- Test: `backend/app/tests/test_scholarship_configuration_endpoints.py`

**Steps:**

- [ ] Write a failing test. Add to the `TestScholarshipConfigurationEndpoints` class (4-space indent):

```python
    @pytest.mark.asyncio
    async def test_list_emits_shared_quota_sources_not_prior_quota_years(
        self,
        authenticated_admin_client: AsyncClient,
        db: AsyncSession,
        test_scholarship_type,
        test_admin_with_scholarship_access,
    ):
        """The list endpoint row must carry project_numbers + shared_quota_sources
        and must NOT carry the dropped prior_quota_years key."""
        cfg = ScholarshipConfiguration(
            scholarship_type_id=test_scholarship_type.id,
            academic_year=114,
            semester=Semester.first,
            config_name="List Row 114",
            config_code="LISTROW-114-1",
            amount=40000,
            project_numbers={"nstc": "114R000001"},
            shared_quota_sources=[{"source_config_code": "X-113-1", "sub_types": ["nstc"]}],
            is_active=True,
            created_by=test_admin_with_scholarship_access.id,
        )
        db.add(cfg)
        await db.commit()
        await db.refresh(cfg)

        response = await authenticated_admin_client.get(
            BASE, params={"scholarship_type_id": test_scholarship_type.id, "academic_year": 114}
        )
        assert response.status_code == 200
        rows = response.json()["data"]
        row = next(r for r in rows if r["config_code"] == "LISTROW-114-1")
        assert row["project_numbers"] == {"nstc": "114R000001"}
        assert row["shared_quota_sources"] == [{"source_config_code": "X-113-1", "sub_types": ["nstc"]}]
        assert "prior_quota_years" not in row
```

- [ ] Run it, expect FAIL. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "list_emits_shared_quota" -p no:cacheprovider
```
Expect failure: the list row currently emits `"prior_quota_years"` (so `"prior_quota_years" not in row` is False) and has no `shared_quota_sources` key (KeyError on `row["shared_quota_sources"]`).

- [ ] Update the list response builder. In `backend/app/api/v1/endpoints/scholarship_configurations.py`, the current code at lines 1319-1322 reads:
```python
                "total_quota": config.total_quota,
                "quotas": config.quotas,
                "project_numbers": config.project_numbers,
                "prior_quota_years": config.prior_quota_years,
```
Replace it with:
```python
                "total_quota": config.total_quota,
                "quotas": config.quotas,
                "project_numbers": config.project_numbers,
                "shared_quota_sources": config.shared_quota_sources,
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_scholarship_configuration_endpoints.py -k "list_emits_shared_quota" -p no:cacheprovider
```
Expect 1 passed.

- [ ] Confirm no remaining `prior_quota_years` reference in the endpoint file. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend grep -n "prior_quota_years" app/api/v1/endpoints/scholarship_configurations.py
```
Expect no output (exit code 1 / empty).

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/scholarship_configurations.py --select=B904,B014 --max-line-length=120
```
Expect no output.

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/scholarship_configurations.py backend/app/tests/test_scholarship_configuration_endpoints.py
git commit -m "feat(config): list GET emits shared_quota_sources+project_numbers, drops prior_quota_years"
```

---

### Task 5.7: Re-key the `payment_rosters.py` `allocation_map` from `allocation_year` to `allocation_config_id`

**Files:**
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py:588-592` (allocation_map builder), `:636-637` (student_info dict)
- Test: `backend/app/tests/test_payment_roster_allocation_map.py` (new)

**Steps:**

- [ ] Write a failing test. Create `backend/app/tests/test_payment_roster_allocation_map.py`. The `allocation_map` is built inline in a roster-validation endpoint; the focused, low-cost assertion is that the `CollegeRankingItem` read no longer references the dropped `allocation_year` attribute and reads `allocation_config_id` instead. Pin it at the source level (AST/text), matching the project's existing source-invariant test style:

```python
"""
Source-invariant test: after the shared-pool migration `CollegeRankingItem`
no longer has an `allocation_year` column, so the payment-roster
`allocation_map` builder must read `allocation_config_id`. A stale
`ri.allocation_year` read would raise AttributeError at request time
(the roster-validation endpoint builds this map for every allocated item).
"""

from pathlib import Path

ENDPOINT = (
    Path(__file__).resolve().parents[2]
    / "app"
    / "api"
    / "v1"
    / "endpoints"
    / "payment_rosters.py"
)


def test_allocation_map_reads_allocation_config_id_not_year():
    source = ENDPOINT.read_text(encoding="utf-8")
    # The dropped column must not be read off a CollegeRankingItem row alias.
    assert "ri.allocation_year" not in source
    # The map must now carry the consumed-config id.
    assert "ri.allocation_config_id" in source
    assert '"allocation_config_id": ri.allocation_config_id' in source


def test_student_info_exposes_allocation_config_id():
    source = ENDPOINT.read_text(encoding="utf-8")
    assert 'allocation_map.get(application.id, {}).get("allocation_config_id")' in source
    assert 'allocation_map.get(application.id, {}).get("allocation_year")' not in source
```

- [ ] Run it, expect FAIL. Run (pure source test — host pytest is fine):
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_roster_allocation_map.py -p no:cacheprovider
```
Expect failure: `ri.allocation_year` is still present and `ri.allocation_config_id` is absent.

- [ ] Re-key the map builder. In `backend/app/api/v1/endpoints/payment_rosters.py`, the current code at lines 588-592 reads:
```python
            for ri in alloc_items:
                allocation_map[ri.application_id] = {
                    "allocated_sub_type": ri.allocated_sub_type,
                    "allocation_year": ri.allocation_year,
                }
```
Replace it with:
```python
            for ri in alloc_items:
                allocation_map[ri.application_id] = {
                    "allocated_sub_type": ri.allocated_sub_type,
                    "allocation_config_id": ri.allocation_config_id,
                }
```

- [ ] Re-key the `student_info` consumer. In the same file the current code at lines 636-637 reads:
```python
                "allocated_sub_type": allocation_map.get(application.id, {}).get("allocated_sub_type"),
                "allocation_year": allocation_map.get(application.id, {}).get("allocation_year"),
```
Replace it with:
```python
                "allocated_sub_type": allocation_map.get(application.id, {}).get("allocated_sub_type"),
                "allocation_config_id": allocation_map.get(application.id, {}).get("allocation_config_id"),
```

- [ ] Run the test, expect PASS. Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_payment_roster_allocation_map.py -p no:cacheprovider
```
Expect 2 passed.

- [ ] Confirm no other `allocation_year` read off a `CollegeRankingItem` row alias remains in this endpoint (the `PaymentRosterItem.allocation_year` display snapshot is kept and must NOT be touched). Run:
```bash
docker compose -f docker-compose.dev.yml exec backend grep -n "allocation_year" app/api/v1/endpoints/payment_rosters.py
```
Review output: any remaining hit must be on a `PaymentRoster`/`PaymentRosterItem` object (kept display snapshot), never on a `CollegeRankingItem` (`ri.`) alias.

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/api/v1/endpoints/payment_rosters.py backend/app/tests/test_payment_roster_allocation_map.py
docker compose -f docker-compose.dev.yml exec backend flake8 app/api/v1/endpoints/payment_rosters.py --select=B904,B014 --max-line-length=120
```
Expect no output.

- [ ] Commit. Run:
```bash
git add backend/app/api/v1/endpoints/payment_rosters.py backend/app/tests/test_payment_roster_allocation_map.py
git commit -m "feat(roster): payment_rosters allocation_map reads CollegeRankingItem.allocation_config_id"
```

---

### Task 5.8: Confirm the display-snapshot readers (`excel_export_service`, `student_scholarship_history_service`) are unaffected

**Files:**
- Read-only audit: `backend/app/services/excel_export_service.py:382-433`, `backend/app/services/student_scholarship_history_service.py:94`
- Test: `backend/app/tests/test_display_snapshot_readers_unaffected.py` (new)

**Steps:**

- [ ] Write a passing-by-design pin test (RED only if the snapshot column were wrongly dropped). Create `backend/app/tests/test_display_snapshot_readers_unaffected.py`:

```python
"""
Pin test: the roster display-year snapshot lives on PaymentRoster /
PaymentRosterItem.allocation_year and is KEPT (spec §8 — denormalized snapshot
= consumed config's academic_year). The excel export and student-history
readers must continue to read `item.allocation_year` off a roster ITEM, never
off a CollegeRankingItem. This guards against an over-eager drop of the kept
snapshot column when CollegeRankingItem.allocation_year is removed.
"""

from pathlib import Path

SERVICES = Path(__file__).resolve().parents[2] / "app" / "services"
EXCEL = SERVICES / "excel_export_service.py"
HISTORY = SERVICES / "student_scholarship_history_service.py"


def test_excel_export_reads_item_allocation_year_snapshot():
    source = EXCEL.read_text(encoding="utf-8")
    # Both the _format_allocation_display helper and the remarks builder read
    # the kept PaymentRosterItem snapshot.
    assert "item.allocation_year" in source


def test_student_history_reads_item_allocation_year_snapshot():
    source = HISTORY.read_text(encoding="utf-8")
    assert "allocation_year=item.allocation_year" in source
```

- [ ] Run it, expect PASS (these readers are already correct — this task only pins them so a later edit can't silently break the kept snapshot path). Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_display_snapshot_readers_unaffected.py -p no:cacheprovider
```
Expect 2 passed.

- [ ] Verify the `PaymentRosterItem.allocation_year` column is still present on the model (it must NOT be dropped — only `CollegeRankingItem.allocation_year` is). Run:
```bash
docker compose -f docker-compose.dev.yml exec backend grep -n "allocation_year" app/models/payment_roster.py
```
Expect hits on `PaymentRoster.allocation_year` and `PaymentRosterItem.allocation_year` (kept).

- [ ] Lint. Run:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app/tests/test_display_snapshot_readers_unaffected.py
```
Expect no output.

- [ ] Commit. Run:
```bash
git add backend/app/tests/test_display_snapshot_readers_unaffected.py
git commit -m "test(roster): pin excel/history readers to kept PaymentRosterItem.allocation_year snapshot"
```

---

### Task 5.9: Full Phase-5 regression + lint gate

**Files:**
- Test: all Phase-5 touched test files (no new code)

**Steps:**

- [ ] Run every test file touched in this phase together:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest \
  app/tests/test_scholarship_configuration_schema_validators.py \
  app/tests/test_shared_quota_link_validation.py \
  app/tests/test_scholarship_configuration_endpoints.py \
  app/tests/test_payment_roster_allocation_map.py \
  app/tests/test_display_snapshot_readers_unaffected.py \
  -p no:cacheprovider
```
Expect all passed, zero failures/errors.

- [ ] Run the broader config defaults + service tests to confirm the schema/endpoint changes didn't break sibling suites:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest \
  app/tests/test_scholarship_configuration_defaults.py \
  app/tests/test_scholarship_configuration_service.py \
  app/tests/test_config_management_schemas.py \
  -p no:cacheprovider
```
Expect all passed. If any test references the dropped `prior_quota_years` on the config schema/model, it belongs to Phase 1/2's scope — note the failure and the file in your hand-off rather than editing it here.

- [ ] Final lint gate over all Phase-5 source files:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 \
  backend/app/schemas/scholarship_configuration.py \
  backend/app/api/v1/endpoints/scholarship_configurations.py \
  backend/app/api/v1/endpoints/payment_rosters.py
docker compose -f docker-compose.dev.yml exec backend flake8 \
  app/schemas/scholarship_configuration.py \
  app/api/v1/endpoints/scholarship_configurations.py \
  app/api/v1/endpoints/payment_rosters.py \
  --select=B904,B014 --max-line-length=120
```
Expect no output from either command.

- [ ] No commit needed (verification-only task); if black reformatted anything, re-run the relevant per-task commit's `git add` + `git commit -m "style(config): black formatting"`.


## Phase 6 — Frontend + seed + test sweep

**Files in this phase:**

| Path | Change |
|---|---|
| `frontend/lib/api/modules/manual-distribution.ts` | `AllocationItem`/`AllocationSuggestion.allocation_year`→`allocation_config_id`; `SubTypeYearCol`→config column type; pool-key fields on `DistributionStudent`/`AvailableQuota`/`RosterSummary`/`SummaryGroup` |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | config-keyed grid columns + `allocation_config_id` payload |
| `frontend/components/admin-configuration-management.tsx` | `shared_quota_sources` picker + `project_numbers` field; `formData` init + `openEditDialog` |
| `frontend/lib/api/types.ts:330-332` | `project_numbers: Record<string,string>`; drop `prior_quota_years`; add `shared_quota_sources` |
| `frontend/lib/api/generated/schema.d.ts` | regenerate |
| `frontend/lib/api/modules/__tests__/manual-distribution.test.ts:126-139` | allocate body `allocation_config_id` |
| `backend/app/db/seed_scholarship_configs.py:96-296` | flat `project_numbers`, `shared_quota_sources`, sibling project codes, re-sync block |
| `backend/scripts/seed_distribution_test_data.py:155-162` | `allocation_year`→`allocation_config_id` |
| §13 backend test files | fixture rewrites (checklist) |

> Phase 6 depends on Phases 1–5 (backend model/schema/service/endpoint and migration) being merged. The backend `AllocationItem.allocation_config_id`, `pool()`/`remaining()`, `get_quota_status` config-keyed `by_config` payload, and `ScholarshipConfiguration.shared_quota_sources` / flat `project_numbers` already exist when these tasks run. All run-commands assume the dev stack is up (`docker compose -f docker-compose.dev.yml up -d`) and the backend is reachable at `localhost:8000`.

### Task 6.1: Pin allocate body to `allocation_config_id` in the FE module test (RED)

**Files:**
- Modify: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts:115-144`
- Test: same file

- [ ] Replace the `allocate` test body (currently pinning `allocation_year`) with the new `allocation_config_id` shape. Current code is:
```ts
    await api.allocate({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      allocations: [
        { ranking_item_id: 1, sub_type_code: "nstc", allocation_year: 114 },
        { ranking_item_id: 2, sub_type_code: null, allocation_year: null },
      ],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/allocate",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          allocations: [
            { ranking_item_id: 1, sub_type_code: "nstc", allocation_year: 114 },
            { ranking_item_id: 2, sub_type_code: null, allocation_year: null },
          ],
        },
      }
    );
```
  Replace with:
```ts
    await api.allocate({
      scholarship_type_id: 7,
      academic_year: 114,
      semester: "first",
      allocations: [
        { ranking_item_id: 1, sub_type_code: "nstc", allocation_config_id: 42 },
        { ranking_item_id: 2, sub_type_code: null, allocation_config_id: null },
      ],
    });
    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/manual-distribution/allocate",
      {
        body: {
          scholarship_type_id: 7,
          academic_year: 114,
          semester: "first",
          allocations: [
            { ranking_item_id: 1, sub_type_code: "nstc", allocation_config_id: 42 },
            { ranking_item_id: 2, sub_type_code: null, allocation_config_id: null },
          ],
        },
      }
    );
```
- [ ] Run the test and expect a **TypeScript compile failure** (the module's `AllocationItem` still declares `allocation_year`, not `allocation_config_id`):
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest lib/api/modules/__tests__/manual-distribution.test.ts -t "allocate POSTs"
```
  Expected: `error TS2353: Object literal may only specify known properties, and 'allocation_config_id' does not exist in type 'AllocationItem'.`
- [ ] Commit:
```bash
git add frontend/lib/api/modules/__tests__/manual-distribution.test.ts
git commit -m "test(fe): pin allocate body to allocation_config_id (RED)"
```

### Task 6.2: Rename `allocation_year` → `allocation_config_id` on `AllocationItem` / `AllocationSuggestion` (GREEN)

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:76-86`
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`

- [ ] Replace the two interfaces. Current code is:
```ts
export interface AllocationItem {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_year: number | null;
}

export interface AllocationSuggestion {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_year: number | null;
}
```
  Replace with:
```ts
export interface AllocationItem {
  ranking_item_id: number;
  sub_type_code: string | null;
  /** The config whose quota this slot consumes (own config or a linked source). Null only for the whole-period sentinel. */
  allocation_config_id: number | null;
}

export interface AllocationSuggestion {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_config_id: number | null;
}
```
- [ ] Run the test and expect **PASS**:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest lib/api/modules/__tests__/manual-distribution.test.ts -t "allocate POSTs"
```
  Expected: `1 passed`.
- [ ] Commit:
```bash
git add frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat(fe): AllocationItem/Suggestion use allocation_config_id"
```

### Task 6.3: Replace `SubTypeYearCol` with a config-keyed column type

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:51-74`
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts` (compile guard via the 16-method invariant test)

- [ ] Replace the `YearQuota` / `SubTypeQuotaStatus` / `SubTypeYearCol` block. Current code is:
```ts
export interface YearQuota {
  total: number;
  allocated: number;
  remaining: number;
  by_college: Record<string, CollegeQuota>;
}

export interface SubTypeQuotaStatus {
  display_name: string;
  /** Multi-year quota data: year string → quota info */
  by_year: Record<string, YearQuota>;
}

export type QuotaStatus = Record<string, SubTypeQuotaStatus>;

/** A flattened (sub_type × year) column descriptor for the distribution table */
export interface SubTypeYearCol {
  sub_type: string;
  year: number;
  display_name: string; // e.g., "114年 國科會博士生獎學金"
  total: number;
  remaining: number; // based on DB-confirmed allocations
  key: string; // composite key: "nstc:114"
}
```
  Replace with:
```ts
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

export interface SubTypeQuotaStatus {
  display_name: string;
  /** Distributable configs for this sub_type, keyed by config_id string. */
  by_config: Record<string, ConfigQuota>;
}

export type QuotaStatus = Record<string, SubTypeQuotaStatus>;

/** A flattened (sub_type × source-config) column descriptor for the distribution table */
export interface SubTypeConfigCol {
  sub_type: string;
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  display_name: string; // e.g., "國科會 · phd_114"
  total: number;
  remaining: number; // live: pool_total − consumers, from /quota-status
  key: string; // composite key: "nstc:42" (sub_type:config_id)
}
```
- [ ] Run the type-check and expect it to **report errors in the panel** (the panel still imports/uses `SubTypeYearCol`); this confirms the rename is wired:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep -E "SubTypeYearCol|by_year|\.year" | head
```
  Expected: errors referencing `SubTypeYearCol` / `by_year` in `ManualDistributionPanel.tsx` (resolved in Task 6.6).
- [ ] Commit:
```bash
git add frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat(fe): config-keyed quota column type (by_config/SubTypeConfigCol)"
```

### Task 6.4: Re-key pool fields on `DistributionStudent` / `DistributionStateAvailableQuota`

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:12-43` (DistributionStudent), `:213-220` (DistributionStateAvailableQuota)
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`

- [ ] In `DistributionStudent`, replace the pool key with the config id but keep `renewal_year` as display. Current line `:19`:
```ts
  allocated_sub_type: string | null;
  allocation_year: number | null;
```
  Replace with:
```ts
  allocated_sub_type: string | null;
  /** Config whose quota this student's slot consumes. Seed the checked column from (allocated_sub_type, allocation_config_id). */
  allocation_config_id: number | null;
```
- [ ] In `DistributionStateAvailableQuota`, replace the pool key. Current code `:213-220`:
```ts
/** Available pool per (sub_type, allocation_year): total / used / remaining. */
export interface DistributionStateAvailableQuota {
  sub_type: string;
  allocation_year: number;
  total: number;
  used: number;
  remaining: number;
}
```
  Replace with:
```ts
/** Available pool per (sub_type, config): total / used / remaining. */
export interface DistributionStateAvailableQuota {
  sub_type: string;
  config_id: number;
  config_code: string;
  academic_year: number;
  is_own: boolean;
  total: number;
  used: number;
  remaining: number;
}
```
- [ ] Run the 16-method invariant test (asserts the module still compiles & exports the same surface) and expect **PASS**:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest lib/api/modules/__tests__/manual-distribution.test.ts -t "module exposes exactly 16 methods"
```
  Expected: `1 passed`.
- [ ] Commit:
```bash
git add frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat(fe): DistributionStudent/AvailableQuota pool keys → config"
```

### Task 6.5: Re-key roster/summary display fields (keep `allocation_year` as display snapshot)

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts:128-139` (RosterSummary), `:167-172` (DistributionSummaryGroup), `:246-260` (ReleaseChainItem.freed_slot)
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`

- [ ] `RosterSummary` keeps `allocation_year` (display snapshot per spec §8) and gains `allocation_config_id`. Current code `:128-139`:
```ts
export interface RosterSummary {
  id: number;
  roster_code: string;
  sub_type: string;
  allocation_year: number;
  project_number: string | null;
  period_label: string;
  status: string;
  qualified_count: number;
  disqualified_count: number;
  total_amount: string;
}
```
  Replace with:
```ts
export interface RosterSummary {
  id: number;
  roster_code: string;
  sub_type: string;
  /** Consumed config id (pool key for this roster). */
  allocation_config_id: number | null;
  /** Frozen display snapshot = consumed config's academic_year. */
  allocation_year: number | null;
  project_number: string | null;
  period_label: string;
  status: string;
  qualified_count: number;
  disqualified_count: number;
  total_amount: string;
}
```
- [ ] `DistributionSummaryGroup` is a pool key → re-key to config (carry display year). Current code `:167-172`:
```ts
export interface DistributionSummaryGroup {
  sub_type: string;
  allocation_year: number;
  count: number;
  students: DistributionSummaryStudent[];
}
```
  Replace with:
```ts
export interface DistributionSummaryGroup {
  sub_type: string;
  allocation_config_id: number | null;
  /** Consumed config's academic_year, for the "XXX 年度" group label. */
  allocation_year: number | null;
  count: number;
  students: DistributionSummaryStudent[];
}
```
- [ ] `ReleaseChainItem.freed_slot` is a pool key → re-key. Current code `:252-256`:
```ts
  /** The slot that would be freed. */
  freed_slot: {
    sub_type: string | null;
    allocation_year: number | null;
  };
```
  Replace with:
```ts
  /** The slot that would be freed. */
  freed_slot: {
    sub_type: string | null;
    allocation_config_id: number | null;
  };
```
- [ ] Run the full module test file and expect **PASS** (no test pins these fields directly; this verifies the module still compiles):
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest lib/api/modules/__tests__/manual-distribution.test.ts
```
  Expected: `16 passed`.
- [ ] Commit:
```bash
git add frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat(fe): roster/summary/freed_slot keyed on allocation_config_id"
```

### Task 6.6: Convert `LocalAlloc`, `makeColKey`, `subTypeCols`, counts to config keys

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx:12-23` (import), `:75-87` (LocalAlloc + makeColKey), `:219-262` (subTypeCols + localAllocCounts)
- Test: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` (compiled via `tsc`)

- [ ] Update the type import. Current code `:13-23` imports `SubTypeYearCol`; replace that one name:
```ts
  SubTypeYearCol,
```
  with:
```ts
  SubTypeConfigCol,
```
- [ ] Replace `LocalAlloc` + `makeColKey`. Current code `:75-87`:
```ts
/** Local allocation state for a student: which (sub_type, year) they're assigned to */
interface LocalAlloc {
  sub_type: string;
  year: number;
}

const ALL_DEPTS_OWN = "__college_all__";
const ALL_DEPTS_SYSTEM = "__all__";

/** Composite key for a (sub_type, year) column: "nstc:114" */
function makeColKey(sub_type: string, year: number) {
  return `${sub_type}:${year}`;
}
```
  Replace with:
```ts
/** Local allocation state for a student: which (sub_type, config) they're assigned to */
interface LocalAlloc {
  sub_type: string;
  config_id: number;
}

const ALL_DEPTS_OWN = "__college_all__";
const ALL_DEPTS_SYSTEM = "__all__";

/** Composite key for a (sub_type, config) column: "nstc:42" */
function makeColKey(sub_type: string, config_id: number) {
  return `${sub_type}:${config_id}`;
}
```
- [ ] Replace `subTypeCols` (the flatten) and `localAllocCounts`. Current code `:219-262`:
```ts
  /**
   * Flatten quota status into (sub_type × year) columns, ordered by:
   * - sub_type (by appearance order in quotaStatus keys)
   * - year descending (current year first, then prior years)
   */
  const subTypeCols = useMemo<SubTypeYearCol[]>(() => {
    const cols: SubTypeYearCol[] = [];
    for (const [sub_type, stData] of Object.entries(quotaStatus)) {
      const years = Object.keys(stData.by_year)
        .map(Number)
        .sort((a, b) => b - a); // descending: 114, 113, 112
      const isMultiYear = years.length > 1;
      const shortName = getSubTypeShortName(sub_type, stData.display_name);
      for (const year of years) {
        const yData = stData.by_year[String(year)];
        if (!yData || yData.total <= 0) continue;
        // Multi-year sub-types (e.g. nstc): prefix with year → "114 國科會", "113 國科會"
        // Single-year sub-types (e.g. moe_1w): just the short name → "教育部+1"
        const display_name = isMultiYear ? `${year} ${shortName}` : shortName;
        cols.push({
          sub_type,
          year,
          display_name,
          total: yData.total,
          remaining: yData.remaining,
          key: makeColKey(sub_type, year),
        });
      }
    }
    return cols;
  }, [quotaStatus]);

  /** Count how many local allocations are using each (sub_type, year) slot */
  const localAllocCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const col of subTypeCols) counts[col.key] = 0;
    for (const [, alloc] of localAllocations) {
      if (alloc) {
        const k = makeColKey(alloc.sub_type, alloc.year);
        counts[k] = (counts[k] ?? 0) + 1;
      }
    }
    return counts;
  }, [localAllocations, subTypeCols]);
```
  Replace with:
```ts
  /**
   * Flatten quota status into (sub_type × source-config) columns, ordered by:
   * - sub_type (by appearance order in quotaStatus keys)
   * - own config first, then linked sources by descending academic_year
   */
  const subTypeCols = useMemo<SubTypeConfigCol[]>(() => {
    const cols: SubTypeConfigCol[] = [];
    for (const [sub_type, stData] of Object.entries(quotaStatus)) {
      const configs = Object.values(stData.by_config).sort((a, b) => {
        if (a.is_own !== b.is_own) return a.is_own ? -1 : 1; // own first
        return b.academic_year - a.academic_year; // then descending year
      });
      const isMulti = configs.length > 1;
      const shortName = getSubTypeShortName(sub_type, stData.display_name);
      for (const cData of configs) {
        if (cData.total <= 0) continue;
        // Multi-config sub-types (e.g. nstc borrowing): label with config code → "國科會 · phd_114"
        // Single-config sub-types (e.g. moe_1w): just the short name → "教育部+1"
        const display_name = isMulti ? `${shortName} · ${cData.config_code}` : shortName;
        cols.push({
          sub_type,
          config_id: cData.config_id,
          config_code: cData.config_code,
          academic_year: cData.academic_year,
          is_own: cData.is_own,
          display_name,
          total: cData.total,
          remaining: cData.remaining,
          key: makeColKey(sub_type, cData.config_id),
        });
      }
    }
    return cols;
  }, [quotaStatus]);

  /** Count how many local allocations are using each (sub_type, config) slot */
  const localAllocCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const col of subTypeCols) counts[col.key] = 0;
    for (const [, alloc] of localAllocations) {
      if (alloc) {
        const k = makeColKey(alloc.sub_type, alloc.config_id);
        counts[k] = (counts[k] ?? 0) + 1;
      }
    }
    return counts;
  }, [localAllocations, subTypeCols]);
```
- [ ] Run `tsc` (scoped grep) and expect the remaining errors to be in the seeding/handlers/cells (fixed in 6.7–6.9), NOT in `subTypeCols`/`by_config`:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep "ManualDistributionPanel" | grep -E "by_config|SubTypeConfigCol" | head
```
  Expected: no output (those two are resolved).
- [ ] Commit:
```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(fe): panel columns keyed on (sub_type, config)"
```

### Task 6.7: Re-key seeding of `localAllocations` from `allocation_config_id`

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx:286-296` (fetchData seed), `:314-329` (preview apply), `:563-574` (finalize reload seed), `:705-717` (restore reload seed)
- Test: panel compiled via `tsc`

- [ ] In `fetchData` seeding, current code `:286-296`:
```ts
        const allocMap = new Map<number, LocalAlloc | null>();
        for (const s of studentsResp.data) {
          if (s.is_allocated && s.allocated_sub_type) {
            allocMap.set(s.ranking_item_id, {
              sub_type: s.allocated_sub_type,
              year: s.allocation_year ?? selectedAcademicYear!,
            });
          } else {
            allocMap.set(s.ranking_item_id, null);
          }
        }
```
  Replace with:
```ts
        const allocMap = new Map<number, LocalAlloc | null>();
        for (const s of studentsResp.data) {
          if (s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null) {
            allocMap.set(s.ranking_item_id, {
              sub_type: s.allocated_sub_type,
              config_id: s.allocation_config_id,
            });
          } else {
            allocMap.set(s.ranking_item_id, null);
          }
        }
```
- [ ] In the preview-apply loop, current code `:314-329`:
```ts
        // Apply auto-preview suggestions for unallocated students
        let hasPreview = false;
        for (const suggestion of previewSuggestions) {
          if (
            suggestion.sub_type_code &&
            suggestion.allocation_year &&
            !allocMap.get(suggestion.ranking_item_id)
          ) {
            allocMap.set(suggestion.ranking_item_id, {
              sub_type: suggestion.sub_type_code,
              year: suggestion.allocation_year,
            });
            hasPreview = true;
          }
        }
```
  Replace with:
```ts
        // Apply auto-preview suggestions for unallocated students
        let hasPreview = false;
        for (const suggestion of previewSuggestions) {
          if (
            suggestion.sub_type_code &&
            suggestion.allocation_config_id != null &&
            !allocMap.get(suggestion.ranking_item_id)
          ) {
            allocMap.set(suggestion.ranking_item_id, {
              sub_type: suggestion.sub_type_code,
              config_id: suggestion.allocation_config_id,
            });
            hasPreview = true;
          }
        }
```
- [ ] In the finalize reload seeding, current code `:563-574`:
```ts
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.is_allocated && s.allocated_sub_type) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                year: s.allocation_year ?? selectedAcademicYear!,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
```
  Replace with:
```ts
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                config_id: s.allocation_config_id,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
```
- [ ] In the restore reload seeding, current code `:705-717`:
```ts
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.is_allocated && s.allocated_sub_type) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                year: s.allocation_year ?? selectedAcademicYear!,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
```
  Replace with:
```ts
          const initial = new Map<number, LocalAlloc | null>();
          for (const s of studentsResp.data) {
            if (s.is_allocated && s.allocated_sub_type && s.allocation_config_id != null) {
              initial.set(s.ranking_item_id, {
                sub_type: s.allocated_sub_type,
                config_id: s.allocation_config_id,
              });
            } else {
              initial.set(s.ranking_item_id, null);
            }
          }
          setLocalAllocations(initial);
```
- [ ] Run `tsc` and expect no remaining `.year` / `allocation_year` errors in these blocks:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep "ManualDistributionPanel" | grep -E "allocation_year|\.year" | head
```
  Expected: only the handler/payload/cell sites remain (fixed in 6.8–6.9).
- [ ] Commit:
```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(fe): seed localAllocations from allocation_config_id"
```

### Task 6.8: Re-key `handleCheckbox`, preview payload, and `handleSave` allocate payload

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx:435-449` (preview payload), `:474-490` (handleCheckbox), `:498-504` (handleSave payload)
- Test: panel compiled via `tsc`

- [ ] Replace the preview payload builder. Current code `:435-441`:
```ts
      const allocations = Array.from(localAllocations.entries())
        .filter(([, alloc]) => alloc !== null)
        .map(([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_year: alloc?.year ?? null,
        }));
```
  Replace with:
```ts
      const allocations = Array.from(localAllocations.entries())
        .filter(([, alloc]) => alloc !== null)
        .map(([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_config_id: alloc?.config_id ?? null,
        }));
```
- [ ] Replace `handleCheckbox`. Current code `:474-490`:
```ts
  const handleCheckbox = (
    rankingItemId: number,
    sub_type: string,
    year: number
  ) => {
    setLocalAllocations(prev => {
      const next = new Map(prev);
      const cur = next.get(rankingItemId);
      // Radio-like: clicking active → uncheck; clicking other → set exclusively
      if (cur?.sub_type === sub_type && cur?.year === year) {
        next.set(rankingItemId, null);
      } else {
        next.set(rankingItemId, { sub_type, year });
      }
      return next;
    });
  };
```
  Replace with:
```ts
  const handleCheckbox = (
    rankingItemId: number,
    sub_type: string,
    config_id: number
  ) => {
    setLocalAllocations(prev => {
      const next = new Map(prev);
      const cur = next.get(rankingItemId);
      // Radio-like: clicking active → uncheck; clicking other → set exclusively
      if (cur?.sub_type === sub_type && cur?.config_id === config_id) {
        next.set(rankingItemId, null);
      } else {
        next.set(rankingItemId, { sub_type, config_id });
      }
      return next;
    });
  };
```
- [ ] Replace the `handleSave` payload builder. Current code `:498-504`:
```ts
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_year: alloc?.year ?? null,
        })
      );
```
  Replace with:
```ts
      const allocations = Array.from(localAllocations.entries()).map(
        ([ranking_item_id, alloc]) => ({
          ranking_item_id,
          sub_type_code: alloc?.sub_type ?? null,
          allocation_config_id: alloc?.config_id ?? null,
        })
      );
```
- [ ] Run `tsc` and expect no handler/payload errors remaining:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep "ManualDistributionPanel" | grep -E "handleCheckbox|allocation_year|\.year" | head
```
  Expected: only the grid-cell `onChange`/`isChecked` sites remain (fixed in 6.9).
- [ ] Commit:
```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(fe): handleCheckbox + allocate/preview payload use config_id"
```

### Task 6.9: Re-key grid cells, header, sidebar, and roster-result label

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx:1116-1124` (roster result label), `:1280-1290` (header), `:1390-1466` (grid cell), `:1627-1665` (sidebar prior-year flag)
- Test: panel compiled via `tsc`

- [ ] In the grid cell, replace the `isChecked` test and the `onChange` call. Current code `:1398-1400`:
```ts
                                  const isChecked =
                                    curAlloc?.sub_type === col.sub_type &&
                                    curAlloc?.year === col.year;
```
  Replace with:
```ts
                                  const isChecked =
                                    curAlloc?.sub_type === col.sub_type &&
                                    curAlloc?.config_id === col.config_id;
```
- [ ] In the same cell, the `onChange` handler. Current code `:1456-1462`:
```ts
                                        onChange={() =>
                                          handleCheckbox(
                                            student.ranking_item_id,
                                            col.sub_type,
                                            col.year
                                          )
                                        }
```
  Replace with:
```ts
                                        onChange={() =>
                                          handleCheckbox(
                                            student.ranking_item_id,
                                            col.sub_type,
                                            col.config_id
                                          )
                                        }
```
- [ ] In the column header, the prior-year orange test reads `col.year`. Current code `:1285-1289`:
```ts
                          <span
                            className={`font-semibold ${col.year < (selectedAcademicYear ?? 9999) ? "text-orange-600" : "text-slate-700"}`}
                          >
                            {col.display_name}
                          </span>
```
  Replace with:
```ts
                          <span
                            className={`font-semibold ${col.academic_year < (selectedAcademicYear ?? 9999) ? "text-orange-600" : "text-slate-700"}`}
                          >
                            {col.display_name}
                          </span>
```
- [ ] In the sidebar, the `isPriorYear` flag reads `col.year`. Current code `:1632`:
```ts
                const isPriorYear = col.year < (selectedAcademicYear ?? 9999);
```
  Replace with:
```ts
                const isPriorYear = col.academic_year < (selectedAcademicYear ?? 9999);
```
- [ ] In the roster-result label, `r.allocation_year` may be null now — guard it. Current code `:1116-1124`:
```ts
              {rosterResult.rosters.map(r => (
                <div
                  key={r.roster_code}
                  className="text-xs text-blue-700 flex gap-3"
                >
                  <span className="font-mono">{r.roster_code}</span>
                  <span>
                    {r.sub_type} {r.allocation_year} 年度
                  </span>
```
  Replace with:
```ts
              {rosterResult.rosters.map(r => (
                <div
                  key={r.roster_code}
                  className="text-xs text-blue-700 flex gap-3"
                >
                  <span className="font-mono">{r.roster_code}</span>
                  <span>
                    {r.sub_type}
                    {r.allocation_year != null ? ` ${r.allocation_year} 年度` : ""}
                  </span>
```
- [ ] Also update the local `rosterResult` state type (`:194-204`) which pins `allocation_year: number`. Current code:
```ts
    rosters: Array<{
      roster_code: string;
      sub_type: string;
      allocation_year: number;
      project_number: string | null;
      qualified_count: number;
      total_amount: string;
    }>;
```
  Replace with:
```ts
    rosters: Array<{
      roster_code: string;
      sub_type: string;
      allocation_year: number | null;
      project_number: string | null;
      qualified_count: number;
      total_amount: string;
    }>;
```
- [ ] Run the full panel type-check and expect **clean** (no `allocation_year` / `.year` / `by_year` / `SubTypeYearCol` errors):
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep "ManualDistributionPanel" | head
```
  Expected: no output.
- [ ] Commit:
```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(fe): grid cells/header/sidebar/roster-label use config columns"
```

### Task 6.10: Narrow `ScholarshipConfiguration` types (project_numbers flat, drop prior_quota_years, add shared_quota_sources)

**Files:**
- Modify: `frontend/lib/api/types.ts:330-332` (ScholarshipConfiguration), `:1166-1168` (ScholarshipConfigurationFormData)
- Test: `frontend/lib/api/types.ts` compiled via `tsc`

- [ ] In `ScholarshipConfiguration`, replace the three lines. Current code `:330-332`:
```ts
  quotas?: Record<string, any>;
  project_numbers?: Record<string, Record<string, string>>;
  prior_quota_years?: Record<string, number[]>;
```
  Replace with:
```ts
  quotas?: Record<string, Record<string, number>>;
  project_numbers?: Record<string, string>;
  shared_quota_sources?: { source_config_code: string; sub_types: string[] }[];
```
- [ ] In `ScholarshipConfigurationFormData`, replace the form's `prior_quota_years` line. Current code `:1167`:
```ts
  prior_quota_years?: Record<string, any> | string;
```
  Replace with:
```ts
  project_numbers?: Record<string, string> | string;
  shared_quota_sources?: { source_config_code: string; sub_types: string[] }[] | string;
```
- [ ] Run `tsc` and expect errors to appear **only** in `admin-configuration-management.tsx` (still references `prior_quota_years`); this confirms the type change is enforced:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep -E "prior_quota_years" | head
```
  Expected: errors in `admin-configuration-management.tsx` (resolved in 6.11–6.12).
- [ ] Commit:
```bash
git add frontend/lib/api/types.ts
git commit -m "feat(fe): ScholarshipConfiguration project_numbers flat + shared_quota_sources"
```

### Task 6.11: Replace `prior_quota_years` textarea with a `shared_quota_sources` picker (both create & edit forms)

**Files:**
- Modify: `frontend/components/admin-configuration-management.tsx:1771-1808` (create form), `:2246-2284` (edit form)
- Test: component compiled via `tsc`

- [ ] In the **create** form, replace the prior-year textarea block (`:1771-1808`). Current code:
```tsx
                {formData.quota_management_mode === "matrix_based" && (
                  <div>
                    <Label>前年度配額設定 (JSON 格式)</Label>
                    <div className="mt-1 mb-2 text-sm text-muted-foreground">
                      <p>
                        設定各子類型可使用的前年度配額，格式：
                        {`{"nstc": [113, 112], "moe_1w": []}`}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        空陣列 [] 表示僅限當年度配額
                      </p>
                    </div>
                    <Textarea
                      value={
                        typeof formData.prior_quota_years === "object"
                          ? JSON.stringify(formData.prior_quota_years, null, 2)
                          : formData.prior_quota_years || ""
                      }
                      onChange={e => {
                        try {
                          const parsed = e.target.value
                            ? JSON.parse(e.target.value)
                            : {};
                          setFormData(prev => ({
                            ...prev,
                            prior_quota_years: parsed,
                          }));
                        } catch {
                          setFormData(prev => ({
                            ...prev,
                            prior_quota_years: e.target.value,
                          }));
                        }
                      }}
                      placeholder='{"nstc": [113], "moe_1w": []}'
                      className="min-h-[80px] font-mono text-sm"
                    />
                  </div>
                )}
```
  Replace with (the picker is extracted as a shared component in the next sub-step; here we just call it):
```tsx
                {formData.quota_management_mode === "matrix_based" && (
                  <SharedQuotaSourcesPicker
                    value={
                      Array.isArray(formData.shared_quota_sources)
                        ? formData.shared_quota_sources
                        : []
                    }
                    onChange={next =>
                      setFormData(prev => ({ ...prev, shared_quota_sources: next }))
                    }
                    subTypes={Object.keys(
                      (typeof formData.quotas === "object" && formData.quotas) || {}
                    )}
                    candidateConfigs={configurations.filter(
                      c =>
                        c.academic_year < (formData.academic_year ?? 0) &&
                        c.config_code !== formData.config_code
                    )}
                  />
                )}
```
- [ ] In the **edit** form, replace the identical block (`:2246-2284`) with the **same** `<SharedQuotaSourcesPicker .../>` JSX (the picker reads `formData.shared_quota_sources` so both forms share one component — DRY).
- [ ] Add the `SharedQuotaSourcesPicker` component above the exported component (after the imports, before `export function ...ConfigurationManagement`). Insert:
```tsx
function SharedQuotaSourcesPicker({
  value,
  onChange,
  subTypes,
  candidateConfigs,
}: {
  value: { source_config_code: string; sub_types: string[] }[];
  onChange: (next: { source_config_code: string; sub_types: string[] }[]) => void;
  subTypes: string[];
  candidateConfigs: { config_code: string; academic_year: number }[];
}) {
  const entryFor = (code: string) =>
    value.find(e => e.source_config_code === code);

  const toggleConfig = (code: string, on: boolean) => {
    if (on) {
      onChange([...value, { source_config_code: code, sub_types: [] }]);
    } else {
      onChange(value.filter(e => e.source_config_code !== code));
    }
  };

  const toggleSubType = (code: string, st: string, on: boolean) => {
    onChange(
      value.map(e => {
        if (e.source_config_code !== code) return e;
        const sub_types = on
          ? [...e.sub_types, st]
          : e.sub_types.filter(s => s !== st);
        return { ...e, sub_types };
      })
    );
  };

  return (
    <div>
      <Label>共用前年度配額來源</Label>
      <p className="mt-1 mb-2 text-sm text-muted-foreground">
        勾選要借用剩餘名額的前年度配置（依代碼），並選擇可借用的子類型。
      </p>
      {candidateConfigs.length === 0 ? (
        <p className="text-xs text-muted-foreground">無可借用的前年度配置</p>
      ) : (
        <div className="space-y-2">
          {candidateConfigs.map(c => {
            const entry = entryFor(c.config_code);
            const checked = !!entry;
            return (
              <div key={c.config_code} className="border rounded-lg p-2">
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={e => toggleConfig(c.config_code, e.target.checked)}
                  />
                  {c.config_code}（{c.academic_year} 學年）
                </label>
                {checked && (
                  <div className="mt-2 flex flex-wrap gap-3 pl-6">
                    {subTypes.length === 0 ? (
                      <span className="text-xs text-muted-foreground">
                        請先設定本配置的配額子類型
                      </span>
                    ) : (
                      subTypes.map(st => (
                        <label
                          key={st}
                          className="flex items-center gap-1 text-xs"
                        >
                          <input
                            type="checkbox"
                            checked={entry?.sub_types.includes(st) ?? false}
                            onChange={e =>
                              toggleSubType(c.config_code, st, e.target.checked)
                            }
                          />
                          {st}
                        </label>
                      ))
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
```
- [ ] Run `tsc` and expect no `prior_quota_years` errors in this file:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep "admin-configuration-management" | grep prior_quota_years | head
```
  Expected: no output.
- [ ] Commit:
```bash
git add frontend/components/admin-configuration-management.tsx
git commit -m "feat(fe): shared_quota_sources picker replaces prior_quota_years textarea"
```

### Task 6.12: Add `project_numbers` field + wire `formData` init / `openEditDialog`

**Files:**
- Modify: `frontend/components/admin-configuration-management.tsx:494-511` (handleCreate init), `:533-548` (openEditDialog), and add a `project_numbers` textarea below the picker in both forms
- Test: component compiled via `tsc`

- [ ] In `handleCreateConfiguration`, the init object omits the two new fields. Current code `:496-509`:
```tsx
    setFormData({
      scholarship_type_id: selectedScholarshipType.id,
      academic_year: taiwanYear,
      semester: "first",
      currency: "TWD",
      is_active: true,
      version: "1.0",
      has_quota_limit: false,
      has_college_quota: false,
      quota_management_mode: "none",
      total_quota: 0,
      quotas: {},
      whitelist_student_ids: {},
    });
```
  Replace with:
```tsx
    setFormData({
      scholarship_type_id: selectedScholarshipType.id,
      academic_year: taiwanYear,
      semester: "first",
      currency: "TWD",
      is_active: true,
      version: "1.0",
      has_quota_limit: false,
      has_college_quota: false,
      quota_management_mode: "none",
      total_quota: 0,
      quotas: {},
      project_numbers: {},
      shared_quota_sources: [],
      whitelist_student_ids: {},
    });
```
- [ ] In `openEditDialog`, replace the `prior_quota_years` seed. Current code `:546-547`:
```tsx
      quotas: config.quotas,
      prior_quota_years: config.prior_quota_years || {},
```
  Replace with:
```tsx
      quotas: config.quotas,
      project_numbers: config.project_numbers || {},
      shared_quota_sources: config.shared_quota_sources || [],
```
- [ ] Add a `project_numbers` textarea immediately after the `<SharedQuotaSourcesPicker .../>` in **both** the create form (`:1771` block, after the picker JSX) and the edit form (`:2246` block, after the picker JSX). Insert this identical block in each:
```tsx
                {formData.quota_management_mode === "matrix_based" && (
                  <div>
                    <Label>計畫編號 (JSON 格式)</Label>
                    <p className="mt-1 mb-2 text-sm text-muted-foreground">
                      每個子類型一組計畫編號，格式：{`{"nstc": "114R000001"}`}
                    </p>
                    <Textarea
                      value={
                        typeof formData.project_numbers === "object"
                          ? JSON.stringify(formData.project_numbers, null, 2)
                          : formData.project_numbers || ""
                      }
                      onChange={e => {
                        try {
                          const parsed = e.target.value
                            ? JSON.parse(e.target.value)
                            : {};
                          setFormData(prev => ({
                            ...prev,
                            project_numbers: parsed,
                          }));
                        } catch {
                          setFormData(prev => ({
                            ...prev,
                            project_numbers: e.target.value,
                          }));
                        }
                      }}
                      placeholder='{"nstc": "114R000001"}'
                      className="min-h-[60px] font-mono text-sm"
                    />
                  </div>
                )}
```
- [ ] Run the full frontend type-check and expect **clean** (whole repo):
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | grep -E "prior_quota_years|allocation_year|project_numbers|by_year|SubTypeYearCol" | head
```
  Expected: no output.
- [ ] Commit:
```bash
git add frontend/components/admin-configuration-management.tsx
git commit -m "feat(fe): config editor project_numbers field + formData wiring"
```

### Task 6.13: Regenerate OpenAPI schema types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (generated)
- Test: generated file diff + frontend `tsc`

- [ ] Confirm the backend (with Phases 1–5 merged) is serving the new schema — `AllocationItem.allocation_config_id`, `shared_quota_sources`, flat `project_numbers`:
```bash
curl -s http://localhost:8000/api/v1/openapi.json | grep -o "allocation_config_id\|shared_quota_sources" | sort -u
```
  Expected: both strings present. If empty, Phases 1–5 are not up — stop and rebuild the backend first.
- [ ] Regenerate:
```bash
cd /home/howard/scholarship-system/.claude/worktrees/config-shared-quota-pools/frontend && npm run api:generate
```
- [ ] Verify the regenerated file dropped `allocation_year` from the allocation request component and added the new config fields:
```bash
grep -c "allocation_config_id" /home/howard/scholarship-system/.claude/worktrees/config-shared-quota-pools/frontend/lib/api/generated/schema.d.ts
```
  Expected: count ≥ 1.
- [ ] Run the full frontend type-check against the regenerated schema and expect **clean**:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx tsc --noEmit --skipLibCheck 2>&1 | tail -5
```
  Expected: no errors.
- [ ] Commit:
```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(fe): regenerate OpenAPI schema (allocation_config_id, shared_quota_sources)"
```

### Task 6.14: Run the full frontend test + lint sweep

**Files:**
- Test: `frontend/lib/api/modules/__tests__/manual-distribution.test.ts`, `frontend/components/__tests__/admin-configuration-management.test.tsx`

- [ ] Run the manual-distribution module tests and expect **PASS**:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest lib/api/modules/__tests__/manual-distribution.test.ts
```
  Expected: `16 passed`.
- [ ] Run the config-management component tests and expect **PASS** (it mocks `ScholarshipConfigurationFormData: {}` so the picker change must not break render):
```bash
docker compose -f docker-compose.dev.yml exec frontend npx jest components/__tests__/admin-configuration-management.test.tsx
```
  Expected: all passing. If a test asserted on the old `prior_quota_years` textarea, update that assertion to target the `共用前年度配額來源` picker label instead, then re-run.
- [ ] Run lint over the two changed FE files:
```bash
docker compose -f docker-compose.dev.yml exec frontend npx eslint components/admin/manual-distribution/ManualDistributionPanel.tsx components/admin-configuration-management.tsx lib/api/modules/manual-distribution.ts lib/api/types.ts
```
  Expected: no errors.
- [ ] Commit any test-assertion fixups:
```bash
git add frontend/components/__tests__/admin-configuration-management.test.tsx
git commit -m "test(fe): retarget config editor test to shared_quota_sources picker"
```

### Task 6.15: Seed — flatten `project_numbers`, add `shared_quota_sources`, give siblings own project codes

**Files:**
- Modify: `backend/app/db/seed_scholarship_configs.py:108-124` (phd_112 quotas → add project_numbers), `:145-161` (phd_113 → add project_numbers), `:214-224` (phd_114 prior_quota_years/project_numbers)
- Test: re-run seed against fresh DB (Task 6.18 covers the migration; this is a data-only seed verify)

- [ ] Give `phd_112` its own flat `project_numbers` so a borrow from it resolves a code (spec §11.4 — siblings currently have `project_numbers=NULL`). After the `phd_112` `quotas` block (`:108-124`), the dict ends at `:124` with the `nstc` college map. Insert a `project_numbers` key right after that `quotas` dict closes. Current code `:124-126`:
```python
                },
            },
            "amount": 40000,
```
  Replace with:
```python
                },
            },
            "project_numbers": {"nstc": "112R000001"},
            "amount": 40000,
```
  > Note: two `},\n            },` pairs exist (one per phd config). Apply this only inside the `phd_112` block (the one preceded by `"config_code": "phd_112"`). Verify by reading `:96-126` before editing.
- [ ] Give `phd_113` its own flat `project_numbers`. In the `phd_113` block, current code `:160-162`:
```python
                },
            },
            "amount": 40000,
```
  Replace with:
```python
                },
            },
            "project_numbers": {"nstc": "113R000001"},
            "amount": 40000,
```
  > Apply only inside the `phd_113` block (preceded by `"config_code": "phd_113"`).
- [ ] In `phd_114`, replace `prior_quota_years` + nested `project_numbers` with `shared_quota_sources` + flat `project_numbers`. Current code `:214-224`:
```python
            "prior_quota_years": {"nstc": [113, 112], "moe_1w": []},
            "project_numbers": {
                "nstc": {
                    "114": "114R000001",
                    "113": "113R000001",
                    "112": "112R000001",
                },
                "moe_1w": {
                    "114": "114E000001",
                },
            },
```
  Replace with:
```python
            "shared_quota_sources": [
                {"source_config_code": "phd_113", "sub_types": ["nstc"]},
                {"source_config_code": "phd_112", "sub_types": ["nstc"]},
            ],
            "project_numbers": {
                "nstc": "114R000001",
                "moe_1w": "114E000001",
            },
```
- [ ] Verify the file parses and contains no `prior_quota_years`:
```bash
docker compose -f docker-compose.dev.yml exec backend python -c "import ast; ast.parse(open('app/db/seed_scholarship_configs.py').read()); print('OK')"
docker compose -f docker-compose.dev.yml exec backend grep -c prior_quota_years app/db/seed_scholarship_configs.py
```
  Expected: `OK`, then `0` (after Task 6.16 removes the re-sync reference, this includes that line too — for now expect `1` from the re-sync block, fixed next).
- [ ] Commit:
```bash
git add backend/app/db/seed_scholarship_configs.py
git commit -m "feat(seed): flat project_numbers + shared_quota_sources, sibling project codes"
```

### Task 6.16: Seed — replace the `prior_quota_years` re-sync block with `shared_quota_sources`

**Files:**
- Modify: `backend/app/db/seed_scholarship_configs.py:288-296` (existing-config re-sync)
- Test: seed re-run idempotency

- [ ] Replace the re-sync branch. Current code `:288-296`:
```python
        else:
            # Update prior_quota_years on existing configs if provided in seed data
            if "prior_quota_years" in config_data and existing.prior_quota_years != config_data["prior_quota_years"]:
                existing.prior_quota_years = config_data["prior_quota_years"]
                logger.info(f"Updated prior_quota_years for: {config_data['config_code']}")
            # Update project_numbers on existing configs if provided in seed data
            if "project_numbers" in config_data and existing.project_numbers != config_data["project_numbers"]:
                existing.project_numbers = config_data["project_numbers"]
                logger.info(f"Updated project_numbers for: {config_data['config_code']}")
```
  Replace with:
```python
        else:
            # Update shared_quota_sources on existing configs if provided in seed data
            if (
                "shared_quota_sources" in config_data
                and existing.shared_quota_sources != config_data["shared_quota_sources"]
            ):
                existing.shared_quota_sources = config_data["shared_quota_sources"]
                logger.info(f"Updated shared_quota_sources for: {config_data['config_code']}")
            # Update project_numbers on existing configs if provided in seed data
            if "project_numbers" in config_data and existing.project_numbers != config_data["project_numbers"]:
                existing.project_numbers = config_data["project_numbers"]
                logger.info(f"Updated project_numbers for: {config_data['config_code']}")
```
- [ ] Verify no `prior_quota_years` remains and black passes:
```bash
docker compose -f docker-compose.dev.yml exec backend grep -c prior_quota_years app/db/seed_scholarship_configs.py
docker compose -f docker-compose.dev.yml exec backend python -m black --check --line-length=120 app/db/seed_scholarship_configs.py
```
  Expected: `0`, then `would not reformat` / passes.
- [ ] Commit:
```bash
git add backend/app/db/seed_scholarship_configs.py
git commit -m "feat(seed): re-sync shared_quota_sources instead of prior_quota_years"
```

### Task 6.17: Seed distribution test data — `allocation_year` → `allocation_config_id`

**Files:**
- Modify: `backend/scripts/seed_distribution_test_data.py:155-162`
- Test: re-run the seed script

- [ ] Replace the `CollegeRankingItem` construction. Current code `:155-162`:
```python
                item = CollegeRankingItem(
                    ranking_id=ranking.id,
                    application_id=app.id,
                    rank_position=idx,
                    status="ranked",
                    allocated_sub_type=None,
                    allocation_year=None,
                )
```
  Replace with:
```python
                item = CollegeRankingItem(
                    ranking_id=ranking.id,
                    application_id=app.id,
                    rank_position=idx,
                    status="ranked",
                    allocated_sub_type=None,
                    allocation_config_id=None,
                )
```
- [ ] Parse-check and black:
```bash
docker compose -f docker-compose.dev.yml exec backend python -c "import ast; ast.parse(open('scripts/seed_distribution_test_data.py').read()); print('OK')"
docker compose -f docker-compose.dev.yml exec backend python -m black --check --line-length=120 scripts/seed_distribution_test_data.py
```
  Expected: `OK`, black passes.
- [ ] Commit:
```bash
git add backend/scripts/seed_distribution_test_data.py
git commit -m "feat(seed): distribution test data uses allocation_config_id"
```

### Task 6.18: Verify seed runs end-to-end on a fresh DB

**Files:**
- Test: `backend/app/db/seed_scholarship_configs.py`, `backend/scripts/seed_distribution_test_data.py` (runtime verify)

- [ ] Rebuild the DB (applies both shared-quota migrations — MIGRATION 1 then MIGRATION 2 — then seeds):
```bash
/home/howard/scholarship-system/.claude/worktrees/config-shared-quota-pools/scripts/reset_database.sh
```
  Expected: completes without error; logs show `Created configuration: phd_112/113/114`.
- [ ] Confirm the seeded configs carry flat `project_numbers` and `shared_quota_sources` (and no `prior_quota_years` column exists post-drop):
```bash
docker compose -f docker-compose.dev.yml exec backend python -c "
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.scholarship import ScholarshipConfiguration as C
async def m():
    async with AsyncSessionLocal() as db:
        for code in ('phd_112','phd_113','phd_114'):
            c=(await db.execute(select(C).where(C.config_code==code))).scalar_one()
            print(code, c.project_numbers, getattr(c,'shared_quota_sources',None))
asyncio.run(m())
"
```
  Expected: `phd_112 {'nstc': '112R000001'} None`, `phd_113 {'nstc': '113R000001'} None`, `phd_114 {'nstc': '114R000001', 'moe_1w': '114E000001'} [{'source_config_code': 'phd_113', ...}, {'source_config_code': 'phd_112', ...}]`.
- [ ] Run the distribution-test seed and confirm it inserts ranking items with `allocation_config_id IS NULL`:
```bash
docker compose -f docker-compose.dev.yml exec backend python scripts/seed_distribution_test_data.py
```
  Expected: `Seeded: 3 applications, 1 ranking with 3 items` and no `allocation_year` AttributeError.
- [ ] No code change in this task. If anything fails, fix the offending seed file and re-commit under its task number; otherwise nothing to commit.

### Task 6.19: Checklist — rewrite §13 backend test fixtures for `allocation_config_id` / `shared_quota_sources` / `by_config`

> These tests exercise services rewritten in Phases 3–5; the fixtures and assertions must move off the dropped columns or the suites fail to import/collect. Each item is a concrete fixture edit verified by running that one file in the dev container. Run each with:
> `docker compose -f docker-compose.dev.yml exec backend pytest app/tests/<file> -p no:cacheprovider -q` (or `tests/<file>` for the host-path one).

- [ ] **`app/tests/test_distribution_state_endpoint.py`** — fixture `config` (`:106-110`) uses year-keyed `quotas` + `prior_quota_years`. Change `quotas` to the per-college matrix shape `{"nstc": {"E": 8, "C": 2}, "moe_1w": {"E": 5}}`, delete the `prior_quota_years=...` line, and add `shared_quota_sources=[{"source_config_code": "<prior-config-code>", "sub_types": ["nstc"]}]` plus a seeded prior config row for that code. Rewrite the two `available_quotas` assertions (`:278-289`, `:363-367`) to key on `(q["sub_type"], q["config_id"])` instead of `(q["sub_type"], q["allocation_year"])`, and assert the renewal-subtracted `remaining` (§17.1: renewals now reduce remaining). Expected after rewrite: file collects and passes.

- [ ] **`app/tests/test_challenge_release_distribution.py`** — fixture config (`:169`) sets `prior_quota_years={"nstc":[113], "moe_1w":[]}`; replace with `shared_quota_sources=[{"source_config_code":"phd_113","sub_types":["nstc"]}]` and seed a `phd_113`-equivalent config. The two assertions reading `rank9_item.allocation_year == RENEWAL_YEAR` (`:331`, `:338`) must become `rank9_item.allocation_config_id == <prior_config.id>` (the freed renewal's consumed config). Update the docstring (`:24`) wording from `allocation_year = 113` to `allocation_config_id = <prior config>`.

- [ ] **`app/tests/test_renewal_end_to_end.py`** — fixture config (`:208`) `prior_quota_years={"nstc":[113],"moe_1w":[]}` → `shared_quota_sources=[{"source_config_code":"phd_113","sub_types":["nstc"]}]` + seeded prior config. The promotion assertions `item.allocation_year == CURRENT_ACADEMIC_YEAR` (`:447`) and `item.allocation_year == RENEWAL_YEAR` (`:469`) become `item.allocation_config_id == <own_config.id>` and `item.allocation_config_id == <prior_config.id>` respectively. Update docstring (`:26`) `allocation_year=113` → `allocation_config_id=<prior config>`.

- [ ] **`app/tests/test_restore_allocation_service.py`** — the `CollegeRankingItem(... allocation_year=114)` fixture (`:100`) → `allocation_config_id=<config.id>` (the config the item consumes; build/seed that config in the fixture). The assertion `allocated_item.allocation_year == 114` (`:209`) → `allocated_item.allocation_config_id == <config.id>`. Update docstring (`:10`) `allocation_year` → `allocation_config_id`.

- [ ] **`app/tests/test_roster_distribution_reconcile_service.py`** — the item-builder helper passes `allocation_year=alloc_year` in three places (`:127`, `:143`, `:163`); change each to `allocation_config_id=alloc_config_id` (thread a `config_id` arg through the helper, defaulting to the seeded config, `None` for whole-period). The assertion `entry.allocation_year == 114` (`:223`) → `entry.allocation_config_id == <config.id>`. Update the whole-period docstring (`:336`) `sub_type=NULL / allocation_year=NULL` → `sub_type=NULL / allocation_config_id=NULL`.

- [ ] **`tests/test_auto_allocate_preview.py`** (host path) — every expected suggestion dict pins `"allocation_year": <int|None>` (`:175`, `:176`, `:248`, `:281`, `:312`, `:343`, `:375`, `:451`, `:453`, `:489`, `:569`). Change each key to `"allocation_config_id"` with the value being the **config id** the suggestion targets (own config id for current-year, the linked source's id for the `113` cases at `:248`, `None` for the no-allocation cases at `:343`/`:453`). Also re-key the in-fixture per-college tracker setup (the helper at `:119` `Optional[int] = None` parameter for `allocation_year`) to `allocation_config_id`, matching the `(allocation_config_id, sub_type, college)` tracker introduced in Phase 4 §6.4.

- [ ] **`app/tests/test_excel_export_service_pure_helpers.py`** and **`app/tests/test_excel_export_pure_helpers.py`** — any fixture/roster-item building an `allocation_year` value as a *quota key* must instead set `allocation_config_id` and keep `allocation_year` only as the frozen display snapshot (= consumed config's `academic_year`). Audit the `allocation_year` reads in these files and `app/tests/test_excel_export_service_rows.py`; where the export reads the display year, leave the assertion (the snapshot is preserved) — only update any place that previously derived the year from a now-dropped column. Run all three excel test files; expected: pass with the display-year column intact.

- [ ] **Final gate** — after all rewrites, run the §13 set together plus lint:
```bash
docker compose -f docker-compose.dev.yml exec backend pytest app/tests/test_distribution_state_endpoint.py app/tests/test_challenge_release_distribution.py app/tests/test_renewal_end_to_end.py app/tests/test_restore_allocation_service.py app/tests/test_roster_distribution_reconcile_service.py app/tests/test_excel_export_service_pure_helpers.py app/tests/test_excel_export_pure_helpers.py -p no:cacheprovider -q
docker compose -f docker-compose.dev.yml exec backend python -m pytest tests/test_auto_allocate_preview.py -p no:cacheprovider -q
docker compose -f docker-compose.dev.yml exec backend bash -lc "python -m black --check --line-length=120 app/tests tests/test_auto_allocate_preview.py && flake8 app/tests --select=B904,B014 --max-line-length=120"
```
  Expected: all green; black + flake8 clean.
- [ ] Commit:
```bash
git add backend/app/tests backend/tests/test_auto_allocate_preview.py
git commit -m "test(backend): rewrite §13 fixtures for allocation_config_id + shared_quota_sources"
```
