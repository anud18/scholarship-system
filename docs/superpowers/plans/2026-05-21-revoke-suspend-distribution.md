# Revoke / Suspend Scholarship Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the admin Manual Distribution Panel's single "取消" (✕) row button into two post-roster-generation actions — 撤銷 (revoke) and 停發 (suspend) — that remove a student from all non-LOCKED rosters and surface manual-cleanup hints on LOCKED rosters.

**Architecture:** Backend service writes new `quota_allocation_status` values (`revoked`, `suspended`) on `applications`, hard-deletes the matching `PaymentRosterItem` rows from non-LOCKED rosters, and writes audit log entries. Frontend swaps the row ✕ for two coloured buttons with confirmation dialogs; the roster detail dialog renders a collapsible "status change notice" panel that lists revoked/suspended students still embedded in any LOCKED roster and provides a per-row [從本造冊移除] button.

**Tech Stack:** Python / FastAPI / SQLAlchemy async / Alembic / Pydantic v2 / Next.js / React / openapi-typescript / Playwright

**Spec:** `docs/superpowers/specs/2026-05-21-revoke-suspend-distribution-design.md`

---

## File Structure

### Backend — new

| File | Responsibility |
|---|---|
| `backend/alembic/versions/20260521_revoke_suspend.py` | Add 6 columns to `applications`, 1 column to `payment_rosters`, with existence checks |
| `backend/app/tests/test_revoke_suspend_service.py` | Unit tests for revoke/suspend service methods |
| `backend/app/tests/test_roster_item_removal_service.py` | Unit tests for LOCKED-roster item removal and revoked/suspended listing |
| `backend/app/tests/test_revoke_suspend_endpoints.py` | API tests for the 4 new endpoints |
| `backend/app/tests/test_revoke_suspend_flow.py` | Integration test covering the multi-roster flow |
| `frontend/e2e/admin/revoke-suspend.spec.ts` | Playwright E2E test |

### Backend — modify

| File | Change |
|---|---|
| `backend/app/models/application.py` | + 6 columns (revoke/suspend metadata) |
| `backend/app/models/payment_roster.py` | + `excel_stale` boolean column |
| `backend/app/schemas/application.py` | + `RevokeRequest`, `SuspendRequest` |
| `backend/app/schemas/payment_roster.py` | + `RevokedSuspendedListResponse`, `RemoveLockedItemRequest` |
| `backend/app/services/manual_distribution_service.py` | + `revoke_allocation`, `suspend_allocation`, shared `_cancel_allocation` helper |
| `backend/app/services/roster_service.py` | + `get_revoked_suspended_for_roster`, `remove_item_from_locked_roster` |
| `backend/app/api/v1/endpoints/manual_distribution.py` | + 2 POST endpoints |
| `backend/app/api/v1/endpoints/payment_rosters.py` | + 1 GET + 1 DELETE endpoint |

### Frontend — modify

| File | Change |
|---|---|
| `frontend/lib/api/modules/manual-distribution.ts` | + `revoke`, `suspend` methods |
| `frontend/lib/api/modules/payment-rosters.ts` | + `getRevokedSuspended`, `removeItemFromLockedRoster` methods |
| `frontend/lib/api/generated/schema.d.ts` | Regenerate via `npm run api:generate` |
| `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Replace ✕ column with two buttons + two AlertDialogs |
| `frontend/components/roster/RosterDetailDialog.tsx` | Add 狀態變更通知 panel + Excel-stale banner |

---

## Task 0: Create isolated worktree

**Files:**
- N/A (environment setup)

- [ ] **Step 1: Use the worktree skill**

Invoke `superpowers:using-git-worktrees`. When prompted, name the worktree `revoke-suspend-distribution` and branch from `main`. Resulting path will be `.worktrees/revoke-suspend-distribution` (or similar).

- [ ] **Step 2: Verify worktree**

```bash
cd .worktrees/revoke-suspend-distribution
git status
git branch --show-current
```

Expected: clean tree on a new branch derived from `main`. All subsequent tasks run inside this worktree.

- [ ] **Step 3: Sanity-check dev environment can boot**

```bash
docker compose -f docker-compose.dev.yml up -d backend postgres
docker compose -f docker-compose.dev.yml logs backend --tail 30
```

Expected: backend reports `Uvicorn running on http://0.0.0.0:8000`.

---

## Task 1: Database migration + model fields

**Files:**
- Create: `backend/alembic/versions/20260521_revoke_suspend.py`
- Modify: `backend/app/models/application.py` (add 6 columns after existing fields)
- Modify: `backend/app/models/payment_roster.py` (add `excel_stale` after `notes`)
- Test: `backend/app/tests/test_revoke_suspend_models.py`

- [ ] **Step 1: Write the failing model test**

Create `backend/app/tests/test_revoke_suspend_models.py`:

```python
"""Pin: applications + payment_rosters expose the revoke/suspend metadata
columns at the ORM layer so service code can read/write them."""

from app.models.application import Application
from app.models.payment_roster import PaymentRoster


def test_application_has_revoke_metadata_columns():
    cols = {c.name for c in Application.__table__.columns}
    assert {"revoked_at", "revoked_by", "revoke_reason"}.issubset(cols)


def test_application_has_suspend_metadata_columns():
    cols = {c.name for c in Application.__table__.columns}
    assert {"suspended_at", "suspended_by", "suspend_reason"}.issubset(cols)


def test_payment_roster_has_excel_stale_column():
    cols = {c.name for c in PaymentRoster.__table__.columns}
    assert "excel_stale" in cols
```

- [ ] **Step 2: Run and confirm it fails**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_models.py -v
```

Expected: 3 FAILs with `AssertionError` (columns missing).

- [ ] **Step 3: Add the 6 columns to `Application`**

In `backend/app/models/application.py`, locate the existing imports near the top — confirm `ForeignKey`, `DateTime`, `Text`, and `Integer` are imported (they already are). Then add the 6 new columns to the `Application` class (place them just before the `__table_args__` or after the most recent column definition):

```python
    # Revoke / Suspend metadata (spec 2026-05-21)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    suspended_at = Column(DateTime(timezone=True), nullable=True)
    suspended_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    suspend_reason = Column(Text, nullable=True)
```

- [ ] **Step 4: Add `excel_stale` to `PaymentRoster`**

In `backend/app/models/payment_roster.py`, inside the `PaymentRoster` class, add a column after the existing `notes`/`processing_log` block (and before `created_at`):

```python
    # Set True when an item is removed from a LOCKED roster — UI shows
    # "請重新匯出 Excel" hint. Cleared after re-export.
    excel_stale = Column(Boolean, default=False, nullable=False, server_default="false")
```

- [ ] **Step 5: Re-run the model test**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_models.py -v
```

Expected: 3 PASS.

- [ ] **Step 6: Write the Alembic migration**

Create `backend/alembic/versions/20260521_revoke_suspend.py`:

```python
"""Add revoke/suspend metadata to applications + excel_stale flag to payment_rosters.

Spec: docs/superpowers/specs/2026-05-21-revoke-suspend-distribution-design.md

# Schema changes

`applications` — 6 new nullable columns capturing who/when/why an application
was revoked or suspended:
  - revoked_at, revoked_by (FK users), revoke_reason (text)
  - suspended_at, suspended_by (FK users), suspend_reason (text)

`payment_rosters` — 1 new boolean `excel_stale` (default False). Flipped True
when an admin removes an item from a LOCKED roster; cleared on Excel re-export.

# Safety

All `add_column` calls are wrapped in existence checks so the migration is
idempotent on partially-migrated databases (matches project convention —
see backend/CLAUDE.md "Alembic Migration Development Rules").

`quota_allocation_status` already accepts arbitrary strings (plain VARCHAR);
the new values `revoked`/`suspended` need no DDL.

Revision ID: revoke_suspend_001
Revises: email_tpl_scholar_type_001
Create Date: 2026-05-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "revoke_suspend_001"
down_revision: Union[str, Sequence[str], None] = "email_tpl_scholar_type_001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


APPLICATION_COLUMNS = [
    ("revoked_at", sa.DateTime(timezone=True), True, None),
    ("revoked_by", sa.Integer(), True, "users.id"),
    ("revoke_reason", sa.Text(), True, None),
    ("suspended_at", sa.DateTime(timezone=True), True, None),
    ("suspended_by", sa.Integer(), True, "users.id"),
    ("suspend_reason", sa.Text(), True, None),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_app_cols = {c["name"] for c in inspector.get_columns("applications")}
    for name, coltype, nullable, fk in APPLICATION_COLUMNS:
        if name in existing_app_cols:
            continue
        kwargs = {"nullable": nullable}
        col = sa.Column(name, coltype, **kwargs)
        op.add_column("applications", col)
        if fk:
            # Create FK separately so the column add stays simple
            op.create_foreign_key(
                f"fk_applications_{name}_users",
                "applications",
                "users",
                [name],
                ["id"],
                ondelete="SET NULL",
            )

    existing_roster_cols = {c["name"] for c in inspector.get_columns("payment_rosters")}
    if "excel_stale" not in existing_roster_cols:
        op.add_column(
            "payment_rosters",
            sa.Column(
                "excel_stale",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_app_cols = {c["name"] for c in inspector.get_columns("applications")}
    for name, _coltype, _nullable, fk in APPLICATION_COLUMNS:
        if name not in existing_app_cols:
            continue
        if fk:
            # Best-effort: drop constraint by predictable name
            try:
                op.drop_constraint(
                    f"fk_applications_{name}_users", "applications", type_="foreignkey"
                )
            except Exception:
                pass
        op.drop_column("applications", name)

    existing_roster_cols = {c["name"] for c in inspector.get_columns("payment_rosters")}
    if "excel_stale" in existing_roster_cols:
        op.drop_column("payment_rosters", "excel_stale")
```

- [ ] **Step 7: Apply the migration**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected output ends with:
```
INFO  [alembic.runtime.migration] Running upgrade email_tpl_scholar_type_001 -> revoke_suspend_001, Add revoke/suspend metadata...
```

- [ ] **Step 8: Verify columns exist in the running Postgres**

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U scholarship_user -d scholarship_db -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='applications' AND column_name LIKE 'revoke%' OR column_name LIKE 'suspend%' ORDER BY column_name;"
docker compose -f docker-compose.dev.yml exec postgres psql -U scholarship_user -d scholarship_db -c \
  "SELECT column_name FROM information_schema.columns WHERE table_name='payment_rosters' AND column_name='excel_stale';"
```

Expected: 6 application columns and 1 payment_roster column listed.

- [ ] **Step 9: Commit**

```bash
git add backend/alembic/versions/20260521_revoke_suspend.py \
        backend/app/models/application.py \
        backend/app/models/payment_roster.py \
        backend/app/tests/test_revoke_suspend_models.py
git commit -m "feat(db): add revoke/suspend metadata + excel_stale flag"
```

---

## Task 2: Pydantic request/response schemas

**Files:**
- Modify: `backend/app/schemas/application.py` (add at end)
- Modify: `backend/app/schemas/payment_roster.py` (add at end)
- Test: `backend/app/tests/test_revoke_suspend_schemas.py`

- [ ] **Step 1: Write the failing schema test**

Create `backend/app/tests/test_revoke_suspend_schemas.py`:

```python
"""Pin: revoke/suspend request schemas reject empty/too-long reasons and
parse valid input. RevokedSuspendedListResponse shape mirrors the API spec."""

import pytest
from pydantic import ValidationError

from app.schemas.application import RevokeRequest, SuspendRequest
from app.schemas.payment_roster import (
    RemoveLockedItemRequest,
    RevokedSuspendedListResponse,
    RevokedSuspendedEntry,
)


def test_revoke_request_requires_non_empty_reason():
    with pytest.raises(ValidationError):
        RevokeRequest(reason="")


def test_revoke_request_rejects_too_long_reason():
    with pytest.raises(ValidationError):
        RevokeRequest(reason="x" * 501)


def test_revoke_request_accepts_valid_reason():
    req = RevokeRequest(reason="violated scholarship terms")
    assert req.reason == "violated scholarship terms"


def test_suspend_request_validates_same_way():
    with pytest.raises(ValidationError):
        SuspendRequest(reason="")
    assert SuspendRequest(reason="leave of absence").reason == "leave of absence"


def test_remove_locked_item_request_reason_optional():
    assert RemoveLockedItemRequest().reason is None
    assert RemoveLockedItemRequest(reason="clean up").reason == "clean up"


def test_revoked_suspended_list_response_shape():
    entry = RevokedSuspendedEntry(
        application_id=1,
        student_name="王小明",
        student_id_number="B12345",
        event_at="2026-05-21T10:00:00Z",
        reason="test",
    )
    resp = RevokedSuspendedListResponse(revoked=[entry], suspended=[])
    assert resp.revoked[0].student_name == "王小明"
    assert resp.suspended == []
```

- [ ] **Step 2: Run, confirm failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_schemas.py -v
```

Expected: ImportError (schemas not yet defined).

- [ ] **Step 3: Add request schemas to `application.py`**

Append to `backend/app/schemas/application.py`:

```python
from pydantic import BaseModel, Field


class RevokeRequest(BaseModel):
    """Body for POST /manual-distribution/applications/{id}/revoke"""

    reason: str = Field(..., min_length=1, max_length=500)


class SuspendRequest(BaseModel):
    """Body for POST /manual-distribution/applications/{id}/suspend"""

    reason: str = Field(..., min_length=1, max_length=500)
```

(If `BaseModel`/`Field` are already imported at the top of the file, omit the import line — Python will complain about redefinition but it will not error; safest is to dedupe.)

- [ ] **Step 4: Add roster schemas to `payment_roster.py`**

Append to `backend/app/schemas/payment_roster.py`:

```python
from typing import List, Optional

from pydantic import BaseModel, Field


class RemoveLockedItemRequest(BaseModel):
    """Body for DELETE /payment-rosters/{roster_id}/items/{item_id}"""

    reason: Optional[str] = Field(None, max_length=500)


class RevokedSuspendedEntry(BaseModel):
    application_id: int
    student_name: str
    student_id_number: str
    event_at: str  # ISO timestamp of revoke or suspend
    reason: Optional[str] = None
    item_id: Optional[int] = None  # PaymentRosterItem.id (for the DELETE button)


class RevokedSuspendedListResponse(BaseModel):
    """Response body for GET /payment-rosters/{roster_id}/revoked-suspended"""

    revoked: List[RevokedSuspendedEntry]
    suspended: List[RevokedSuspendedEntry]
```

- [ ] **Step 5: Re-run test**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_schemas.py -v
```

Expected: 6 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/schemas/application.py \
        backend/app/schemas/payment_roster.py \
        backend/app/tests/test_revoke_suspend_schemas.py
git commit -m "feat(schemas): add revoke/suspend request and response schemas"
```

---

## Task 3: Service — `revoke_allocation` (with shared internal helper)

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py`
- Test: `backend/app/tests/test_revoke_suspend_service.py`

- [ ] **Step 1: Write failing service tests**

Create `backend/app/tests/test_revoke_suspend_service.py`:

```python
"""Pin: revoke_allocation flips the right application columns, hard-deletes
non-LOCKED roster items, leaves LOCKED roster items alone, and writes an
audit log. Conflict + 400 paths surface as exceptions."""

import pytest
from datetime import datetime, timezone

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.manual_distribution_service import ManualDistributionService


@pytest.mark.asyncio
async def test_revoke_sets_status_and_metadata(async_db_session, allocated_application, admin_user):
    svc = ManualDistributionService(async_db_session)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_user.id,
        reason="violated terms",
    )
    await async_db_session.commit()
    await async_db_session.refresh(allocated_application)
    assert allocated_application.status == ApplicationStatus.cancelled
    assert allocated_application.quota_allocation_status == "revoked"
    assert allocated_application.revoke_reason == "violated terms"
    assert allocated_application.revoked_by == admin_user.id
    assert allocated_application.revoked_at is not None


@pytest.mark.asyncio
async def test_revoke_hard_deletes_items_from_non_locked_rosters(
    async_db_session, allocated_application, draft_roster_with_item, admin_user
):
    item_id = draft_roster_with_item.items[0].id
    svc = ManualDistributionService(async_db_session)
    result = await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_user.id,
        reason="x",
    )
    await async_db_session.commit()
    deleted = await async_db_session.get(PaymentRosterItem, item_id)
    assert deleted is None
    assert draft_roster_with_item.id in result["affected_unlocked_rosters"]


@pytest.mark.asyncio
async def test_revoke_leaves_locked_roster_items_intact(
    async_db_session, allocated_application, locked_roster_with_item, admin_user
):
    item_id = locked_roster_with_item.items[0].id
    svc = ManualDistributionService(async_db_session)
    await svc.revoke_allocation(
        application_id=allocated_application.id,
        admin_user_id=admin_user.id,
        reason="x",
    )
    await async_db_session.commit()
    still_there = await async_db_session.get(PaymentRosterItem, item_id)
    assert still_there is not None


@pytest.mark.asyncio
async def test_revoke_twice_raises_conflict(async_db_session, allocated_application, admin_user):
    svc = ManualDistributionService(async_db_session)
    await svc.revoke_allocation(allocated_application.id, admin_user.id, "first")
    await async_db_session.commit()
    with pytest.raises(ValueError, match="already"):
        await svc.revoke_allocation(allocated_application.id, admin_user.id, "second")


@pytest.mark.asyncio
async def test_revoke_non_allocated_raises(async_db_session, unallocated_application, admin_user):
    svc = ManualDistributionService(async_db_session)
    with pytest.raises(ValueError, match="not.*allocated"):
        await svc.revoke_allocation(unallocated_application.id, admin_user.id, "x")


@pytest.mark.asyncio
async def test_revoke_writes_audit_log(async_db_session, allocated_application, admin_user):
    from sqlalchemy import select
    svc = ManualDistributionService(async_db_session)
    await svc.revoke_allocation(allocated_application.id, admin_user.id, "reason text")
    await async_db_session.commit()
    rows = (await async_db_session.execute(
        select(AuditLog).where(AuditLog.action == "application.revoke")
    )).scalars().all()
    assert len(rows) == 1
    log = rows[0]
    assert log.resource_id == str(allocated_application.id)
    assert log.user_id == admin_user.id
    assert log.new_values["reason"] == "reason text"
    assert "affected_unlocked_rosters" in log.new_values
```

Add fixtures at the top of the same file (or in `conftest.py` if you prefer to share with later tasks):

```python
@pytest_asyncio.fixture
async def admin_user(async_db_session):
    from app.models.user import User, UserRole, UserType
    u = User(
        email="admin@nycu.edu.tw",
        name="Admin",
        role=UserRole.admin,
        user_type=UserType.employee,
    )
    async_db_session.add(u)
    await async_db_session.commit()
    await async_db_session.refresh(u)
    return u


@pytest_asyncio.fixture
async def allocated_application(async_db_session):
    """An application in the post-finalize 'allocated' state."""
    from app.models.application import Application, ApplicationStatus
    app = Application(
        student_id=1,  # adjust to your conftest student fixture if available
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        quota_allocation_status="allocated",
        sub_scholarship_type="nstc",
    )
    async_db_session.add(app)
    await async_db_session.commit()
    await async_db_session.refresh(app)
    return app


@pytest_asyncio.fixture
async def unallocated_application(async_db_session):
    from app.models.application import Application, ApplicationStatus
    app = Application(
        student_id=2,
        scholarship_type_id=1,
        academic_year=114,
        semester="first",
        status=ApplicationStatus.approved,
        quota_allocation_status=None,
    )
    async_db_session.add(app)
    await async_db_session.commit()
    await async_db_session.refresh(app)
    return app


@pytest_asyncio.fixture
async def draft_roster_with_item(async_db_session, allocated_application):
    from app.models.payment_roster import (
        PaymentRoster, PaymentRosterItem, RosterStatus, RosterCycle, RosterTriggerType,
    )
    r = PaymentRoster(
        roster_code="ROSTER-TEST-DRAFT",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=1,
    )
    item = PaymentRosterItem(
        roster=r,
        application_id=allocated_application.id,
        student_id_number="B12345",
        student_name="王小明",
        scholarship_name="NSTC",
        scholarship_amount=40000,
    )
    async_db_session.add_all([r, item])
    await async_db_session.commit()
    await async_db_session.refresh(r)
    return r


@pytest_asyncio.fixture
async def locked_roster_with_item(async_db_session, allocated_application):
    from app.models.payment_roster import (
        PaymentRoster, PaymentRosterItem, RosterStatus, RosterCycle, RosterTriggerType,
    )
    r = PaymentRoster(
        roster_code="ROSTER-TEST-LOCKED",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=1,
    )
    item = PaymentRosterItem(
        roster=r,
        application_id=allocated_application.id,
        student_id_number="B12345",
        student_name="王小明",
        scholarship_name="NSTC",
        scholarship_amount=40000,
    )
    async_db_session.add_all([r, item])
    await async_db_session.commit()
    await async_db_session.refresh(r)
    return r
```

Add the `async_db_session` fixture if it doesn't already exist in `backend/app/tests/conftest.py` — check first by running:
```bash
docker compose -f docker-compose.dev.yml exec backend grep -n "async_db_session" app/tests/conftest.py
```
If missing, copy the existing async-session fixture pattern from `app/tests/conftest.py` (look for `AsyncSession`).

- [ ] **Step 2: Run, confirm failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_service.py -v
```

Expected: AttributeError (`ManualDistributionService` has no `revoke_allocation`).

- [ ] **Step 3: Implement helper + `revoke_allocation` in service**

In `backend/app/services/manual_distribution_service.py`, add new imports (top of file):

```python
from typing import Literal
from app.models.audit_log import AuditLog
```

Add these methods inside the `ManualDistributionService` class (after `finalize`):

```python
    async def revoke_allocation(
        self, application_id: int, admin_user_id: int, reason: str
    ) -> dict:
        """Revoke an allocated application: status -> cancelled,
        quota_allocation_status -> revoked, hard-delete its PaymentRosterItem
        rows in all non-LOCKED rosters, write audit log."""
        return await self._cancel_allocation(
            application_id=application_id,
            admin_user_id=admin_user_id,
            reason=reason,
            mode="revoke",
        )

    async def suspend_allocation(
        self, application_id: int, admin_user_id: int, reason: str
    ) -> dict:
        """Suspend an allocated application: status -> cancelled,
        quota_allocation_status -> suspended, hard-delete its PaymentRosterItem
        rows in all non-LOCKED rosters, write audit log."""
        return await self._cancel_allocation(
            application_id=application_id,
            admin_user_id=admin_user_id,
            reason=reason,
            mode="suspend",
        )

    async def _cancel_allocation(
        self,
        application_id: int,
        admin_user_id: int,
        reason: str,
        mode: Literal["revoke", "suspend"],
    ) -> dict:
        from app.models.application import Application, ApplicationStatus
        from app.models.payment_roster import (
            PaymentRoster,
            PaymentRosterItem,
            RosterStatus,
        )

        # 1. Row-lock the application
        result = await self.db.execute(
            select(Application).where(Application.id == application_id).with_for_update()
        )
        app = result.scalar_one_or_none()
        if app is None:
            raise ValueError(f"Application {application_id} not found")

        # 2. Conflict check
        if app.quota_allocation_status in ("revoked", "suspended"):
            raise ValueError(
                f"Application {application_id} already {app.quota_allocation_status}"
            )

        # 3. 400 check
        if app.quota_allocation_status != "allocated":
            raise ValueError(
                f"Application {application_id} is not allocated "
                f"(quota_allocation_status={app.quota_allocation_status})"
            )

        now = datetime.now(timezone.utc)

        # 4. Update application columns
        app.status = ApplicationStatus.cancelled
        if mode == "revoke":
            app.quota_allocation_status = "revoked"
            app.revoked_at = now
            app.revoked_by = admin_user_id
            app.revoke_reason = reason
        else:
            app.quota_allocation_status = "suspended"
            app.suspended_at = now
            app.suspended_by = admin_user_id
            app.suspend_reason = reason

        # 5. Hard-delete items in non-LOCKED rosters
        items_result = await self.db.execute(
            select(PaymentRosterItem)
            .join(PaymentRoster, PaymentRosterItem.roster_id == PaymentRoster.id)
            .where(
                PaymentRosterItem.application_id == application_id,
                PaymentRoster.status != RosterStatus.LOCKED,
            )
        )
        items_to_delete = items_result.scalars().all()
        affected_roster_ids = sorted({i.roster_id for i in items_to_delete})

        for item in items_to_delete:
            await self.db.delete(item)

        # 6. Recompute roster totals for affected rosters
        for roster_id in affected_roster_ids:
            await self._recompute_roster_totals(roster_id)

        # 7. Audit log
        action = "application.revoke" if mode == "revoke" else "application.suspend"
        log = AuditLog.create_log(
            user_id=admin_user_id,
            action=action,
            resource_type="application",
            resource_id=str(application_id),
            description=f"{mode} application {application_id}",
            new_values={"reason": reason, "affected_unlocked_rosters": affected_roster_ids},
        )
        self.db.add(log)

        await self.db.flush()

        return {
            "application_id": application_id,
            "quota_allocation_status": app.quota_allocation_status,
            "event_at": now.isoformat(),
            "affected_unlocked_rosters": affected_roster_ids,
        }

    async def _recompute_roster_totals(self, roster_id: int) -> None:
        """Recompute total_applications, qualified_count, total_amount for a roster."""
        from sqlalchemy import func
        from app.models.payment_roster import PaymentRoster, PaymentRosterItem

        agg = await self.db.execute(
            select(
                func.count(PaymentRosterItem.id),
                func.coalesce(func.sum(PaymentRosterItem.scholarship_amount), 0),
            ).where(PaymentRosterItem.roster_id == roster_id)
        )
        total_count, total_amount = agg.one()

        roster = await self.db.get(PaymentRoster, roster_id)
        if roster:
            roster.total_applications = total_count
            roster.qualified_count = total_count
            roster.total_amount = total_amount
```

(If `select` is not already imported at module level, add `from sqlalchemy import select`; check existing imports.)

- [ ] **Step 4: Re-run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_service.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/manual_distribution_service.py \
        backend/app/tests/test_revoke_suspend_service.py
git commit -m "feat(service): add revoke_allocation + suspend_allocation"
```

---

## Task 4: Service — `suspend_allocation` test coverage

`suspend_allocation` was implemented in Task 3 (it shares `_cancel_allocation`). Add explicit suspend tests to be sure the suspend code-path is exercised.

**Files:**
- Modify: `backend/app/tests/test_revoke_suspend_service.py` (append)

- [ ] **Step 1: Append suspend tests**

```python
@pytest.mark.asyncio
async def test_suspend_sets_status_and_metadata(async_db_session, allocated_application, admin_user):
    svc = ManualDistributionService(async_db_session)
    await svc.suspend_allocation(allocated_application.id, admin_user.id, "leave")
    await async_db_session.commit()
    await async_db_session.refresh(allocated_application)
    assert allocated_application.status == ApplicationStatus.cancelled
    assert allocated_application.quota_allocation_status == "suspended"
    assert allocated_application.suspend_reason == "leave"
    assert allocated_application.suspended_by == admin_user.id


@pytest.mark.asyncio
async def test_suspend_then_revoke_raises_conflict(async_db_session, allocated_application, admin_user):
    svc = ManualDistributionService(async_db_session)
    await svc.suspend_allocation(allocated_application.id, admin_user.id, "first")
    await async_db_session.commit()
    with pytest.raises(ValueError, match="already"):
        await svc.revoke_allocation(allocated_application.id, admin_user.id, "second")


@pytest.mark.asyncio
async def test_suspend_writes_audit_log_with_suspend_action(async_db_session, allocated_application, admin_user):
    from sqlalchemy import select
    svc = ManualDistributionService(async_db_session)
    await svc.suspend_allocation(allocated_application.id, admin_user.id, "x")
    await async_db_session.commit()
    log = (await async_db_session.execute(
        select(AuditLog).where(AuditLog.action == "application.suspend")
    )).scalar_one()
    assert log.resource_id == str(allocated_application.id)
```

- [ ] **Step 2: Run**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_service.py -v
```

Expected: 9 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_revoke_suspend_service.py
git commit -m "test(service): cover suspend_allocation paths"
```

---

## Task 5: Service — `get_revoked_suspended_for_roster` + `remove_item_from_locked_roster`

**Files:**
- Modify: `backend/app/services/roster_service.py`
- Test: `backend/app/tests/test_roster_item_removal_service.py`

- [ ] **Step 1: Confirm `roster_service.py` is sync, identify class name**

```bash
docker compose -f docker-compose.dev.yml exec backend grep -nE "^class |def __init__" app/services/roster_service.py | head -20
```

Note the class name (likely `RosterService`) and that its `__init__` takes a sync `Session`. Use it in the test.

- [ ] **Step 2: Write failing tests**

Create `backend/app/tests/test_roster_item_removal_service.py`:

```python
"""Pin: get_revoked_suspended_for_roster returns split lists per
quota_allocation_status; remove_item_from_locked_roster only works on
LOCKED rosters, recomputes totals, sets excel_stale, leaves status LOCKED,
and writes audit log."""

import pytest

from app.models.application import Application, ApplicationStatus
from app.models.audit_log import AuditLog
from app.models.payment_roster import PaymentRoster, PaymentRosterItem, RosterStatus
from app.services.roster_service import RosterService


@pytest.fixture
def sync_session(db_session_sync):  # use whatever the project's sync session fixture is named
    return db_session_sync


@pytest.fixture
def locked_roster_two_items(sync_session, admin_user_sync):
    from app.models.payment_roster import RosterCycle, RosterTriggerType
    a1 = Application(student_id=1, scholarship_type_id=1, academic_year=114,
                     semester="first", status=ApplicationStatus.cancelled,
                     quota_allocation_status="revoked", revoke_reason="bad",
                     revoked_by=admin_user_sync.id)
    a2 = Application(student_id=2, scholarship_type_id=1, academic_year=114,
                     semester="first", status=ApplicationStatus.cancelled,
                     quota_allocation_status="suspended", suspend_reason="leave",
                     suspended_by=admin_user_sync.id)
    sync_session.add_all([a1, a2])
    sync_session.flush()
    r = PaymentRoster(
        roster_code="ROSTER-LOCK-1",
        scholarship_configuration_id=1,
        period_label="2025-12",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.LOCKED,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_user_sync.id,
    )
    sync_session.add(r)
    sync_session.flush()
    sync_session.add_all([
        PaymentRosterItem(roster_id=r.id, application_id=a1.id,
                          student_id_number="B1", student_name="W",
                          scholarship_name="NSTC", scholarship_amount=40000),
        PaymentRosterItem(roster_id=r.id, application_id=a2.id,
                          student_id_number="B2", student_name="L",
                          scholarship_name="NSTC", scholarship_amount=40000),
    ])
    sync_session.commit()
    sync_session.refresh(r)
    return r


def test_get_revoked_suspended_splits_by_status(sync_session, locked_roster_two_items):
    svc = RosterService(sync_session)
    out = svc.get_revoked_suspended_for_roster(locked_roster_two_items.id)
    assert len(out["revoked"]) == 1
    assert len(out["suspended"]) == 1
    assert out["revoked"][0].student_id_number == "B1"
    assert out["suspended"][0].student_id_number == "B2"


def test_remove_item_from_locked_roster_deletes_item_and_marks_stale(
    sync_session, locked_roster_two_items, admin_user_sync
):
    item = locked_roster_two_items.items[0]
    svc = RosterService(sync_session)
    svc.remove_item_from_locked_roster(
        roster_id=locked_roster_two_items.id,
        item_id=item.id,
        admin_user_id=admin_user_sync.id,
        reason="cleanup",
    )
    sync_session.commit()
    sync_session.refresh(locked_roster_two_items)
    assert sync_session.get(PaymentRosterItem, item.id) is None
    assert locked_roster_two_items.excel_stale is True
    assert locked_roster_two_items.status == RosterStatus.LOCKED
    assert locked_roster_two_items.qualified_count == 1


def test_remove_item_on_non_locked_roster_raises(sync_session, admin_user_sync):
    from app.models.payment_roster import RosterCycle, RosterTriggerType
    r = PaymentRoster(
        roster_code="ROSTER-DRAFT-1",
        scholarship_configuration_id=1,
        period_label="2026-01",
        academic_year=114,
        roster_cycle=RosterCycle.MONTHLY,
        status=RosterStatus.DRAFT,
        trigger_type=RosterTriggerType.MANUAL,
        created_by=admin_user_sync.id,
    )
    sync_session.add(r); sync_session.flush()
    item = PaymentRosterItem(
        roster_id=r.id, application_id=1,
        student_id_number="X", student_name="X",
        scholarship_name="N", scholarship_amount=1,
    )
    sync_session.add(item); sync_session.commit()
    svc = RosterService(sync_session)
    with pytest.raises(ValueError, match="LOCKED"):
        svc.remove_item_from_locked_roster(r.id, item.id, admin_user_sync.id, None)


def test_remove_item_writes_audit_log(sync_session, locked_roster_two_items, admin_user_sync):
    item = locked_roster_two_items.items[0]
    svc = RosterService(sync_session)
    svc.remove_item_from_locked_roster(
        locked_roster_two_items.id, item.id, admin_user_sync.id, "cleanup"
    )
    sync_session.commit()
    log = sync_session.query(AuditLog).filter(
        AuditLog.action == "roster.item_removed_after_lock"
    ).one()
    assert log.resource_id == str(locked_roster_two_items.id)
    assert log.new_values["item_id"] == item.id
    assert log.new_values["reason"] == "cleanup"
```

(Replace `db_session_sync` and `admin_user_sync` with whatever the project's existing sync-session and sync-admin fixtures are. Check `backend/app/tests/conftest.py` first; if not present, add minimal versions following the same pattern as the async ones from Task 3.)

- [ ] **Step 3: Run, confirm failure**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_roster_item_removal_service.py -v
```

Expected: AttributeError (methods missing).

- [ ] **Step 4: Implement service methods**

In `backend/app/services/roster_service.py`, locate the `RosterService` class (or whatever the existing class is named). Add:

```python
    def get_revoked_suspended_for_roster(self, roster_id: int) -> dict:
        """Return revoked / suspended entries for a roster — i.e. items still
        present in this (LOCKED) roster whose linked Application has been
        revoked or suspended after the lock."""
        from app.models.application import Application
        from app.models.payment_roster import PaymentRosterItem
        from app.schemas.payment_roster import RevokedSuspendedEntry

        rows = (
            self.db.query(PaymentRosterItem, Application)
            .join(Application, PaymentRosterItem.application_id == Application.id)
            .filter(
                PaymentRosterItem.roster_id == roster_id,
                Application.quota_allocation_status.in_(("revoked", "suspended")),
            )
            .all()
        )
        revoked, suspended = [], []
        for item, app in rows:
            entry = RevokedSuspendedEntry(
                application_id=app.id,
                student_name=item.student_name,
                student_id_number=item.student_id_number,
                event_at=(
                    app.revoked_at if app.quota_allocation_status == "revoked"
                    else app.suspended_at
                ).isoformat(),
                reason=(
                    app.revoke_reason if app.quota_allocation_status == "revoked"
                    else app.suspend_reason
                ),
                item_id=item.id,
            )
            (revoked if app.quota_allocation_status == "revoked" else suspended).append(entry)
        return {"revoked": revoked, "suspended": suspended}

    def remove_item_from_locked_roster(
        self,
        roster_id: int,
        item_id: int,
        admin_user_id: int,
        reason: str | None,
    ) -> dict:
        """Hard-delete a PaymentRosterItem from a LOCKED roster. Recompute
        roster totals, set excel_stale=True, write audit log. Roster stays
        LOCKED."""
        from sqlalchemy import func
        from app.models.audit_log import AuditLog
        from app.models.payment_roster import (
            PaymentRoster,
            PaymentRosterItem,
            RosterStatus,
        )

        roster = self.db.get(PaymentRoster, roster_id)
        if roster is None:
            raise ValueError(f"Roster {roster_id} not found")
        if roster.status != RosterStatus.LOCKED:
            raise ValueError(
                f"Roster {roster_id} is not LOCKED (status={roster.status.value})"
            )

        item = self.db.get(PaymentRosterItem, item_id)
        if item is None or item.roster_id != roster_id:
            raise ValueError(f"Item {item_id} not found in roster {roster_id}")

        removed_amount = item.scholarship_amount
        removed_app_id = item.application_id
        self.db.delete(item)
        self.db.flush()

        # Recompute totals
        total_count, total_amount = self.db.query(
            func.count(PaymentRosterItem.id),
            func.coalesce(func.sum(PaymentRosterItem.scholarship_amount), 0),
        ).filter(PaymentRosterItem.roster_id == roster_id).one()
        roster.total_applications = total_count
        roster.qualified_count = total_count
        roster.total_amount = total_amount
        roster.excel_stale = True

        self.db.add(AuditLog.create_log(
            user_id=admin_user_id,
            action="roster.item_removed_after_lock",
            resource_type="payment_roster",
            resource_id=str(roster_id),
            description=f"Removed item {item_id} (application {removed_app_id}) from LOCKED roster",
            new_values={
                "item_id": item_id,
                "application_id": removed_app_id,
                "reason": reason,
                "removed_amount": float(removed_amount) if removed_amount else 0,
            },
        ))
        return {
            "roster_id": roster_id,
            "removed_item_id": item_id,
            "qualified_count": total_count,
            "total_amount": float(total_amount),
            "excel_stale": True,
        }
```

- [ ] **Step 5: Re-run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_roster_item_removal_service.py -v
```

Expected: 4 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/roster_service.py \
        backend/app/tests/test_roster_item_removal_service.py
git commit -m "feat(roster): add LOCKED-roster item removal + revoked/suspended listing"
```

---

## Task 6: Backend endpoints — POST revoke / suspend

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py`
- Test: `backend/app/tests/test_revoke_suspend_endpoints.py`

- [ ] **Step 1: Write failing API tests**

Create `backend/app/tests/test_revoke_suspend_endpoints.py`:

```python
"""Pin: revoke + suspend POST endpoints return the ApiResponse envelope,
require admin auth, reject empty reason (422), surface conflict as 409,
surface non-allocated as 400."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_revoke_endpoint_success(client_admin: AsyncClient, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "violated"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["quota_allocation_status"] == "revoked"


@pytest.mark.asyncio
async def test_suspend_endpoint_success(client_admin: AsyncClient, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/suspend",
        json={"reason": "leave"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["quota_allocation_status"] == "suspended"


@pytest.mark.asyncio
async def test_revoke_empty_reason_returns_422(client_admin, allocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_revoke_twice_returns_409(client_admin, allocated_application):
    await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "first"},
    )
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "second"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_revoke_non_allocated_returns_400(client_admin, unallocated_application):
    resp = await client_admin.post(
        f"/api/v1/manual-distribution/applications/{unallocated_application.id}/revoke",
        json={"reason": "x"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_revoke_requires_admin(client_student, allocated_application):
    resp = await client_student.post(
        f"/api/v1/manual-distribution/applications/{allocated_application.id}/revoke",
        json={"reason": "x"},
    )
    assert resp.status_code in (401, 403)
```

(`client_admin` and `client_student` are the project's auth client fixtures — confirm names in existing tests, e.g. `grep -n "client_admin" backend/app/tests/*.py`.)

- [ ] **Step 2: Run, confirm failure (404 since endpoints don't exist)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_endpoints.py -v -k "revoke or suspend"
```

Expected: tests fail with 404.

- [ ] **Step 3: Add endpoints**

In `backend/app/api/v1/endpoints/manual_distribution.py`, add imports near the top:

```python
from app.schemas.application import RevokeRequest, SuspendRequest
```

Add two endpoints (place near the existing `finalize` endpoint):

```python
@router.post("/applications/{application_id}/revoke")
async def revoke_application_allocation(
    application_id: int,
    request: RevokeRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """撤銷已分發學生：從未鎖定造冊移除 + 標記 application 為 cancelled/revoked。"""
    service = ManualDistributionService(db)
    try:
        result = await service.revoke_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
        return {"success": True, "message": "已撤銷", "data": result}
    except ValueError as e:
        msg = str(e)
        if "already" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@router.post("/applications/{application_id}/suspend")
async def suspend_application_allocation(
    application_id: int,
    request: SuspendRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_admin_user),
):
    """停發已分發學生：從未鎖定造冊移除 + 標記 application 為 cancelled/suspended。"""
    service = ManualDistributionService(db)
    try:
        result = await service.suspend_allocation(
            application_id=application_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        await db.commit()
        return {"success": True, "message": "已停發", "data": result}
    except ValueError as e:
        msg = str(e)
        if "already" in msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e
```

(`HTTPException` and `status` are already imported in this file — confirm with `grep "from fastapi"`.)

- [ ] **Step 4: Re-run tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_endpoints.py -v
```

Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/manual_distribution.py \
        backend/app/tests/test_revoke_suspend_endpoints.py
git commit -m "feat(api): add revoke + suspend application endpoints"
```

---

## Task 7: Backend endpoints — GET revoked-suspended + DELETE locked item

**Files:**
- Modify: `backend/app/api/v1/endpoints/payment_rosters.py`
- Test: `backend/app/tests/test_revoke_suspend_endpoints.py` (append)

- [ ] **Step 1: Append failing API tests**

Append to `backend/app/tests/test_revoke_suspend_endpoints.py`:

```python
@pytest.mark.asyncio
async def test_get_revoked_suspended_returns_split_lists(
    client_admin, locked_roster_two_items
):
    resp = await client_admin.get(
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/revoked-suspended"
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data["revoked"]) == 1
    assert len(data["suspended"]) == 1


@pytest.mark.asyncio
async def test_delete_locked_item_returns_200_and_sets_stale(
    client_admin, locked_roster_two_items
):
    item_id = locked_roster_two_items.items[0].id
    resp = await client_admin.delete(
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/items/{item_id}",
        json={"reason": "cleanup"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["excel_stale"] is True


@pytest.mark.asyncio
async def test_delete_item_on_non_locked_returns_400(client_admin, draft_roster_with_item):
    item_id = draft_roster_with_item.items[0].id
    resp = await client_admin.delete(
        f"/api/v1/payment-rosters/{draft_roster_with_item.id}/items/{item_id}",
        json={"reason": "x"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_item_requires_admin(client_student, locked_roster_two_items):
    item_id = locked_roster_two_items.items[0].id
    resp = await client_student.delete(
        f"/api/v1/payment-rosters/{locked_roster_two_items.id}/items/{item_id}",
        json={"reason": "x"},
    )
    assert resp.status_code in (401, 403)
```

- [ ] **Step 2: Run, confirm failure (404)**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_endpoints.py::test_get_revoked_suspended_returns_split_lists -v
```

Expected: 404.

- [ ] **Step 3: Confirm payment_rosters.py session + auth pattern**

```bash
docker compose -f docker-compose.dev.yml exec backend grep -nE "get_sync_db|get_current" app/api/v1/endpoints/payment_rosters.py | head -10
```

Confirmed: this file uses `db: Session = Depends(get_sync_db)` and `current_user: User = Depends(get_current_user)` — **note** it's `get_current_user`, NOT `get_current_admin_user`. Admin-role check is enforced inline. Match this pattern.

- [ ] **Step 4: Add endpoints**

In `backend/app/api/v1/endpoints/payment_rosters.py`, add imports (place near existing schema/service imports):

```python
from app.models.user import UserRole
from app.schemas.payment_roster import (
    RemoveLockedItemRequest,
    RevokedSuspendedListResponse,
)
from app.services.roster_service import RosterService
```

Add a small helper inside the same file (right after the imports, or after the router declaration) for the inline admin check (mirrors the existing convention in this file — check the first endpoint to see exactly how admin-role checks are written; if there's already a helper named e.g. `_require_admin`, use that):

```python
def _require_admin(user) -> None:
    if user.role not in (UserRole.admin, UserRole.super_admin):
        raise HTTPException(status_code=403, detail="Admin role required")
```

Add the two endpoints (place near other LOCKED-roster admin endpoints in the file):

```python
@router.get("/{roster_id}/revoked-suspended")
def get_revoked_suspended(
    roster_id: int,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """List students still embedded in this roster whose allocation was
    later revoked or suspended."""
    _require_admin(current_user)
    svc = RosterService(db)
    try:
        result = svc.get_revoked_suspended_for_roster(roster_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    payload = RevokedSuspendedListResponse(**result).model_dump()
    return {"success": True, "message": "OK", "data": payload}


@router.delete("/{roster_id}/items/{item_id}")
def remove_locked_roster_item(
    roster_id: int,
    item_id: int,
    request: RemoveLockedItemRequest,
    db: Session = Depends(get_sync_db),
    current_user: User = Depends(get_current_user),
):
    """Hard-delete a single item from a LOCKED roster. Roster stays LOCKED;
    excel_stale is set to True; audit log written."""
    _require_admin(current_user)
    svc = RosterService(db)
    try:
        result = svc.remove_item_from_locked_roster(
            roster_id=roster_id,
            item_id=item_id,
            admin_user_id=current_user.id,
            reason=request.reason,
        )
        db.commit()
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "message": "已從造冊移除", "data": result}
```

(`Session`, `User`, `get_current_user`, `get_sync_db` are all already imported in this file.)

- [ ] **Step 5: Re-run all endpoint tests**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_endpoints.py -v
```

Expected: all 10 PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1/endpoints/payment_rosters.py \
        backend/app/tests/test_revoke_suspend_endpoints.py
git commit -m "feat(api): add roster revoked-suspended listing + locked-item delete"
```

---

## Task 8: Regenerate OpenAPI types + add frontend API client methods

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts`
- Modify: `frontend/lib/api/modules/payment-rosters.ts`
- Regenerate: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Regenerate OpenAPI types from running backend**

Ensure backend is running on `localhost:8000`. Then:

```bash
cd frontend
npm run api:generate
```

Expected: `lib/api/generated/schema.d.ts` updated, includes paths for `/api/v1/manual-distribution/applications/{application_id}/revoke`, `/suspend`, and `/api/v1/payment-rosters/{roster_id}/revoked-suspended`, `/items/{item_id}`.

- [ ] **Step 2: Add revoke/suspend methods to `manual-distribution.ts`**

At the end of the object literal that defines `manualDistribution` (look for the existing `finalize:` block — add after it inside the same object), append:

```typescript
    revoke: async (
      application_id: number,
      reason: string
    ): Promise<ApiResponse<{
      application_id: number;
      quota_allocation_status: "revoked";
      event_at: string;
      affected_unlocked_rosters: number[];
    }>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/applications/{application_id}/revoke",
        {
          params: { path: { application_id } },
          body: { reason },
        }
      );
      return toApiResponse(response) as ApiResponse<{
        application_id: number;
        quota_allocation_status: "revoked";
        event_at: string;
        affected_unlocked_rosters: number[];
      }>;
    },

    suspend: async (
      application_id: number,
      reason: string
    ): Promise<ApiResponse<{
      application_id: number;
      quota_allocation_status: "suspended";
      event_at: string;
      affected_unlocked_rosters: number[];
    }>> => {
      const response = await typedClient.raw.POST(
        "/api/v1/manual-distribution/applications/{application_id}/suspend",
        {
          params: { path: { application_id } },
          body: { reason },
        }
      );
      return toApiResponse(response) as ApiResponse<{
        application_id: number;
        quota_allocation_status: "suspended";
        event_at: string;
        affected_unlocked_rosters: number[];
      }>;
    },
```

- [ ] **Step 3: Add roster methods to `payment-rosters.ts`**

Open `frontend/lib/api/modules/payment-rosters.ts`. It uses the factory pattern (`export function createPaymentRostersApi() { return { ... } }`). Two changes:

(a) Add exported types at top of file (after imports):

```typescript
export interface RevokedSuspendedEntry {
  application_id: number;
  student_name: string;
  student_id_number: string;
  event_at: string;
  reason: string | null;
  item_id: number | null;
}

export interface RevokedSuspendedList {
  revoked: RevokedSuspendedEntry[];
  suspended: RevokedSuspendedEntry[];
}
```

(b) Inside the object returned by `createPaymentRostersApi()`, add the two new methods (place them alongside existing methods — match the indentation):

```typescript
    getRevokedSuspended: async (
      roster_id: number
    ): Promise<ApiResponse<RevokedSuspendedList>> => {
      const response = await typedClient.raw.GET(
        "/api/v1/payment-rosters/{roster_id}/revoked-suspended",
        { params: { path: { roster_id } } }
      );
      return toApiResponse(response) as ApiResponse<RevokedSuspendedList>;
    },

    removeItemFromLockedRoster: async (
      roster_id: number,
      item_id: number,
      reason: string | null
    ): Promise<ApiResponse<{
      roster_id: number;
      removed_item_id: number;
      qualified_count: number;
      total_amount: number;
      excel_stale: boolean;
    }>> => {
      const response = await typedClient.raw.DELETE(
        "/api/v1/payment-rosters/{roster_id}/items/{item_id}",
        {
          params: { path: { roster_id, item_id } },
          body: { reason },
        }
      );
      return toApiResponse(response) as ApiResponse<{
        roster_id: number;
        removed_item_id: number;
        qualified_count: number;
        total_amount: number;
        excel_stale: boolean;
      }>;
    },
```

Consumers call these via `apiClient.paymentRosters.getRevokedSuspended(...)` — the central `apiClient` (`frontend/lib/api/index.ts`) already lazy-instantiates the factory and exposes it as `.paymentRosters`.

- [ ] **Step 4: Run TypeScript build to verify**

```bash
cd frontend && npm run typecheck
```

Expected: no errors. If types mismatch the regenerated schema, adjust path strings to exactly match the generated `paths` keys.

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/manual-distribution.ts \
        frontend/lib/api/modules/payment-rosters.ts \
        frontend/lib/api/generated/schema.d.ts
git commit -m "feat(frontend-api): add revoke/suspend + roster item removal clients"
```

---

## Task 9: ManualDistributionPanel — replace ✕ with 撤｜停 buttons

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

- [ ] **Step 1: Update the column header (line ~1029-1034)**

Find the existing column header:
```tsx
<th
  rowSpan={2}
  className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-8 bg-red-50"
>
  取消
</th>
```

Replace with:
```tsx
<th
  rowSpan={2}
  className="px-1.5 py-1.5 border border-slate-200 text-center font-semibold text-[11px] w-16 bg-red-50"
>
  動作
</th>
```

- [ ] **Step 2: Add state + handlers at top of the component**

Inside the `ManualDistributionPanel` function, after existing `useState` hooks:

```tsx
const [revokeTarget, setRevokeTarget] = useState<DistributionStudent | null>(null);
const [suspendTarget, setSuspendTarget] = useState<DistributionStudent | null>(null);
const [actionReason, setActionReason] = useState("");
const [isActioning, setIsActioning] = useState(false);

const handleRevokeConfirm = async () => {
  if (!revokeTarget || actionReason.trim().length === 0) return;
  setIsActioning(true);
  try {
    const resp = await apiClient.manualDistribution.revoke(
      revokeTarget.application_id,
      actionReason.trim()
    );
    if (resp.success) {
      setSaveMessage({ type: "success", text: `已撤銷 ${revokeTarget.student_name}` });
      await fetchData();
    } else {
      setSaveMessage({ type: "error", text: resp.message || "撤銷失敗" });
    }
  } catch (err: any) {
    setSaveMessage({ type: "error", text: err?.message || "撤銷失敗" });
  } finally {
    setIsActioning(false);
    setRevokeTarget(null);
    setActionReason("");
  }
};

const handleSuspendConfirm = async () => {
  if (!suspendTarget || actionReason.trim().length === 0) return;
  setIsActioning(true);
  try {
    const resp = await apiClient.manualDistribution.suspend(
      suspendTarget.application_id,
      actionReason.trim()
    );
    if (resp.success) {
      setSaveMessage({ type: "success", text: `已停發 ${suspendTarget.student_name}` });
      await fetchData();
    } else {
      setSaveMessage({ type: "error", text: resp.message || "停發失敗" });
    }
  } catch (err: any) {
    setSaveMessage({ type: "error", text: err?.message || "停發失敗" });
  } finally {
    setIsActioning(false);
    setSuspendTarget(null);
    setActionReason("");
  }
};

const isFinalized = (student: DistributionStudent) =>
  student.status === "allocated" || student.status === "approved";
```

(`apiClient.manualDistribution.revoke` is the method added in Task 8. Confirm the existing component already imports `apiClient`.)

- [ ] **Step 3: Replace the row's ✕ cell (line ~1188-1212)**

Replace the existing `{/* Cancel allocation button */}` `<td>` block with:

```tsx
{/* 撤銷 / 停發 buttons (post-roster generation actions) */}
<td className="px-1 py-1.5 border-r border-slate-100 text-center">
  <div className="flex justify-center gap-0.5">
    <button
      onClick={() => {
        setRevokeTarget(student);
        setActionReason("");
      }}
      disabled={!isFinalized(student)}
      className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
        isFinalized(student)
          ? "bg-red-100 text-red-700 border-red-300 hover:bg-red-200 cursor-pointer"
          : "bg-slate-50 text-slate-300 border-slate-200 cursor-not-allowed"
      }`}
      title={isFinalized(student) ? "撤銷此學生獎學金（過往造冊需手動處理）" : "尚未分發，無法撤銷"}
    >
      撤
    </button>
    <button
      onClick={() => {
        setSuspendTarget(student);
        setActionReason("");
      }}
      disabled={!isFinalized(student)}
      className={`px-1.5 py-0.5 text-[10px] rounded border transition-colors ${
        isFinalized(student)
          ? "bg-orange-100 text-orange-700 border-orange-300 hover:bg-orange-200 cursor-pointer"
          : "bg-slate-50 text-slate-300 border-slate-200 cursor-not-allowed"
      }`}
      title={isFinalized(student) ? "停發此學生（過往造冊保留）" : "尚未分發，無法停發"}
    >
      停
    </button>
  </div>
</td>
```

- [ ] **Step 4: Add the two AlertDialogs near the end of the component's JSX (before closing fragment/div)**

```tsx
<AlertDialog open={!!revokeTarget} onOpenChange={(open) => !open && setRevokeTarget(null)}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>
        確認撤銷 {revokeTarget?.student_name} 的獎學金分配？
      </AlertDialogTitle>
      <AlertDialogDescription asChild>
        <div className="text-sm text-slate-600 space-y-2">
          <p>撤銷後：</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>此學生將從目前所有未鎖定造冊中移除</li>
            <li>此學生申請狀態變更為「已取消」</li>
            <li>已鎖定的歷史造冊需手動清除（清單會列在受影響造冊頁面提示）</li>
          </ul>
          <div className="pt-2">
            <label className="block text-sm font-medium mb-1">
              撤銷原因（必填）
            </label>
            <textarea
              className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
              rows={3}
              maxLength={500}
              value={actionReason}
              onChange={(e) => setActionReason(e.target.value)}
              placeholder="請說明撤銷原因…"
            />
          </div>
        </div>
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel disabled={isActioning}>取消</AlertDialogCancel>
      <AlertDialogAction
        disabled={isActioning || actionReason.trim().length === 0}
        onClick={handleRevokeConfirm}
        className="bg-red-600 hover:bg-red-700 text-white"
      >
        {isActioning ? "處理中…" : "確認撤銷"}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>

<AlertDialog open={!!suspendTarget} onOpenChange={(open) => !open && setSuspendTarget(null)}>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>
        確認停發 {suspendTarget?.student_name} 的獎學金分配？
      </AlertDialogTitle>
      <AlertDialogDescription asChild>
        <div className="text-sm text-slate-600 space-y-2">
          <p>停發後：</p>
          <ul className="list-disc pl-5 space-y-1">
            <li>此學生將從目前所有未鎖定造冊中移除</li>
            <li>此學生申請狀態變更為「已取消」</li>
            <li>已鎖定的歷史造冊不受影響（金額已發放保留）</li>
          </ul>
          <div className="pt-2">
            <label className="block text-sm font-medium mb-1">
              停發原因（必填）
            </label>
            <textarea
              className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
              rows={3}
              maxLength={500}
              value={actionReason}
              onChange={(e) => setActionReason(e.target.value)}
              placeholder="請說明停發原因…"
            />
          </div>
        </div>
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel disabled={isActioning}>取消</AlertDialogCancel>
      <AlertDialogAction
        disabled={isActioning || actionReason.trim().length === 0}
        onClick={handleSuspendConfirm}
        className="bg-orange-600 hover:bg-orange-700 text-white"
      >
        {isActioning ? "處理中…" : "確認停發"}
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

- [ ] **Step 5: Manual smoke test**

```bash
docker compose -f docker-compose.dev.yml up -d
```

Browse to `http://localhost:3000`, log in as `admin@nycu.edu.tw`, open Manual Distribution Panel for a finalized scholarship, verify:
- Row has `撤｜停` buttons (red + orange)
- Pre-finalize row buttons are disabled (greyed)
- Clicking 撤 opens dialog; confirm button stays disabled until reason filled
- Filling reason + confirm → success toast, student row updates

- [ ] **Step 6: Commit**

```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat(ui): replace cancel column with revoke/suspend buttons + dialogs"
```

---

## Task 10: RosterDetailDialog — status change notice + Excel-stale banner

**Files:**
- Modify: `frontend/components/roster/RosterDetailDialog.tsx`

- [ ] **Step 1: Read the existing component**

```bash
sed -n '1,80p' frontend/components/roster/RosterDetailDialog.tsx
```

Note where the dialog body starts and where to insert the new panel (at the very top of the body, above the existing roster details).

- [ ] **Step 2: Add fetch hook for revoked/suspended list**

Add imports at top of file (`apiClient` should already be imported or accessible — check the existing file. If it imports from `@/lib/api/index`, reuse that):

```tsx
import { apiClient } from "@/lib/api";
import type { RevokedSuspendedList } from "@/lib/api/modules/payment-rosters";
```

Inside the component, after existing `useState` hooks:

```tsx
const [revokedSuspended, setRevokedSuspended] = useState<RevokedSuspendedList>({
  revoked: [],
  suspended: [],
});
const [removingItemId, setRemovingItemId] = useState<number | null>(null);

useEffect(() => {
  if (!open || !roster || roster.status !== "locked") return;
  let cancelled = false;
  apiClient.paymentRosters.getRevokedSuspended(roster.id).then((resp) => {
    if (!cancelled && resp.success && resp.data) {
      setRevokedSuspended(resp.data);
    }
  });
  return () => {
    cancelled = true;
  };
}, [open, roster?.id, roster?.status]);

const handleRemoveLockedItem = async (itemId: number, studentName: string) => {
  if (!roster) return;
  if (!confirm(`確認從本造冊移除 ${studentName}？(此操作會將造冊標記為「需重新匯出 Excel」)`)) return;
  setRemovingItemId(itemId);
  try {
    const resp = await apiClient.paymentRosters.removeItemFromLockedRoster(roster.id, itemId, null);
    if (resp.success) {
      const refresh = await apiClient.paymentRosters.getRevokedSuspended(roster.id);
      if (refresh.success && refresh.data) setRevokedSuspended(refresh.data);
      // Tell parent to refetch — prop name varies. Check existing prop list on
      // RosterDetailDialog: likely `onChanged` or `onRefresh`. If neither
      // exists, lift state up later — for now, call `window.location.reload()`
      // is acceptable as a temporary measure but prefer a callback if one is wired.
      onChanged?.();
    } else {
      alert(resp.message || "移除失敗");
    }
  } finally {
    setRemovingItemId(null);
  }
};
```

Before pasting, run `grep "onChanged\|onRefresh\|onUpdate" frontend/components/roster/RosterDetailDialog.tsx` to confirm which callback prop already exists; if none, add one to the props type and wire it from the parent.

- [ ] **Step 3: Render the panel at the top of the dialog body**

Insert this JSX inside the dialog's content section, immediately after the dialog header:

```tsx
{roster?.status === "locked" && (
  <>
    {roster.excel_stale && (
      <div className="mb-3 p-3 border border-amber-300 bg-amber-50 rounded flex items-center justify-between">
        <span className="text-amber-800 text-sm">
          ⚠️ 造冊資料已變更，請重新匯出 Excel
        </span>
        {/* Reuse existing "重新匯出 Excel" handler from this component if it exists,
            otherwise leave the button absent for now. */}
      </div>
    )}

    {(revokedSuspended.revoked.length > 0 || revokedSuspended.suspended.length > 0) && (
      <div className="mb-4 space-y-3">
        {revokedSuspended.revoked.length > 0 && (
          <details open className="border border-red-300 bg-red-50 rounded p-3">
            <summary className="text-red-800 font-semibold cursor-pointer text-sm">
              ⚠️ 此造冊有 {revokedSuspended.revoked.length} 位學生被撤銷，請手動處理
            </summary>
            <ul className="mt-2 space-y-2">
              {revokedSuspended.revoked.map((s) => (
                <li key={s.application_id} className="text-sm flex items-start justify-between gap-3">
                  <div>
                    <div>
                      <span className="font-medium">{s.student_name}</span>
                      <span className="text-slate-500"> ({s.student_id_number})</span>
                      <span className="text-xs text-slate-500 ml-2">
                        撤銷於 {new Date(s.event_at).toLocaleDateString()}
                      </span>
                    </div>
                    {s.reason && (
                      <div className="text-xs text-slate-600">原因：{s.reason}</div>
                    )}
                  </div>
                  {s.item_id !== null && (
                    <button
                      onClick={() => handleRemoveLockedItem(s.item_id!, s.student_name)}
                      disabled={removingItemId === s.item_id}
                      className="px-2 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700 disabled:opacity-50"
                    >
                      {removingItemId === s.item_id ? "處理中…" : "從本造冊移除"}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}

        {revokedSuspended.suspended.length > 0 && (
          <details open className="border border-slate-300 bg-slate-50 rounded p-3">
            <summary className="text-slate-700 font-semibold cursor-pointer text-sm">
              ℹ️ 此造冊有 {revokedSuspended.suspended.length} 位學生被停發（僅資訊）
            </summary>
            <ul className="mt-2 space-y-1">
              {revokedSuspended.suspended.map((s) => (
                <li key={s.application_id} className="text-sm">
                  <span className="font-medium">{s.student_name}</span>
                  <span className="text-slate-500"> ({s.student_id_number})</span>
                  <span className="text-xs text-slate-500 ml-2">
                    停發於 {new Date(s.event_at).toLocaleDateString()}
                  </span>
                  {s.reason && (
                    <div className="text-xs text-slate-600">原因：{s.reason}</div>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}
      </div>
    )}
  </>
)}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd frontend && npm run typecheck
```

Expected: no errors.

- [ ] **Step 5: Manual smoke test**

Open a LOCKED roster's detail dialog and verify:
- Without any revoked/suspended students → panel is hidden
- After revoking a student (use Task 9 button) → re-open dialog, panel appears with name
- Click [從本造冊移除] → confirm → name disappears, Excel-stale banner appears

- [ ] **Step 6: Commit**

```bash
git add frontend/components/roster/RosterDetailDialog.tsx
git commit -m "feat(ui): roster status-change notice + locked-item removal button"
```

---

## Task 11: Playwright E2E test

**Files:**
- Create: `frontend/e2e/admin/revoke-suspend.spec.ts`

- [ ] **Step 1: Write the E2E spec**

Create `frontend/e2e/admin/revoke-suspend.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";

/**
 * Pin: admin can revoke a finalized student from Manual Distribution Panel
 * and the LOCKED-roster detail dialog surfaces the revoked student with a
 * working "從本造冊移除" button.
 *
 * Pre-req: seeded data must contain a scholarship that's already finalized
 * (distribution_executed=True) and has at least one LOCKED payment_roster
 * containing one of the allocated students. Use `./scripts/reset_database.sh`
 * + the seed flow to set this up if running locally.
 */
test.describe("admin revoke/suspend distribution", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("http://localhost:3000/login");
    await page.fill('input[name="email"]', "admin@nycu.edu.tw");
    await page.fill('input[name="password"]', "admin123");
    await page.click('button[type="submit"]');
    await page.waitForURL("**/admin/**");
  });

  test("撤 button opens dialog with disabled confirm until reason filled", async ({ page }) => {
    await page.goto("http://localhost:3000/admin/manual-distribution");
    // Wait for table to load
    await page.waitForSelector('table th:has-text("動作")');
    // Click first 撤 button
    const revokeBtn = page.locator('button[title*="撤銷此學生"]').first();
    await revokeBtn.click();
    // Confirm button should be disabled when reason is empty
    const confirm = page.locator('button:has-text("確認撤銷")');
    await expect(confirm).toBeDisabled();
    // Fill reason
    await page.fill('textarea[placeholder*="撤銷原因"]', "test revoke");
    await expect(confirm).toBeEnabled();
    await confirm.click();
    // Success toast
    await expect(page.locator('text=已撤銷')).toBeVisible({ timeout: 5000 });
  });

  test("locked roster dialog shows revoked panel and item-remove works", async ({ page }) => {
    await page.goto("http://localhost:3000/admin/payment-rosters");
    // Open first LOCKED roster's detail dialog (CSS depends on the existing list UI; adjust as needed)
    const lockedRow = page.locator('tr:has-text("已鎖定")').first();
    await lockedRow.locator('button:has-text("查看")').click();
    // Wait for revoked/suspended panel
    const panel = page.locator('text=請手動處理');
    await expect(panel).toBeVisible({ timeout: 5000 });
    // Click 從本造冊移除
    page.once('dialog', d => d.accept());
    await page.locator('button:has-text("從本造冊移除")').first().click();
    // Excel stale banner appears
    await expect(page.locator('text=請重新匯出 Excel')).toBeVisible({ timeout: 5000 });
  });
});
```

- [ ] **Step 2: Run E2E (with backend + frontend up)**

```bash
docker compose -f docker-compose.dev.yml up -d
cd frontend && npx playwright test e2e/admin/revoke-suspend.spec.ts --reporter=list
```

Expected: 2 PASS. If selectors don't match (because the existing roster list/dialog UI differs), adjust selectors — the spec's *intent* is what matters: pin the user-visible flow.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/admin/revoke-suspend.spec.ts
git commit -m "test(e2e): revoke + locked-roster item removal flow"
```

---

## Task 12: Integration test — multi-roster end-to-end

**Files:**
- Create: `backend/app/tests/test_revoke_suspend_flow.py`

- [ ] **Step 1: Write the integration test**

Create `backend/app/tests/test_revoke_suspend_flow.py`:

```python
"""Pin: revoke flow across two rosters — one LOCKED, one DRAFT — leaves
LOCKED items intact while removing them from DRAFT, and the GET
revoked-suspended endpoint reports the LOCKED-roster name."""

import pytest
from sqlalchemy import select

from app.models.application import Application, ApplicationStatus
from app.models.payment_roster import PaymentRosterItem, RosterStatus
from app.services.manual_distribution_service import ManualDistributionService
from app.services.roster_service import RosterService


@pytest.mark.asyncio
async def test_revoke_spans_locked_and_draft_rosters(
    async_db_session,
    sync_session,
    allocated_application,
    locked_roster_with_item,
    draft_roster_with_item,
    admin_user,
):
    """Revoke a student who appears in both a LOCKED and a DRAFT roster.
    Expect: DRAFT item gone, LOCKED item still present, revoked-suspended
    listing reports the student under 'revoked' for the LOCKED roster."""

    svc = ManualDistributionService(async_db_session)
    await svc.revoke_allocation(allocated_application.id, admin_user.id, "spans both")
    await async_db_session.commit()

    # DRAFT item gone
    draft_item_id = draft_roster_with_item.items[0].id
    assert await async_db_session.get(PaymentRosterItem, draft_item_id) is None

    # LOCKED item still present
    locked_item_id = locked_roster_with_item.items[0].id
    assert await async_db_session.get(PaymentRosterItem, locked_item_id) is not None

    # Application updated
    refreshed = await async_db_session.get(Application, allocated_application.id)
    assert refreshed.status == ApplicationStatus.cancelled
    assert refreshed.quota_allocation_status == "revoked"

    # GET revoked-suspended reports it
    roster_svc = RosterService(sync_session)
    listing = roster_svc.get_revoked_suspended_for_roster(locked_roster_with_item.id)
    assert len(listing["revoked"]) == 1
    assert listing["revoked"][0].application_id == allocated_application.id

    # Admin removes it from LOCKED roster
    roster_svc.remove_item_from_locked_roster(
        locked_roster_with_item.id, locked_item_id, admin_user.id, "manual cleanup"
    )
    sync_session.commit()
    sync_session.refresh(locked_roster_with_item)
    assert locked_roster_with_item.excel_stale is True
    assert locked_roster_with_item.status == RosterStatus.LOCKED
```

- [ ] **Step 2: Run**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest \
  app/tests/test_revoke_suspend_flow.py -v
```

Expected: 1 PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_revoke_suspend_flow.py
git commit -m "test(integration): revoke flow across locked + draft rosters"
```

---

## Task 13: Final verification + open PR

- [ ] **Step 1: Run full backend test suite**

```bash
docker compose -f docker-compose.dev.yml exec backend pytest -q
```

Expected: all green (or no new failures relative to `main`).

- [ ] **Step 2: Frontend typecheck + build**

```bash
cd frontend && npm run typecheck && npm run build
```

Expected: clean.

- [ ] **Step 3: Push branch + open PR**

```bash
git push -u origin HEAD
gh pr create --title "feat: revoke/suspend scholarship distribution" --body "$(cat <<'EOF'
## Summary
- Split the admin Manual Distribution Panel's row ✕ into 撤 (red) and 停 (orange) buttons
- 撤銷 / 停發 hard-deletes items in non-LOCKED rosters; LOCKED rosters surface a manual-cleanup panel
- Roster detail dialog shows revoked/suspended students + per-row [從本造冊移除] button + Excel-stale banner

Spec: docs/superpowers/specs/2026-05-21-revoke-suspend-distribution-design.md

## Test plan
- [x] Backend unit tests (`test_revoke_suspend_service.py`, `test_roster_item_removal_service.py`, `test_revoke_suspend_schemas.py`, `test_revoke_suspend_models.py`)
- [x] Backend endpoint tests (`test_revoke_suspend_endpoints.py`)
- [x] Backend integration test (`test_revoke_suspend_flow.py`)
- [x] Frontend Playwright E2E (`e2e/admin/revoke-suspend.spec.ts`)
- [ ] Manual smoke on http://localhost:3000 as admin@nycu.edu.tw
EOF
)"
```

---

## Notes for the executing agent

- **Match existing patterns first.** Where this plan says "use `Depends(get_db)`" or "use `Session`", first grep the target file to confirm the project's existing dep symbol — the manual_distribution endpoint is async (`get_db`), payment_rosters endpoint is sync (`get_sync_db`). Same applies to test fixtures.
- **Don't skip migrations.** If a step says run `alembic upgrade head` and it fails, fix the migration — don't `git stash` past it.
- **Frequent commits.** Every task ends with a commit. Don't bundle.
- **Run the test you wrote.** TDD: write, fail, implement, pass, commit.
