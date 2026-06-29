# Hide Submitted / No-Eligible Scholarships From Apply Flow — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hide scholarships a student has already submitted (and show a clear message when none are applyable) from the student apply flow, while keeping the read-only catalog complete.

**Architecture:** The backend computes a single boolean `already_submitted` per eligible scholarship via a dedicated `EXISTS` query over an explicit `HIDDEN_APPLICATION_STATUSES` allow-list, and surfaces it on `EligibleScholarshipResponse`. The frontend adds an `isApplyableScholarship` predicate and applies it only in the two apply-flow surfaces (wizard dropdown + portal "新申請" gate); the catalog is untouched.

**Tech Stack:** FastAPI + SQLAlchemy (async) + PostgreSQL; Next.js + React + TypeScript; pytest (unit + integration suites); jest (frontend).

**Spec:** `docs/superpowers/specs/2026-06-29-hide-submitted-scholarships-from-apply-flow-design.md`

## Global Constraints

- Branch: `worktree-hide-applied-scholarships`. Commit messages in English, conventional-commits format. No co-author/attribution trailer (disabled globally).
- API responses keep the ApiResponse wrapper `{success, message, data}`; do NOT introduce `response_model`.
- Status constants are `.value` strings, matching the existing `REVIEWABLE_APPLICATION_STATUSES` convention in `backend/app/models/enums.py`.
- The hide-set invariant: a scholarship is shown in the apply flow ⟺ a fresh/continued application is submittable (consistent with the `DUPLICATE_APPLICATION` guard in `applications.py`).
- Backend lint is hard-gated: `uvx --from "black==26.3.1" black --check --line-length=120 backend/app` and `flake8 app --select=B904,B014 --max-line-length=120` must pass.
- Run backend pytest inside the dev container; async/`*_service*` tests land in the integration suite, sync tests in the unit suite.
- `ApplicationStatus` has exactly 13 values: draft, submitted, under_review, pending_documents, approved, partial_approved, rejected, returned, withdrawn, cancelled, manual_excluded, cancelled_by_challenge, deleted. Do NOT change enum values (would trip the enum-pin tripwire `test_shared_enums_value_contract.py`).

---

### Task 1: Status sets + DRY the duplicate-application guard

**Files:**
- Modify: `backend/app/models/enums.py` (add 3 constants after `REVIEWABLE_APPLICATION_STATUSES`, ~line 56)
- Modify: `backend/app/api/v1/endpoints/applications.py:154-159` (use the shared constant) + its enums import
- Test: `backend/app/tests/test_application_status_sets.py` (new, sync unit test)

**Interfaces:**
- Produces: `REAPPLY_ALLOWED_APPLICATION_STATUSES`, `EDITABLE_APPLICATION_STATUSES`, `HIDDEN_APPLICATION_STATUSES` — each a `list[str]` of `ApplicationStatus.*.value`, importable from `app.models.enums`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_application_status_sets.py`:

```python
"""Pin: the apply-flow visibility sets partition every ApplicationStatus value.

These three sets decide whether a scholarship is shown in the student apply
flow. They MUST stay a partition of the full enum so a newly-added status is
forced into a deliberate classification (and never silently both-shown-and-hidden).
"""

from app.models.enums import (
    ApplicationStatus,
    EDITABLE_APPLICATION_STATUSES,
    HIDDEN_APPLICATION_STATUSES,
    REAPPLY_ALLOWED_APPLICATION_STATUSES,
)


def test_sets_are_value_strings():
    all_values = {s.value for s in ApplicationStatus}
    for bucket in (
        REAPPLY_ALLOWED_APPLICATION_STATUSES,
        EDITABLE_APPLICATION_STATUSES,
        HIDDEN_APPLICATION_STATUSES,
    ):
        assert set(bucket) <= all_values


def test_sets_partition_the_enum():
    reapply = set(REAPPLY_ALLOWED_APPLICATION_STATUSES)
    editable = set(EDITABLE_APPLICATION_STATUSES)
    hidden = set(HIDDEN_APPLICATION_STATUSES)

    # disjoint
    assert reapply & editable == set()
    assert reapply & hidden == set()
    assert editable & hidden == set()

    # cover every enum value
    assert reapply | editable | hidden == {s.value for s in ApplicationStatus}


def test_hidden_set_is_exactly_the_submitted_and_beyond_statuses():
    assert set(HIDDEN_APPLICATION_STATUSES) == {
        "submitted",
        "under_review",
        "pending_documents",
        "approved",
        "partial_approved",
        "manual_excluded",
        "cancelled_by_challenge",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_application_status_sets.py -p no:cacheprovider -q`
Expected: FAIL with `ImportError: cannot import name 'REAPPLY_ALLOWED_APPLICATION_STATUSES'`.

- [ ] **Step 3: Add the constants**

In `backend/app/models/enums.py`, immediately after the `REVIEWABLE_APPLICATION_STATUSES = [...]` block (before `class ReviewStage`), add:

```python
# ── Apply-flow visibility sets ───────────────────────────────────────
# Partition every ApplicationStatus value into three buckets that decide
# whether a scholarship is shown in the STUDENT APPLY FLOW.
# Invariant: shown ⟺ a fresh/continued application is still submittable
# (kept consistent with the DUPLICATE_APPLICATION guard in applications.py).

# Terminal/withdrawn states the duplicate guard does NOT block — the student may
# re-apply, so the scholarship stays visible. Mirrors the guard's exclude set;
# `deleted` is a soft-delete tombstone, intentionally treated as re-applyable.
REAPPLY_ALLOWED_APPLICATION_STATUSES = [
    ApplicationStatus.withdrawn.value,
    ApplicationStatus.rejected.value,
    ApplicationStatus.cancelled.value,
    ApplicationStatus.deleted.value,
]

# In-progress states the student finishes IN PLACE via the edit flow — the
# scholarship stays visible so the draft/returned item can be completed.
EDITABLE_APPLICATION_STATUSES = [
    ApplicationStatus.draft.value,
    ApplicationStatus.returned.value,
]

# "已送出/處理中" — a blocking application exists that is NOT continuable in
# place, so the scholarship is HIDDEN from the apply flow. Exactly the complement
# of REAPPLY_ALLOWED ∪ EDITABLE over the full enum. `manual_excluded` and
# `cancelled_by_challenge` are here because the duplicate guard blocks them too
# (showing them would only lead to a DUPLICATE_APPLICATION error on submit).
HIDDEN_APPLICATION_STATUSES = [
    ApplicationStatus.submitted.value,
    ApplicationStatus.under_review.value,
    ApplicationStatus.pending_documents.value,
    ApplicationStatus.approved.value,
    ApplicationStatus.partial_approved.value,
    ApplicationStatus.manual_excluded.value,
    ApplicationStatus.cancelled_by_challenge.value,
]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_application_status_sets.py -p no:cacheprovider -q`
Expected: PASS (3 passed).

- [ ] **Step 5: DRY the duplicate guard to use the shared constant**

In `backend/app/api/v1/endpoints/applications.py`, add the import (alongside the existing enum imports near the top of the file):

```python
from app.models.enums import REAPPLY_ALLOWED_APPLICATION_STATUSES
```

Then replace the inline list at `applications.py:154-159`:

```python
        # 排除已撤回/拒絕/取消/刪除的申請
        excluded_statuses = [
            ApplicationStatus.withdrawn,
            ApplicationStatus.rejected,
            ApplicationStatus.cancelled,
            ApplicationStatus.deleted,
        ]
```

with:

```python
        # 排除已撤回/拒絕/取消/刪除的申請 (shared set — see app.models.enums)
        excluded_statuses = REAPPLY_ALLOWED_APPLICATION_STATUSES
```

(`Application.status.notin_(excluded_statuses)` with `.value` strings matches how the sibling `get_application_status` already uses `Application.status.in_([.value strings])` against this enum column. Task 2's integration test exercises the same value-string membership and de-risks this change.)

- [ ] **Step 6: Verify no regression in application endpoint tests + lint**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests -k "application and (duplicate or create)" -p no:cacheprovider -q
docker compose -f docker-compose.dev.yml exec backend bash -lc 'uvx --from "black==26.3.1" black --check --line-length=120 app/models/enums.py app/api/v1/endpoints/applications.py && flake8 app/models/enums.py app/api/v1/endpoints/applications.py --select=B904,B014 --max-line-length=120'
```
Expected: tests PASS (or no tests collected for the `-k` filter — acceptable), lint clean.

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/enums.py backend/app/api/v1/endpoints/applications.py backend/app/tests/test_application_status_sets.py
git commit -m "feat(enums): add apply-flow status sets and DRY the duplicate guard"
```

---

### Task 2: `has_blocking_application` query method

**Files:**
- Modify: `backend/app/services/eligibility_service.py` (add method to `EligibilityService`)
- Test: `backend/app/tests/test_eligibility_blocking_service.py` (new, async integration test)

**Interfaces:**
- Consumes: `HIDDEN_APPLICATION_STATUSES` (Task 1).
- Produces: `EligibilityService.has_blocking_application(user_id: int, config) -> bool` — returns `True` iff the student has an application for `(user_id, config.scholarship_type_id, config.academic_year, config.semester)` whose status is in `HIDDEN_APPLICATION_STATUSES`. `config` only needs `.scholarship_type_id`, `.academic_year`, `.semester`.

- [ ] **Step 1: Write the failing test**

Create `backend/app/tests/test_eligibility_blocking_service.py`:

```python
"""Integration tests for EligibilityService.has_blocking_application.

A scholarship is hidden from the apply flow iff the student has a 'blocking'
(submitted-and-beyond) application for the same (type, year, semester).
"""

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.enums import Semester
from app.models.scholarship import ScholarshipType
from app.models.user import User
from app.services.eligibility_service import EligibilityService

_SEQ = 0


async def _make_application(db: AsyncSession, user: User, scholarship: ScholarshipType, status: str) -> Application:
    global _SEQ
    _SEQ += 1
    app = Application(
        user_id=user.id,
        scholarship_type_id=scholarship.id,
        sub_type_selection_mode="single",
        status=status,
        app_id=f"TEST-BLOCK-{_SEQ:06d}",
        academic_year=2024,
        semester="first",
        student_data={"name": "Test Student"},
        submitted_form_data={},
        agree_terms=True,
    )
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


def _config(scholarship: ScholarshipType) -> SimpleNamespace:
    return SimpleNamespace(
        scholarship_type_id=scholarship.id,
        academic_year=2024,
        semester=Semester.first,
    )


@pytest.mark.parametrize(
    "status,expected",
    [
        ("submitted", True),
        ("under_review", True),
        ("pending_documents", True),
        ("approved", True),
        ("partial_approved", True),
        ("manual_excluded", True),
        ("cancelled_by_challenge", True),
        ("draft", False),
        ("returned", False),
        ("rejected", False),
        ("withdrawn", False),
        ("cancelled", False),
        ("deleted", False),
    ],
)
async def test_has_blocking_application_truth_table(db, test_user, test_scholarship, status, expected):
    await _make_application(db, test_user, test_scholarship, status)
    service = EligibilityService(db)
    result = await service.has_blocking_application(test_user.id, _config(test_scholarship))
    assert result is expected


async def test_no_application_is_not_blocking(db, test_user, test_scholarship):
    service = EligibilityService(db)
    assert await service.has_blocking_application(test_user.id, _config(test_scholarship)) is False


async def test_rejected_plus_new_draft_is_not_blocking_and_does_not_crash(db, test_user, test_scholarship):
    # A student who was rejected then started a fresh draft has TWO rows for the
    # same config. EXISTS over the hidden set must return False (re-applyable)
    # and must not raise MultipleResultsFound.
    await _make_application(db, test_user, test_scholarship, "rejected")
    await _make_application(db, test_user, test_scholarship, "draft")
    service = EligibilityService(db)
    assert await service.has_blocking_application(test_user.id, _config(test_scholarship)) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_eligibility_blocking_service.py -p no:cacheprovider -q`
Expected: FAIL with `AttributeError: 'EligibilityService' object has no attribute 'has_blocking_application'`.

- [ ] **Step 3: Implement the method**

In `backend/app/services/eligibility_service.py`, add the import near the other enums import (`from app.models.application import Application, ApplicationStatus` already exists; add a separate line):

```python
from app.models.enums import HIDDEN_APPLICATION_STATUSES
```

Then add this method to the `EligibilityService` class (e.g. directly above `get_application_status`, ~line 478). `select` and `and_` are already imported at the top of the file.

```python
    async def has_blocking_application(self, user_id: int, config) -> bool:
        """Whether the student already has a submitted-and-beyond application
        for this scholarship configuration — i.e. one that should HIDE the
        scholarship from the apply flow.

        Uses the same (user, type, year, semester) key and semester comparison
        as the DUPLICATE_APPLICATION guard so 'shown ⟺ submittable' holds. An
        EXISTS query: deterministic, no None edge, safe with multiple rows.
        """
        if config.semester:
            semester_filter = Application.semester == config.semester
        else:
            semester_filter = Application.semester.is_(None)

        stmt = (
            select(Application.id)
            .where(
                and_(
                    Application.user_id == user_id,
                    Application.scholarship_type_id == config.scholarship_type_id,
                    Application.academic_year == config.academic_year,
                    semester_filter,
                    Application.status.in_(HIDDEN_APPLICATION_STATUSES),
                )
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests/test_eligibility_blocking_service.py -p no:cacheprovider -q`
Expected: PASS (15 passed).

- [ ] **Step 5: Lint**

Run: `docker compose -f docker-compose.dev.yml exec backend bash -lc 'uvx --from "black==26.3.1" black --check --line-length=120 app/services/eligibility_service.py && flake8 app/services/eligibility_service.py --select=B904,B014 --max-line-length=120'`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/eligibility_service.py backend/app/tests/test_eligibility_blocking_service.py
git commit -m "feat(eligibility): add has_blocking_application EXISTS query"
```

---

### Task 3: Surface `already_submitted` on the eligible endpoint

**Files:**
- Modify: `backend/app/services/scholarship_service.py:152-156` and `:224-239` (replace status call, set `already_submitted`)
- Modify: `backend/app/schemas/scholarship.py:259-286` (add field)
- Modify: `backend/app/api/v1/endpoints/scholarships.py:225-253` (pass through)

**Interfaces:**
- Consumes: `EligibilityService.has_blocking_application` (Task 2).
- Produces: `EligibleScholarshipResponse.already_submitted: bool` (default `False`) — `True` when the student has a blocking application for that configuration.

- [ ] **Step 1: Replace the status call in the service**

In `backend/app/services/scholarship_service.py`, at `:152-156`, replace:

```python
            # Always get application status if user_id is provided, regardless of eligibility
            application_status = {}
            if user_id:
                application_status = await eligibility_service.get_application_status(user_id, config)
```

with:

```python
            # Whether the student already has a submitted-and-beyond application
            # for this configuration → hides it from the apply flow (see spec).
            already_submitted = False
            if user_id:
                already_submitted = await eligibility_service.has_blocking_application(user_id, config)
```

- [ ] **Step 2: Set `already_submitted` on the scholarship dict (drop the stripped status fields)**

In the same file at `:224-239`, replace the `scholarship_dict.update({...})` block's application-status fields. Change:

```python
                scholarship_dict.update(
                    {
                        "quota_available": quota_available,
                        "quota_info": quota_info,
                        # Add rule evaluation results
                        "passed": eligibility_details.get("passed", []),
                        "warnings": eligibility_details.get("warnings", []),
                        "errors": eligibility_details.get("errors", []),
                        # Add application status information
                        "application_status": application_status.get("application_status"),
                        "can_apply": application_status.get("can_apply", True),
                        "status_display": application_status.get("status_display", "可申請"),
                        "has_application": application_status.get("has_application", False),
                        "application_id": application_status.get("application_id"),
                    }
                )
```

to:

```python
                scholarship_dict.update(
                    {
                        "quota_available": quota_available,
                        "quota_info": quota_info,
                        # Add rule evaluation results
                        "passed": eligibility_details.get("passed", []),
                        "warnings": eligibility_details.get("warnings", []),
                        "errors": eligibility_details.get("errors", []),
                        # Hide already-submitted scholarships from the apply flow
                        "already_submitted": already_submitted,
                    }
                )
```

(The removed `application_status`/`can_apply`/`status_display`/`has_application`/`application_id` keys were already stripped by `EligibleScholarshipResponse` and unused downstream.)

- [ ] **Step 3: Add the schema field**

In `backend/app/schemas/scholarship.py`, inside `class EligibleScholarshipResponse` (after `subtype_eligibility: Dict[...] = {}`, before `model_config`), add:

```python
    already_submitted: bool = False
```

- [ ] **Step 4: Pass it through in the endpoint**

In `backend/app/api/v1/endpoints/scholarships.py`, in the `EligibleScholarshipResponse(...)` constructor (~`:225-253`), add a line (e.g. after `created_at=scholarship.get("created_at"),`):

```python
            already_submitted=scholarship.get("already_submitted", False),
```

- [ ] **Step 5: Verify the full eligible suite + lint**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend python -m pytest app/tests -k "eligible or eligibility or scholarship_service" -p no:cacheprovider -q
docker compose -f docker-compose.dev.yml exec backend bash -lc 'uvx --from "black==26.3.1" black --check --line-length=120 app/services/scholarship_service.py app/schemas/scholarship.py app/api/v1/endpoints/scholarships.py && flake8 app/services/scholarship_service.py app/schemas/scholarship.py app/api/v1/endpoints/scholarships.py --select=B904,B014 --max-line-length=120'
```
Expected: tests PASS, lint clean.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/scholarship_service.py backend/app/schemas/scholarship.py backend/app/api/v1/endpoints/scholarships.py
git commit -m "feat(scholarships): expose already_submitted on the eligible response"
```

---

### Task 4: Frontend type + `isApplyableScholarship` predicate

**Files:**
- Modify: `frontend/lib/api/types.ts:209-244` (add field to `ScholarshipType`)
- Modify: `frontend/lib/scholarship-eligibility.ts` (add predicate)
- Test: `frontend/lib/__tests__/scholarship-eligibility.test.ts` (new)

**Interfaces:**
- Consumes: `ScholarshipType.already_submitted?: boolean`, `isSelectableScholarship`.
- Produces: `isApplyableScholarship(scholarship: ScholarshipType): boolean`.

- [ ] **Step 1: Write the failing test**

Create `frontend/lib/__tests__/scholarship-eligibility.test.ts`:

```ts
import type { ScholarshipType } from "@/lib/api/types";
import {
  isApplyableScholarship,
  isSelectableScholarship,
} from "@/lib/scholarship-eligibility";

const selectable = {
  eligible_sub_types: [
    { value: "nstc", label: "NSTC", label_en: "NSTC", is_default: true },
  ],
  errors: [],
} as unknown as ScholarshipType;

describe("isApplyableScholarship", () => {
  it("is true for a selectable scholarship with no submission", () => {
    expect(isSelectableScholarship(selectable)).toBe(true);
    expect(isApplyableScholarship(selectable)).toBe(true);
  });

  it("is false when already submitted", () => {
    const submitted = { ...selectable, already_submitted: true } as ScholarshipType;
    expect(isApplyableScholarship(submitted)).toBe(false);
  });

  it("is true when already_submitted is explicitly false", () => {
    const notSubmitted = { ...selectable, already_submitted: false } as ScholarshipType;
    expect(isApplyableScholarship(notSubmitted)).toBe(true);
  });

  it("is false when not selectable, even if not submitted", () => {
    const notSelectable = {
      eligible_sub_types: [],
      errors: [],
      already_submitted: false,
    } as unknown as ScholarshipType;
    expect(isApplyableScholarship(notSelectable)).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx jest lib/__tests__/scholarship-eligibility.test.ts`
Expected: FAIL with `isApplyableScholarship is not a function` (or a TS error that the export is missing).

- [ ] **Step 3: Add the field to the type**

In `frontend/lib/api/types.ts`, inside `interface ScholarshipType` (e.g. after `terms_document_url?: string;`), add:

```ts
  already_submitted?: boolean;
```

- [ ] **Step 4: Add the predicate**

In `frontend/lib/scholarship-eligibility.ts`, append:

```ts
// Apply-flow predicate: a scholarship is offered in the student apply flow only
// when it is selectable AND the student has not already submitted it. The
// backend computes `already_submitted` (see EligibleScholarshipResponse).
export function isApplyableScholarship(scholarship: ScholarshipType): boolean {
  return isSelectableScholarship(scholarship) && !scholarship.already_submitted;
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd frontend && npx jest lib/__tests__/scholarship-eligibility.test.ts`
Expected: PASS (4 passed).

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/api/types.ts frontend/lib/scholarship-eligibility.ts frontend/lib/__tests__/scholarship-eligibility.test.ts
git commit -m "feat(frontend): add isApplyableScholarship predicate and already_submitted type"
```

---

### Task 5: Apply the filter in the two apply-flow surfaces + empty-state copy

**Files:**
- Modify: `frontend/lib/i18n.ts:337-340` (zh) and `:851-855` (en) — add `all_eligible_already_submitted`
- Modify: `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:57` (import) and `:744` (filter)
- Modify: `frontend/components/enhanced-student-portal.tsx:36` (import) and `:1336-1355` (gate + empty state)

**Interfaces:**
- Consumes: `isApplyableScholarship` (Task 4), `t("messages.all_eligible_already_submitted")`.

- [ ] **Step 1: Add i18n strings (zh + en)**

In `frontend/lib/i18n.ts`, in the **zh** `messages` block (after `no_eligible_scholarships_desc`, ~`:340`):

```ts
      all_eligible_already_submitted: "您可申請的獎學金皆已送出，請至「我的申請」查看進度",
```

In the **en** `messages` block (after `no_eligible_scholarships_desc`, ~`:855`):

```ts
      all_eligible_already_submitted:
        "You have already submitted every scholarship you can apply for. See progress under \"My Applications\".",
```

- [ ] **Step 2: Verify i18n parity test still passes**

Run: `cd frontend && npx jest lib/__tests__/i18n.test.ts`
Expected: PASS (zh/en key parity holds because the key was added to both trees).

- [ ] **Step 3: Switch the wizard dropdown to the apply-flow predicate**

In `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx`, change the import at `:57`:

```ts
import { isSelectableScholarship } from "@/lib/scholarship-eligibility";
```

to:

```ts
import { isApplyableScholarship } from "@/lib/scholarship-eligibility";
```

Then at `:744`, change:

```ts
        setEligibleScholarships(response.data.filter(isSelectableScholarship));
```

to:

```ts
        setEligibleScholarships(response.data.filter(isApplyableScholarship));
```

(`isSelectableScholarship` has no other use in this file; the import swap is complete.)

- [ ] **Step 4: Switch the portal gate + differentiate the empty state**

In `frontend/components/enhanced-student-portal.tsx`, change the import at `:36`:

```ts
import { isSelectableScholarship } from "@/lib/scholarship-eligibility";
```

to (keep both — `isSelectableScholarship` is still used at `:1363` for the catalog):

```ts
import {
  isApplyableScholarship,
  isSelectableScholarship,
} from "@/lib/scholarship-eligibility";
```

Then replace the new-application gate block at `:1336-1355`:

```tsx
      {activeTab === "new-application" &&
        (editingApplication ||
        eligibleScholarships.some(isSelectableScholarship) ? (
          <StudentApplicationWizard
            user={user}
            locale={locale}
            onApplicationComplete={handleApplicationComplete}
            editingApplication={editingApplication}
            initialStep={editingApplication ? 2 : undefined}
          />
        ) : (
          <Card>
            <CardContent className="p-6 text-center">
              <AlertTriangle className="h-8 w-8 text-orange-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold">
                {t("messages.no_eligible_scholarships")}
              </h3>
            </CardContent>
          </Card>
        ))}
```

with:

```tsx
      {activeTab === "new-application" &&
        (editingApplication ||
        eligibleScholarships.some(isApplyableScholarship) ? (
          <StudentApplicationWizard
            user={user}
            locale={locale}
            onApplicationComplete={handleApplicationComplete}
            editingApplication={editingApplication}
            initialStep={editingApplication ? 2 : undefined}
          />
        ) : (
          <Card>
            <CardContent className="p-6 text-center">
              <AlertTriangle className="h-8 w-8 text-orange-500 mx-auto mb-4" />
              <h3 className="text-lg font-semibold">
                {eligibleScholarships.some(isSelectableScholarship)
                  ? t("messages.all_eligible_already_submitted")
                  : t("messages.no_eligible_scholarships")}
              </h3>
            </CardContent>
          </Card>
        ))}
```

(When some scholarships are selectable but none are applyable → all were submitted → show the "皆已送出" message; otherwise the student is simply not eligible → keep the existing message.)

- [ ] **Step 5: Typecheck + lint the frontend**

Run:
```bash
cd frontend && npx tsc --noEmit && npx eslint components/enhanced-student-portal.tsx components/student-wizard/steps/ScholarshipApplicationStep.tsx lib/scholarship-eligibility.ts lib/i18n.ts
```
Expected: no type errors, no lint errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/lib/i18n.ts frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx frontend/components/enhanced-student-portal.tsx
git commit -m "feat(frontend): hide already-submitted scholarships from the apply flow"
```

---

### Task 6: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts` (generated)

**Interfaces:** none (keeps generated types in sync with the new backend field; CI validates sync).

- [ ] **Step 1: Ensure the backend is running with the new field**

Run: `docker compose -f docker-compose.dev.yml up -d backend` (or confirm it's already up and hot-reloaded with Task 3's changes).
Verify: `curl -s localhost:8000/openapi.json | grep -q already_submitted && echo OK`
Expected: `OK`.

- [ ] **Step 2: Regenerate**

Run: `cd frontend && npm run api:generate`
Expected: `lib/api/generated/schema.d.ts` updated to include `already_submitted` on the eligible-scholarship schema.

- [ ] **Step 3: Typecheck**

Run: `cd frontend && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore(api): regenerate OpenAPI types for already_submitted"
```

---

### Task 7 (optional): E2E — submitted scholarship hidden from apply flow but kept in catalog

**Files:**
- Create: `frontend/e2e/specs/student-hide-submitted-scholarship.spec.ts`

**Interfaces:** Consumes the full stack behavior from Tasks 1-6.

- [ ] **Step 1: Write the E2E spec**

Create `frontend/e2e/specs/student-hide-submitted-scholarship.spec.ts`. Follow the existing student E2E patterns in `frontend/e2e/specs/student-duplicate-reapply.spec.ts` (auth/setup helpers, seeded data). The assertions:

```ts
// After a student has a SUBMITTED application for scholarship X:
// 1) the "學生申請" wizard scholarship <Select> does NOT list X
// 2) the "獎學金列表" catalog DOES still list X
// (Reuse the spec's login + seed helpers; do not hand-roll auth.)
```

- [ ] **Step 2: Run it**

Run: `cd frontend && npx playwright test e2e/specs/student-hide-submitted-scholarship.spec.ts`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/specs/student-hide-submitted-scholarship.spec.ts
git commit -m "test(e2e): submitted scholarship hidden from apply flow, kept in catalog"
```

---

## Self-Review

**Spec coverage:**
- Backend `HIDDEN_APPLICATION_STATUSES` + DRY guard → Task 1. ✅
- `has_blocking_application` EXISTS query, semester parity with guard, multi-row safety → Task 2. ✅
- `already_submitted` wired into service + schema + endpoint (with default `False`) → Task 3. ✅
- `/eligible` no longer calls `get_application_status` (crash path removed from hot path) → Task 3, Step 1. ✅
- Frontend type + `isApplyableScholarship` → Task 4. ✅
- Wizard dropdown filter + portal gate + differentiated empty state → Task 5. ✅
- i18n in `frontend/lib/i18n.ts` zh + en → Task 5, Steps 1-2. ✅
- Catalog unchanged → Task 5 keeps `isSelectableScholarship` at `:1363`. ✅
- OpenAPI regen → Task 6. ✅
- Tests (backend truth table incl. manual_excluded/cancelled_by_challenge, multi-row; frontend unit; optional E2E) → Tasks 1, 2, 4, 7. ✅
- Out-of-scope (catalog, guard behavior, renewal/challenge cards) → respected; no tasks touch them.

**Placeholder scan:** No TBD/TODO; every code step shows full code. Task 7 is explicitly optional and points at an existing spec to mirror rather than inventing auth scaffolding.

**Type consistency:** `has_blocking_application(user_id, config) -> bool` is defined in Task 2 and consumed identically in Task 3. `already_submitted` is `bool` (backend) / `boolean?` (frontend) throughout. `isApplyableScholarship` signature defined in Task 4 and used unchanged in Task 5. Status constant names identical across Tasks 1-3.
