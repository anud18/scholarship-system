# Roster ↔ Distribution Reconcile (補充人) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an admin open a generated payment roster, compare it against its slice of the distribution, and selectively add the allocated students missing from the roster (補充人) and/or remove items no longer allocated.

**Architecture:** Two new sync `RosterService` methods (`get_distribution_diff_for_roster`, `reconcile_roster`) re-derive the allowed add/remove sets server-side (never trusting the client) by mirroring `generate_rosters_from_distribution`'s grouping, reuse `_create_roster_item` + `_validate_student_eligibility` to build added items, recompute totals via a new `_recompute_roster_totals_sync` helper, set `excel_stale=True`, and audit each change. Two endpoints (`GET /{roster_id}/distribution-diff`, `POST /{roster_id}/reconcile`) follow the existing sync-endpoint convention. The frontend adds a 「比對分發名單」section to `RosterDetailDialog` with checkbox add/remove + a confirm sub-dialog.

**Tech Stack:** FastAPI + SQLAlchemy (sync `Session`), Pydantic v2, pytest (`db_sync`), Next.js + React + openapi-fetch, jest.

**Reconcile is presentation-layer only:** it edits `payment_roster_items` + roster totals. It NEVER touches `Application.quota_allocation_status` or quota counters. Distribution already consumed quota; the roster is downstream.

**Spec:** `docs/superpowers/specs/2026-06-06-roster-distribution-reconcile-design.md`

---

## File Structure

**Backend (modify):**
- `backend/app/schemas/payment_roster.py` — add `DistributionDiffEntry`, `DistributionDiff`, `ReconcileRequest`, `ReconcileResultEntry`, `ReconcileResult` at end of file (after L345).
- `backend/app/services/roster_service.py` — add `_recompute_roster_totals_sync`, `_resolve_distribution_for_roster`, `get_distribution_diff_for_roster`, `_verify_and_create_item`, `reconcile_roster`. Add `DistributionDiffEntry` to the existing `from app.schemas.payment_roster import (...)` line.
- `backend/app/api/v1/endpoints/payment_rosters.py` — add `GET /{roster_id}/distribution-diff` + `POST /{roster_id}/reconcile`; add new schema names to the `from app.schemas.payment_roster import (...)` block; add `"excel_stale": roster.excel_stale` to the cycle-status period entry dicts.

**Backend (create):**
- `backend/app/tests/test_roster_distribution_reconcile_service.py` — sync unit-lane tests for diff + reconcile.

**Frontend (modify):**
- `frontend/lib/api/modules/payment-rosters.ts` — add `DistributionDiff`/`DistributionDiffEntry` interfaces + `getDistributionDiff` + `reconcileRoster` methods.
- `frontend/lib/api/modules/__tests__/payment-rosters.test.ts` — tests for the two new methods.
- `frontend/lib/api/generated/schema.d.ts` — regenerated (Task 6).
- `frontend/components/roster/RosterListTable.tsx` — add `excel_stale?: boolean` to its `Period` interface.
- `frontend/components/roster/RosterDetailDialog.tsx` — add the 「比對分發名單」section + reconcile confirm sub-dialog.

---

## Task 1: Backend schemas

**Files:**
- Modify: `backend/app/schemas/payment_roster.py` (append after L345)

- [ ] **Step 1: Add the new schema classes**

Append to the END of `backend/app/schemas/payment_roster.py` (imports `BaseModel, ConfigDict, Field`, `datetime`, `Decimal`, `Any, Dict, List, Optional` already present at L6-11):

```python


class DistributionDiffEntry(BaseModel):
    """One row in a roster↔distribution diff. Used for both add and remove sides."""

    application_id: int
    item_id: Optional[int] = None  # set only for to_remove rows (the PaymentRosterItem id)
    student_id: Optional[str] = None  # 學號 (std_stdcode), display only
    student_name: str
    department_name: Optional[str] = None
    college_name: Optional[str] = None
    allocation_year: Optional[int] = None
    allocated_sub_type: Optional[str] = None
    application_identity: Optional[str] = None
    scholarship_amount: float


class DistributionDiff(BaseModel):
    """Response for GET /payment-rosters/{roster_id}/distribution-diff."""

    roster_id: int
    roster_code: str
    status: str
    allocation_year: Optional[int] = None
    sub_type: Optional[str] = None
    to_add: List[DistributionDiffEntry]  # allocated in distribution, missing from roster
    to_remove: List[DistributionDiffEntry]  # in roster, no longer allocated


class ReconcileRequest(BaseModel):
    """Body for POST /payment-rosters/{roster_id}/reconcile."""

    add_application_ids: List[int] = Field(default_factory=list)
    remove_item_ids: List[int] = Field(default_factory=list)
    reason: Optional[str] = Field(None, max_length=500)


class ReconcileResultEntry(BaseModel):
    application_id: Optional[int] = None
    item_id: Optional[int] = None
    is_included: Optional[bool] = None
    exclusion_reason: Optional[str] = None


class ReconcileResult(BaseModel):
    """Response for POST /payment-rosters/{roster_id}/reconcile."""

    added: List[ReconcileResultEntry]
    removed: List[ReconcileResultEntry]
    qualified_count: int
    total_applications: int
    total_amount: float
    excel_stale: bool
```

- [ ] **Step 2: Verify it imports**

Run: `cd backend && python -c "from app.schemas.payment_roster import DistributionDiff, DistributionDiffEntry, ReconcileRequest, ReconcileResult, ReconcileResultEntry; print('ok')"`
Expected: `ok` (use the dev container / an env with `DATABASE_URL`, `SECRET_KEY`, `MINIO_*` set — see memory `backend_local_pytest_env`; or run inside `docker compose -f docker-compose.dev.yml exec backend python -c "..."`).

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/payment_roster.py
git commit -m "feat(roster): add distribution-diff and reconcile schemas"
```

---

## Task 2: Backend service — diff computation + totals helper

**Files:**
- Modify: `backend/app/services/roster_service.py`
- Test: `backend/app/tests/test_roster_distribution_reconcile_service.py` (create)

Context: `RosterService` is SYNC (`self.db: Session`). `and_`, `or_`, `func`, `case as sa_case`, `joinedload`, `Application`, `ScholarshipConfiguration`, `PaymentRoster`, `PaymentRosterItem`, `RosterStatus`, `StudentVerificationStatus`, `AuditLog` are already imported at module top (L6-34). `CollegeRanking`/`CollegeRankingItem` are NOT — import them locally inside each method (pattern at L823). `RosterService.__init__` already sets `self.student_verification_service`.

- [ ] **Step 1: Write the failing test (diff)**

Create `backend/app/tests/test_roster_distribution_reconcile_service.py`. This file is plain sync `def` with NO `pytestmark` → runs in the fast UNIT CI lane. Fixtures mirror `test_roster_item_removal_service.py` + `test_restore_allocation_service.py`.

```python
"""Pin: get_distribution_diff_for_roster computes the allocated-but-missing
(to_add) and in-roster-but-unallocated (to_remove) sets by mirroring
generate_rosters_from_distribution grouping; reconcile_roster applies a
validated, server-re-derived selection, recomputes totals, sets excel_stale,
and audits — on COMPLETED and LOCKED rosters."""

from decimal import Decimal

import pytest

from app.core.exceptions import RosterLockedError
from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType
from app.services.roster_service import RosterService


def _admin(db_sync, nycu_id="reconcile_admin"):
    u = User(
        nycu_id=nycu_id,
        email=f"{nycu_id}@nycu.edu.tw",
        name="Reconcile Admin",
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


def _scholarship(db_sync, code="reconcile_sch"):
    s = ScholarshipType(code=code, name="Reconcile Scholarship", description="x")
    db_sync.add(s)
    db_sync.flush()
    return s


def _config(db_sync, scholarship, *, academic_year=114):
    c = ScholarshipConfiguration(
        scholarship_type_id=scholarship.id,
        config_code=f"RC-{academic_year}-1",
        config_name="Reconcile Config",
        academic_year=academic_year,
        semester="first",
        amount=Decimal("50000"),
        has_quota_limit=False,
    )
    db_sync.add(c)
    db_sync.flush()
    return c


def _application(db_sync, user, scholarship, config, *, app_id, std_code, sub_type="nstc"):
    a = Application(
        user_id=user.id,
        app_id=app_id,
        scholarship_type_id=scholarship.id,
        scholarship_configuration_id=config.id,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[],
        sub_scholarship_type=sub_type,
        student_data={
            "std_stdcode": std_code,
            "std_pid": f"A{std_code}",
            "std_cname": f"學生{std_code}",
            "trm_depname": "教育博",
            "trm_academyname": "人社院",
        },
        submitted_form_data={
            "fields": {"postal_account": {"value": "0001234567"}}
        },
        amount=Decimal("50000"),
    )
    db_sync.add(a)
    db_sync.flush()
    return a


def _ranking(db_sync, scholarship, *, sub_type="nstc"):
    r = CollegeRanking(
        scholarship_type_id=scholarship.id,
        sub_type_code=sub_type,
        academic_year=114,
        semester="first",
        ranking_name="R",
        is_finalized=True,
        ranking_status="finalized",
        distribution_executed=True,
    )
    db_sync.add(r)
    db_sync.flush()
    return r


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


@pytest.fixture
def diff_scenario(db_sync):
    """One nstc-114 roster holding student A; distribution has A (already in
    roster) + B (allocated, missing → to_add). A third item C sits in the
    roster but is NOT allocated → to_remove."""
    admin = _admin(db_sync)
    sch = _scholarship(db_sync)
    config = _config(db_sync, sch)
    ua = _student(db_sync, "rc_a")
    ub = _student(db_sync, "rc_b")
    uc = _student(db_sync, "rc_c")
    app_a = _application(db_sync, ua, sch, config, app_id="APP-RC-A", std_code="111A")
    app_b = _application(db_sync, ub, sch, config, app_id="APP-RC-B", std_code="111B")
    app_c = _application(db_sync, uc, sch, config, app_id="APP-RC-C", std_code="111C")
    ranking = _ranking(db_sync, sch)
    _ranking_item(db_sync, ranking, app_a, rank=1)  # allocated, in roster
    _ranking_item(db_sync, ranking, app_b, rank=2)  # allocated, missing → to_add
    _ranking_item(db_sync, ranking, app_c, rank=3, allocated=False)  # not allocated
    roster = _roster(db_sync, config, admin)
    _roster_item(db_sync, roster, app_a)  # matches distribution
    item_c = _roster_item(db_sync, roster, app_c)  # orphan → to_remove
    db_sync.commit()
    return {
        "admin": admin,
        "config": config,
        "roster": roster,
        "app_a": app_a.id,
        "app_b": app_b.id,
        "app_c": app_c.id,
        "item_c": item_c.id,
    }


def test_distribution_diff_lists_missing_and_orphan(db_sync, diff_scenario):
    svc = RosterService(db_sync)
    diff = svc.get_distribution_diff_for_roster(diff_scenario["roster"].id)

    add_ids = {e.application_id for e in diff["to_add"]}
    remove_item_ids = {e.item_id for e in diff["to_remove"]}

    assert add_ids == {diff_scenario["app_b"]}
    assert remove_item_ids == {diff_scenario["item_c"]}
    # to_add carries display fields from student_data
    entry = next(e for e in diff["to_add"] if e.application_id == diff_scenario["app_b"])
    assert entry.student_id == "111B"
    assert entry.department_name == "教育博"
    assert entry.allocated_sub_type == "nstc"
    assert entry.allocation_year == 114
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest app/tests/test_roster_distribution_reconcile_service.py::test_distribution_diff_lists_missing_and_orphan -p no:cacheprovider -v`
Expected: FAIL with `AttributeError: 'RosterService' object has no attribute 'get_distribution_diff_for_roster'`.

- [ ] **Step 3: Add the totals helper + diff method**

In `backend/app/services/roster_service.py`, first extend the schema import (find `from app.schemas.payment_roster import RevokedSuspendedEntry` at L30 and replace):

```python
from app.schemas.payment_roster import DistributionDiffEntry, RevokedSuspendedEntry
```

Then add these three methods inside `class RosterService` (place them just before `remove_item_from_locked_roster` at L1801, after `get_revoked_suspended_for_roster`):

```python
    def _recompute_roster_totals_sync(self, roster_id: int) -> tuple:
        """Recompute + persist total_applications / qualified_count /
        disqualified_count / total_amount for a roster from its items.
        Returns (qualified, total_count, total_amount). SYNC."""
        total_count, qualified, total_amount = (
            self.db.query(
                func.count(PaymentRosterItem.id),
                func.coalesce(
                    func.sum(sa_case((PaymentRosterItem.is_included.is_(True), 1), else_=0)),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        sa_case(
                            (PaymentRosterItem.is_included.is_(True), PaymentRosterItem.scholarship_amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .filter(PaymentRosterItem.roster_id == roster_id)
            .one()
        )
        roster = self.db.get(PaymentRoster, roster_id)
        roster.total_applications = total_count
        roster.qualified_count = qualified
        roster.disqualified_count = total_count - qualified
        roster.total_amount = total_amount
        return qualified, total_count, total_amount

    def _resolve_distribution_for_roster(self, roster: PaymentRoster) -> dict:
        """Return {application_id: CollegeRankingItem} for allocated ranking
        items that belong in THIS roster's (allocation_year, sub_type) group,
        across all finalized + distribution_executed rankings for the roster's
        scholarship_type / academic_year / semester. Mirrors
        generate_rosters_from_distribution grouping exactly."""
        from app.models.college_review import CollegeRanking, CollegeRankingItem

        config = self.db.get(ScholarshipConfiguration, roster.scholarship_configuration_id)
        if config is None:
            raise ValueError(f"Scholarship configuration {roster.scholarship_configuration_id} not found")

        semester = config.semester.value if config.semester else None
        if semester in (None, "annual", "yearly", ""):
            sem_filter = or_(
                CollegeRanking.semester.is_(None),
                CollegeRanking.semester == "annual",
                CollegeRanking.semester == "yearly",
            )
        else:
            sem_filter = CollegeRanking.semester == semester

        rankings = (
            self.db.query(CollegeRanking)
            .filter(
                and_(
                    CollegeRanking.scholarship_type_id == config.scholarship_type_id,
                    CollegeRanking.academic_year == config.academic_year,
                    sem_filter,
                    CollegeRanking.is_finalized.is_(True),
                    CollegeRanking.distribution_executed.is_(True),
                )
            )
            .all()
        )
        ranking_ids = [r.id for r in rankings]
        if not ranking_ids:
            return {}

        allocated = (
            self.db.query(CollegeRankingItem)
            .options(joinedload(CollegeRankingItem.application))
            .filter(
                and_(
                    CollegeRankingItem.ranking_id.in_(ranking_ids),
                    CollegeRankingItem.is_allocated.is_(True),
                )
            )
            .all()
        )

        roster_year = roster.allocation_year or config.academic_year
        roster_sub = roster.sub_type or "general"

        result: dict = {}
        for item in allocated:
            item_year = item.allocation_year or config.academic_year
            item_sub = item.allocated_sub_type or "general"
            if item_year == roster_year and item_sub == roster_sub:
                result[item.application_id] = item
        return result

    def get_distribution_diff_for_roster(self, roster_id: int) -> dict:
        """Compute the diff between this roster and its slice of the
        distribution. Returns a dict with to_add (allocated-but-missing) and
        to_remove (in-roster-but-unallocated) lists of DistributionDiffEntry."""
        from app.models.application import ApplicationStatus

        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")

        config = self.db.get(ScholarshipConfiguration, roster.scholarship_configuration_id)
        allocated_map = self._resolve_distribution_for_roster(roster)

        existing_items = (
            self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id).all()
        )
        existing_app_ids = {it.application_id for it in existing_items}

        to_add = []
        for app_id, ranking_item in allocated_map.items():
            if app_id in existing_app_ids:
                continue
            application = ranking_item.application
            if application is None or application.status != ApplicationStatus.approved:
                continue
            sd = application.student_data or {}
            to_add.append(
                DistributionDiffEntry(
                    application_id=app_id,
                    item_id=None,
                    student_id=sd.get("std_stdcode", ""),
                    student_name=sd.get("std_cname", ""),
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=ranking_item.allocation_year,
                    allocated_sub_type=ranking_item.allocated_sub_type,
                    application_identity=None,
                    scholarship_amount=float(
                        application.amount or (config.amount if config else 0) or 0
                    ),
                )
            )

        to_remove = []
        for item in existing_items:
            if item.application_id in allocated_map:
                continue
            sd = {}
            if item.application_id:
                app = self.db.get(Application, item.application_id)
                sd = (app.student_data or {}) if app else {}
            to_remove.append(
                DistributionDiffEntry(
                    application_id=item.application_id,
                    item_id=item.id,
                    student_id=sd.get("std_stdcode", item.student_id_number),
                    student_name=item.student_name,
                    department_name=sd.get("trm_depname"),
                    college_name=sd.get("trm_academyname"),
                    allocation_year=item.allocation_year,
                    allocated_sub_type=item.allocated_sub_type,
                    application_identity=item.application_identity,
                    scholarship_amount=float(item.scholarship_amount or 0),
                )
            )

        return {
            "roster_id": roster.id,
            "roster_code": roster.roster_code,
            "status": roster.status.value,
            "allocation_year": roster.allocation_year,
            "sub_type": roster.sub_type,
            "to_add": to_add,
            "to_remove": to_remove,
        }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest app/tests/test_roster_distribution_reconcile_service.py::test_distribution_diff_lists_missing_and_orphan -p no:cacheprovider -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git commit -m "feat(roster): compute distribution diff for a generated roster"
```

---

## Task 3: Backend service — reconcile apply

**Files:**
- Modify: `backend/app/services/roster_service.py`
- Test: `backend/app/tests/test_roster_distribution_reconcile_service.py`

- [ ] **Step 1: Write the failing tests (reconcile add + remove + validation + state)**

Append to `backend/app/tests/test_roster_distribution_reconcile_service.py`:

```python
def test_reconcile_adds_missing_and_removes_orphan(db_sync, diff_scenario):
    svc = RosterService(db_sync)
    roster_id = diff_scenario["roster"].id
    result = svc.reconcile_roster(
        roster_id=roster_id,
        add_application_ids=[diff_scenario["app_b"]],
        remove_item_ids=[diff_scenario["item_c"]],
        admin_user_id=diff_scenario["admin"].id,
        reason="sync",
    )

    assert len(result["added"]) == 1
    assert result["added"][0]["application_id"] == diff_scenario["app_b"]
    assert result["added"][0]["item_id"] is not None
    assert len(result["removed"]) == 1
    assert result["removed"][0]["item_id"] == diff_scenario["item_c"]
    assert result["excel_stale"] is True

    db_sync.refresh(diff_scenario["roster"])
    # roster now holds app_a (kept) + app_b (added); app_c removed → 2 items
    assert diff_scenario["roster"].total_applications == 2
    assert db_sync.get(PaymentRosterItem, diff_scenario["item_c"]) is None
    # added item is included (student_data has bank account, verification disabled)
    assert result["added"][0]["is_included"] is True


def test_reconcile_rejects_application_not_in_diff(db_sync, diff_scenario):
    svc = RosterService(db_sync)
    with pytest.raises(ValueError, match="not addable"):
        svc.reconcile_roster(
            roster_id=diff_scenario["roster"].id,
            add_application_ids=[diff_scenario["app_a"]],  # already in roster → not addable
            remove_item_ids=[],
            admin_user_id=diff_scenario["admin"].id,
            reason=None,
        )


def test_reconcile_rejects_item_not_orphan(db_sync, diff_scenario):
    # app_a's roster item is still allocated → not removable via reconcile
    svc = RosterService(db_sync)
    a_item = (
        db_sync.query(PaymentRosterItem)
        .filter(
            PaymentRosterItem.roster_id == diff_scenario["roster"].id,
            PaymentRosterItem.application_id == diff_scenario["app_a"],
        )
        .one()
    )
    with pytest.raises(ValueError, match="not removable"):
        svc.reconcile_roster(
            roster_id=diff_scenario["roster"].id,
            add_application_ids=[],
            remove_item_ids=[a_item.id],
            admin_user_id=diff_scenario["admin"].id,
            reason=None,
        )


def test_reconcile_rejects_draft_roster(db_sync, diff_scenario):
    roster = diff_scenario["roster"]
    roster.status = RosterStatus.DRAFT
    db_sync.commit()
    svc = RosterService(db_sync)
    with pytest.raises(RosterLockedError, match="COMPLETED or LOCKED"):
        svc.reconcile_roster(
            roster_id=roster.id,
            add_application_ids=[diff_scenario["app_b"]],
            remove_item_ids=[],
            admin_user_id=diff_scenario["admin"].id,
            reason=None,
        )


def test_reconcile_works_on_completed_roster(db_sync, diff_scenario):
    roster = diff_scenario["roster"]
    roster.status = RosterStatus.COMPLETED
    db_sync.commit()
    svc = RosterService(db_sync)
    result = svc.reconcile_roster(
        roster_id=roster.id,
        add_application_ids=[diff_scenario["app_b"]],
        remove_item_ids=[],
        admin_user_id=diff_scenario["admin"].id,
        reason=None,
    )
    assert len(result["added"]) == 1
    db_sync.refresh(roster)
    assert roster.status == RosterStatus.COMPLETED  # status unchanged
    assert roster.excel_stale is True


def test_reconcile_writes_audit_logs(db_sync, diff_scenario):
    svc = RosterService(db_sync)
    svc.reconcile_roster(
        roster_id=diff_scenario["roster"].id,
        add_application_ids=[diff_scenario["app_b"]],
        remove_item_ids=[diff_scenario["item_c"]],
        admin_user_id=diff_scenario["admin"].id,
        reason="sync",
    )
    added_log = (
        db_sync.query(AuditLog)
        .filter(AuditLog.action == "roster.item_added_from_distribution")
        .one()
    )
    assert added_log.new_values["application_id"] == diff_scenario["app_b"]
    summary = db_sync.query(AuditLog).filter(AuditLog.action == "roster.reconciled").one()
    assert summary.new_values["added"] == 1
    assert summary.new_values["removed"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest app/tests/test_roster_distribution_reconcile_service.py -p no:cacheprovider -v -k reconcile`
Expected: FAIL with `AttributeError: 'RosterService' object has no attribute 'reconcile_roster'`.

- [ ] **Step 3: Add `_verify_and_create_item` + `reconcile_roster`**

Add inside `class RosterService`, right after `get_distribution_diff_for_roster` (from Task 2):

```python
    def _verify_and_create_item(self, roster: PaymentRoster, application: Application) -> PaymentRosterItem:
        """Verify (if enabled) + validate eligibility + build a PaymentRosterItem.
        Mirrors the generation per-application block (L1678-1698). self.db.add()s
        the item (does NOT flush/commit) and returns it."""
        verification_result = None
        verification_status = StudentVerificationStatus.VERIFIED
        fresh_student_data = None

        if roster.student_verification_enabled:
            sd = application.student_data or {}
            verification_result = self.student_verification_service.verify_student(
                sd.get("std_stdcode"), sd.get("std_cname")
            )
            verification_status = verification_result.get("status", StudentVerificationStatus.VERIFIED)
            if verification_status != StudentVerificationStatus.API_ERROR:
                fresh_student_data = verification_result.get("student_info", {})

        eligibility_result = self._validate_student_eligibility(
            application, roster.academic_year, roster.period_label, fresh_api_data=fresh_student_data
        )
        return self._create_roster_item(
            roster, application, verification_result, verification_status, eligibility_result
        )

    def reconcile_roster(
        self,
        roster_id: int,
        add_application_ids: List[int],
        remove_item_ids: List[int],
        admin_user_id: int,
        reason: Optional[str] = None,
    ) -> dict:
        """Apply a selective add/remove against a generated roster, validated
        against the server-re-derived distribution diff. Works on COMPLETED and
        LOCKED rosters. Recomputes totals, sets excel_stale=True, audits each
        change, commits. NEVER touches quota_allocation_status."""
        from app.models.application import ApplicationStatus

        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")
        if roster.status not in (RosterStatus.COMPLETED, RosterStatus.LOCKED):
            raise RosterLockedError(
                f"Roster {roster_id} must be COMPLETED or LOCKED to reconcile "
                f"(status={roster.status.value})"
            )

        add_ids = list(dict.fromkeys(add_application_ids or []))
        remove_ids = list(dict.fromkeys(remove_item_ids or []))

        # Re-derive allowed sets — never trust the client.
        allocated_map = self._resolve_distribution_for_roster(roster)
        existing_items = (
            self.db.query(PaymentRosterItem).filter(PaymentRosterItem.roster_id == roster_id).all()
        )
        existing_app_ids = {it.application_id for it in existing_items}
        items_by_id = {it.id: it for it in existing_items}

        allowed_add = {
            aid
            for aid, ri in allocated_map.items()
            if aid not in existing_app_ids
            and ri.application is not None
            and ri.application.status == ApplicationStatus.approved
        }
        allowed_remove = {it.id for it in existing_items if it.application_id not in allocated_map}

        bad_add = [a for a in add_ids if a not in allowed_add]
        if bad_add:
            raise ValueError(f"Applications {bad_add} are not addable from the current distribution diff")
        bad_remove = [r for r in remove_ids if r not in allowed_remove]
        if bad_remove:
            raise ValueError(f"Items {bad_remove} are not removable from the current distribution diff")

        added, removed = [], []

        for app_id in add_ids:
            application = self.db.get(Application, app_id)
            item = self._verify_and_create_item(roster, application)
            self.db.flush()
            added.append(
                {
                    "application_id": app_id,
                    "item_id": item.id,
                    "is_included": item.is_included,
                    "exclusion_reason": item.exclusion_reason,
                }
            )
            self.db.add(
                AuditLog.create_log(
                    user_id=admin_user_id,
                    action="roster.item_added_from_distribution",
                    resource_type="payment_roster",
                    resource_id=str(roster_id),
                    description=f"Added item {item.id} (application {app_id}) to roster from distribution",
                    new_values={
                        "item_id": item.id,
                        "application_id": app_id,
                        "is_included": item.is_included,
                        "reason": reason,
                    },
                )
            )

        for item_id in remove_ids:
            item = items_by_id[item_id]
            removed_app_id = item.application_id
            removed_amount = item.scholarship_amount
            self.db.delete(item)
            removed.append({"item_id": item_id, "application_id": removed_app_id})
            self.db.add(
                AuditLog.create_log(
                    user_id=admin_user_id,
                    action="roster.item_removed_after_lock",
                    resource_type="payment_roster",
                    resource_id=str(roster_id),
                    description=f"Removed item {item_id} (application {removed_app_id}) during reconcile",
                    new_values={
                        "item_id": item_id,
                        "application_id": removed_app_id,
                        "reason": reason,
                        "removed_amount": float(removed_amount) if removed_amount else 0,
                    },
                )
            )

        self.db.flush()
        qualified, total_count, total_amount = self._recompute_roster_totals_sync(roster_id)
        if added or removed:
            roster.excel_stale = True

        self.db.add(
            AuditLog.create_log(
                user_id=admin_user_id,
                action="roster.reconciled",
                resource_type="payment_roster",
                resource_id=str(roster_id),
                description=f"Reconciled roster: +{len(added)} / -{len(removed)}",
                new_values={"added": len(added), "removed": len(removed), "reason": reason},
            )
        )
        self.db.commit()

        return {
            "added": added,
            "removed": removed,
            "qualified_count": qualified,
            "total_applications": total_count,
            "total_amount": float(total_amount),
            "excel_stale": roster.excel_stale,
        }
```

- [ ] **Step 4: Run the full service test file**

Run: `cd backend && python -m pytest app/tests/test_roster_distribution_reconcile_service.py -p no:cacheprovider -v`
Expected: all tests PASS.

- [ ] **Step 5: Run lint gates (hard-gated in CI)**

```bash
cd backend && uvx --from "black==26.3.1" black --check --line-length=120 app/services/roster_service.py app/schemas/payment_roster.py app/tests/test_roster_distribution_reconcile_service.py
flake8 app/services/roster_service.py app/tests/test_roster_distribution_reconcile_service.py --select=B904,B014 --max-line-length=120
```
Expected: no output (clean). If black reports diffs, run without `--check` to autoformat, then re-commit.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/roster_service.py backend/app/tests/test_roster_distribution_reconcile_service.py
git commit -m "feat(roster): reconcile a roster against its distribution slice"
```

---

## Task 4: Backend endpoints

**Files:**
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py`
- Test: `backend/app/tests/test_roster_distribution_reconcile_api.py` (create)

- [ ] **Step 1: Write the failing API test**

Create `backend/app/tests/test_roster_distribution_reconcile_api.py`. This uses the async `db` + `client` fixtures (auto-routes to the integration CI lane). It mirrors `test_roster_lifecycle.py`'s async fixtures + auth override.

```python
"""API pin: GET /distribution-diff returns to_add/to_remove; POST /reconcile
applies a validated selection and returns ApiResponse with recomputed totals."""

from decimal import Decimal
from unittest.mock import Mock

import pytest
import pytest_asyncio
from httpx import AsyncClient

from app.models.application import Application, ApplicationStatus
from app.models.college_review import CollegeRanking, CollegeRankingItem
from app.models.payment_roster import (
    PaymentRoster,
    PaymentRosterItem,
    RosterCycle,
    RosterStatus,
    RosterTriggerType,
)
from app.models.scholarship import (
    ScholarshipConfiguration,
    ScholarshipType,
    SubTypeSelectionMode,
)
from app.models.user import User, UserRole, UserType


def _mock_admin() -> Mock:
    u = Mock(spec=User)
    u.id = 1
    u.role = UserRole.admin
    u.email = "admin_rc@nycu.edu.tw"
    u.name = "Admin RC"
    u.has_role.side_effect = lambda role: role == UserRole.admin
    u.is_admin.return_value = True
    return u


@pytest_asyncio.fixture
async def admin_api_client(db, client: AsyncClient):
    from app.core.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: _mock_admin()
    yield client
    app.dependency_overrides.pop(get_current_user, None)


@pytest_asyncio.fixture
async def api_scenario(db):
    admin = User(nycu_id="rc_api_admin", email="rc_api_admin@nycu.edu.tw", name="A",
                 role=UserRole.admin, user_type=UserType.employee)
    s_b = User(nycu_id="rc_api_b", email="rc_api_b@nycu.edu.tw", name="B",
               role=UserRole.student, user_type=UserType.student)
    db.add_all([admin, s_b])
    await db.flush()

    sch = ScholarshipType(code="rc_api_sch", name="RC API", description="x")
    db.add(sch)
    await db.flush()
    config = ScholarshipConfiguration(
        scholarship_type_id=sch.id, config_code="RC-API-114-1", config_name="C",
        academic_year=114, semester="first", amount=Decimal("50000"), has_quota_limit=False,
    )
    db.add(config)
    await db.flush()

    app_b = Application(
        user_id=s_b.id, app_id="APP-RC-API-B", scholarship_type_id=sch.id,
        scholarship_configuration_id=config.id, academic_year=114, semester="first",
        status=ApplicationStatus.approved, sub_type_selection_mode=SubTypeSelectionMode.single,
        scholarship_subtype_list=[], sub_scholarship_type="nstc",
        student_data={"std_stdcode": "222B", "std_pid": "A222B", "std_cname": "乙",
                      "trm_depname": "教博"},
        submitted_form_data={"fields": {"postal_account": {"value": "0009"}}},
        amount=Decimal("50000"),
    )
    db.add(app_b)
    await db.flush()

    ranking = CollegeRanking(
        scholarship_type_id=sch.id, sub_type_code="nstc", academic_year=114, semester="first",
        ranking_name="R", is_finalized=True, ranking_status="finalized", distribution_executed=True,
    )
    db.add(ranking)
    await db.flush()
    db.add(CollegeRankingItem(
        ranking_id=ranking.id, application_id=app_b.id, rank_position=1,
        is_allocated=True, allocated_sub_type="nstc", allocation_year=114, status="allocated",
    ))

    roster = PaymentRoster(
        roster_code="ROSTER-RC-API-1", scholarship_configuration_id=config.id, period_label="114",
        academic_year=114, roster_cycle=RosterCycle.YEARLY, sub_type="nstc", allocation_year=114,
        status=RosterStatus.LOCKED, trigger_type=RosterTriggerType.MANUAL, created_by=admin.id,
        student_verification_enabled=False,
    )
    db.add(roster)
    await db.flush()  # roster has NO item for app_b → app_b is to_add
    await db.commit()
    return {"roster_id": roster.id, "app_b": app_b.id}


@pytest.mark.asyncio
async def test_distribution_diff_endpoint(admin_api_client, api_scenario):
    resp = await admin_api_client.get(
        f"/api/v1/payment-rosters/{api_scenario['roster_id']}/distribution-diff"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    add_ids = [e["application_id"] for e in body["data"]["to_add"]]
    assert api_scenario["app_b"] in add_ids


@pytest.mark.asyncio
async def test_reconcile_endpoint_adds_member(admin_api_client, api_scenario):
    resp = await admin_api_client.post(
        f"/api/v1/payment-rosters/{api_scenario['roster_id']}/reconcile",
        json={"add_application_ids": [api_scenario["app_b"]], "remove_item_ids": [], "reason": "sync"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert len(body["data"]["added"]) == 1
    assert body["data"]["excel_stale"] is True
```

- [ ] **Step 2: Run to verify it fails**

Run the local sync command (env prefix from Task 3) on `app/tests/test_roster_distribution_reconcile_api.py`.
Expected: FAIL — `AttributeError: module 'app.api.v1.endpoints.payment_rosters' has no attribute 'get_distribution_diff'` (endpoints not added yet).

> **NOTE (environment correction):** The endpoints use `get_sync_db` (sync `Session`) and the reconcile endpoint wraps `with_lock_sync` (needs Redis). conftest's sync test engine is a SEPARATE in-memory DB from the async `db` fixture, and there is no Redis in the test/CI lane. So the API test does NOT use httpx/async `db`. Instead it **calls the endpoint functions directly** with the `db_sync` session and a `monkeypatch` that replaces `with_lock_sync` with a no-op contextmanager. The corrected test is provided by the controller at dispatch time. These tests are plain sync `def` (unit lane).

- [ ] **Step 3: Add the endpoints**

In `backend/app/api/v1/endpoints/payment_rosters.py`, extend the schema import block (find `from app.schemas.payment_roster import (` at L32-35 and replace with):

```python
from app.schemas.payment_roster import (
    DistributionDiff,
    ReconcileRequest,
    ReconcileResult,
    RemoveLockedItemRequest,
    RevokedSuspendedListResponse,
)
```

Then add these two endpoints at the END of the file (after `remove_locked_roster_item`, ~L2125):

```python
@router.get("/{roster_id}/distribution-diff")
def get_distribution_diff(
    roster_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Compare a generated roster against its slice of the distribution.
    Returns allocated-but-missing (to_add) and in-roster-but-unallocated
    (to_remove) lists for the admin to selectively reconcile."""
    _require_admin(current_user)
    svc = RosterService(db)
    try:
        result = svc.get_distribution_diff_for_roster(roster_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = DistributionDiff(**result).model_dump()
    return {"success": True, "message": "OK", "data": payload}


@router.post("/{roster_id}/reconcile")
def reconcile_roster_endpoint(
    roster_id: int,
    request: ReconcileRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Selectively add allocated students missing from the roster (補充人) and/or
    remove items no longer allocated. Works on COMPLETED and LOCKED rosters;
    sets excel_stale; audits each change. Presentation-layer only — does not
    touch quota."""
    _require_admin(current_user)
    lock_key = f"roster:reconcile:{roster_id}"
    try:
        with with_lock_sync(lock_key, ttl_seconds=300):
            svc = RosterService(db)
            result = svc.reconcile_roster(
                roster_id=roster_id,
                add_application_ids=request.add_application_ids,
                remove_item_ids=request.remove_item_ids,
                admin_user_id=current_user.id,
                reason=request.reason,
            )
    except LockBusy as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="造冊處理中，請稍候再試") from exc
    except (ValueError, RosterLockedError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = ReconcileResult(**result).model_dump()
    return {"success": True, "message": "已更新造冊名單", "data": payload}
```

- [ ] **Step 4: Run to verify it passes**

Run the local sync command (env prefix from Task 3) on `app/tests/test_roster_distribution_reconcile_api.py` with `--no-cov`.
Expected: PASS (4 tests: diff returns ApiResponse, diff requires admin → 403, reconcile adds member, reconcile maps service ValueError → 400). The `with_lock_sync` no-op monkeypatch means no Redis is required.

- [ ] **Step 5: Lint + commit**

```bash
cd backend && uvx --from "black==26.3.1" black --check --line-length=120 app/api/v1/endpoints/payment_rosters.py
flake8 app/api/v1/endpoints/payment_rosters.py --select=B904,B014 --max-line-length=120
git add backend/app/api/v1/endpoints/payment_rosters.py backend/app/tests/test_roster_distribution_reconcile_api.py
git commit -m "feat(roster): add distribution-diff and reconcile endpoints"
```

---

## Task 5: Surface `excel_stale` in cycle-status (so the stale banner can fire)

**Files:**
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py` (cycle-status period entry dicts)

Context: the cycle-status endpoint builds a period `entry` dict per roster but OMITS `excel_stale` (verified: monthly branch ~L945-957, plus the semi_yearly ~L1013 and yearly branches repeat the same dict). Because of this, `period.excel_stale` in the frontend is always `undefined` and the existing amber banner never shows. Add the field to every such entry dict.

- [ ] **Step 1: Find every period entry dict**

Run: `cd backend && grep -n '"roster_status": roster.status.value' app/api/v1/endpoints/payment_rosters.py`
Expected: 2-3 line numbers (one per cycle branch).

- [ ] **Step 2: Add `excel_stale` to each**

For EACH match, add a line directly after the `"roster_status": roster.status.value,` line:

```python
                            "excel_stale": roster.excel_stale,
```

(Match the surrounding indentation exactly — it differs per branch. The key sits alongside `roster_status`, `sub_type`, `allocation_year` in the same dict.)

- [ ] **Step 3: Verify no syntax break**

Run: `cd backend && python -c "import ast; ast.parse(open('app/api/v1/endpoints/payment_rosters.py').read()); print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/payment_rosters.py
git commit -m "fix(roster): include excel_stale in cycle-status period entries"
```

---

## Task 6: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (generated)

- [ ] **Step 1: Start the backend, regenerate**

```bash
docker compose -f docker-compose.dev.yml up -d backend
cd frontend && npm run api:generate
```
(Backend must answer on `localhost:8000`. Per project CLAUDE.md §8.)

- [ ] **Step 2: Confirm the new routes landed**

Run: `cd frontend && grep -c "distribution-diff\|/reconcile" lib/api/generated/schema.d.ts`
Expected: ≥ 2 (both paths present). If 0, the backend wasn't serving the new routes — restart it and re-run Step 1.

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(api): regenerate OpenAPI types for reconcile routes"
```

---

## Task 7: Frontend API module methods

**Files:**
- Modify: `frontend/lib/api/modules/payment-rosters.ts`
- Test: `frontend/lib/api/modules/__tests__/payment-rosters.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to `frontend/lib/api/modules/__tests__/payment-rosters.test.ts` (the file already mocks `typedClient.raw.{GET,POST}` and defines `_ok`):

```typescript
describe("getDistributionDiff", () => {
  it("calls GET with the roster_id path param", async () => {
    const api = createPaymentRostersApi();
    mockedRaw.GET.mockResolvedValue(_ok({ roster_id: 7, to_add: [], to_remove: [] }));

    const res = await api.getDistributionDiff(7);

    expect(mockedRaw.GET).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}/distribution-diff",
      { params: { path: { roster_id: 7 } } }
    );
    expect(res.success).toBe(true);
  });
});

describe("reconcileRoster", () => {
  it("calls POST with path + add/remove body", async () => {
    const api = createPaymentRostersApi();
    mockedRaw.POST.mockResolvedValue(_ok({ added: [], removed: [], excel_stale: true }));

    const res = await api.reconcileRoster(7, {
      add_application_ids: [11],
      remove_item_ids: [22],
      reason: "sync",
    });

    expect(mockedRaw.POST).toHaveBeenCalledWith(
      "/api/v1/payment-rosters/{roster_id}/reconcile",
      {
        params: { path: { roster_id: 7 } },
        body: { add_application_ids: [11], remove_item_ids: [22], reason: "sync" },
      }
    );
    expect(res.success).toBe(true);
  });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd frontend && npx jest lib/api/modules/__tests__/payment-rosters.test.ts -t "getDistributionDiff|reconcileRoster"`
Expected: FAIL — `api.getDistributionDiff is not a function`.

- [ ] **Step 3: Add the interfaces + methods**

In `frontend/lib/api/modules/payment-rosters.ts`, add these exported interfaces near `RevokedSuspendedList` (after L30, before `export function createPaymentRostersApi()`):

```typescript
export interface DistributionDiffEntry {
  application_id: number;
  item_id: number | null;
  student_id: string | null;
  student_name: string;
  department_name: string | null;
  college_name: string | null;
  allocation_year: number | null;
  allocated_sub_type: string | null;
  application_identity: string | null;
  scholarship_amount: number;
}

export interface DistributionDiff {
  roster_id: number;
  roster_code: string;
  status: string;
  allocation_year: number | null;
  sub_type: string | null;
  to_add: DistributionDiffEntry[];
  to_remove: DistributionDiffEntry[];
}

export interface ReconcileResult {
  added: { application_id: number | null; item_id: number | null; is_included: boolean | null; exclusion_reason: string | null }[];
  removed: { application_id: number | null; item_id: number | null }[];
  qualified_count: number;
  total_applications: number;
  total_amount: number;
  excel_stale: boolean;
}
```

Then add these two methods inside the object returned by `createPaymentRostersApi()` (mirror `getRevokedSuspended` / `excludeRosterItem`):

```typescript
    /**
     * 取得造冊與分發名單的差異 (補充/移除候選)
     * GET /api/v1/payment-rosters/{roster_id}/distribution-diff
     */
    getDistributionDiff: async (
      roster_id: number
    ): Promise<ApiResponse<DistributionDiff>> => {
      const response = await typedClient.raw.GET(
        '/api/v1/payment-rosters/{roster_id}/distribution-diff',
        { params: { path: { roster_id } } }
      );
      return toApiResponse(response) as ApiResponse<DistributionDiff>;
    },

    /**
     * 依分發名單補充/移除造冊明細
     * POST /api/v1/payment-rosters/{roster_id}/reconcile
     */
    reconcileRoster: async (
      roster_id: number,
      body: {
        add_application_ids: number[];
        remove_item_ids: number[];
        reason?: string;
      }
    ): Promise<ApiResponse<ReconcileResult>> => {
      const response = await typedClient.raw.POST(
        '/api/v1/payment-rosters/{roster_id}/reconcile',
        {
          params: { path: { roster_id } },
          body: {
            add_application_ids: body.add_application_ids,
            remove_item_ids: body.remove_item_ids,
            reason: body.reason ?? null,
          },
        }
      );
      return toApiResponse(response) as ApiResponse<ReconcileResult>;
    },
```

NOTE: this requires Task 6 (schema regen) to be done first, otherwise the literal paths are not in the generated `paths` union and TypeScript fails to compile. If you must implement before regen, use the `(typedClient.raw.GET as any)` / `(typedClient.raw.POST as any)` escape hatch with an `// eslint-disable-next-line @typescript-eslint/no-explicit-any` line exactly like `regenerateRoster` (L305-317), then switch back after regen.

- [ ] **Step 4: Run to verify they pass + typecheck**

Run: `cd frontend && npx jest lib/api/modules/__tests__/payment-rosters.test.ts -t "getDistributionDiff|reconcileRoster"`
Expected: PASS.
Run: `cd frontend && npx tsc --noEmit`
Expected: no errors for `payment-rosters.ts` (paths resolve after Task 6).

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/payment-rosters.ts frontend/lib/api/modules/__tests__/payment-rosters.test.ts
git commit -m "feat(roster): add getDistributionDiff and reconcileRoster api methods"
```

---

## Task 8: Add `excel_stale` to RosterListTable's Period type

**Files:**
- Modify: `frontend/components/roster/RosterListTable.tsx` (Period interface, L29-51)

Context: `RosterListTable`'s `Period` interface lacks `excel_stale`, so even after Task 5 sends it, the value is dropped before reaching `RosterDetailDialog` (whose Period already declares it at L60). Add it.

- [ ] **Step 1: Add the field**

In `frontend/components/roster/RosterListTable.tsx`, inside the `Period` interface (the block at L29-51, alongside `sub_type?`, `allocation_year?`), add:

```typescript
  excel_stale?: boolean;
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no new errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/components/roster/RosterListTable.tsx
git commit -m "fix(roster): carry excel_stale through RosterListTable Period"
```

---

## Task 9: RosterDetailDialog — 「比對分發名單」section

**Files:**
- Modify: `frontend/components/roster/RosterDetailDialog.tsx`

Context (verbatim layout facts): the dialog is a SINGLE vertical-scroll `<DialogContent className="max-w-5xl max-h-[90vh] overflow-y-auto">` (NOT top-level Tabs). The body is a stack of conditional `<div>` blocks: header → `{period.roster_status === "locked" && (<> stale-banner + RevokedSuspendedSection </>)}` (L408-438) → loading/per-college-Tabs/single-table list → summary+lock/unlock footer. Add the reconcile section as a new block, gated on `period.roster_status === "completed" || period.roster_status === "locked"`. Mirror `submitExclude` (L210-237) for the mutate→refresh→toast flow and the #66 sub-dialog (L538-623) for the confirm. `apiClient`, `toast`, `Loader2`, `Button`, `Table*`, `Checkbox`? — Checkbox is NOT imported; add it.

- [ ] **Step 1: Add imports + state**

In the imports block (top of `RosterDetailDialog.tsx`), add:

```typescript
import { Checkbox } from "@/components/ui/checkbox";
import { AlertTriangle, RefreshCw } from "lucide-react";
import type { DistributionDiff, DistributionDiffEntry } from "@/lib/api/modules/payment-rosters";
```

In the state-hooks region (near L97-122), add:

```typescript
  // 比對分發名單 (reconcile) state
  const [diff, setDiff] = useState<DistributionDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [selectedAddIds, setSelectedAddIds] = useState<Set<number>>(new Set());
  const [selectedRemoveItemIds, setSelectedRemoveItemIds] = useState<Set<number>>(new Set());
  const [reconcileConfirmOpen, setReconcileConfirmOpen] = useState(false);
  const [reconcileSubmitting, setReconcileSubmitting] = useState(false);

  const canReconcile =
    period.roster_status === "completed" || period.roster_status === "locked";
```

- [ ] **Step 2: Add the diff loader + apply handler**

Add these alongside the other handlers (near `submitExclude`, ~L210-237):

```typescript
  const loadDistributionDiff = async () => {
    if (!period.roster_id) return;
    setDiffLoading(true);
    try {
      const resp = await apiClient.paymentRosters.getDistributionDiff(period.roster_id);
      if (resp.success && resp.data) {
        setDiff(resp.data);
        setSelectedAddIds(new Set());
        setSelectedRemoveItemIds(new Set());
      } else {
        toast.error(resp.message || "比對失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "比對失敗");
    } finally {
      setDiffLoading(false);
    }
  };

  const toggle = (set: Set<number>, id: number): Set<number> => {
    const next = new Set(set);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  };

  const submitReconcile = async () => {
    if (!period.roster_id) return;
    setReconcileSubmitting(true);
    try {
      const resp = await apiClient.paymentRosters.reconcileRoster(period.roster_id, {
        add_application_ids: Array.from(selectedAddIds),
        remove_item_ids: Array.from(selectedRemoveItemIds),
      });
      if (resp.success) {
        const added = resp.data?.added.length ?? 0;
        const removed = resp.data?.removed.length ?? 0;
        toast.success(`已更新造冊名單：新增 ${added} 人 / 移除 ${removed} 人`);
        setReconcileConfirmOpen(false);
        await loadRosterItems();
        await loadDistributionDiff();
      } else {
        toast.error(resp.message || "更新造冊名單失敗");
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "更新造冊名單失敗");
    } finally {
      setReconcileSubmitting(false);
    }
  };
```

- [ ] **Step 3: Render the section**

Inside the render, immediately AFTER the `{period.roster_status === "locked" && (<>...</>)}` fragment closes (after L438) and BEFORE the list block, insert:

```tsx
        {canReconcile && (
          <div className="mb-4 p-3 border rounded">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">比對分發名單</span>
              <Button size="sm" variant="outline" onClick={loadDistributionDiff} disabled={diffLoading}>
                {diffLoading ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <RefreshCw className="h-4 w-4 mr-1" />}
                比對分發 vs 造冊
              </Button>
            </div>

            {diff && diff.to_add.length === 0 && diff.to_remove.length === 0 && (
              <p className="mt-2 text-sm text-muted-foreground">名單一致，無需補充。</p>
            )}

            {diff && diff.to_add.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-emerald-700">待補充 ({diff.to_add.length})</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10"></TableHead>
                      <TableHead>學號</TableHead>
                      <TableHead>姓名</TableHead>
                      <TableHead>系所</TableHead>
                      <TableHead className="text-right">金額</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {diff.to_add.map((e: DistributionDiffEntry) => (
                      <TableRow key={`add-${e.application_id}`}>
                        <TableCell>
                          <Checkbox
                            checked={selectedAddIds.has(e.application_id)}
                            onCheckedChange={() =>
                              setSelectedAddIds(prev => toggle(prev, e.application_id))
                            }
                          />
                        </TableCell>
                        <TableCell>{e.student_id}</TableCell>
                        <TableCell>{e.student_name}</TableCell>
                        <TableCell>{e.department_name}</TableCell>
                        <TableCell className="text-right">{e.scholarship_amount}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {diff && diff.to_remove.length > 0 && (
              <div className="mt-3">
                <p className="text-sm font-medium text-red-700">待移除 ({diff.to_remove.length})</p>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="w-10"></TableHead>
                      <TableHead>學號</TableHead>
                      <TableHead>姓名</TableHead>
                      <TableHead>系所</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {diff.to_remove.map((e: DistributionDiffEntry) => (
                      <TableRow key={`rm-${e.item_id}`}>
                        <TableCell>
                          <Checkbox
                            checked={!!e.item_id && selectedRemoveItemIds.has(e.item_id)}
                            onCheckedChange={() =>
                              e.item_id &&
                              setSelectedRemoveItemIds(prev => toggle(prev, e.item_id as number))
                            }
                          />
                        </TableCell>
                        <TableCell>{e.student_id}</TableCell>
                        <TableCell>{e.student_name}</TableCell>
                        <TableCell>{e.department_name}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}

            {diff && (selectedAddIds.size > 0 || selectedRemoveItemIds.size > 0) && (
              <div className="mt-3 flex justify-end">
                <Button size="sm" onClick={() => setReconcileConfirmOpen(true)}>
                  套用 (新增 {selectedAddIds.size} / 移除 {selectedRemoveItemIds.size})
                </Button>
              </div>
            )}
          </div>
        )}
```

- [ ] **Step 4: Add the confirm sub-dialog**

Add as a SIBLING of the main `DialogContent`, just before the outer `</Dialog>` (next to the #66 exclude sub-dialog at L538-623):

```tsx
      {/* 比對分發名單 confirm */}
      <Dialog
        open={reconcileConfirmOpen}
        onOpenChange={open => !open && !reconcileSubmitting && setReconcileConfirmOpen(false)}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>確認更新造冊名單</DialogTitle>
            <DialogDescription className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 text-amber-500" />
              <span>
                將新增 <strong>{selectedAddIds.size}</strong> 人、移除{" "}
                <strong>{selectedRemoveItemIds.size}</strong> 人。此操作會將造冊標記為「需重新匯出 Excel」並記錄稽核日誌。
              </span>
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setReconcileConfirmOpen(false)}
              disabled={reconcileSubmitting}
            >
              取消
            </Button>
            <Button onClick={submitReconcile} disabled={reconcileSubmitting}>
              {reconcileSubmitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              確認套用
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
```

- [ ] **Step 5: Typecheck + lint**

Run: `cd frontend && npx tsc --noEmit && npx eslint components/roster/RosterDetailDialog.tsx`
Expected: no errors. (If `@/components/ui/checkbox` does not exist, run `grep -r "components/ui/checkbox" frontend/components | head` to confirm the path; the project uses shadcn/ui so it should exist — if not, swap the `<Checkbox>` for a native `<input type="checkbox">`.)

- [ ] **Step 6: Commit**

```bash
git add frontend/components/roster/RosterDetailDialog.tsx
git commit -m "feat(roster): add 比對分發名單 reconcile section to RosterDetailDialog"
```

---

## Task 10: End-to-end smoke test

**Files:** none (manual verification via the playwright-test-and-debug skill)

- [ ] **Step 1: Bring up the stack + seed**

```bash
docker compose -f docker-compose.dev.yml up -d
```
Ensure a scholarship with a finalized + distribution-executed ranking and a generated (LOCKED or COMPLETED) roster exists where at least one allocated student is missing from the roster (e.g. add an `is_supplementary` allocated ranking item after generation, or remove one roster item).

- [ ] **Step 2: Drive the flow**

Using the playwright-test-and-debug skill: log in as `admin`, open the roster management dashboard → open the target roster's detail dialog → click **比對分發 vs 造冊** → confirm the missing student appears under 待補充 → tick it → 套用 → confirm → assert the toast shows 新增 1 人, the roster item count increments, and the 「需重新匯出 Excel」amber banner appears.

- [ ] **Step 3: Backend full suite (touched files)**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest \
  app/tests/test_roster_distribution_reconcile_service.py \
  app/tests/test_roster_distribution_reconcile_api.py \
  app/tests/test_roster_item_removal_service.py \
  app/tests/test_roster_service_generation.py -p no:cacheprovider -q
```
Expected: all PASS (generation tests confirm `_create_roster_item` / verification reuse did not regress).

---

## Self-Review

**Spec coverage:**
- Distribution-diff only → Task 2 `_resolve_distribution_for_roster` (allocated ranking items only); Task 3 re-derives `allowed_add`/`allowed_remove` and rejects anything else. ✓
- COMPLETED + LOCKED states → Task 3 guard `status in (COMPLETED, LOCKED)`; tests `test_reconcile_works_on_completed_roster` + LOCKED scenario. ✓
- Per-roster, bidirectional → Task 2 `to_add`/`to_remove`; Task 9 two checkbox groups. ✓
- Selective + confirm → Task 9 checkboxes + confirm sub-dialog; nothing mutates until 確認套用. ✓
- Reuse generation builder → Task 3 `_verify_and_create_item` → `_validate_student_eligibility` + `_create_roster_item`. ✓
- Presentation-only (no quota mutation) → reconcile never references `quota_allocation_status`/quota; asserted by absence. ✓
- excel_stale + re-export hint → Task 3 sets `excel_stale=True`; Task 5 surfaces it in cycle-status; Task 8 carries it through; Task 9 confirm copy mentions re-export. ✓
- Audit per add/remove + summary → Task 3 three `AuditLog.create_log` actions; `test_reconcile_writes_audit_logs`. ✓
- Out-of-scope (new group with no roster; arbitrary students) → not implemented (diff is per existing roster, add restricted to `allowed_add`). ✓

**Placeholder scan:** no TBD/TODO; every code step is complete and copy-pasteable. ✓

**Type/name consistency:** service `get_distribution_diff_for_roster` / `reconcile_roster`; endpoints `get_distribution_diff` / `reconcile_roster_endpoint`; api `getDistributionDiff` / `reconcileRoster`; schemas `DistributionDiff`/`DistributionDiffEntry`/`ReconcileRequest`/`ReconcileResult`/`ReconcileResultEntry` — used consistently across backend, endpoint wrapping (`DistributionDiff(**result)`, `ReconcileResult(**result)`), frontend interfaces, and tests. `_recompute_roster_totals_sync` returns `(qualified, total_count, total_amount)` and is consumed in that order in `reconcile_roster`. ✓

**Known follow-up (not blocking):** `_verify_and_create_item` duplicates ~12 lines of the generation per-application verify block rather than refactoring the generation hot path to share it — intentional, to avoid destabilizing generation; a future refactor could unify them with the existing generation tests as the safety net.
