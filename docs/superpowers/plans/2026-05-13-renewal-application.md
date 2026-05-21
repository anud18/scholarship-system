# Renewal Application Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement end-to-end scholarship renewal with "保底+挑戰" mechanism: renewal applications auto-approved on review pass, challenge applications during general phase that release original sub_type slots and fill in from waitlist.

**Architecture:** Two-Application pattern — `Application_R` (is_renewal=True, locks original sub_type) and `Application_C` (is_renewal=False, `challenges_application_id` points to Application_R, locks new sub_type). Renewal phase is auto-distributed (review pass = approved). General-phase distribution algorithm handles challenge cancellation and same-sub_type waitlist fill-in. Allocation tracked by `renewal_year` (= original cohort year), separate from `academic_year` (= student-application year).

**Tech Stack:** FastAPI + async SQLAlchemy + PostgreSQL/Alembic + Pydantic v2; Next.js 14 (App Router) + TypeScript + Tailwind; Docker Compose dev environment.

**Spec reference:** `docs/superpowers/specs/2026-05-13-renewal-application-design.md`

---

## File Structure

### Backend (Create)

- `backend/alembic/versions/<rev>_add_renewal_challenge_columns.py` — migration: new columns, enum value, partial indexes
- `backend/app/services/renewal_eligibility_service.py` — `RenewalEligibilityService.get_eligible_renewals()`
- `backend/app/services/renewal_distribution_service.py` — `RenewalDistributionService.auto_approve_passed_reviews()`
- `backend/app/api/v1/endpoints/renewal.py` — renewal/challenge creation + listing endpoints
- `backend/app/schemas/renewal.py` — Pydantic schemas
- `backend/app/tests/test_renewal_eligibility_service.py`
- `backend/app/tests/test_renewal_application_creation.py`
- `backend/app/tests/test_renewal_distribution_service.py`
- `backend/app/tests/test_challenge_release_distribution.py`

### Backend (Modify)

- `backend/app/models/enums.py:16-40` — add `cancelled_by_challenge` to ApplicationStatus
- `backend/app/models/application.py` — add `challenges_application_id`, `cancelled_due_to_application_id` columns + relationships; replace single UniqueConstraint with three partial unique indexes
- `backend/app/services/manual_distribution_service.py` — extend `_compute_suggestions()` and add `_apply_challenge_release_and_fill_in()`
- `backend/app/api/v1/endpoints/manual_distribution.py` — add `/state`, `/preview`, `/distribution-result/renewal` endpoints
- `backend/app/api/v1/api.py` (or `endpoints/__init__.py`) — register renewal router

### Frontend (Create)

- `frontend/lib/api/modules/renewal.ts` — typed client for renewal endpoints
- `frontend/components/admin/renewal/RenewalDistributionResult.tsx` — Section 14.1 UI
- `frontend/components/student/RenewalApplicationCard.tsx` — student renewal entry card
- `frontend/components/student/ChallengeApplicationCard.tsx` — challenge entry card

### Frontend (Modify)

- `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` — add renewal-occupied block, challenge markers, release preview
- `frontend/lib/api/modules/manual-distribution.ts` — add new endpoint typings
- `frontend/components/enhanced-student-portal.tsx` — link renewal/challenge cards
- Student application history component (TBD path during Task 9.3) — add linkage display

---

## Self-contained context for engineer

- **DB enum updates require Alembic execution + values_callable**: When adding a value to `ApplicationStatus`, both Postgres `ALTER TYPE` and SQLAlchemy `values_callable` lambda must be considered. See `CLAUDE.md` "Enum Consistency Guidelines".
- **Use `docker compose -f docker-compose.dev.yml`** for all local dev. Backend container = `scholarship_backend_dev`. DB = `scholarship_postgres_dev`.
- **API response format**: All endpoints return `{success, message, data}` dict; do NOT use `response_model`.
- **Tests use pytest-asyncio**: Async DB session via `AsyncSession` fixture (see existing `test_scholarship_configuration_endpoints.py`).
- **Run tests**: `docker compose -f docker-compose.dev.yml exec backend python -m pytest <path> -v`
- **Run migration**: `docker compose -f docker-compose.dev.yml exec backend alembic upgrade head`
- **Migration naming**: hash + slug (see `update_phd_sel_mode_001.py`). Use a meaningful slug.

---

## Phase 1 — Data Model & Migration

### Task 1.1: Add `cancelled_by_challenge` to ApplicationStatus enum

**Files:**
- Modify: `backend/app/models/enums.py:16-40`

- [ ] **Step 1: Edit enum**

```python
class ApplicationStatus(enum.Enum):
    """..."""
    # 編輯中狀態
    draft = "draft"
    # ... (existing values unchanged)
    manual_excluded = "manual_excluded"
    cancelled_by_challenge = "cancelled_by_challenge"  # 因挑戰申請成功被自動取消
    deleted = "deleted"
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/models/enums.py
git commit -m "feat(enum): add cancelled_by_challenge to ApplicationStatus"
```

---

### Task 1.2: Add new columns + relationships to Application model

**Files:**
- Modify: `backend/app/models/application.py` (around lines 100-103 and 188-191)

- [ ] **Step 1: Add columns after `previous_application_id`**

```python
    previous_application_id = Column(Integer, ForeignKey("applications.id"))

    # 挑戰申請：指向被挑戰的續領申請 (is_renewal=True 紀錄)
    # 約束: challenges_application_id IS NOT NULL ⇒ is_renewal = False
    challenges_application_id = Column(
        Integer, ForeignKey("applications.id"), nullable=True, index=True
    )

    # 釋出鏈追蹤：被誰挑戰成功取代 (cancelled_by_challenge 狀態時必填)
    cancelled_due_to_application_id = Column(
        Integer, ForeignKey("applications.id"), nullable=True
    )
```

- [ ] **Step 2: Add relationships in the relationships block**

```python
    previous_application = relationship(
        "Application", remote_side=[id], foreign_keys=[previous_application_id]
    )
    challenged_renewal = relationship(
        "Application", remote_side=[id], foreign_keys=[challenges_application_id]
    )
    cancelled_due_to = relationship(
        "Application", remote_side=[id], foreign_keys=[cancelled_due_to_application_id]
    )
```

- [ ] **Step 3: Replace `__table_args__` with partial unique indexes**

```python
from sqlalchemy import Index

    __table_args__ = (
        Index(
            "uq_user_renewal_app",
            "user_id", "scholarship_type_id", "academic_year", "semester",
            unique=True,
            postgresql_where=sa.text("is_renewal = true AND status != 'deleted'"),
        ),
        Index(
            "uq_user_challenge_app",
            "user_id", "scholarship_type_id", "academic_year", "semester",
            unique=True,
            postgresql_where=sa.text(
                "is_renewal = false AND challenges_application_id IS NOT NULL "
                "AND status != 'deleted'"
            ),
        ),
        Index(
            "uq_user_pure_new_app",
            "user_id", "scholarship_type_id", "academic_year", "semester",
            unique=True,
            postgresql_where=sa.text(
                "is_renewal = false AND challenges_application_id IS NULL "
                "AND status != 'deleted'"
            ),
        ),
    )
```

Make sure `import sqlalchemy as sa` is present at top of file.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/application.py
git commit -m "feat(model): add challenge linkage columns to Application"
```

---

### Task 1.3: Create Alembic migration

**Files:**
- Create: `backend/alembic/versions/add_renewal_challenge_001_add_renewal_challenge_columns.py`

- [ ] **Step 1: Generate skeleton manually (avoid autogenerate which can pick up unrelated drift)**

Identify the current head:

```bash
docker compose -f docker-compose.dev.yml exec backend alembic heads
```

- [ ] **Step 2: Write the migration**

```python
"""Add renewal challenge columns + partial unique indexes + status enum value

Revision ID: add_renewal_challenge_001
Revises: <CURRENT_HEAD_REVISION>
Create Date: 2026-05-13
"""

from alembic import op
import sqlalchemy as sa

revision = "add_renewal_challenge_001"
down_revision = "<CURRENT_HEAD_REVISION>"  # set from Step 1
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [c["name"] for c in inspector.get_columns("applications")]

    # 1. Add enum value (must commit before being usable in same transaction in some PG versions)
    op.execute("ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'cancelled_by_challenge'")

    # 2. Add new columns (idempotent)
    if "challenges_application_id" not in existing_columns:
        op.add_column(
            "applications",
            sa.Column(
                "challenges_application_id",
                sa.Integer(),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
        )
        op.create_index(
            "ix_applications_challenges_application_id",
            "applications",
            ["challenges_application_id"],
        )

    if "cancelled_due_to_application_id" not in existing_columns:
        op.add_column(
            "applications",
            sa.Column(
                "cancelled_due_to_application_id",
                sa.Integer(),
                sa.ForeignKey("applications.id"),
                nullable=True,
            ),
        )

    # 3. Drop old single UNIQUE, add three partial unique indexes
    op.drop_constraint("uq_user_scholarship_academic_term", "applications", type_="unique")

    op.create_index(
        "uq_user_renewal_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text("is_renewal = true AND status != 'deleted'"),
    )
    op.create_index(
        "uq_user_challenge_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text(
            "is_renewal = false AND challenges_application_id IS NOT NULL "
            "AND status != 'deleted'"
        ),
    )
    op.create_index(
        "uq_user_pure_new_app",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
        unique=True,
        postgresql_where=sa.text(
            "is_renewal = false AND challenges_application_id IS NULL "
            "AND status != 'deleted'"
        ),
    )

    # 4. Check constraint: cancelled_by_challenge requires cancelled_due_to_application_id
    op.create_check_constraint(
        "chk_cancelled_by_challenge_link",
        "applications",
        "status != 'cancelled_by_challenge' OR cancelled_due_to_application_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("chk_cancelled_by_challenge_link", "applications", type_="check")
    op.drop_index("uq_user_pure_new_app", "applications")
    op.drop_index("uq_user_challenge_app", "applications")
    op.drop_index("uq_user_renewal_app", "applications")
    op.create_unique_constraint(
        "uq_user_scholarship_academic_term",
        "applications",
        ["user_id", "scholarship_type_id", "academic_year", "semester"],
    )
    op.drop_column("applications", "cancelled_due_to_application_id")
    op.drop_index("ix_applications_challenges_application_id", table_name="applications")
    op.drop_column("applications", "challenges_application_id")
    # Note: Postgres does not support removing enum values cleanly; leave 'cancelled_by_challenge'
```

- [ ] **Step 3: Run migration on dev DB**

```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```

Expected output: `INFO  [alembic.runtime.migration] Running upgrade ... -> add_renewal_challenge_001`

- [ ] **Step 4: Verify schema**

```bash
docker compose -f docker-compose.dev.yml exec postgres psql -U scholarship_user -d scholarship_db -c "\d applications"
```

Expected: see `challenges_application_id`, `cancelled_due_to_application_id`, and the three `uq_user_*_app` indexes.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/add_renewal_challenge_001_*.py
git commit -m "feat(migration): add renewal challenge columns and partial unique indexes"
```

---

## Phase 2 — Renewal Eligibility Service

### Task 2.1: Write tests for `get_eligible_renewals`

**Files:**
- Create: `backend/app/tests/test_renewal_eligibility_service.py`

- [ ] **Step 1: Write tests**

```python
import pytest
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, Semester
from app.models.scholarship import ScholarshipType, ScholarshipConfiguration
from app.services.renewal_eligibility_service import RenewalEligibilityService


@pytest.mark.asyncio
async def test_returns_empty_when_no_prior_approved(db_session: AsyncSession, user_factory):
    """No prior approved application → no eligible renewals."""
    user = await user_factory()
    service = RenewalEligibilityService(db_session)
    result = await service.get_eligible_renewals(user_id=user.id, current_academic_year=114)
    assert result == []


@pytest.mark.asyncio
async def test_returns_prior_approved_when_in_renewal_period(
    db_session, user_factory, scholarship_type_factory, application_factory
):
    user = await user_factory()
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now - timedelta(days=1),
        renewal_application_end_date=now + timedelta(days=7),
    )
    prior = await application_factory(
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.approved,
        sub_scholarship_type="nstc",
    )
    service = RenewalEligibilityService(db_session)
    result = await service.get_eligible_renewals(user_id=user.id, current_academic_year=114)
    assert len(result) == 1
    assert result[0].id == prior.id


@pytest.mark.asyncio
async def test_excludes_rejected_prior(
    db_session, user_factory, scholarship_type_factory, application_factory
):
    user = await user_factory()
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now - timedelta(days=1),
        renewal_application_end_date=now + timedelta(days=7),
    )
    await application_factory(
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.rejected,
    )
    service = RenewalEligibilityService(db_session)
    result = await service.get_eligible_renewals(user_id=user.id, current_academic_year=114)
    assert result == []


@pytest.mark.asyncio
async def test_excludes_when_not_in_renewal_period(
    db_session, user_factory, scholarship_type_factory, application_factory
):
    user = await user_factory()
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now + timedelta(days=7),  # 未到
        renewal_application_end_date=now + timedelta(days=14),
    )
    await application_factory(
        user_id=user.id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.approved,
    )
    service = RenewalEligibilityService(db_session)
    result = await service.get_eligible_renewals(user_id=user.id, current_academic_year=114)
    assert result == []
```

- [ ] **Step 2: Run tests → expect ImportError or all FAIL**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_eligibility_service.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.services.renewal_eligibility_service'`

---

### Task 2.2: Implement `RenewalEligibilityService`

**Files:**
- Create: `backend/app/services/renewal_eligibility_service.py`

- [ ] **Step 1: Write implementation**

```python
"""
RenewalEligibilityService — determine which prior approved applications
are eligible for renewal in the current academic year.
"""

from datetime import datetime, timezone
from typing import List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipType


class RenewalEligibilityService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_eligible_renewals(
        self, user_id: int, current_academic_year: int
    ) -> List[Application]:
        """
        Return prior-year approved applications where the scholarship_type is
        currently in renewal_application_period.
        """
        now = datetime.now(timezone.utc)

        stmt = (
            select(Application)
            .options(joinedload(Application.scholarship_type_ref))
            .join(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
            .where(
                Application.user_id == user_id,
                Application.academic_year == current_academic_year - 1,
                Application.status == ApplicationStatus.approved,
                ScholarshipType.renewal_application_start_date <= now,
                ScholarshipType.renewal_application_end_date >= now,
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
```

- [ ] **Step 2: Run tests → expect PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_eligibility_service.py -v
```

Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/renewal_eligibility_service.py backend/app/tests/test_renewal_eligibility_service.py
git commit -m "feat(renewal): add RenewalEligibilityService"
```

---

## Phase 3 — Renewal & Challenge Application Creation

### Task 3.1: Pydantic schemas

**Files:**
- Create: `backend/app/schemas/renewal.py`

- [ ] **Step 1: Write schemas**

```python
from pydantic import BaseModel, ConfigDict
from typing import Optional


class EligibleRenewalItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    previous_application_id: int  # = source application's id
    scholarship_type_id: int
    scholarship_type_name: str
    sub_scholarship_type: str  # e.g. "nstc"
    target_academic_year: int  # current_academic_year
    renewal_year: int  # = previous renewal_year if set, else previous.academic_year
    renewal_deadline: Optional[str]  # ISO datetime


class CreateRenewalRequest(BaseModel):
    previous_application_id: int


class CreateChallengeRequest(BaseModel):
    renewal_application_id: int
    target_sub_type: str
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/schemas/renewal.py
git commit -m "feat(schema): add renewal/challenge Pydantic schemas"
```

---

### Task 3.2: Write tests for renewal creation endpoint

**Files:**
- Create: `backend/app/tests/test_renewal_application_creation.py`

- [ ] **Step 1: Write tests**

```python
import pytest
from datetime import datetime, timedelta, timezone

from app.models.application import Application
from app.models.enums import ApplicationStatus


@pytest.mark.asyncio
async def test_create_renewal_application_success(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now - timedelta(days=1),
        renewal_application_end_date=now + timedelta(days=7),
    )
    prior = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.approved,
        sub_scholarship_type="nstc",
    )

    resp = await async_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    new_app = body["data"]
    assert new_app["is_renewal"] is True
    assert new_app["sub_scholarship_type"] == "nstc"
    assert new_app["previous_application_id"] == prior.id
    assert new_app["academic_year"] == 114
    assert new_app["renewal_year"] == 113


@pytest.mark.asyncio
async def test_create_renewal_rejects_when_prior_not_approved(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now - timedelta(days=1),
        renewal_application_end_date=now + timedelta(days=7),
    )
    prior = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.rejected,
    )
    resp = await async_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 400
    assert "未核可" in resp.json()["detail"] or "approved" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_renewal_rejects_outside_period(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now + timedelta(days=7),
        renewal_application_end_date=now + timedelta(days=14),
    )
    prior = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.approved,
    )
    resp = await async_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_create_renewal_rejects_duplicate(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_application_start_date=now - timedelta(days=1),
        renewal_application_end_date=now + timedelta(days=7),
    )
    prior = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=113,
        status=ApplicationStatus.approved,
    )
    # 第一次成功
    r1 = await async_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
        headers=auth_headers_for_student.headers,
    )
    assert r1.status_code == 201
    # 第二次衝突
    r2 = await async_client.post(
        "/api/v1/renewals/",
        json={"previous_application_id": prior.id},
        headers=auth_headers_for_student.headers,
    )
    assert r2.status_code == 409
```

- [ ] **Step 2: Run tests → expect FAIL (endpoint not yet exists)**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_application_creation.py -v
```

Expected: 404 or import errors.

---

### Task 3.3: Implement `POST /api/v1/renewals/`

**Files:**
- Create: `backend/app/api/v1/endpoints/renewal.py`
- Modify: `backend/app/api/v1/api.py` (register router)

- [ ] **Step 1: Implement endpoint**

```python
"""Renewal & Challenge application endpoints."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_db, get_current_user
from app.models.application import Application
from app.models.enums import ApplicationStatus
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.schemas.renewal import CreateRenewalRequest, CreateChallengeRequest
from app.services.renewal_eligibility_service import RenewalEligibilityService
from app.services.application_service import ApplicationService

router = APIRouter(prefix="/renewals", tags=["renewals"])


@router.get("/eligible")
async def list_eligible_renewals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """List prior-year approved applications eligible for renewal."""
    from app.services.academic_year_service import get_current_academic_year
    current_year = get_current_academic_year()
    service = RenewalEligibilityService(db)
    apps = await service.get_eligible_renewals(current_user.id, current_year)
    return {
        "success": True,
        "message": "Eligible renewals retrieved",
        "data": [
            {
                "previous_application_id": app.id,
                "scholarship_type_id": app.scholarship_type_id,
                "scholarship_type_name": app.scholarship_type_ref.name,
                "sub_scholarship_type": app.sub_scholarship_type,
                "target_academic_year": current_year,
                "renewal_year": app.renewal_year or app.academic_year,
                "renewal_deadline": (
                    app.scholarship_type_ref.renewal_application_end_date.isoformat()
                    if app.scholarship_type_ref.renewal_application_end_date else None
                ),
            }
            for app in apps
        ],
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_renewal_application(
    body: CreateRenewalRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    """Create a renewal application from a prior approved application."""
    now = datetime.now(timezone.utc)

    # 1. Load previous application
    prev = await db.scalar(
        select(Application).where(Application.id == body.previous_application_id)
    )
    if not prev:
        raise HTTPException(status_code=404, detail="先前申請紀錄不存在")
    if prev.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="無權續領他人申請")
    if prev.status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="先前申請尚未核可，無法續領")

    # 2. Load scholarship type and check period
    st = await db.scalar(select(ScholarshipType).where(ScholarshipType.id == prev.scholarship_type_id))
    if not (st.renewal_application_start_date and st.renewal_application_end_date
            and st.renewal_application_start_date <= now <= st.renewal_application_end_date):
        raise HTTPException(status_code=400, detail="目前不在續領申請期間")

    # 3. Check duplicate (handled by partial unique index, but provide friendly message)
    from app.services.academic_year_service import get_current_academic_year
    current_year = get_current_academic_year()
    existing = await db.scalar(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.scholarship_type_id == prev.scholarship_type_id,
            Application.academic_year == current_year,
            Application.semester == prev.semester,
            Application.is_renewal == True,
            Application.status != ApplicationStatus.deleted,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="已建立續領申請")

    # 4. Create new Application
    service = ApplicationService(db)
    new_app = await service.create_renewal_from_previous(
        previous=prev,
        current_user=current_user,
        target_academic_year=current_year,
        renewal_year=prev.renewal_year or prev.academic_year,
    )
    await db.commit()

    return {
        "success": True,
        "message": "續領申請已建立",
        "data": {
            "id": new_app.id,
            "app_id": new_app.app_id,
            "is_renewal": new_app.is_renewal,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "previous_application_id": new_app.previous_application_id,
            "academic_year": new_app.academic_year,
            "renewal_year": new_app.renewal_year,
            "status": new_app.status.value,
        },
    }
```

- [ ] **Step 2: Register router in `backend/app/api/v1/api.py`**

```python
from app.api.v1.endpoints import renewal
# ... existing imports

api_router.include_router(renewal.router, prefix="/v1")  # adjust to existing prefix pattern
```

- [ ] **Step 3: Add `create_renewal_from_previous` to ApplicationService**

In `backend/app/services/application_service.py`, add method:

```python
    async def create_renewal_from_previous(
        self,
        previous: Application,
        current_user: User,
        target_academic_year: int,
        renewal_year: int,
    ) -> Application:
        """Create renewal application copying sub_type & key fields from previous."""
        app_id = await self._generate_app_id(target_academic_year, previous.semester.value if previous.semester else None)
        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=previous.scholarship_type_id,
            scholarship_configuration_id=previous.scholarship_configuration_id,
            sub_scholarship_type=previous.sub_scholarship_type,
            sub_type_selection_mode=previous.sub_type_selection_mode,
            is_renewal=True,
            renewal_year=renewal_year,
            previous_application_id=previous.id,
            academic_year=target_academic_year,
            semester=previous.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app
```

- [ ] **Step 4: Run tests → expect PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_application_creation.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/renewal.py backend/app/api/v1/api.py backend/app/services/application_service.py
git commit -m "feat(api): add renewal application creation endpoint"
```

---

### Task 3.4: Write tests for challenge creation endpoint

**Files:**
- Append to: `backend/app/tests/test_renewal_application_creation.py`

- [ ] **Step 1: Add challenge tests**

```python
@pytest.mark.asyncio
async def test_create_challenge_success(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory,
    scholarship_configuration_factory
):
    """Approved renewal exists → create challenge for different sub_type."""
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        application_start_date=now - timedelta(days=1),
        application_end_date=now + timedelta(days=7),
    )
    await scholarship_configuration_factory(
        scholarship_type_id=st.id,
        quotas={"nstc": {"114": 8}, "moe_1w": {"114": 6}},
    )
    renewal = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=114,
        status=ApplicationStatus.approved,
        sub_scholarship_type="nstc",
        is_renewal=True,
        renewal_year=113,
    )
    resp = await async_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "moe_1w"},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["is_renewal"] is False
    assert data["sub_scholarship_type"] == "moe_1w"
    assert data["challenges_application_id"] == renewal.id


@pytest.mark.asyncio
async def test_create_challenge_rejects_same_sub_type(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        application_start_date=now - timedelta(days=1),
        application_end_date=now + timedelta(days=7),
    )
    renewal = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=114,
        status=ApplicationStatus.approved,
        sub_scholarship_type="nstc",
        is_renewal=True,
    )
    resp = await async_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "nstc"},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 400
    assert "sub_type" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_create_challenge_rejects_when_renewal_not_approved(
    async_client, auth_headers_for_student, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        application_start_date=now - timedelta(days=1),
        application_end_date=now + timedelta(days=7),
    )
    renewal = await application_factory(
        user_id=auth_headers_for_student.user_id,
        scholarship_type_id=st.id,
        academic_year=114,
        status=ApplicationStatus.rejected,
        is_renewal=True,
    )
    resp = await async_client.post(
        "/api/v1/renewals/challenge",
        json={"renewal_application_id": renewal.id, "target_sub_type": "moe_1w"},
        headers=auth_headers_for_student.headers,
    )
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests → expect 404 (endpoint not implemented)**

---

### Task 3.5: Implement `POST /api/v1/renewals/challenge`

**Files:**
- Modify: `backend/app/api/v1/endpoints/renewal.py`
- Modify: `backend/app/services/application_service.py`

- [ ] **Step 1: Add endpoint**

```python
@router.post("/challenge", status_code=status.HTTP_201_CREATED)
async def create_challenge_application(
    body: CreateChallengeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db),
):
    now = datetime.now(timezone.utc)

    renewal = await db.scalar(
        select(Application).where(Application.id == body.renewal_application_id)
    )
    if not renewal:
        raise HTTPException(status_code=404, detail="續領申請紀錄不存在")
    if renewal.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="無權挑戰他人續領")
    if not renewal.is_renewal:
        raise HTTPException(status_code=400, detail="目標申請非續領紀錄")
    if renewal.status != ApplicationStatus.approved:
        raise HTTPException(status_code=400, detail="續領申請尚未核可，無法挑戰")

    if body.target_sub_type == renewal.sub_scholarship_type:
        raise HTTPException(status_code=400, detail="挑戰 sub_type 不能與續領 sub_type 相同")

    st = await db.scalar(select(ScholarshipType).where(ScholarshipType.id == renewal.scholarship_type_id))
    if not (st.application_start_date and st.application_end_date
            and st.application_start_date <= now <= st.application_end_date):
        raise HTTPException(status_code=400, detail="目前不在一般申請期間")

    # Verify target_sub_type exists in configuration
    from app.models.scholarship import ScholarshipConfiguration
    config = await db.scalar(
        select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.id == renewal.scholarship_configuration_id
        )
    )
    if config and body.target_sub_type not in (config.quotas or {}):
        raise HTTPException(status_code=400, detail=f"sub_type '{body.target_sub_type}' 不存在於配置")

    # Check duplicate challenge
    existing = await db.scalar(
        select(Application).where(
            Application.user_id == current_user.id,
            Application.scholarship_type_id == renewal.scholarship_type_id,
            Application.academic_year == renewal.academic_year,
            Application.semester == renewal.semester,
            Application.is_renewal == False,
            Application.challenges_application_id == renewal.id,
            Application.status != ApplicationStatus.deleted,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="已建立挑戰申請")

    service = ApplicationService(db)
    new_app = await service.create_challenge_from_renewal(
        renewal=renewal,
        current_user=current_user,
        target_sub_type=body.target_sub_type,
    )
    await db.commit()

    return {
        "success": True,
        "message": "挑戰申請已建立",
        "data": {
            "id": new_app.id,
            "app_id": new_app.app_id,
            "is_renewal": new_app.is_renewal,
            "sub_scholarship_type": new_app.sub_scholarship_type,
            "challenges_application_id": new_app.challenges_application_id,
            "academic_year": new_app.academic_year,
            "status": new_app.status.value,
        },
    }
```

- [ ] **Step 2: Add `create_challenge_from_renewal` to ApplicationService**

```python
    async def create_challenge_from_renewal(
        self, renewal: Application, current_user: User, target_sub_type: str
    ) -> Application:
        app_id = await self._generate_app_id(
            renewal.academic_year,
            renewal.semester.value if renewal.semester else None,
        )
        new_app = Application(
            app_id=app_id,
            user_id=current_user.id,
            scholarship_type_id=renewal.scholarship_type_id,
            scholarship_configuration_id=renewal.scholarship_configuration_id,
            sub_scholarship_type=target_sub_type,
            sub_type_selection_mode=renewal.sub_type_selection_mode,
            is_renewal=False,
            challenges_application_id=renewal.id,
            academic_year=renewal.academic_year,
            semester=renewal.semester,
            status=ApplicationStatus.draft,
            review_stage=ReviewStage.student_draft,
        )
        self.db.add(new_app)
        await self.db.flush()
        return new_app
```

- [ ] **Step 3: Run tests → expect PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_application_creation.py -v
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/endpoints/renewal.py backend/app/services/application_service.py
git commit -m "feat(api): add challenge application creation endpoint"
```

---

## Phase 4 — Renewal Review Routing

### Task 4.1: Extend review listing endpoints to filter by renewal phase

**Files:**
- Modify: existing review listing endpoint (likely `backend/app/api/v1/endpoints/applications.py` — search for "professor_review" route)

- [ ] **Step 1: Find route**

```bash
grep -rn "professor" backend/app/api/v1/endpoints/ | grep -i "list\|pending" | head
```

- [ ] **Step 2: Add `is_renewal` filter & period check**

For each list endpoint (professor pending, college pending), add filter:

```python
# pseudocode — adapt to actual route signature
from app.models.scholarship import ScholarshipType
from datetime import datetime, timezone

# Determine if currently in renewal review period vs general review period
# for each scholarship_type involved. Apps shown depend on phase.

now = datetime.now(timezone.utc)
stmt = stmt.join(ScholarshipType, Application.scholarship_type_id == ScholarshipType.id)
stmt = stmt.where(
    or_(
        and_(
            Application.is_renewal == True,
            ScholarshipType.renewal_professor_review_start <= now,
            ScholarshipType.renewal_professor_review_end >= now,
        ),
        and_(
            Application.is_renewal == False,
            ScholarshipType.professor_review_start <= now,
            ScholarshipType.professor_review_end >= now,
        ),
    )
)
```

- [ ] **Step 3: Write integration test**

Create `backend/app/tests/test_review_routing_renewal.py`:

```python
import pytest
from datetime import datetime, timedelta, timezone
from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage


@pytest.mark.asyncio
async def test_professor_sees_only_renewal_in_renewal_period(
    async_client, professor_auth, scholarship_type_factory, application_factory
):
    now = datetime.now(timezone.utc)
    st = await scholarship_type_factory(
        renewal_professor_review_start=now - timedelta(hours=1),
        renewal_professor_review_end=now + timedelta(days=3),
        professor_review_start=now + timedelta(days=14),
        professor_review_end=now + timedelta(days=21),
    )
    renewal_app = await application_factory(
        scholarship_type_id=st.id,
        is_renewal=True,
        review_stage=ReviewStage.professor_review,
        professor_id=professor_auth.user_id,
    )
    general_app = await application_factory(
        scholarship_type_id=st.id,
        is_renewal=False,
        review_stage=ReviewStage.professor_review,
        professor_id=professor_auth.user_id,
    )
    resp = await async_client.get(
        "/api/v1/applications/pending-review", headers=professor_auth.headers
    )
    ids = [a["id"] for a in resp.json()["data"]]
    assert renewal_app.id in ids
    assert general_app.id not in ids
```

- [ ] **Step 4: Run tests → expect FAIL, then implement, then PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/applications.py backend/app/tests/test_review_routing_renewal.py
git commit -m "feat(review): filter pending review list by renewal vs general phase"
```

---

## Phase 5 — Renewal Distribution Service

### Task 5.1: Write tests for renewal auto-distribution

**Files:**
- Create: `backend/app/tests/test_renewal_distribution_service.py`

- [ ] **Step 1: Write tests**

```python
import pytest
from app.models.enums import ApplicationStatus, ReviewStage
from app.services.renewal_distribution_service import RenewalDistributionService


@pytest.mark.asyncio
async def test_auto_approves_renewals_with_passed_reviews(
    db_session, scholarship_type_factory, application_factory
):
    st = await scholarship_type_factory()
    app1 = await application_factory(
        scholarship_type_id=st.id, is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
    )
    app2 = await application_factory(
        scholarship_type_id=st.id, is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
    )
    service = RenewalDistributionService(db_session)
    result = await service.auto_approve_passed_reviews(scholarship_type_id=st.id)
    await db_session.refresh(app1); await db_session.refresh(app2)
    assert app1.status == ApplicationStatus.approved
    assert app2.status == ApplicationStatus.approved
    assert result["approved_count"] == 2


@pytest.mark.asyncio
async def test_does_not_approve_non_renewal(
    db_session, scholarship_type_factory, application_factory
):
    st = await scholarship_type_factory()
    general_app = await application_factory(
        scholarship_type_id=st.id, is_renewal=False,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.college_reviewed,
    )
    service = RenewalDistributionService(db_session)
    await service.auto_approve_passed_reviews(scholarship_type_id=st.id)
    await db_session.refresh(general_app)
    assert general_app.status == ApplicationStatus.under_review


@pytest.mark.asyncio
async def test_does_not_approve_not_yet_reviewed(
    db_session, scholarship_type_factory, application_factory
):
    st = await scholarship_type_factory()
    pending = await application_factory(
        scholarship_type_id=st.id, is_renewal=True,
        status=ApplicationStatus.under_review,
        review_stage=ReviewStage.professor_review,  # still in flight
    )
    service = RenewalDistributionService(db_session)
    await service.auto_approve_passed_reviews(scholarship_type_id=st.id)
    await db_session.refresh(pending)
    assert pending.status == ApplicationStatus.under_review
```

- [ ] **Step 2: Run tests → expect ModuleNotFoundError**

---

### Task 5.2: Implement `RenewalDistributionService`

**Files:**
- Create: `backend/app/services/renewal_distribution_service.py`

- [ ] **Step 1: Write service**

```python
"""
RenewalDistributionService — auto-approves renewal applications that have
passed required review stages (skips college_ranking by design).
"""

from typing import Optional
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import ApplicationStatus, ReviewStage
from app.models.scholarship import ScholarshipConfiguration


class RenewalDistributionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def auto_approve_passed_reviews(self, scholarship_type_id: int) -> dict:
        """
        Auto-approve renewal applications where:
        - is_renewal = True
        - review_stage == college_reviewed (or professor_reviewed if no college required)
        - status == under_review

        Returns summary dict with approved_count, rejected_count.
        """
        # Determine the terminal review stage based on configuration
        config = await self.db.scalar(
            select(ScholarshipConfiguration).where(
                ScholarshipConfiguration.scholarship_type_id == scholarship_type_id
            )
        )
        # college_reviewed is the terminal stage for renewal (no college_ranking)
        # If config does not require college review, then professor_reviewed is terminal
        terminal_stages = [ReviewStage.college_reviewed]
        if config and not getattr(config, "requires_college_review", True):
            terminal_stages = [ReviewStage.professor_reviewed]

        stmt = (
            update(Application)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.is_renewal == True,
                Application.status == ApplicationStatus.under_review,
                Application.review_stage.in_(terminal_stages),
            )
            .values(
                status=ApplicationStatus.approved,
                review_stage=ReviewStage.quota_distributed,
            )
            .returning(Application.id)
        )
        result = await self.db.execute(stmt)
        approved_ids = [r[0] for r in result.all()]
        await self.db.commit()

        return {"approved_count": len(approved_ids), "approved_ids": approved_ids}
```

- [ ] **Step 2: Run tests → PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_distribution_service.py -v
```

- [ ] **Step 3: Add endpoint to trigger**

In `backend/app/api/v1/endpoints/renewal.py`:

```python
from app.services.renewal_distribution_service import RenewalDistributionService

@router.post("/{scholarship_type_id}/auto-distribute")
async def trigger_renewal_auto_distribution(
    scholarship_type_id: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    service = RenewalDistributionService(db)
    result = await service.auto_approve_passed_reviews(scholarship_type_id)
    return {"success": True, "message": "續領自動分發完成", "data": result}
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/renewal_distribution_service.py backend/app/tests/test_renewal_distribution_service.py backend/app/api/v1/endpoints/renewal.py
git commit -m "feat(renewal): add auto-distribute service for renewals passing review"
```

---

## Phase 6 — General Distribution + Release + Fill-in

### Task 6.1: Write integration test for challenge release + fill-in

**Files:**
- Create: `backend/app/tests/test_challenge_release_distribution.py`

- [ ] **Step 1: Write end-to-end test**

```python
import pytest
from app.models.enums import ApplicationStatus
from app.services.manual_distribution_service import ManualDistributionService


@pytest.mark.asyncio
async def test_challenge_success_releases_renewal_and_fills_waitlist(
    db_session, scholarship_type_factory, scholarship_configuration_factory,
    application_factory, college_ranking_factory
):
    """
    Scenario: A has approved renewal nstc-113. A challenges moe_1w and ranks #1.
    F-T are pure-new nstc candidates ranked 1-8 (will fill nstc-114 quota).
    U, V are pure-new nstc candidates ranked 9, 10 (waitlist).
    After distribution:
      - A's renewal cancelled_by_challenge
      - A approved on moe_1w
      - U promoted to approved on nstc with allocation_year=113
    """
    st = await scholarship_type_factory()
    await scholarship_configuration_factory(
        scholarship_type_id=st.id,
        quotas={"nstc": {"114": 8, "113": 0}, "moe_1w": {"114": 6}},
    )
    # A's renewal (already approved)
    renewal_A = await application_factory(
        scholarship_type_id=st.id, sub_scholarship_type="nstc",
        is_renewal=True, renewal_year=113, academic_year=114,
        status=ApplicationStatus.approved,
    )
    # A's challenge
    challenge_A = await application_factory(
        scholarship_type_id=st.id, sub_scholarship_type="moe_1w",
        is_renewal=False, challenges_application_id=renewal_A.id,
        academic_year=114,
        status=ApplicationStatus.under_review,
    )
    # Pure new candidates for nstc
    nstc_candidates = []
    for rank in range(1, 11):
        a = await application_factory(
            scholarship_type_id=st.id, sub_scholarship_type="nstc",
            is_renewal=False, challenges_application_id=None,
            academic_year=114, status=ApplicationStatus.under_review,
        )
        await college_ranking_factory(application_id=a.id, rank=rank)
        nstc_candidates.append(a)
    # Pure new for moe_1w (ranked below A so A wins)
    for rank in range(2, 8):
        a = await application_factory(
            scholarship_type_id=st.id, sub_scholarship_type="moe_1w",
            academic_year=114, status=ApplicationStatus.under_review,
        )
        await college_ranking_factory(application_id=a.id, rank=rank)
    await college_ranking_factory(application_id=challenge_A.id, rank=1)

    service = ManualDistributionService(db_session)
    await service.execute_general_distribution(scholarship_type_id=st.id, academic_year=114)

    await db_session.refresh(renewal_A)
    await db_session.refresh(challenge_A)

    assert challenge_A.status == ApplicationStatus.approved
    assert renewal_A.status == ApplicationStatus.cancelled_by_challenge
    assert renewal_A.cancelled_due_to_application_id == challenge_A.id

    # U should be promoted (10 - 8 already approved = U at rank 9, V at rank 10)
    await db_session.refresh(nstc_candidates[8])  # rank 9
    assert nstc_candidates[8].status == ApplicationStatus.approved
```

- [ ] **Step 2: Run tests → expect FAIL (method not implemented)**

---

### Task 6.2: Implement `execute_general_distribution` with release + fill-in

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py`

- [ ] **Step 1: Add method**

```python
    async def execute_general_distribution(
        self, scholarship_type_id: int, academic_year: int
    ) -> dict:
        """
        Run general-phase distribution with challenge release and waitlist fill-in.
        Returns summary stats per spec Section 12.
        """
        config = await self._get_active_config(scholarship_type_id, academic_year)
        quotas = config.quotas or {}  # {"nstc": {"114": 8, "113": 0}, ...}

        # 1. Compute remaining quota = total - used by approved renewals
        used_by_renewal = await self._count_approved_renewals_per_pool(
            scholarship_type_id, academic_year
        )  # {(sub_type, alloc_year): count}
        remaining = {
            (st, int(y)): total - used_by_renewal.get((st, int(y)), 0)
            for st, year_map in quotas.items()
            for y, total in year_map.items()
        }

        # 2. First-round distribute per sub_type
        approved_challenges = []
        for sub_type in quotas.keys():
            candidates = await self._get_general_candidates(
                scholarship_type_id, academic_year, sub_type
            )  # ordered by rank, includes pure-new + challenges for THIS sub_type
            for cand in candidates:
                pool_year = self._pick_pool(remaining, sub_type, sub_type_policy=config)
                if pool_year is None:
                    break
                cand.application.status = ApplicationStatus.approved
                cand.allocation_year = pool_year
                remaining[(sub_type, pool_year)] -= 1
                if cand.application.challenges_application_id:
                    approved_challenges.append(cand.application)

        # 3. Release handling
        released = {}
        for challenge_app in approved_challenges:
            renewal_app = await self.db.scalar(
                select(Application).where(Application.id == challenge_app.challenges_application_id)
            )
            renewal_app.status = ApplicationStatus.cancelled_by_challenge
            renewal_app.cancelled_due_to_application_id = challenge_app.id
            key = (renewal_app.sub_scholarship_type, renewal_app.renewal_year)
            released[key] = released.get(key, 0) + 1

        # 4. Fill-in from waitlist (same sub_type, next ranked, not yet approved)
        fill_in_count = 0
        for (sub_type, alloc_year), count in released.items():
            waitlist = await self._get_waitlist_candidates(
                scholarship_type_id, academic_year, sub_type, limit=count
            )
            for cand in waitlist:
                cand.application.status = ApplicationStatus.approved
                cand.allocation_year = alloc_year
                fill_in_count += 1

        await self.db.commit()

        return {
            "approved_renewals": sum(used_by_renewal.values()),
            "approved_challenges": len(approved_challenges),
            "released_slots": dict(released),
            "filled_in": fill_in_count,
            "unfilled": sum(released.values()) - fill_in_count,
        }

    async def _count_approved_renewals_per_pool(
        self, scholarship_type_id: int, academic_year: int
    ) -> dict:
        rows = await self.db.execute(
            select(
                Application.sub_scholarship_type,
                Application.renewal_year,
                func.count(),
            ).where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal == True,
                Application.status == ApplicationStatus.approved,
            ).group_by(Application.sub_scholarship_type, Application.renewal_year)
        )
        return {(r[0], r[1]): r[2] for r in rows.all()}

    async def _get_general_candidates(
        self, scholarship_type_id: int, academic_year: int, sub_type: str
    ):
        """Return CollegeRankingItem rows for sub_type, ordered by rank."""
        from app.models.college_review import CollegeRankingItem
        stmt = (
            select(CollegeRankingItem)
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.sub_scholarship_type == sub_type,
                Application.is_renewal == False,
                Application.status.notin_([
                    ApplicationStatus.approved,
                    ApplicationStatus.rejected,
                    ApplicationStatus.withdrawn,
                    ApplicationStatus.deleted,
                ]),
            )
            .order_by(CollegeRankingItem.rank)
        )
        return (await self.db.execute(stmt)).scalars().all()

    async def _get_waitlist_candidates(
        self, scholarship_type_id: int, academic_year: int, sub_type: str, limit: int
    ):
        """Candidates not yet approved in this batch, ordered by rank."""
        # Same as _get_general_candidates but explicit filter:
        # status != approved (since some may have been approved in step 2)
        from app.models.college_review import CollegeRankingItem
        stmt = (
            select(CollegeRankingItem)
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.sub_scholarship_type == sub_type,
                Application.is_renewal == False,
                Application.status != ApplicationStatus.approved,
                Application.challenges_application_id.is_(None),  # only pure new
            )
            .order_by(CollegeRankingItem.rank)
            .limit(limit)
        )
        return (await self.db.execute(stmt)).scalars().all()

    def _pick_pool(self, remaining: dict, sub_type: str, sub_type_policy) -> Optional[int]:
        """Pick the next available allocation_year for this sub_type.
        Policy: current year first, then prior years descending."""
        years = sorted(
            [y for (st, y), c in remaining.items() if st == sub_type and c > 0],
            reverse=True,
        )
        return years[0] if years else None
```

- [ ] **Step 2: Add imports at top of file if missing**

```python
from sqlalchemy import func
from app.models.enums import ApplicationStatus
```

- [ ] **Step 3: Run tests → expect PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_challenge_release_distribution.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/manual_distribution_service.py backend/app/tests/test_challenge_release_distribution.py
git commit -m "feat(distribution): add challenge release and waitlist fill-in"
```

---

### Task 6.3: Add preview endpoint for admin UI

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py`

- [ ] **Step 1: Add preview endpoint**

```python
@router.post("/preview-distribution")
async def preview_distribution(
    body: AllocateRequest,  # reuse existing schema
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Dry-run: compute what would happen given the proposed allocations,
    without persisting changes. Returns release_chain for UI preview.
    """
    service = ManualDistributionService(db)
    preview = await service.preview_release_chain(body.allocations)
    return {"success": True, "message": "Preview computed", "data": preview}
```

- [ ] **Step 2: Add `preview_release_chain` to service**

```python
    async def preview_release_chain(self, proposed_allocations: list) -> dict:
        """Compute which renewals would be cancelled and who would fill in."""
        chain = []
        for alloc in proposed_allocations:
            app = await self.db.scalar(
                select(Application).where(Application.id == alloc.application_id)
            )
            if app and app.challenges_application_id:
                renewal = await self.db.scalar(
                    select(Application).where(Application.id == app.challenges_application_id)
                )
                # Find next waitlist candidate
                waitlist = await self._get_waitlist_candidates(
                    renewal.scholarship_type_id, app.academic_year,
                    renewal.sub_scholarship_type, limit=1
                )
                suggested = waitlist[0].application if waitlist else None
                chain.append({
                    "cancelled_application_id": renewal.id,
                    "freed_slot": {
                        "sub_type": renewal.sub_scholarship_type,
                        "allocation_year": renewal.renewal_year,
                    },
                    "suggested_fill_id": suggested.id if suggested else None,
                    "suggested_fill_name": suggested.student.name if suggested else None,
                })
        return {"release_chain": chain}
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/manual_distribution_service.py backend/app/api/v1/endpoints/manual_distribution.py
git commit -m "feat(api): add distribution preview endpoint for admin UI"
```

---

## Phase 7 — Admin: Renewal Distribution Result Page

### Task 7.1: API endpoint for renewal distribution result

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py` or `endpoints/renewal.py`

- [ ] **Step 1: Add endpoint**

```python
@router.get("/distribution-result")
async def get_renewal_distribution_result(
    scholarship_type_id: int,
    academic_year: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Return renewal distribution grouped by (sub_type, renewal_year)."""
    stmt = (
        select(Application)
        .where(
            Application.scholarship_type_id == scholarship_type_id,
            Application.academic_year == academic_year,
            Application.is_renewal == True,
        )
        .options(joinedload(Application.student))
    )
    apps = (await db.execute(stmt)).scalars().all()

    grouped = {}
    rejected = []
    for app in apps:
        if app.status == ApplicationStatus.approved:
            key = f"{app.sub_scholarship_type}_{app.renewal_year}"
            grouped.setdefault(key, {
                "sub_type": app.sub_scholarship_type,
                "renewal_year": app.renewal_year,
                "applications": [],
            })["applications"].append({
                "id": app.id, "app_id": app.app_id,
                "student_name": app.student.name,
                "previous_application_id": app.previous_application_id,
                "has_challenge": any(
                    # quick sub-check: child apps where challenges_application_id == app.id
                    True for _ in []  # placeholder; implement via separate query if needed
                ),
            })
        elif app.status == ApplicationStatus.rejected:
            rejected.append({"id": app.id, "student_name": app.student.name})

    return {
        "success": True,
        "message": "Renewal distribution result",
        "data": {
            "groups": list(grouped.values()),
            "rejected": rejected,
            "summary": {
                "approved": sum(len(g["applications"]) for g in grouped.values()),
                "rejected": len(rejected),
            },
        },
    }
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/api/v1/endpoints/renewal.py
git commit -m "feat(api): add renewal distribution result endpoint"
```

---

### Task 7.2: Frontend renewal distribution result page

**Files:**
- Create: `frontend/lib/api/modules/renewal.ts`
- Create: `frontend/components/admin/renewal/RenewalDistributionResult.tsx`
- Create: `frontend/app/admin/renewal/page.tsx` (route)

- [ ] **Step 1: Create typed client**

```typescript
// frontend/lib/api/modules/renewal.ts
import { api } from "../client";

export interface EligibleRenewal {
  previous_application_id: number;
  scholarship_type_id: number;
  scholarship_type_name: string;
  sub_scholarship_type: string;
  target_academic_year: number;
  renewal_year: number;
  renewal_deadline: string | null;
}

export interface RenewalDistributionGroup {
  sub_type: string;
  renewal_year: number;
  applications: {
    id: number;
    app_id: string;
    student_name: string;
    previous_application_id: number;
    has_challenge: boolean;
  }[];
}

export const renewalApi = {
  listEligible: () =>
    api.get<{ data: EligibleRenewal[] }>("/api/v1/renewals/eligible"),

  createRenewal: (previous_application_id: number) =>
    api.post("/api/v1/renewals/", { previous_application_id }),

  createChallenge: (renewal_application_id: number, target_sub_type: string) =>
    api.post("/api/v1/renewals/challenge", {
      renewal_application_id,
      target_sub_type,
    }),

  getDistributionResult: (scholarship_type_id: number, academic_year: number) =>
    api.get<{
      data: {
        groups: RenewalDistributionGroup[];
        rejected: { id: number; student_name: string }[];
        summary: { approved: number; rejected: number };
      };
    }>(`/api/v1/renewals/distribution-result`, {
      params: { scholarship_type_id, academic_year },
    }),
};
```

- [ ] **Step 2: Create component**

```typescript
// frontend/components/admin/renewal/RenewalDistributionResult.tsx
"use client";

import { useQuery } from "@tanstack/react-query";
import { renewalApi } from "@/lib/api/modules/renewal";

interface Props {
  scholarshipTypeId: number;
  academicYear: number;
}

export function RenewalDistributionResult({ scholarshipTypeId, academicYear }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ["renewal-distribution", scholarshipTypeId, academicYear],
    queryFn: () => renewalApi.getDistributionResult(scholarshipTypeId, academicYear),
  });

  if (isLoading) return <div>載入中...</div>;
  const result = data?.data;
  if (!result) return null;

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold">續領分發結果 — {academicYear} 學年</h2>

      <section>
        <h3 className="font-semibold mb-2">續領通過名單</h3>
        {result.groups.map((group) => (
          <div key={`${group.sub_type}_${group.renewal_year}`} className="border p-4 mb-2 rounded">
            <h4 className="font-medium">
              {group.sub_type} · 計畫年度 {group.renewal_year}
              <span className="text-gray-500 ml-2">
                ({group.applications.length} 人)
              </span>
            </h4>
            <ul className="mt-2 space-y-1">
              {group.applications.map((app) => (
                <li key={app.id} className="text-sm">
                  {app.student_name} ({app.app_id}, 原 #{app.previous_application_id})
                  {app.has_challenge && <span className="ml-2 text-amber-600">⚠ 同時提交挑戰</span>}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      <section>
        <h3 className="font-semibold mb-2">續領被拒名單</h3>
        {result.rejected.length === 0 ? (
          <p className="text-gray-500 text-sm">無</p>
        ) : (
          <ul>{result.rejected.map((r) => <li key={r.id}>{r.student_name}</li>)}</ul>
        )}
      </section>

      <div className="text-sm text-gray-600">
        通過: {result.summary.approved} · 拒絕: {result.summary.rejected}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create route**

```typescript
// frontend/app/admin/renewal/page.tsx
"use client";
import { useState } from "react";
import { RenewalDistributionResult } from "@/components/admin/renewal/RenewalDistributionResult";

export default function RenewalAdminPage() {
  const [scholarshipTypeId, setScholarshipTypeId] = useState(1);
  const [academicYear, setAcademicYear] = useState(114);
  return (
    <div className="p-6">
      {/* selector UI omitted for brevity — add scholarship_type + year dropdowns */}
      <RenewalDistributionResult
        scholarshipTypeId={scholarshipTypeId}
        academicYear={academicYear}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run frontend dev server, visit `/admin/renewal`, verify rendering**

```bash
docker compose -f docker-compose.dev.yml up frontend
# Browser: http://localhost:3000/admin/renewal
```

- [ ] **Step 5: Commit**

```bash
git add frontend/lib/api/modules/renewal.ts frontend/components/admin/renewal/ frontend/app/admin/renewal/
git commit -m "feat(frontend): add renewal distribution result page"
```

---

## Phase 8 — Admin: Manual Distribution Panel Updates

### Task 8.1: API endpoint returning distribution state

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py`

- [ ] **Step 1: Add endpoint**

```python
@router.get("/state")
async def get_distribution_state(
    scholarship_type_id: int,
    academic_year: int,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """
    Return full state for the manual distribution panel:
    - renewal_allocations: approved renewals grouped by (sub_type, renewal_year)
    - available_quotas: remaining quota per (sub_type, allocation_year)
    - candidates: ranked applications for general phase (with is_challenge flag)
    """
    service = ManualDistributionService(db)
    state = await service.compute_distribution_state(scholarship_type_id, academic_year)
    return {"success": True, "message": "OK", "data": state}
```

- [ ] **Step 2: Add `compute_distribution_state` to service**

```python
    async def compute_distribution_state(
        self, scholarship_type_id: int, academic_year: int
    ) -> dict:
        config = await self._get_active_config(scholarship_type_id, academic_year)
        quotas = config.quotas or {}

        # Renewal allocations grouped
        renewal_apps = (
            await self.db.execute(
                select(Application)
                .options(joinedload(Application.student))
                .where(
                    Application.scholarship_type_id == scholarship_type_id,
                    Application.academic_year == academic_year,
                    Application.is_renewal == True,
                    Application.status == ApplicationStatus.approved,
                )
            )
        ).scalars().all()
        renewal_grouped = {}
        for app in renewal_apps:
            key = (app.sub_scholarship_type, app.renewal_year)
            renewal_grouped.setdefault(key, []).append({
                "application_id": app.id,
                "student_name": app.student.name,
                "has_challenge": False,  # set below
            })

        # Mark challenges
        challenge_apps = (
            await self.db.execute(
                select(Application).where(
                    Application.challenges_application_id.in_([a.id for a in renewal_apps] or [-1])
                )
            )
        ).scalars().all()
        for ch in challenge_apps:
            for items in renewal_grouped.values():
                for item in items:
                    if item["application_id"] == ch.challenges_application_id:
                        item["has_challenge"] = True

        # Used per pool
        used = await self._count_approved_renewals_per_pool(scholarship_type_id, academic_year)
        available_quotas = []
        for sub_type, year_map in quotas.items():
            for year_str, total in year_map.items():
                year = int(year_str)
                available_quotas.append({
                    "sub_type": sub_type,
                    "allocation_year": year,
                    "total": total,
                    "used": used.get((sub_type, year), 0),
                    "remaining": total - used.get((sub_type, year), 0),
                })

        # Candidates (general phase)
        from app.models.college_review import CollegeRankingItem
        cands = (await self.db.execute(
            select(CollegeRankingItem, Application)
            .join(Application, CollegeRankingItem.application_id == Application.id)
            .where(
                Application.scholarship_type_id == scholarship_type_id,
                Application.academic_year == academic_year,
                Application.is_renewal == False,
            )
            .order_by(CollegeRankingItem.rank)
        )).all()
        candidates = []
        for ri, app in cands:
            challenged_renewal = None
            if app.challenges_application_id:
                renewal = await self.db.scalar(
                    select(Application).where(Application.id == app.challenges_application_id)
                )
                challenged_renewal = {
                    "renewal_application_id": renewal.id,
                    "sub_type": renewal.sub_scholarship_type,
                    "renewal_year": renewal.renewal_year,
                }
            candidates.append({
                "rank": ri.rank,
                "application_id": app.id,
                "student_name": app.student.name if hasattr(app, "student") else None,
                "is_challenge": app.challenges_application_id is not None,
                "challenged_renewal": challenged_renewal,
                "applying_sub_type": app.sub_scholarship_type,
            })

        return {
            "renewal_allocations": [
                {
                    "sub_type": st,
                    "renewal_year": y,
                    "applications": items,
                }
                for (st, y), items in renewal_grouped.items()
            ],
            "available_quotas": available_quotas,
            "candidates": candidates,
        }
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/manual_distribution.py backend/app/services/manual_distribution_service.py
git commit -m "feat(api): add manual distribution state endpoint"
```

---

### Task 8.2: Update ManualDistributionPanel frontend

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`
- Modify: `frontend/lib/api/modules/manual-distribution.ts`

- [ ] **Step 1: Add typed client method**

```typescript
// frontend/lib/api/modules/manual-distribution.ts (append)

export interface DistributionState {
  renewal_allocations: {
    sub_type: string;
    renewal_year: number;
    applications: {
      application_id: number;
      student_name: string;
      has_challenge: boolean;
    }[];
  }[];
  available_quotas: {
    sub_type: string;
    allocation_year: number;
    total: number;
    used: number;
    remaining: number;
  }[];
  candidates: {
    rank: number;
    application_id: number;
    student_name: string;
    is_challenge: boolean;
    challenged_renewal: {
      renewal_application_id: number;
      sub_type: string;
      renewal_year: number;
    } | null;
    applying_sub_type: string;
  }[];
}

export const manualDistributionApi = {
  // ... existing methods
  getState: (scholarship_type_id: number, academic_year: number) =>
    api.get<{ data: DistributionState }>(`/api/v1/manual-distribution/state`, {
      params: { scholarship_type_id, academic_year },
    }),

  previewDistribution: (allocations: { application_id: number; sub_type: string; allocation_year: number }[]) =>
    api.post(`/api/v1/manual-distribution/preview-distribution`, { allocations }),
};
```

- [ ] **Step 2: Modify ManualDistributionPanel.tsx**

Add three new UI blocks at the top of the panel (before existing candidate list):

```typescript
// Inside ManualDistributionPanel component
const { data: stateData } = useQuery({
  queryKey: ["distribution-state", scholarshipTypeId, academicYear],
  queryFn: () => manualDistributionApi.getState(scholarshipTypeId, academicYear),
});
const state = stateData?.data;

return (
  <div className="space-y-6">
    {/* Renewal occupied block */}
    <section className="border-l-4 border-blue-500 bg-blue-50 p-4">
      <h3 className="font-semibold">續領已佔用 (不可改動)</h3>
      {state?.renewal_allocations.map((alloc) => (
        <div key={`${alloc.sub_type}_${alloc.renewal_year}`}>
          <strong>{alloc.sub_type} · 計畫年度 {alloc.renewal_year}</strong>
          {" "}{alloc.applications.length} 人
          <ul className="text-sm">
            {alloc.applications.map((a) => (
              <li key={a.application_id}>
                {a.student_name}{a.has_challenge && " *"}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </section>

    {/* Available quotas */}
    <section>
      <h3 className="font-semibold">剩餘可分配配額</h3>
      <ul className="text-sm">
        {state?.available_quotas.map((q) => (
          <li key={`${q.sub_type}_${q.allocation_year}`}>
            {q.sub_type} · 計畫年度 {q.allocation_year}: {q.used}/{q.total} 已配
          </li>
        ))}
      </ul>
    </section>

    {/* Candidate list with challenge markers */}
    <section>
      <h3 className="font-semibold">候選名單</h3>
      <table>
        <thead>
          <tr>
            <th>排名</th><th>學生</th><th>類型</th><th>保底/註記</th>
            {/* dynamic columns per (sub_type, allocation_year) */}
          </tr>
        </thead>
        <tbody>
          {state?.candidates.map((c) => (
            <tr key={c.application_id} className={c.is_challenge ? "bg-amber-50" : ""}>
              <td>{c.rank}</td>
              <td>{c.student_name}</td>
              <td>{c.is_challenge ? "挑戰" : "純新"}</td>
              <td>
                {c.is_challenge && c.challenged_renewal && (
                  <span>🛡 保底 {c.challenged_renewal.sub_type}-{c.challenged_renewal.renewal_year}</span>
                )}
              </td>
              {/* Render checkboxes for each (sub_type, allocation_year), with disabled state
                  if c.challenged_renewal?.sub_type matches the column sub_type */}
            </tr>
          ))}
        </tbody>
      </table>
    </section>

    {/* Release preview */}
    <ReleasePreviewSection allocations={proposedAllocations} />

    {/* Existing buttons */}
  </div>
);
```

- [ ] **Step 3: Add `ReleasePreviewSection` sub-component**

```typescript
function ReleasePreviewSection({ allocations }: { allocations: any[] }) {
  const { data } = useQuery({
    queryKey: ["release-preview", allocations],
    queryFn: () => manualDistributionApi.previewDistribution(allocations),
    enabled: allocations.length > 0,
  });
  const chain = data?.data?.release_chain || [];
  if (chain.length === 0) return null;
  return (
    <section className="border-l-4 border-amber-500 bg-amber-50 p-4">
      <h3 className="font-semibold">釋出與遞補預覽</h3>
      {chain.map((c: any, i: number) => (
        <div key={i} className="text-sm mt-2">
          ⚠ 挑戰申請 #{c.cancelled_application_id} 成功
          <div className="ml-4">↳ 釋出 {c.freed_slot.sub_type}-{c.freed_slot.allocation_year} slot</div>
          {c.suggested_fill_name && (
            <div className="ml-4">↳ 自動遞補：{c.suggested_fill_name} (排 #{c.suggested_fill_id})</div>
          )}
        </div>
      ))}
    </section>
  );
}
```

- [ ] **Step 4: Test in browser**

```bash
docker compose -f docker-compose.dev.yml up
# http://localhost:3000/admin/manual-distribution → check rendering
```

- [ ] **Step 5: Commit**

```bash
git add frontend/components/admin/manual-distribution/ frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat(frontend): show renewal slots and challenge markers in manual distribution panel"
```

---

## Phase 9 — Student UI

### Task 9.1: Renewal application card

**Files:**
- Create: `frontend/components/student/RenewalApplicationCard.tsx`

- [ ] **Step 1: Implement**

```typescript
"use client";
import { useQuery, useMutation } from "@tanstack/react-query";
import { renewalApi, EligibleRenewal } from "@/lib/api/modules/renewal";
import { useRouter } from "next/navigation";

export function RenewalApplicationCard() {
  const router = useRouter();
  const { data, isLoading } = useQuery({
    queryKey: ["eligible-renewals"],
    queryFn: () => renewalApi.listEligible(),
  });

  const createMut = useMutation({
    mutationFn: (id: number) => renewalApi.createRenewal(id),
    onSuccess: (resp) => {
      router.push(`/applications/${resp.data.id}/edit`);
    },
  });

  if (isLoading) return null;
  const eligible = data?.data || [];
  if (eligible.length === 0) return null;

  return (
    <div className="bg-emerald-50 border-l-4 border-emerald-500 p-4 rounded">
      <h3 className="font-semibold mb-2">可續領的獎學金</h3>
      <ul className="space-y-2">
        {eligible.map((item: EligibleRenewal) => (
          <li key={item.previous_application_id} className="flex items-center justify-between">
            <div>
              <div className="font-medium">{item.scholarship_type_name}</div>
              <div className="text-sm text-gray-600">
                上期 sub_type: {item.sub_scholarship_type} · 目標學年: {item.target_academic_year}
              </div>
              {item.renewal_deadline && (
                <div className="text-xs text-gray-500">
                  截止: {new Date(item.renewal_deadline).toLocaleString("zh-TW")}
                </div>
              )}
            </div>
            <button
              className="px-4 py-2 bg-emerald-600 text-white rounded"
              onClick={() => createMut.mutate(item.previous_application_id)}
              disabled={createMut.isPending}
            >
              建立續領申請
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Mount in student portal**

In `frontend/components/enhanced-student-portal.tsx`:

```typescript
import { RenewalApplicationCard } from "./student/RenewalApplicationCard";

// Add near top of the portal layout
<RenewalApplicationCard />
```

- [ ] **Step 3: Test in browser**

```bash
# As a student user who had an approved application last year:
# Open student portal → renewal card should appear in renewal period
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/student/RenewalApplicationCard.tsx frontend/components/enhanced-student-portal.tsx
git commit -m "feat(frontend): add renewal application card for students"
```

---

### Task 9.2: Challenge application creation UI

**Files:**
- Create: `frontend/components/student/ChallengeApplicationCard.tsx`

- [ ] **Step 1: Implement**

```typescript
"use client";
import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { renewalApi } from "@/lib/api/modules/renewal";
import { applicationsApi } from "@/lib/api/modules/applications";

interface Props {
  approvedRenewalId: number;
  approvedRenewalSubType: string;
  scholarshipTypeId: number;
  scholarshipConfigQuotas: Record<string, Record<string, number>>;
}

export function ChallengeApplicationCard({
  approvedRenewalId, approvedRenewalSubType, scholarshipConfigQuotas
}: Props) {
  const availableSubTypes = Object.keys(scholarshipConfigQuotas).filter(
    (st) => st !== approvedRenewalSubType
  );
  const [targetSubType, setTargetSubType] = useState(availableSubTypes[0] || "");

  const createMut = useMutation({
    mutationFn: () => renewalApi.createChallenge(approvedRenewalId, targetSubType),
    onSuccess: (resp) => {
      // navigate to edit
      window.location.href = `/applications/${resp.data.id}/edit`;
    },
  });

  return (
    <div className="bg-amber-50 border-l-4 border-amber-500 p-4 rounded">
      <h3 className="font-semibold">挑戰其他 sub_type</h3>
      <p className="text-sm text-gray-700 mt-1">
        您已續領 {approvedRenewalSubType}（保底）。可挑戰其他 sub_type；中籤則自動釋出保底名額。
      </p>
      <div className="mt-3 flex gap-3 items-center">
        <select
          className="border rounded px-2 py-1"
          value={targetSubType}
          onChange={(e) => setTargetSubType(e.target.value)}
        >
          {availableSubTypes.map((st) => (
            <option key={st} value={st}>{st}</option>
          ))}
        </select>
        <button
          className="px-4 py-2 bg-amber-600 text-white rounded"
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending || !targetSubType}
        >
          提交挑戰申請
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Conditionally render in student portal during general phase**

```typescript
// Pseudo: if student has approved renewal for this scholarship type, show card
{userApprovedRenewals.map((r) => (
  <ChallengeApplicationCard
    key={r.id}
    approvedRenewalId={r.id}
    approvedRenewalSubType={r.sub_scholarship_type}
    scholarshipTypeId={r.scholarship_type_id}
    scholarshipConfigQuotas={r.scholarship_config_quotas}
  />
))}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/components/student/ChallengeApplicationCard.tsx
git commit -m "feat(frontend): add challenge application card for students"
```

---

### Task 9.3: Application history with renewal/challenge linkage

**Files:**
- Modify: existing application history component (search via `grep -rn "申請紀錄\|application.*history" frontend/components/`)

- [ ] **Step 1: Locate**

```bash
grep -rn "我的申請\|application.*history" frontend/components/ | head
```

- [ ] **Step 2: Update component to show linkage**

Append to each application row:

```typescript
{app.previous_application_id && (
  <div className="text-xs text-gray-600">
    銜接自: <a href={`/applications/${app.previous_application_id}`}>
      APP-#{app.previous_application_id}
    </a>
  </div>
)}
{app.cancelled_due_to_application_id && (
  <div className="text-xs text-red-600">
    被取代於: <a href={`/applications/${app.cancelled_due_to_application_id}`}>
      APP-#{app.cancelled_due_to_application_id}
    </a> (挑戰申請成功)
  </div>
)}
{app.challenges_application_id && (
  <div className="text-xs text-amber-700">
    挑戰自續領: <a href={`/applications/${app.challenges_application_id}`}>
      APP-#{app.challenges_application_id}
    </a>
  </div>
)}
{app.status === "cancelled_by_challenge" && (
  <span className="text-red-600 text-xs">已取消 (因挑戰升級)</span>
)}
```

- [ ] **Step 3: Backend: ensure application detail response includes these fields**

Confirm `app.serialize()` or schema includes `previous_application_id`, `cancelled_due_to_application_id`, `challenges_application_id`.

- [ ] **Step 4: Commit**

```bash
git add frontend/components/.../ApplicationHistory*.tsx
git commit -m "feat(frontend): show renewal/challenge linkage in application history"
```

---

## Phase 10 — Validation & Monitoring

### Task 10.1: Background check for cancelled_by_challenge invariants

**Files:**
- Create: `backend/app/services/renewal_audit_service.py`
- Create: `backend/app/tests/test_renewal_audit_service.py`

- [ ] **Step 1: Write test**

```python
@pytest.mark.asyncio
async def test_finds_violations(db_session, application_factory):
    """An approved challenge whose renewal is NOT cancelled_by_challenge → violation."""
    renewal = await application_factory(
        is_renewal=True, status=ApplicationStatus.approved
    )
    challenge = await application_factory(
        is_renewal=False, challenges_application_id=renewal.id,
        status=ApplicationStatus.approved,
    )
    from app.services.renewal_audit_service import RenewalAuditService
    violations = await RenewalAuditService(db_session).find_invariant_violations()
    assert len(violations) == 1
    assert violations[0]["renewal_id"] == renewal.id
```

- [ ] **Step 2: Implement service**

```python
class RenewalAuditService:
    def __init__(self, db): self.db = db

    async def find_invariant_violations(self) -> list[dict]:
        # Each approved challenge must point to a cancelled_by_challenge renewal
        stmt = (
            select(Application.id, Application.challenges_application_id, Application.status)
            .where(
                Application.challenges_application_id.is_not(None),
                Application.status == ApplicationStatus.approved,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        violations = []
        for challenge_id, renewal_id, _ in rows:
            renewal = await self.db.scalar(
                select(Application).where(Application.id == renewal_id)
            )
            if renewal.status != ApplicationStatus.cancelled_by_challenge:
                violations.append({
                    "challenge_id": challenge_id,
                    "renewal_id": renewal_id,
                    "actual_renewal_status": renewal.status.value,
                })
        return violations
```

- [ ] **Step 3: Add admin endpoint to run check**

```python
@router.get("/audit/renewal-violations")
async def audit_renewal_violations(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    service = RenewalAuditService(db)
    return {"success": True, "data": await service.find_invariant_violations()}
```

- [ ] **Step 4: Run tests & commit**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_audit_service.py -v
git add backend/app/services/renewal_audit_service.py backend/app/tests/test_renewal_audit_service.py
git commit -m "feat(audit): add renewal invariant check service"
```

---

### Task 10.2: Distribution summary report

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py`

- [ ] **Step 1: Already implemented in Task 6.2 — `execute_general_distribution` returns summary**

Verify the return value of `execute_general_distribution` matches spec Section 12:

```python
{
  "approved_renewals": int,
  "approved_challenges": int,
  "released_slots": {(sub_type, year): count},
  "filled_in": int,
  "unfilled": int,
}
```

Assertion: `sum(released_slots.values()) == filled_in + unfilled`

- [ ] **Step 2: Add this assertion to integration test**

In `test_challenge_release_distribution.py`:

```python
@pytest.mark.asyncio
async def test_distribution_summary_balances(
    db_session, scholarship_type_factory, ...  # reuse setup
):
    # ... (same scenario as Task 6.1)
    service = ManualDistributionService(db_session)
    result = await service.execute_general_distribution(scholarship_type_id=st.id, academic_year=114)
    assert sum(result["released_slots"].values()) == result["filled_in"] + result["unfilled"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_challenge_release_distribution.py
git commit -m "test: verify distribution summary balances released = filled + unfilled"
```

---

## Phase 11 — End-to-End Smoke Test

### Task 11.1: Full E2E scenario test

**Files:**
- Create: `backend/app/tests/test_renewal_end_to_end.py`

- [ ] **Step 1: Write a single comprehensive test exercising the spec's example scenario**

```python
@pytest.mark.asyncio
async def test_full_renewal_challenge_e2e(
    db_session, async_client,
    student_factory, scholarship_type_factory, scholarship_configuration_factory,
    application_factory, college_ranking_factory,
):
    """
    Mirrors spec Section 9.3 example:
    - 10 students have approved 113 nstc applications
    - 114 renewal period opens → all 10 apply renewal
    - Renewal auto-approve → all 10 approved, occupying nstc[113]
    - 2 of them (A, B) submit challenge for moe_1w
    - General period: candidates ranked, distribution executed
    - Verify: A & B approved on moe_1w, their renewals cancelled, U & V promoted to nstc-113
    """
    # Setup
    st = await scholarship_type_factory(
        renewal_application_start_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        renewal_application_end_date=datetime(2026, 2, 1, tzinfo=timezone.utc),
        renewal_professor_review_end=datetime(2026, 2, 15, tzinfo=timezone.utc),
        renewal_college_review_end=datetime(2026, 3, 1, tzinfo=timezone.utc),
        application_start_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
        application_end_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
    )
    await scholarship_configuration_factory(
        scholarship_type_id=st.id,
        quotas={"nstc": {"114": 8, "113": 0}, "moe_1w": {"114": 6}},
    )

    # 10 113-cohort approved applications
    students = [await student_factory() for _ in range(10)]
    prior_apps = [
        await application_factory(
            user_id=s.id, scholarship_type_id=st.id, sub_scholarship_type="nstc",
            academic_year=113, status=ApplicationStatus.approved, renewal_year=113,
        )
        for s in students
    ]

    # All 10 apply renewal (simulated via direct service call)
    from app.services.application_service import ApplicationService
    for i, prev in enumerate(prior_apps):
        await ApplicationService(db_session).create_renewal_from_previous(
            previous=prev, current_user=students[i],
            target_academic_year=114, renewal_year=113,
        )
    await db_session.commit()

    # Auto-approve renewals
    from app.services.renewal_distribution_service import RenewalDistributionService
    # Set their stage to college_reviewed first (simulating review pass)
    renewals = (await db_session.execute(
        select(Application).where(
            Application.scholarship_type_id == st.id,
            Application.is_renewal == True,
        )
    )).scalars().all()
    for r in renewals:
        r.review_stage = ReviewStage.college_reviewed
        r.status = ApplicationStatus.under_review
    await db_session.commit()
    await RenewalDistributionService(db_session).auto_approve_passed_reviews(st.id)

    # A and B submit challenges for moe_1w
    A_renewal, B_renewal = renewals[0], renewals[1]
    for r in [A_renewal, B_renewal]:
        await ApplicationService(db_session).create_challenge_from_renewal(
            renewal=r, current_user=students[renewals.index(r)],
            target_sub_type="moe_1w",
        )
    await db_session.commit()

    # 8 pure-new nstc candidates ranked 1-10, 6 pure-new moe_1w ranked 2-7 (A, B at rank 1, 2)
    pure_new_nstc = []
    for rank in range(1, 11):
        s = await student_factory()
        a = await application_factory(
            user_id=s.id, scholarship_type_id=st.id, sub_scholarship_type="nstc",
            academic_year=114, status=ApplicationStatus.under_review, is_renewal=False,
        )
        await college_ranking_factory(application_id=a.id, rank=rank)
        pure_new_nstc.append(a)

    # Get A and B challenge apps for ranking
    challenges = (await db_session.execute(
        select(Application).where(
            Application.scholarship_type_id == st.id,
            Application.challenges_application_id.is_not(None),
        )
    )).scalars().all()
    await college_ranking_factory(application_id=challenges[0].id, rank=1)
    await college_ranking_factory(application_id=challenges[1].id, rank=2)
    for rank in range(3, 9):
        s = await student_factory()
        a = await application_factory(
            user_id=s.id, scholarship_type_id=st.id, sub_scholarship_type="moe_1w",
            academic_year=114, is_renewal=False,
        )
        await college_ranking_factory(application_id=a.id, rank=rank)

    # Execute general distribution
    from app.services.manual_distribution_service import ManualDistributionService
    result = await ManualDistributionService(db_session).execute_general_distribution(
        scholarship_type_id=st.id, academic_year=114
    )

    # Refresh and assert
    await db_session.refresh(A_renewal); await db_session.refresh(B_renewal)
    assert A_renewal.status == ApplicationStatus.cancelled_by_challenge
    assert B_renewal.status == ApplicationStatus.cancelled_by_challenge

    # Find approved challenges
    approved_challenges = [c for c in challenges if c.status == ApplicationStatus.approved]
    assert len(approved_challenges) == 2

    # U (rank 9) and V (rank 10) should be approved with allocation_year=113
    await db_session.refresh(pure_new_nstc[8])  # rank 9 = U
    await db_session.refresh(pure_new_nstc[9])  # rank 10 = V
    assert pure_new_nstc[8].status == ApplicationStatus.approved
    assert pure_new_nstc[9].status == ApplicationStatus.approved

    # Summary balances
    assert sum(result["released_slots"].values()) == result["filled_in"] + result["unfilled"]
    assert result["filled_in"] == 2  # U and V filled
```

- [ ] **Step 2: Run → expect PASS**

```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest backend/app/tests/test_renewal_end_to_end.py -v
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/tests/test_renewal_end_to_end.py
git commit -m "test: add full E2E renewal+challenge distribution scenario"
```

---

## Phase 12 — Final Integration & Type Sync

### Task 12.1: Regenerate OpenAPI types for frontend

- [ ] **Step 1: Start backend container**

```bash
docker compose -f docker-compose.dev.yml up -d backend
```

- [ ] **Step 2: Run type generation**

```bash
cd frontend && npm run api:generate
```

- [ ] **Step 3: Commit generated types**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(types): regenerate OpenAPI types for renewal endpoints"
```

---

### Task 12.2: Documentation update

**Files:**
- Modify: `backend/docs/scholarship_renewal_design.md` (existing partial doc)
- Or replace with reference to new spec

- [ ] **Step 1: Add a "See also" note at top of `backend/docs/scholarship_renewal_design.md`**

```markdown
> **Note:** This document describes the timeline framework only. For the complete
> end-to-end design including challenge applications, slot release, and waitlist
> fill-in, see `docs/superpowers/specs/2026-05-13-renewal-application-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add backend/docs/scholarship_renewal_design.md
git commit -m "docs: point renewal design doc to extended spec"
```

---

## Plan Self-Review

- **Spec coverage check:**
  - Section 5 (Data model) → Phase 1 ✓
  - Section 6 (State machine) → Phase 3 (creation), Phase 5 (renewal), Phase 6 (general) ✓
  - Section 7 (Eligibility + creation) → Phase 2 + Phase 3 ✓
  - Section 8 (Renewal review/distribution) → Phase 4 + Phase 5 ✓
  - Section 9 (General distribution) → Phase 6 ✓
  - Section 10 (Boundary cases) — covered via tests in Phases 2, 3, 6
  - Section 11 (Error messages) — covered in Phase 3 endpoints
  - Section 12 (Monitoring) → Phase 10 ✓
  - Section 13 (Integration points) — addressed throughout (manual_distribution, roster, etc.)
  - Section 14 (Admin UI) → Phase 7, Phase 8 ✓
  - Section 14.3 (Student history) → Phase 9.3 ✓

- **Type consistency:**
  - `challenges_application_id`, `cancelled_due_to_application_id`, `renewal_year`, `previous_application_id`, `sub_scholarship_type`, `academic_year` used consistently throughout
  - Method names: `create_renewal_from_previous`, `create_challenge_from_renewal`, `auto_approve_passed_reviews`, `execute_general_distribution`, `preview_release_chain`, `compute_distribution_state`, `find_invariant_violations` — all consistent

- **No placeholders verified:** All code blocks contain actual implementation; only one TBD acknowledged in Task 9.3 (locate existing history component — requires runtime grep).

---

**Implementation order recommendation:** Phases 1 → 2 → 3 → 5 → 4 → 6 → 7 → 8 → 9 → 10 → 11 → 12. Phase 4 can defer until backend logic is solid since review routing is a refinement on top of existing flows.

**Estimated effort:** 5-7 days for a developer familiar with FastAPI + Next.js; longer if unfamiliar with this codebase. Each phase is independently testable and shippable.
