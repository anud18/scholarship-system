# Batch Import Aligned with Student Self-Submission — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Batch-imported applications behave like student self-submitted ones: same review flow (`submitted` → professor → college), same `submitted_form_data` structure, same field values (`config.amount`, `config.config_name`), postal/advisor data in `UserProfile`, and eligibility warnings at preview.

**Architecture:** Extract the drift-prone application-construction core into a new shared module `backend/app/services/application_builder.py` (app_id generation, sub-type derivation/validation/ordering, submitted-state field values, professor auto-assign). Both `ApplicationService` (student path — pure refactor, behavior unchanged) and `BatchImportService` (batch path — behavior changes per spec) call it.

**Tech Stack:** FastAPI, SQLAlchemy async, pandas/openpyxl, pytest (`asyncio_mode=auto`), Next.js frontend (no code change expected).

**Spec:** `docs/superpowers/specs/2026-07-09-batch-import-like-student-submission-design.md`

## Global Constraints

- Run backend tests inside the dev container: `docker exec scholarship_backend_dev python -m pytest <path> -v --no-cov -p no:cacheprovider`
- `async def` tests run in the **integration** CI lane automatically (`asyncio_mode=auto`); sync tests run in **unit**. Do not convert existing sync tests to async.
- Lint gates (hard): `uvx --from "black==26.3.1" black --check --line-length=120 backend/app`; `flake8 app --select=B904,B014 --max-line-length=120` (run inside `backend/`); `raise` inside `except` must use `from exc`; `logger.warning/error` interpolating the exception inside `except` must pass `exc_info=True`.
- Enum convention: Python enum members lowercase matching DB values; pass enum **members** (not `.value`) when constructing in-memory test objects.
- Never build test models via `Model.__new__`; use `Model(**kwargs)` or `m = Model(); m.__dict__.update(...)` for duck-typed stubs.
- API responses stay in `{success, message, data}` format.
- Commit messages in English, conventional-commit style.
- Keep `app_id` suffix `"U"` for batch imports. No email automation, no fixed-document cloning, no DB migration, no data backfill.
- Sub-types are configuration-driven strings, lowercase (`nstc`, `moe_1w`, …) — never enum-constrained.

---

### Task 1: `application_builder.py` — pure helpers (sub-type derivation, validation, ordering, submitted values)

**Files:**
- Create: `backend/app/services/application_builder.py`
- Test: `backend/app/tests/test_application_builder.py`

**Interfaces:**
- Produces (later tasks import these from `app.services.application_builder`):
  - `FORCED_FIRST_PREFERENCE: str = "moe_1w"`
  - `derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str`
  - `validate_sub_type_for_submission(scholarship, sub_scholarship_type: Optional[str]) -> None` (raises `app.core.exceptions.ValidationError`)
  - `order_sub_type_preferences(sub_types: List[str]) -> List[str]`
  - `build_submitted_application_values(scholarship, config) -> Dict[str, Any]` with keys `status`, `status_name`, `review_stage`, `submitted_at`, `amount`, `scholarship_name`

- [ ] **Step 1: Write the failing tests**

Create `backend/app/tests/test_application_builder.py`. These are **sync** tests (unit lane) — the helpers under test are pure.

```python
"""Unit tests for the shared application builder helpers.

These helpers are the single source of truth for logic that previously
drifted between the student self-submission path (ApplicationService)
and the batch import path (BatchImportService).
"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.exceptions import ValidationError
from app.services.application_builder import (
    FORCED_FIRST_PREFERENCE,
    build_submitted_application_values,
    derive_sub_scholarship_type,
    order_sub_type_preferences,
    validate_sub_type_for_submission,
)


# --- derive_sub_scholarship_type -------------------------------------------


def test_derive_sub_type_empty_list_returns_general():
    assert derive_sub_scholarship_type([]) == "general"
    assert derive_sub_scholarship_type(None) == "general"


def test_derive_sub_type_first_entry_lowercased():
    assert derive_sub_scholarship_type(["NSTC", "moe_1w"]) == "nstc"


# --- validate_sub_type_for_submission ---------------------------------------


def _scholarship_stub(sub_type_list):
    return SimpleNamespace(sub_type_list=sub_type_list)


def test_validate_rejects_general_when_real_sub_types_exist():
    with pytest.raises(ValidationError):
        validate_sub_type_for_submission(_scholarship_stub(["nstc", "moe_1w"]), "general")


def test_validate_accepts_real_sub_type_case_insensitive():
    validate_sub_type_for_submission(_scholarship_stub(["NSTC", "moe_1w"]), "nstc")


def test_validate_rejects_arbitrary_sub_type_when_none_defined():
    with pytest.raises(ValidationError):
        validate_sub_type_for_submission(_scholarship_stub([]), "nstc")


def test_validate_accepts_general_when_none_defined():
    validate_sub_type_for_submission(_scholarship_stub([]), "general")
    validate_sub_type_for_submission(_scholarship_stub(None), None)


# --- order_sub_type_preferences ---------------------------------------------


def test_order_forces_moe_1w_first():
    assert order_sub_type_preferences(["nstc", "moe_1w"]) == ["moe_1w", "nstc"]


def test_order_preserves_order_without_moe_1w():
    assert order_sub_type_preferences(["nstc", "moe_2w"]) == ["nstc", "moe_2w"]


def test_order_single_and_empty():
    assert order_sub_type_preferences(["moe_1w"]) == ["moe_1w"]
    assert order_sub_type_preferences([]) == []


def test_forced_first_preference_constant_matches_frontend():
    # Mirrors FORCED_FIRST_PREFERENCE in
    # frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
    assert FORCED_FIRST_PREFERENCE == "moe_1w"


# --- build_submitted_application_values --------------------------------------


def test_build_submitted_values_uses_config_amount_and_name():
    scholarship = SimpleNamespace(name="博士生獎學金")
    config = SimpleNamespace(config_name="博士生獎學金 114學年", amount=40000)

    values = build_submitted_application_values(scholarship, config)

    assert values["status"] == "submitted"
    assert values["status_name"]  # non-empty i18n text
    assert values["review_stage"] == "student_submitted"
    assert values["amount"] == 40000
    assert values["scholarship_name"] == "博士生獎學金 114學年"
    assert isinstance(values["submitted_at"], datetime)
    assert values["submitted_at"].tzinfo == timezone.utc


def test_build_submitted_values_falls_back_to_scholarship_name():
    scholarship = SimpleNamespace(name="博士生獎學金")
    config = SimpleNamespace(config_name=None, amount=None)

    values = build_submitted_application_values(scholarship, config)

    assert values["scholarship_name"] == "博士生獎學金"
    assert values["amount"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.application_builder'`

- [ ] **Step 3: Write the module (pure helpers only)**

Create `backend/app/services/application_builder.py`. The derivation/validation bodies are **moved verbatim** from `ApplicationService._derive_sub_scholarship_type` / `_validate_sub_type_for_submission` (`backend/app/services/application_service.py:452-492`) so behavior is identical:

```python
"""Shared application-construction helpers.

Single source of truth for logic used by BOTH the student self-submission
path (ApplicationService) and the batch import path (BatchImportService).
Any submitted-application field rule that must stay identical across the
two paths belongs here — that is the module's only admission criterion.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.core.exceptions import ValidationError
from app.models.enums import ApplicationStatus, ReviewStage
from app.utils.i18n import ScholarshipI18n

logger = logging.getLogger(__name__)

# Mirrors FORCED_FIRST_PREFERENCE in
# frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx:
# the manual preference-ordering UI is hidden; MOE (moe_1w) is always the
# first preference when selected alongside other sub-types.
FORCED_FIRST_PREFERENCE = "moe_1w"


def derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str:
    """Derive the denormalized scalar `sub_scholarship_type` from the selected
    sub-type list: first entry wins, normalized to lowercase; empty → "general".
    """
    if scholarship_subtype_list:
        return scholarship_subtype_list[0].lower()
    return "general"


def validate_sub_type_for_submission(scholarship, sub_scholarship_type: Optional[str]) -> None:
    """Reject the synthetic "general" category on submission for scholarships
    that define real sub-types, and arbitrary sub-types for scholarships that
    define none. Comparison is case-insensitive.
    """
    if scholarship is None:
        return
    real_sub_types = [st.lower() for st in (scholarship.sub_type_list or []) if st and st.lower() != "general"]
    normalized = (sub_scholarship_type or "general").lower()
    if real_sub_types:
        if normalized not in real_sub_types:
            raise ValidationError("此獎學金需選擇申請類別（" + "、".join(real_sub_types) + "），不可使用通用類別")
    elif normalized != "general":
        raise ValidationError("此獎學金不提供申請類別選擇，不可指定子類別")


def order_sub_type_preferences(sub_types: List[str]) -> List[str]:
    """Order a selected sub-type list the way the student wizard does:
    FORCED_FIRST_PREFERENCE (moe_1w) leads when present; the rest keep
    their given order. Returns a new list.
    """
    if FORCED_FIRST_PREFERENCE in sub_types:
        return [FORCED_FIRST_PREFERENCE] + [st for st in sub_types if st != FORCED_FIRST_PREFERENCE]
    return list(sub_types)


def build_submitted_application_values(scholarship, config) -> Dict[str, Any]:
    """Field values every application must carry the moment it is submitted,
    regardless of which path created it.
    """
    return {
        "status": ApplicationStatus.submitted.value,
        "status_name": ScholarshipI18n.get_application_status_text(ApplicationStatus.submitted.value),
        "review_stage": ReviewStage.student_submitted.value,
        "submitted_at": datetime.now(timezone.utc),
        "amount": config.amount,
        "scholarship_name": config.config_name or scholarship.name,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/application_builder.py backend/app/tests/test_application_builder.py
cd backend && flake8 app/services/application_builder.py app/tests/test_application_builder.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/application_builder.py backend/app/tests/test_application_builder.py
git commit -m "feat: add shared application builder helpers (sub-type + submitted values)"
```

---

### Task 2: `application_builder.py` — async helpers (`generate_app_id`, `assign_professor_from_profile`)

**Files:**
- Modify: `backend/app/services/application_builder.py`
- Test: `backend/app/tests/test_application_builder.py` (append async tests)

**Interfaces:**
- Produces:
  - `async generate_app_id(db, academic_year: int, semester, *, suffix: str = "", commit: bool = True) -> str`
    — `semester` accepts `None`, a `Semester` enum member, or a string. `commit=True` commits immediately to release the row lock (student path). `commit=False` holds the lock for the caller's enclosing transaction (batch path — blocks online applications during import, intentionally).
  - `async assign_professor_from_profile(db, application, user_id: int) -> Optional[User]`
    — looks up `UserProfile.advisor_nycu_id` for `user_id`; if a `User` with `role == UserRole.professor` matches, sets `application.professor_id` and returns the professor, else returns `None`. Does NOT overwrite an already-set `application.professor_id`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_application_builder.py`. These are **async** tests (integration lane) using the existing async `db` fixture (see `backend/app/tests/conftest.py` — same fixture `test_batch_import_service_unit.py` uses):

```python
# --- async helpers -----------------------------------------------------------

from app.models.application_sequence import ApplicationSequence  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.user_profile import UserProfile  # noqa: E402
from app.services.application_builder import (  # noqa: E402
    assign_professor_from_profile,
    generate_app_id,
)


async def test_generate_app_id_creates_sequence_and_formats(db):
    app_id = await generate_app_id(db, 114, None)
    assert app_id == "APP-114-0-00001"

    app_id2 = await generate_app_id(db, 114, "yearly")
    assert app_id2 == "APP-114-0-00002"


async def test_generate_app_id_with_suffix_no_commit(db):
    app_id = await generate_app_id(db, 114, "first", suffix="U", commit=False)
    assert app_id == "APP-114-1-00001U"


async def test_assign_professor_sets_id_when_profile_matches(db):
    student = User(nycu_id="313554001", name="學生甲", role="student", user_type="student")
    professor = User(nycu_id="P001234", name="張教授", role="professor", user_type="employee")
    db.add_all([student, professor])
    await db.flush()

    db.add(UserProfile(user_id=student.id, advisor_nycu_id="P001234"))
    await db.flush()

    application = SimpleNamespace(professor_id=None)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is not None
    assert application.professor_id == professor.id


async def test_assign_professor_none_when_no_professor_account(db):
    student = User(nycu_id="313554002", name="學生乙", role="student", user_type="student")
    db.add(student)
    await db.flush()
    db.add(UserProfile(user_id=student.id, advisor_nycu_id="NOSUCH"))
    await db.flush()

    application = SimpleNamespace(professor_id=None)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is None
    assert application.professor_id is None


async def test_assign_professor_does_not_overwrite_existing(db):
    student = User(nycu_id="313554003", name="學生丙", role="student", user_type="student")
    db.add(student)
    await db.flush()

    application = SimpleNamespace(professor_id=999)
    result = await assign_professor_from_profile(db, application, student.id)

    assert result is None
    assert application.professor_id == 999
```

Note: if the `User` constructor requires different kwargs in conftest fixtures, copy the construction style from existing tests in `test_batch_import_service_unit.py` — never invent column names (`nycu_id`/`name`/`status`, NOT `username`/`full_name`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider`
Expected: new tests FAIL with `ImportError: cannot import name 'generate_app_id'`

- [ ] **Step 3: Implement the async helpers**

Append to `backend/app/services/application_builder.py`:

```python
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_sequence import ApplicationSequence
from app.models.user import User, UserRole
from app.models.user_profile import UserProfile


async def generate_app_id(
    db: AsyncSession,
    academic_year: int,
    semester,
    *,
    suffix: str = "",
    commit: bool = True,
) -> str:
    """Generate a sequential application ID with database row locking.

    Format: APP-{academic_year}-{semester_code}-{sequence:05d}{suffix}

    commit=True releases the sequence row lock immediately (student path).
    commit=False keeps the lock until the caller's transaction ends — the
    batch import path relies on this to stay atomic, at the cost of
    blocking online submissions for the duration of the import.
    """
    if semester is None:
        semester = "yearly"
    if hasattr(semester, "value"):
        semester = semester.value

    stmt = (
        select(ApplicationSequence)
        .where(
            and_(
                ApplicationSequence.academic_year == academic_year,
                ApplicationSequence.semester == semester,
            )
        )
        .with_for_update()
    )
    result = await db.execute(stmt)
    seq_record = result.scalar_one_or_none()

    if not seq_record:
        seq_record = ApplicationSequence(academic_year=academic_year, semester=semester, last_sequence=0)
        db.add(seq_record)
        await db.flush()

    seq_record.last_sequence += 1
    sequence_num = seq_record.last_sequence

    if commit:
        await db.commit()

    app_id = ApplicationSequence.format_app_id(academic_year, semester, sequence_num)
    return f"{app_id}{suffix}"


async def assign_professor_from_profile(db: AsyncSession, application, user_id: int):
    """Auto-assign the reviewing professor from the student's UserProfile.

    Looks up UserProfile.advisor_nycu_id and matches a User with
    role=professor. Returns the professor User or None. Never overwrites
    an already-assigned professor_id.
    """
    if getattr(application, "professor_id", None):
        return None

    profile_stmt = select(UserProfile).where(UserProfile.user_id == user_id)
    profile_result = await db.execute(profile_stmt)
    profile = profile_result.scalar_one_or_none()

    if not profile or not profile.advisor_nycu_id:
        return None

    professor_stmt = select(User).where(
        User.nycu_id == profile.advisor_nycu_id,
        User.role == UserRole.professor,
    )
    professor_result = await db.execute(professor_stmt)
    professor = professor_result.scalar_one_or_none()

    if professor:
        application.professor_id = professor.id
        logger.info("Auto-assigned professor %s to application %s", professor.id, getattr(application, "app_id", "?"))
    return professor
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider`
Expected: all PASS

- [ ] **Step 5: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/application_builder.py backend/app/tests/test_application_builder.py
cd backend && flake8 app/services/application_builder.py app/tests/test_application_builder.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/application_builder.py backend/app/tests/test_application_builder.py
git commit -m "feat: add generate_app_id and professor auto-assign to application builder"
```

---

### Task 3: `ApplicationService` delegates to the builder (pure refactor, zero behavior change)

**Files:**
- Modify: `backend/app/services/application_service.py`

**Interfaces:**
- Consumes: everything Task 1–2 produced.
- Produces: no new interface. `ApplicationService._generate_app_id`, `_derive_sub_scholarship_type`, `_validate_sub_type_for_submission` keep their signatures (thin delegates) so all existing call sites and tests stay valid.

- [ ] **Step 1: Replace `_generate_app_id` body with a delegate**

At `backend/app/services/application_service.py:282-342`, replace the entire method body (keep the signature and docstring first line):

```python
    async def _generate_app_id(self, academic_year: int, semester: Optional[str]) -> str:
        """Generate sequential application ID (delegates to application_builder)."""
        from app.services.application_builder import generate_app_id

        return await generate_app_id(self.db, academic_year, semester)
```

- [ ] **Step 2: Replace the two sub-type staticmethods with delegates**

At `backend/app/services/application_service.py:452-492`, replace both staticmethod bodies (keep signatures — tests and call sites reference them via `self.`/class):

```python
    @staticmethod
    def _derive_sub_scholarship_type(scholarship_subtype_list: Optional[List[str]]) -> str:
        """Delegates to application_builder (shared with batch import)."""
        from app.services.application_builder import derive_sub_scholarship_type

        return derive_sub_scholarship_type(scholarship_subtype_list)

    @staticmethod
    def _validate_sub_type_for_submission(scholarship: ScholarshipType, sub_scholarship_type: Optional[str]) -> None:
        """Delegates to application_builder (shared with batch import)."""
        from app.services.application_builder import validate_sub_type_for_submission

        validate_sub_type_for_submission(scholarship, sub_scholarship_type)
```

- [ ] **Step 3: Use `build_submitted_application_values` in `_create_application_instance`**

At `backend/app/services/application_service.py:526-561`, the current code sets `status`/`status_name` inline, then sets `submitted_at`/`review_stage` in the `if not is_draft` block, and the `Application(...)` uses `amount=config.amount`, `scholarship_name=config.config_name or scholarship.name`. Replace with builder values so the submitted-state fields come from one place:

```python
        from app.models.enums import ApplicationStatus
        from app.services.application_builder import build_submitted_application_values
        from app.utils.i18n import ScholarshipI18n

        submitted_values = build_submitted_application_values(scholarship, config)

        if is_draft:
            status = ApplicationStatus.draft.value
            status_name = ScholarshipI18n.get_application_status_text(status)
        else:
            status = submitted_values["status"]
            status_name = submitted_values["status_name"]

        # Create application
        application = Application(
            app_id=app_id,
            user_id=user.id,
            scholarship_type_id=scholarship.id,
            scholarship_configuration_id=config.id,
            scholarship_name=submitted_values["scholarship_name"],
            amount=submitted_values["amount"],
            scholarship_subtype_list=scholarship_subtype_list,
            # Ordered sub-type preference list (志願序). The distribution service
            # reads this first; without it, allocation falls back to selection
            # order. The frontend computes the order (MOE/moe_1w forced first).
            sub_type_preferences=application_data.sub_type_preferences,
            sub_type_selection_mode=sub_type_selection_mode,
            sub_scholarship_type=sub_scholarship_type,
            is_renewal=False,  # New applications are never renewals
            academic_year=academic_year,
            semester=semester,
            student_data=student_snapshot,
            submitted_form_data=application_data.form_data.dict() if application_data.form_data else {},
            agree_terms=application_data.agree_terms or False,
            status=status,
            status_name=status_name,
        )

        if not is_draft:
            application.submitted_at = submitted_values["submitted_at"]
            application.review_stage = submitted_values["review_stage"]

        return application
```

- [ ] **Step 4: Use `assign_professor_from_profile` in `submit_application`**

At `backend/app/services/application_service.py:1313-1333`, the submit path loads `advisor_profile` and then auto-assigns the professor inline. The profile load is reused later for email automation — keep it. Replace ONLY the auto-assign block (`# 自動分配指導教授...` through the `logger.info(...)` inside `if professor:`) with:

```python
        # 自動分配指導教授：根據 UserProfile 的 advisor_nycu_id 查找教授帳號
        from app.services.application_builder import assign_professor_from_profile

        await assign_professor_from_profile(self.db, application, application.user_id)
```

- [ ] **Step 5: Run the full application service + submit test suites (regression gate)**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/ -k "application_service or submit" -v --no-cov -p no:cacheprovider`
Expected: all PASS with **no assertion changes**. If a test fails, the refactor changed behavior — fix the refactor, not the test.

Also run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/application_service.py
cd backend && flake8 app/services/application_service.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/application_service.py
git commit -m "refactor: ApplicationService delegates shared logic to application_builder"
```

---

### Task 4: Batch parse — checkmark semantics, forced preference order, missing-sub-type hard error

**Files:**
- Modify: `backend/app/services/batch_import_service.py` (`parse_excel_file`, new module-level helper)
- Test: `backend/app/tests/test_batch_import_pure_helpers.py`, `backend/app/tests/test_batch_import_service_unit.py`

**Interfaces:**
- Produces: module-level `_is_sub_type_marked(cell) -> bool` in `batch_import_service.py` (positive int/float, digit string, or `V`/`v`/`✓` → True; blank/0/NaN/other → False).
- Changes: `parse_excel_file` row output — `sub_types` is now ordered by `order_sub_type_preferences` (moe_1w first), no longer by Excel numbers. Rows with zero marked sub-types (when `scholarship.sub_type_list` is non-empty) produce a `missing_sub_type` error and are excluded from `parsed_data` (same treatment as the existing blank-student-id parse error — they are not stored, not editable inline, must be fixed in the Excel and re-uploaded).

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_batch_import_pure_helpers.py`:

```python
from app.services.batch_import_service import _is_sub_type_marked


def test_is_sub_type_marked_positive_numbers():
    assert _is_sub_type_marked(1) is True
    assert _is_sub_type_marked(2.0) is True
    assert _is_sub_type_marked("3") is True


def test_is_sub_type_marked_checkmarks():
    assert _is_sub_type_marked("V") is True
    assert _is_sub_type_marked("v") is True
    assert _is_sub_type_marked("✓") is True


def test_is_sub_type_marked_blank_zero_and_noise():
    assert _is_sub_type_marked(None) is False
    assert _is_sub_type_marked("") is False
    assert _is_sub_type_marked(0) is False
    assert _is_sub_type_marked("0") is False
    assert _is_sub_type_marked(float("nan")) is False
    assert _is_sub_type_marked("no") is False
```

Append to `backend/app/tests/test_batch_import_service_unit.py` (async, follow the file's existing fixture style for building the Excel bytes and the scholarship fixture — reuse its helpers for creating a `ScholarshipType` with `sub_type_list=["nstc", "moe_1w"]`):

```python
async def test_parse_orders_preferences_moe_first_regardless_of_numbers(db, scholarship_with_sub_types):
    # 國科會=1, 教育部=2 in the Excel — moe_1w must STILL come first
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": 1, "教育部": 2}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(
        buf.getvalue(), scholarship_with_sub_types.id, 114, None
    )

    assert errors == []
    assert parsed[0]["sub_types"] == ["moe_1w", "nstc"]


async def test_parse_accepts_checkmark_v(db, scholarship_with_sub_types):
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": "V", "教育部": ""}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(
        buf.getvalue(), scholarship_with_sub_types.id, 114, None
    )

    assert errors == []
    assert parsed[0]["sub_types"] == ["nstc"]


async def test_parse_missing_sub_type_is_hard_error(db, scholarship_with_sub_types):
    df = pd.DataFrame([{"學號": "313554001", "學生姓名": "王小明", "國科會": "", "教育部": ""}])
    buf = io.BytesIO()
    df.to_excel(buf, index=False)

    service = BatchImportService(db)
    parsed, errors = await service.parse_excel_file(
        buf.getvalue(), scholarship_with_sub_types.id, 114, None
    )

    assert parsed == []
    assert len(errors) == 1
    assert errors[0].error_type == "missing_sub_type"
    assert errors[0].student_id == "313554001"
```

If `scholarship_with_sub_types` does not exist as a fixture, create it in the same test file mirroring how existing tests in that file build their `ScholarshipType` (check the file's imports/fixtures first — do not invent).

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_pure_helpers.py app/tests/test_batch_import_service_unit.py -v --no-cov -p no:cacheprovider`
Expected: new tests FAIL (`ImportError: cannot import name '_is_sub_type_marked'`; ordering/error assertions fail)

- [ ] **Step 3: Implement**

In `backend/app/services/batch_import_service.py`:

3a. Add module-level helper after `_parse_renewal_year` (~line 68):

```python
_CHECKMARK_VALUES = {"v", "✓"}


def _is_sub_type_marked(cell: Any) -> bool:
    """A sub-type column cell counts as "applied" when it holds a positive
    number or a checkmark (V/v/✓). Blank, 0, NaN, or anything else means
    not applied. Numbers no longer encode preference order — ordering is
    derived by application_builder.order_sub_type_preferences.
    """
    if cell is None:
        return False
    if isinstance(cell, (int, float)):
        if isinstance(cell, float) and pd.isna(cell):
            return False
        return cell > 0
    if isinstance(cell, str):
        stripped = cell.strip()
        if stripped.isdigit():
            return int(stripped) > 0
        return stripped.lower() in _CHECKMARK_VALUES
    return False
```

3b. In `parse_excel_file`, replace BOTH sub-type parsing blocks (Chinese branch ~lines 239-251 and English branch ~lines 281-293). The `priority_entries` sort machinery goes away. Chinese branch:

```python
                    # Parse sub_types from Chinese column names.
                    # Any positive number or checkmark = applied; ordering is
                    # forced by shared rule (moe_1w first), NOT by cell numbers.
                    selected_sub_types = []
                    for chinese_label, sub_type_code in sub_type_labels.items():
                        if chinese_label in df_columns and _is_sub_type_marked(row.get(chinese_label)):
                            selected_sub_types.append(sub_type_code)
                    data_row["sub_types"] = order_sub_type_preferences(selected_sub_types)
```

English branch:

```python
                    # Parse sub_types from English column names (sub_type_*)
                    selected_sub_types = []
                    for col in df_columns:
                        if col.startswith("sub_type_") and _is_sub_type_marked(row.get(col)):
                            selected_sub_types.append(col.replace("sub_type_", ""))
                    data_row["sub_types"] = order_sub_type_preferences(selected_sub_types)
```

Add the import at the top of the file:

```python
from app.services.application_builder import order_sub_type_preferences
```

3c. After the Pydantic validation block (after `normalized_row = validated_row.model_dump()`, before `parsed_data.append(...)` ~line 310), add the hard error:

```python
                # Sub-type is mandatory when the scholarship defines real
                # sub-types — a row with none marked cannot be imported
                # (it would fall into the synthetic "general" bucket which
                # matches no distribution quota slot).
                if scholarship.sub_type_list and not normalized_row.get("sub_types"):
                    errors.append(
                        BatchImportValidationError(
                            row_number=row_number,
                            student_id=student_id,
                            field="sub_types",
                            error_type="missing_sub_type",
                            message="未勾選任何申請類別（國科會/教育部），請於 Excel 中標記後重新上傳",
                        )
                    )
                    continue
```

- [ ] **Step 4: Run tests to verify they pass, plus the full batch test files**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_pure_helpers.py app/tests/test_batch_import_service_unit.py app/tests/test_batch_import_defaults_and_postal.py -v --no-cov -p no:cacheprovider`
Expected: PASS. Pre-existing tests that asserted number-based ordering (e.g. anything asserting `sub_types == ["nstc", "moe_1w"]` because 國科會=1) must be UPDATED to the forced-moe-first expectation — that behavior change is the point of this task; update the assertion and note it in the commit body.

- [ ] **Step 5: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/batch_import_service.py backend/app/tests/test_batch_import_pure_helpers.py backend/app/tests/test_batch_import_service_unit.py
cd backend && flake8 app/services/batch_import_service.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/batch_import_service.py backend/app/tests/test_batch_import_pure_helpers.py backend/app/tests/test_batch_import_service_unit.py
git commit -m "feat: batch import sub-type columns use checkmark semantics with forced moe_1w-first ordering"
```

---

### Task 5: Batch creation aligned with student submission (status, form_data structure, profile upsert, professor assign)

**Files:**
- Modify: `backend/app/services/batch_import_service.py` (`create_applications_from_batch`, new `_upsert_user_profile`, new `_build_submitted_form_data`)
- Test: `backend/app/tests/test_batch_import_service_unit.py`, `backend/app/tests/test_batch_import_defaults_and_postal.py`

**Interfaces:**
- Consumes: `generate_app_id(db, year, sem, suffix="U", commit=False)`, `derive_sub_scholarship_type`, `build_submitted_application_values`, `assign_professor_from_profile` from `app.services.application_builder`.
- Changes to created `Application` rows:
  - `status="submitted"`, `status_name` set, `review_stage="student_submitted"`, `submitted_at` set (all from `build_submitted_application_values`)
  - `amount=config.amount`, `scholarship_name=config.config_name or scholarship.name`
  - `submitted_form_data={"fields": {...standard entries from custom_fields...}, "documents": []}` — postal/advisor NOT included
  - unchanged: `imported_by_id`, `batch_import_id`, `import_source="batch_import"`, `document_status="pending_documents"`, `is_renewal`, `renewal_year`, `sub_type_preferences`
- New side effects per row: `UserProfile` upsert (Excel non-empty values overwrite; blanks preserve; missing profile created), then professor auto-assign.

- [ ] **Step 1: Write the failing tests**

Append to `backend/app/tests/test_batch_import_service_unit.py` (reuse that file's existing fixtures for `batch_import` record / scholarship / config — `test_create_applications_from_batch_success` at line 182 shows the setup pattern; mirror it):

```python
async def test_batch_created_application_matches_student_submission_shape(
    db, batch_import_fixture, scholarship_with_config
):
    """Core spec assertion: a batch-created application looks like a
    student-submitted one (status/review_stage/amount/name/form_data)."""
    parsed_data = [
        {
            "student_id": "313554001",
            "student_name": "王小明",
            "postal_account": "1234567890123",
            "advisor_name": "張教授",
            "advisor_email": "chang@nycu.edu.tw",
            "advisor_nycu_id": "P001234",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["moe_1w", "nstc"],
            "custom_fields": {"contact_phone": "0912345678"},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db)
    created_ids, errors = await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )

    assert errors == []
    app = await db.get(Application, created_ids[0])

    # Review flow parity
    assert app.status == ApplicationStatus.submitted
    assert app.review_stage == "student_submitted"
    assert app.submitted_at is not None
    # Value parity (config-sourced)
    assert app.amount is not None
    assert "114" in app.scholarship_name  # config_name carries the year
    # app_id keeps the batch marker
    assert app.app_id.endswith("U")
    # Standard form-data structure; postal/advisor NOT inside
    assert set(app.submitted_form_data.keys()) == {"fields", "documents"}
    assert app.submitted_form_data["documents"] == []
    assert app.submitted_form_data["fields"]["contact_phone"]["value"] == "0912345678"
    assert "postal_account" not in app.submitted_form_data["fields"]
    # Sub-type scalar via shared derivation
    assert app.sub_scholarship_type == "moe_1w"
    assert app.sub_type_preferences == ["moe_1w", "nstc"]


async def test_batch_upserts_user_profile_with_overwrite(db, batch_import_fixture, scholarship_with_config):
    # Pre-existing profile: advisor set by the student, postal blank
    user = User(nycu_id="313554002", name="陳小華", role="student", user_type="student")
    db.add(user)
    await db.flush()
    db.add(UserProfile(user_id=user.id, account_number=None, advisor_name="舊教授", advisor_nycu_id="P000001"))
    await db.flush()

    parsed_data = [
        {
            "student_id": "313554002",
            "student_name": "陳小華",
            "postal_account": "9876543210987",
            "advisor_name": "李教授",
            "advisor_email": None,  # blank in Excel — must preserve existing (None here)
            "advisor_nycu_id": "P005678",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["nstc"],
            "custom_fields": {},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db)
    await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )

    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == user.id))
    profile = profile_result.scalar_one()
    assert profile.account_number == "9876543210987"  # filled from Excel
    assert profile.advisor_name == "李教授"  # Excel value overwrites
    assert profile.advisor_nycu_id == "P005678"  # Excel value overwrites


async def test_batch_assigns_professor_when_account_exists(db, batch_import_fixture, scholarship_with_config):
    professor = User(nycu_id="P001234", name="張教授", role="professor", user_type="employee")
    db.add(professor)
    await db.flush()

    parsed_data = [
        {
            "student_id": "313554003",
            "student_name": "林小強",
            "postal_account": None,
            "advisor_name": "張教授",
            "advisor_email": "chang@nycu.edu.tw",
            "advisor_nycu_id": "P001234",
            "is_renewal": False,
            "renewal_year": None,
            "sub_types": ["nstc"],
            "custom_fields": {},
            "row_number": 2,
        }
    ]

    service = BatchImportService(db)
    created_ids, _ = await service.create_applications_from_batch(
        batch_import=batch_import_fixture,
        parsed_data=parsed_data,
        scholarship_type_id=scholarship_with_config.id,
        academic_year=114,
        semester=None,
    )

    app = await db.get(Application, created_ids[0])
    assert app.professor_id == professor.id
```

Adjust fixture names (`batch_import_fixture`, `scholarship_with_config`) to whatever the file actually defines — read the file's existing `test_create_applications_from_batch_success` setup first and reuse its fixtures verbatim. `ApplicationStatus.submitted` comparison: DB-loaded model returns the enum member (per repo gotchas); if the existing tests in this file compare `.status` against strings, match their convention.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_service_unit.py -v --no-cov -p no:cacheprovider`
Expected: new tests FAIL (status is `under_review`, form_data flat, no profile rows)

- [ ] **Step 3: Implement**

In `backend/app/services/batch_import_service.py`:

3a. Add imports at top:

```python
from app.models.user_profile import UserProfile
from app.services.application_builder import (
    assign_professor_from_profile,
    build_submitted_application_values,
    derive_sub_scholarship_type,
    generate_app_id,
)
```

3b. Add two private methods to `BatchImportService`:

```python
    async def _upsert_user_profile(self, user: User, row_data: Dict[str, Any]) -> None:
        """Write postal account and advisor info to the student's UserProfile,
        the same place the student self-service flow keeps them.

        Overwrite policy (spec): a non-empty Excel value overwrites the
        existing profile value (paper form is authoritative); a blank Excel
        cell preserves whatever is already there.
        """
        profile_stmt = select(UserProfile).where(UserProfile.user_id == user.id)
        profile_result = await self.db.execute(profile_stmt)
        profile = profile_result.scalar_one_or_none()

        if not profile:
            profile = UserProfile(user_id=user.id)
            self.db.add(profile)

        field_map = {
            "postal_account": "account_number",
            "advisor_name": "advisor_name",
            "advisor_email": "advisor_email",
            "advisor_nycu_id": "advisor_nycu_id",
        }
        for row_key, profile_attr in field_map.items():
            value = row_data.get(row_key)
            if value:
                setattr(profile, profile_attr, value)

    async def _build_submitted_form_data(self, scholarship_code: str, custom_fields: Dict[str, Any]) -> Dict[str, Any]:
        """Shape batch custom-field values into the standard student-submission
        structure: {"fields": {name: {field_id, field_type, value, required}},
        "documents": []}. field_type/required come from the ApplicationField
        definitions; a value with no matching definition falls back to text.
        """
        from app.models.application_field import ApplicationField

        defs_stmt = (
            select(ApplicationField)
            .where(ApplicationField.scholarship_type == scholarship_code)
            .where(ApplicationField.is_active)
        )
        defs_result = await self.db.execute(defs_stmt)
        definitions = {f.field_name: f for f in defs_result.scalars().all()}

        fields = {}
        for field_name, value in (custom_fields or {}).items():
            definition = definitions.get(field_name)
            fields[field_name] = {
                "field_id": field_name,
                "field_type": definition.field_type if definition else "text",
                "value": value,
                "required": bool(definition.is_required) if definition else False,
            }
        return {"fields": fields, "documents": []}
```

3c. In `create_applications_from_batch` (lines 744-857), inside the per-row loop, replace the inline app_id sequence block (lines 757-794) with:

```python
                # Shared sequence logic; commit=False holds the row lock for
                # the whole batch transaction (atomicity over concurrency —
                # online submissions block during the import, intentionally).
                app_id = await generate_app_id(
                    self.db, academic_year, semester, suffix="U", commit=False
                )
```

(`ApplicationSequence` import and the `and_` import become unused in this file — remove them.)

3d. Still in the loop, after the `student_data` snapshot fetch, replace the `submitted_form_data` construction and the `Application(...)` call (lines 816-851) with:

```python
                submitted_form_data = await self._build_submitted_form_data(
                    scholarship.code, row_data.get("custom_fields", {})
                )

                submitted_values = build_submitted_application_values(scholarship, scholarship_config)

                application = Application(
                    app_id=app_id,
                    user_id=user.id,
                    scholarship_type_id=scholarship_type_id,
                    scholarship_configuration_id=scholarship_config.id,
                    scholarship_name=submitted_values["scholarship_name"],
                    amount=submitted_values["amount"],
                    sub_scholarship_type=derive_sub_scholarship_type(row_data.get("sub_types")),
                    scholarship_subtype_list=row_data.get("sub_types", []),
                    sub_type_preferences=row_data.get("sub_types", []) or None,
                    sub_type_selection_mode=scholarship.sub_type_selection_mode,
                    academic_year=academic_year,
                    semester=semester,
                    is_renewal=row_data.get("is_renewal", False),
                    renewal_year=row_data.get("renewal_year"),
                    status=submitted_values["status"],
                    status_name=submitted_values["status_name"],
                    review_stage=submitted_values["review_stage"],
                    imported_by_id=batch_import.importer_id,
                    batch_import_id=batch_import.id,
                    import_source="batch_import",
                    document_status="pending_documents",
                    submitted_at=submitted_values["submitted_at"],
                    student_data=student_data,
                    submitted_form_data=submitted_form_data,
                )
                applications.append(application)
                self.db.add(application)

                # Profile upsert then professor auto-assign — same linkage the
                # student submit path uses (professor review lists match on
                # Application.professor_id).
                await self._upsert_user_profile(user, row_data)
                await assign_professor_from_profile(self.db, application, user.id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_service_unit.py app/tests/test_batch_import_defaults_and_postal.py -v --no-cov -p no:cacheprovider`
Expected: new tests PASS. Existing tests asserting `status == under_review` / flat `submitted_form_data` keys (e.g. `postal_account` at top level) must be UPDATED to the new shape — intended behavior change; update assertions to match the spec (status `submitted`, `{"fields", "documents"}` keys).

- [ ] **Step 5: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/batch_import_service.py backend/app/tests/test_batch_import_service_unit.py backend/app/tests/test_batch_import_defaults_and_postal.py
cd backend && flake8 app/services/batch_import_service.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/batch_import_service.py backend/app/tests/test_batch_import_service_unit.py backend/app/tests/test_batch_import_defaults_and_postal.py
git commit -m "feat: batch-imported applications enter the standard review flow like student submissions"
```

---

### Task 6: Eligibility + professor-account warnings in preview (upload-data & revalidate)

**Files:**
- Modify: `backend/app/services/batch_import_service.py` (new `bulk_check_eligibility`)
- Modify: `backend/app/api/v1/endpoints/batch_import.py` (`upload_batch_import_data` ~line 174, `revalidate_batch_import` ~line 486)
- Test: `backend/app/tests/test_batch_import_service_unit.py`, `backend/app/tests/test_batch_import_endpoints.py`

**Interfaces:**
- Produces: `async BatchImportService.bulk_check_eligibility(parsed_data: List[Dict], scholarship_type_id: int, academic_year: int, semester: Optional[str]) -> List[Dict[str, Any]]` — returns warning dicts in the exact shape the endpoints already store: `{"row_number", "student_id", "field", "warning_type", "message"}`. Warning types: `eligibility_failed`, `eligibility_check_skipped`, `professor_not_found`. Never raises; never blocks.

- [ ] **Step 1: Write the failing service tests**

Append to `backend/app/tests/test_batch_import_service_unit.py`:

```python
async def test_bulk_check_eligibility_flags_failures_but_filters_period(
    db, scholarship_with_config, monkeypatch
):
    service = BatchImportService(db)

    async def fake_snapshot(student_id, academic_year=None, semester=None):
        return {"std_stdcode": student_id, "trm_ascore_gpa": 2.0}

    monkeypatch.setattr(service.student_service, "get_student_snapshot", fake_snapshot)

    async def fake_check(student_data, config, user_id=None):
        # Simulates: outside application period AND a real rule failure
        return False, ["不在申請期間內", "GPA 未達標準"]

    from app.services import batch_import_service as bis_module

    monkeypatch.setattr(
        bis_module.EligibilityService, "check_student_eligibility", staticmethod(fake_check), raising=False
    )

    parsed_data = [{"student_id": "313554001", "sub_types": ["nstc"], "advisor_nycu_id": None, "row_number": 2}]
    warnings = await service.bulk_check_eligibility(
        parsed_data, scholarship_with_config.id, 114, None
    )

    eligibility_warnings = [w for w in warnings if w["warning_type"] == "eligibility_failed"]
    assert len(eligibility_warnings) == 1
    assert "GPA 未達標準" in eligibility_warnings[0]["message"]
    # Application-period reason is exempted for batch import (late entry)
    assert "不在申請期間內" not in eligibility_warnings[0]["message"]


async def test_bulk_check_eligibility_warns_missing_professor_account(db, scholarship_with_config, monkeypatch):
    service = BatchImportService(db)

    async def fake_snapshot(student_id, academic_year=None, semester=None):
        return {"std_stdcode": student_id}

    monkeypatch.setattr(service.student_service, "get_student_snapshot", fake_snapshot)

    parsed_data = [
        {"student_id": "313554001", "sub_types": ["nstc"], "advisor_nycu_id": "NOSUCH", "row_number": 2}
    ]
    warnings = await service.bulk_check_eligibility(parsed_data, scholarship_with_config.id, 114, None)

    professor_warnings = [w for w in warnings if w["warning_type"] == "professor_not_found"]
    assert len(professor_warnings) == 1
    assert "NOSUCH" in professor_warnings[0]["message"]
```

Note on the monkeypatch style: if patching the class method proves awkward, patch where it is looked up (`bis_module.EligibilityService`) or restructure the fake as an instance-level attribute — follow whatever pattern `test_batch_import_service_unit.py` already uses for `student_service` fakes.

- [ ] **Step 2: Run tests to verify they fail**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_service_unit.py -k eligibility -v --no-cov -p no:cacheprovider`
Expected: FAIL — `AttributeError: 'BatchImportService' object has no attribute 'bulk_check_eligibility'`

- [ ] **Step 3: Implement `bulk_check_eligibility`**

Add to `BatchImportService` (import `EligibilityService` at module top: `from app.services.eligibility_service import EligibilityService`):

```python
    # Application-period exemption: batch import exists precisely for
    # post-deadline paper-form entry, so this reason never surfaces.
    _PERIOD_EXEMPT_REASONS = {"不在申請期間內"}

    async def bulk_check_eligibility(
        self,
        parsed_data: List[Dict[str, Any]],
        scholarship_type_id: int,
        academic_year: int,
        semester: Optional[str],
    ) -> List[Dict[str, Any]]:
        """Run the SAME eligibility check the student self-submission path
        uses, demoted to warnings (manual review is the gate for batch
        imports). Also warns when an advisor_nycu_id has no professor
        account (the application would never reach a professor's queue).
        Never raises, never blocks the import.
        """
        warnings: List[Dict[str, Any]] = []

        # Resolve the configuration the same way create_applications_from_batch does
        semester_enum: Optional[Semester] = None
        if semester:
            try:
                semester_enum = Semester(semester)
            except ValueError:
                semester_enum = None

        config_stmt = select(ScholarshipConfiguration).where(
            ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
            ScholarshipConfiguration.academic_year == academic_year,
        )
        if semester_enum is None or semester_enum == Semester.yearly:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester.is_(None))
        else:
            config_stmt = config_stmt.where(ScholarshipConfiguration.semester == semester_enum)
        config_result = await self.db.execute(config_stmt)
        config = config_result.scalar_one_or_none()

        if not config:
            warnings.append(
                {
                    "row_number": None,
                    "student_id": None,
                    "field": "configuration",
                    "warning_type": "eligibility_check_skipped",
                    "message": "找不到對應的獎學金配置，已跳過資格預檢（確認匯入時將會失敗，請先建立配置）。",
                }
            )
            return warnings

        eligibility_service = EligibilityService(self.db)

        # Professor-account existence: one query for all advisor ids
        advisor_ids = {row.get("advisor_nycu_id") for row in parsed_data if row.get("advisor_nycu_id")}
        professor_map: Dict[str, User] = {}
        if advisor_ids:
            prof_stmt = select(User).where(User.nycu_id.in_(list(advisor_ids)), User.role == UserRole.professor)
            prof_result = await self.db.execute(prof_stmt)
            professor_map = {p.nycu_id: p for p in prof_result.scalars().all()}

        for row in parsed_data:
            student_id = row.get("student_id")
            row_number = row.get("row_number")

            advisor_id = row.get("advisor_nycu_id")
            if advisor_id and advisor_id not in professor_map:
                warnings.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "advisor_nycu_id",
                        "warning_type": "professor_not_found",
                        "message": f"查無人事編號 {advisor_id} 的教授帳號，該申請將無法進入教授待審清單。",
                    }
                )

            try:
                snapshot = await self.student_service.get_student_snapshot(
                    student_id, academic_year=str(academic_year), semester=semester
                )
            except Exception:  # noqa: BLE001 — any SIS failure demotes to a skip warning
                logger.warning("Eligibility precheck skipped for %s (SIS error)", student_id, exc_info=True)
                warnings.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "eligibility",
                        "warning_type": "eligibility_check_skipped",
                        "message": f"無法取得學生 {student_id} 的學籍資料，已跳過資格預檢。",
                    }
                )
                continue

            is_eligible, reasons = await eligibility_service.check_student_eligibility(
                student_data=snapshot, config=config
            )
            effective_reasons = [r for r in reasons if r not in self._PERIOD_EXEMPT_REASONS]
            if not is_eligible and effective_reasons:
                warnings.append(
                    {
                        "row_number": row_number,
                        "student_id": student_id,
                        "field": "eligibility",
                        "warning_type": "eligibility_failed",
                        "message": f"學生 {student_id} 資格預檢未通過：{'；'.join(effective_reasons)}（不影響匯入，請人工審查把關）。",
                    }
                )

        return warnings
```

`UserRole` import: `from app.models.user import User, UserRole` (User already imported — extend it).

- [ ] **Step 4: Wire into both preview endpoints**

In `backend/app/api/v1/endpoints/batch_import.py`:

4a. `upload_batch_import_data` — after `validation_warnings.extend(permission_warnings)` (line 174), inside the `if parsed_data:` block:

```python
        eligibility_warnings = await service.bulk_check_eligibility(
            parsed_data=parsed_data,
            scholarship_type_id=scholarship.id,
            academic_year=academic_year,
            semester=normalized_semester,
        )
        validation_warnings.extend(eligibility_warnings)
```

4b. `revalidate_batch_import` — after `validation_warnings.extend(permission_warnings)` (line 486):

```python
    eligibility_warnings = await service.bulk_check_eligibility(
        parsed_data=parsed_data,
        scholarship_type_id=batch_import.scholarship_type_id,
        academic_year=batch_import.academic_year,
        semester=batch_import.semester,
    )
    validation_warnings.extend(eligibility_warnings)
```

- [ ] **Step 5: Add endpoint test + run**

Append to `backend/app/tests/test_batch_import_endpoints.py` a test asserting the upload response surfaces eligibility warnings — mirror that file's existing upload-endpoint test setup (client fixture, auth override, multipart upload), stub `BatchImportService.bulk_check_eligibility` to return one warning dict, and assert it appears in `data["validation_summary"]["warnings"]` with its `message`.

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_service_unit.py app/tests/test_batch_import_endpoints.py -v --no-cov -p no:cacheprovider`
Expected: PASS

- [ ] **Step 6: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/services/batch_import_service.py backend/app/api/v1/endpoints/batch_import.py backend/app/tests/test_batch_import_service_unit.py backend/app/tests/test_batch_import_endpoints.py
cd backend && flake8 app/services/batch_import_service.py app/api/v1/endpoints/batch_import.py --select=B904,B014 --max-line-length=120 && cd ..
git add backend/app/services/batch_import_service.py backend/app/api/v1/endpoints/batch_import.py backend/app/tests/test_batch_import_service_unit.py backend/app/tests/test_batch_import_endpoints.py
git commit -m "feat: eligibility and professor-account warnings in batch import preview"
```

---

### Task 7: Template — checkmark semantics in sample rows

**Files:**
- Modify: `backend/app/api/v1/endpoints/batch_import.py:1746-1756` (sample sub-type values)
- Test: `backend/app/tests/test_batch_import_endpoints.py` (template test, if one asserts sample values)

- [ ] **Step 1: Replace the 志願序-number sample block**

At `backend/app/api/v1/endpoints/batch_import.py:1746-1756`, replace:

```python
    # Add sub_type sample values if applicable.
    # Sub-type cells are checkmarks: 1 (or V) = applying for that category,
    # blank = not applying. Preference order is NOT read from these cells —
    # the system forces MOE (moe_1w) as first preference, mirroring the
    # student wizard. Sample rows show both categories checked.
    if scholarship.sub_type_list:
        for row in sample_data:
            for sub_type_code in scholarship.sub_type_list:
                label = sub_type_labels.get(sub_type_code, sub_type_code)
                row[label] = 1
```

- [ ] **Step 2: Run template endpoint tests**

Run: `docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_endpoints.py -k template -v --no-cov -p no:cacheprovider`
Expected: PASS (update any assertion that expected priority numbers 1/2 in sample cells to expect `1` in every sub-type cell)

- [ ] **Step 3: Lint and commit**

```bash
uvx --from "black==26.3.1" black --line-length=120 backend/app/api/v1/endpoints/batch_import.py
git add backend/app/api/v1/endpoints/batch_import.py backend/app/tests/test_batch_import_endpoints.py
git commit -m "feat: batch import template samples use checkmark semantics for sub-type columns"
```

---

### Task 8: Full verification — backend lanes, frontend, OpenAPI, e2e

**Files:**
- Possibly modify: `frontend/lib/api/generated/schema.d.ts` (regen), `frontend/components/__tests__/batch-import-panel.test.tsx`, `frontend/e2e/specs/batch-import-upload.spec.ts`

- [ ] **Step 1: Full backend batch + application test sweep**

```bash
docker exec scholarship_backend_dev python -m pytest app/tests/test_batch_import_endpoints.py app/tests/test_batch_import_pure_helpers.py app/tests/test_batch_import_service_unit.py app/tests/test_batch_import_defaults_and_postal.py app/tests/test_application_builder.py -v --no-cov -p no:cacheprovider
docker exec scholarship_backend_dev python -m pytest app/tests/ -k "application_service or critical_workflows" --no-cov -p no:cacheprovider -q
```
Expected: all PASS.

- [ ] **Step 2: Repo-wide lint gates**

```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
cd backend && flake8 app --select=B904,B014 --max-line-length=120 && cd ..
docker exec scholarship_backend_dev python -m pytest app/tests/test_no_logger_warning_traceback_loss.py app/tests/test_no_logger_error_traceback_loss.py --no-cov -p no:cacheprovider -q
```
Expected: clean.

- [ ] **Step 3: Frontend checks**

No response-schema shape changed (warnings reuse the existing `{row, field, message}` structure), so `schema.d.ts` regen is likely a no-op — verify:

```bash
cd frontend && npm run api:generate && git diff --stat lib/api/generated/schema.d.ts
```
If the diff is non-empty, commit it. Then run the frontend tests:

```bash
cd frontend && npx vitest run components/__tests__/batch-import-panel.test.tsx lib/api/modules/__tests__/batch-import.test.ts
```
Expected: PASS (the panel renders warnings generically; no code change anticipated).

- [ ] **Step 4: E2E smoke (only if dev stack is up)**

```bash
cd frontend && npx playwright test e2e/specs/batch-import-upload.spec.ts
```
If the spec asserts old behavior (e.g. imported status shown as 審核中), update the assertion to 已提交.

- [ ] **Step 5: End-to-end verification of the real flow**

Use the `playwright-test-and-debug` skill flow: log in as a college user, download the template for the PhD scholarship, upload a filled file (one row with 國科會=1/教育部=1, one row with both blank → expect a missing_sub_type error and an eligibility warning section), confirm the import, then verify in the DB:

```bash
docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -c \
  "SELECT app_id, status, review_stage, amount, scholarship_name, professor_id, submitted_form_data FROM applications WHERE import_source='batch_import' ORDER BY id DESC LIMIT 3;"
docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -c \
  "SELECT user_id, account_number, advisor_name, advisor_nycu_id FROM user_profiles ORDER BY id DESC LIMIT 3;"
```
Expected: `status=submitted`, `review_stage=student_submitted`, amount/name from config, `app_id` ends with `U`, form_data has `fields`/`documents` keys, profile rows upserted. Then log in as the professor account and confirm the imported application appears in the 待審 list.

- [ ] **Step 6: Final commit if anything changed in steps 3–4**

```bash
git add -A && git commit -m "test: update frontend/e2e assertions for batch import review-flow parity"
```

---

## Self-Review Notes (already applied)

- Spec coverage: review-flow parity (Task 5), data-structure parity (Task 5), UserProfile overwrite (Task 5), eligibility/whitelist warnings + period exemption + professor warning (Task 6), sub-type hard error + checkmark parsing + forced ordering (Task 4), amount/config_name (Tasks 1+5), U suffix kept (Tasks 2+5), template samples (Task 7), no email/no clone/no migration (nothing added anywhere).
- Period exemption is implemented by filtering the exact reason string `"不在申請期間內"` from `EligibilityService` output — fragile if that copy changes, but the alternative (a bypass flag threaded through EligibilityService) touches the student path for a batch-only concern. The string is pinned by `_PERIOD_EXEMPT_REASONS` next to a comment; `test_bulk_check_eligibility_flags_failures_but_filters_period` breaks loudly if the copy drifts.
- `missing_sub_type` rows are excluded at parse (like blank-student-id rows): not inline-editable, must fix Excel and re-upload. Matches "預覽擋下" semantics agreed in brainstorming.
- Type consistency: `order_sub_type_preferences` (Tasks 1/4), `generate_app_id(db, year, semester, suffix=, commit=)` (Tasks 2/3/5), `bulk_check_eligibility(parsed_data, scholarship_type_id, academic_year, semester)` (Task 6 service + endpoints) — names and signatures match across tasks.
