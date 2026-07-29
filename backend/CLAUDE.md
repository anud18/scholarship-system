# Backend Guidelines (FastAPI / SQLAlchemy / Alembic)

Loaded when working under `backend/`. Project-wide rules live in `.claude/CLAUDE.md`.

## API Response Standardization

**CRITICAL**: All API endpoints MUST return a consistent ApiResponse format for frontend compatibility.

### Standard Format
```python
{
    "success": bool,
    "message": str,
    "data": any  # Can be dict, list, Pydantic model, or None
}
```

### Backend Implementation Rules

**Remove response_model decorators**:
```python
# ❌ WRONG - Using response_model
@router.get("/users", response_model=List[UserResponse])
async def get_users():
    return users

# ✅ CORRECT - Manual dict wrapping
@router.get("/users")
async def get_users():
    return {
        "success": True,
        "message": "Users retrieved successfully",
        "data": [user.model_dump() for user in users],
    }
```

Convert Pydantic schemas with `.model_dump()` (v2). `PaginatedResponse` is **not** a top-level return — wrap it too: `data=response_data.model_dump()`.

The frontend `api.ts` auto-detects this shape (`"success" in data && "message" in data`), so a non-wrapped endpoint silently falls through to the raw-body path.

### Migration Checklist
When standardizing existing endpoints:
- [ ] Remove `response_model=` parameter from `@router` decorator
- [ ] Wrap return statement in `{success, message, data}` dict format
- [ ] Convert Pydantic schemas using `.model_dump()`
- [ ] Remove unused imports (MessageResponse, specific response models)
- [ ] Run `python -m black` for auto-formatting
- [ ] Verify with `python -m flake8` (check F401 unused imports)
- [ ] Test endpoint returns expected format

## Database Initialization & Migration Standards

### Database Volume Recreation
**ALWAYS** use the automated script for clean database rebuilds:

```bash
./scripts/reset_database.sh
./scripts/reset_database.sh --dry-run  # Preview steps
```

### Alembic Migration Development Rules
**CRITICAL**: Always include existence checks in migrations:

```python
# ✅ CORRECT - Check before creating
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)

# ❌ WRONG - Direct creation without checks
def upgrade() -> None:
    op.create_table('new_table', ...)  # May fail if exists
```

### Database Constraint Requirements
Ensure all constraints used in seed scripts exist in SQLAlchemy models:

```python
# ✅ CORRECT - Define constraints for ON CONFLICT
class ApplicationField(Base):
    __tablename__ = "application_fields"
    __table_args__ = (
        UniqueConstraint('scholarship_type', 'field_name', name='uq_application_field_type_name'),
    )
```

### Migration Testing
Before creating any migration:
- Test on fresh database using `./scripts/reset_database.sh`
- Include existence checks for all DDL operations
- Verify seed scripts work with new constraints
- Test rollback functionality

## Testing, Lint & CI Standards

Hard-won from the 2026-05-30 backend-test-backlog cleanup (cleared ~150 failures). Follow these to avoid re-introducing the same classes of failure.

### CI suite layout (`.github/workflows/ci.yml`)
- **unit**: `app/tests/test_*.py -m "not integration and not asyncio"` — sync tests only.
- **integration**: `app/tests/test_*_service*.py -m "integration or asyncio"` — async tests. `asyncio_mode = auto`, so any `async def test_` is auto-collected here (it is EXCLUDED from unit).
- **smoke**: explicit file list (includes `test_critical_workflows.py`). The former dedicated `critical-workflows` lane was removed as redundant — that file already runs in smoke + integration.
- A test that is `@pytest.mark.asyncio` / `async def` runs in **integration**, not unit. Converting a sync test to async moves it between suites.

### Lint is HARD-gated — black passing is NOT enough
Before committing backend changes, run **all three**:
```bash
uvx --from "black==26.3.1" black --check --line-length=120 backend/app
flake8 app --select=B904,B014 --max-line-length=120     # CI fails hard on these
python -m pytest app/tests/<touched_file> -p no:cacheprovider   # in the dev container
```
- **B904**: `raise` inside `except` must use `raise ... from exc` (or `from None`).
- **B014**: no redundant exception tuples — `PermissionError` ⊂ `OSError`, so write `except OSError`, never `except (PermissionError, OSError)`.
- **WARNING/ERROR-traceback AST invariant** (`test_no_logger_warning_traceback_loss.py`, `test_no_logger_error_traceback_loss.py`): any `logger.warning(...)` / `logger.error(...)` that interpolates the exception variable inside an `except` block MUST also pass `exc_info=True` (or drop the interpolation). The trace gets discarded otherwise.

### Test-fixture pitfalls (the recurring failures)
- **Never build a model with `Model.__new__(Model)` / `object.__new__(Model)` then set attributes** — it bypasses `__init__`, so `_sa_instance_state` is missing and the first instrumented-attribute write raises `'NoneType' object has no attribute 'set'`. Use `Model(**defaults)`; for vestigial/non-column keys or duck-typed relationship stubs use `m = Model(); m.__dict__.update(defaults)` (or `m.__dict__["rel"] = SimpleNamespace(...)`).
- **Keep fixtures in sync with the model.** Passing a removed/renamed column raises `'<field>' is an invalid keyword argument for <Model>`. Known removals: `ScholarshipType.category` (gone; status lives in `status`), `Application.student_id` (student data is external-API now; FK is `user_id`), `User` uses `nycu_id`/`name`/`status` (NOT `username`/`full_name`/`is_active`).
- **Enum vs string in in-memory objects.** A DB-loaded model returns the **enum member** (`Enum` column), but an in-memory fixture holds exactly what you passed. Methods compare against the enum member (`status == ApplicationStatus.submitted`), so pass the member, not `.value`, when constructing test objects — otherwise predicates like `is_editable` / `get_review_stage` silently mismatch.
- **No sync-calling-async.** Service methods on async-session services are `async`; tests must be `async def` + `await` + use the async `db` fixture (not `db_sync`). A sync call returns an un-awaited coroutine → `'coroutine' object has no attribute 'id'`.
- **No env- or cache-dependent assertions.** Settings have non-None defaults (e.g. `student_api_enabled=True`, SIS URLs), so a bare service is "configured" everywhere — `monkeypatch` settings to force the state you assert. The dev container has Redis; CI does not — clear `@cached` state in an autouse fixture (`await invalidate("<prefix>")`) so one test's payload doesn't leak into another.
- **No flaky randomness.** Don't corrupt the *last* base64 char of a random-nonce envelope to test tamper-detection (it can hit only padding bits → no corruption → `DID NOT RAISE`); corrupt a **middle** char (a full byte). Verify determinism by running the test ~30×.

## Model & Schema Gotchas

- **ScholarshipType vs ScholarshipConfiguration split.** Application-period dates, `academic_year`, `amount`, the period-detection properties (`is_renewal_application_period`, `current_application_type`, …) and `can_student_apply*` live on **ScholarshipConfiguration**, NOT `ScholarshipType`. Building these on a `ScholarshipType` is a bug.
- **Renamed-relationship bug class.** Several latent `AttributeError`s came from an incomplete rename: `Application.user`→`.student`, `Application.scholarship_type`→`.scholarship_type_ref`, notification `application.scholarship_type`→`application.scholarship_name`. When you rename a relationship, **grep the whole repo** for the old name (services, endpoints, AND tests that stub it).
- **Coalesce nullable JSON into required-dict response fields.** `ApplicationListResponse.student_data` / `submitted_form_data` are required `Dict`; a draft can have `student_data IS NULL`. Always write `student_data=application.student_data or {}` (see the canonical builders) — passing `None` raises a pydantic `dict_type` error.
- **Pydantic v2 cross-field validators run in field-definition order.** A `@field_validator` on a field reading a flag defined *later* sees that flag as unset. Use `@model_validator(mode="after")` for any rule that spans fields (e.g. renewal-review-dates-require-the-`requires_*`-flag).
- **Enum "pin" tripwire tests** (`test_shared_enums_value_contract.py`) intentionally fail when an enum gains a value — the correct response is to update the count AFTER confirming dependent frontend switches / admin filters handle the new value, not to delete the test.

## Performance Patterns

- **Eager-load to-one relationships read inside loops.** A `db.query(Application).all()` whose rows later read `application.student` / `application.scholarship_configuration.scholarship_type` in a loop is N+1. Add `.options(joinedload(Application.student), joinedload(Application.scholarship_configuration).joinedload(...))` (many-to-one → `joinedload` is safe, no row multiplication).
- **Index foreign keys and audit-trail lookups.** PostgreSQL does NOT auto-index FKs. Index columns filtered/ordered on hot paths (e.g. `applications.scholarship_configuration_id`; composite `audit_logs(resource_type, resource_id, created_at)`), and declare them in the model `__table_args__` so autogenerate stays in sync.
