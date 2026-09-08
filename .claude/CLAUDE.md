# Scholarship System Development Guidelines

Please use English for git commit messages.

## Development Environment

**Use `docker compose -f docker-compose.dev.yml` for all local development.** (There are nine `docker-compose.*.yml` files — dev is never the default `docker-compose.yml`.)

This spins up the full stack (backend, frontend, database, RustFS object storage (S3 API, service name `minio`), mock student API) with hot-reload enabled.

## Core Development Principles

### 1. Error Handling Standards
**CRITICAL**: Never return fallback or mock data when database retrieval fails. Always throw errors directly.

```python
# ❌ WRONG - Don't return fallback data
def get_scholarship_data():
    try:
        return db.get_scholarship()
    except:
        return {"name": "Default Scholarship"}

# ✅ CORRECT - Throw error directly
def get_scholarship_data():
    scholarship = db.get_scholarship()
    if not scholarship:
        raise ScholarshipNotFoundError("No scholarship data available")
    return scholarship
```

### 2. Backward Compatibility Policy
**NO BACKWARD COMPATIBILITY**: Revise code directly without considering forward compatibility. Focus on current requirements and clean implementation.

### 3. Scholarship Configuration Architecture
**USE CONFIGURATION-BASED LOGIC**: Implement scholarship logic using database-driven configuration rather than hardcoded scholarship names.

```python
# ❌ WRONG - Hardcoded scholarship name logic
if scholarship.name == "Academic Excellence":
    # specific logic

# ✅ CORRECT - Configuration-based logic
if scholarship.config.requires_interview:
    # interview logic
```

**Adding New Scholarship Types**:
1. Insert into `scholarship_types` table
2. Create configuration record in `scholarship_configurations`
3. No code changes required - system uses configuration automatically

### 4. Enum Consistency Guidelines
**CRITICAL**: Maintain strict consistency between Python enums, PostgreSQL enums, and TypeScript enums.

#### Python Backend
- Use **lowercase** enum member names matching database values exactly
- Always include `values_callable` parameter in SQLAlchemy columns

```python
# ✅ CORRECT
class Semester(enum.Enum):
    first = "first"
    second = "second"

semester = Column(
    Enum(Semester, values_callable=lambda obj: [e.value for e in obj]),
    nullable=True
)
```

#### TypeScript Frontend
- Use **UPPERCASE** enum member names
- Values must match backend/database exactly (lowercase)

#### PostgreSQL Database
- Enum values are always **lowercase**
- Match Python enum values exactly

The authoritative list of current system enums is `backend/app/models/enums.py` (mirrored in `frontend/lib/enums.ts`). Note one non-obvious case: **EmployeeStatus** values are Chinese (`在職`, `退休`, `在學`, `畢業`), not romanized.

#### Special Case: Scholarship Sub-Types (Configuration-Driven)

**IMPORTANT**: Scholarship sub-types (e.g., `nstc`, `moe_1w`, `moe_2w`) are **NOT enum-constrained**.

**Why?**
- Sub-types are defined in `scholarship_configurations.quotas` JSON field
- Administrators can add new sub-types without code changes
- Follows configuration-based architecture principle

**Naming Convention**:
- Use **lowercase** with **underscore** separation (e.g., `nstc`, `moe_1w`, `new_custom_type`)
- Stored as `String(50)` in database, not Enum
- `ScholarshipSubType` enum exists for backward compatibility only (deprecated)

**Example Configuration**:
```json
{
  "quotas": {
    "nstc": {"C": 12, "A": 8},
    "moe_1w": {"C": 8, "A": 5},
    "custom_new_type": {"C": 10}
  }
}
```

**For Developers**:
- ✅ Use string values directly: `application.sub_scholarship_type = "nstc"`
- ❌ Don't add new values to `ScholarshipSubType` enum
- ✅ Normalize to lowercase in application layer: `sub_type.lower().strip()`

#### Enum Synchronization Checklist
1. Update Python enum in `backend/app/models/enums.py`
2. Update TypeScript enum in `frontend/lib/enums.ts`
3. Create Alembic migration for database enum changes
4. Update all code references using find/replace
5. Test all three layers together

#### Troubleshooting
If you see `LookupError: 'value' is not among the defined enum values`:
1. Check Python enum member names match database values exactly
2. Verify `values_callable` parameter is set in SQLAlchemy columns
3. Ensure frontend sends lowercase values to backend APIs

### 5. API Response Standardization

**CRITICAL**: All API endpoints MUST return a consistent `{success, message, data}` ApiResponse dict — never a `response_model=` decorator. Full rules, examples and the migration checklist: `backend/CLAUDE.md`.

### 6. Application ID Format

Application IDs are `APP-{academic_year}-{semester_code}-{sequence:05d}` with an independent, row-locked sequence per (academic_year, semester). Implementation: `backend/app/models/application_sequence.py` + `_generate_app_id` in `backend/app/services/application_service.py`.

### 7. Application Data Structure Principles

**CRITICAL**: Clear separation between API data snapshot and student-submitted data.

#### student_data (JSON Field)
**Purpose**: Pure SIS API data snapshot at time of application submission.

**Contents**:
- API 1: `ScholarshipStudent` - Basic student information
- API 2: `ScholarshipStudentTerm` - Semester-specific data (申請當時的學期資料)
- **Internal metadata**: `_api_fetched_at`, `_term_data_status`, `_term_error_message`

**Does NOT include**:
- ❌ Student-filled form data (bank account, contact phone, etc.)
- ❌ Application-specific data (scholarship type, application status, etc.)

**Schema Definition**: `backend/app/schemas/student_snapshot.py` (see it for the full field list — API 1 `std_*`/`com_*` fields, API 2 `trm_*` fields, plus the `_api_fetched_at`/`_term_data_status` metadata keys).

#### submitted_form_data (JSON Field)
**Purpose**: Student-filled dynamic form data.

**Contents**:
- Dynamic form fields (bank_account, contact_phone, etc.)
- Uploaded document metadata

**Schema**: See `ApplicationFormData` in `backend/app/schemas/application.py` (a `fields` map of field-id → typed value entries, plus a `documents` list of upload metadata).

#### Review Data Principles
**No Scoring System**: Review mechanism simplified to recommendation/ranking mode.

**Review Flow**:
1. Professor Review: Recommend (yes/no) + comments
2. College Review: Ranking position + comments
3. Final Decision: Approve/Reject + reason

### 8. OpenAPI Type Generation

**When modifying API endpoints/schemas**, regenerate TypeScript types to maintain type safety:

```bash
cd frontend && bun run api:generate
git add lib/api/generated/schema.d.ts
```

CI validates type sync automatically. Backend must be running on `localhost:8000` during generation.

## Database Initialization & Migration Standards

**ALWAYS** rebuild the database with `./scripts/reset_database.sh` (`--dry-run` to preview) — never by hand. Every migration MUST include existence checks before DDL. Full rules, examples and the pre-migration test checklist: `backend/CLAUDE.md`.

## File Upload & Preview Architecture

Files flow `Frontend → Next.js proxy → FastAPI → MinIO`. **Never** hand out direct MinIO URLs, and store `object_name` in the DB, not a full URL. For the proxy header contract (the missing-`Content-Length` trap that produces false "password protected" PDF errors) and the rest of the rules, use the **file-upload-preview** skill.

## Backend Testing, Lint, CI & Model Gotchas

Backend test-suite layout, the hard-gated lint commands (black + flake8 `B904,B014` + the `exc_info=True` AST invariant), the recurring test-fixture pitfalls, the ScholarshipType-vs-ScholarshipConfiguration split and the other model/schema gotchas live in `backend/CLAUDE.md` (loaded automatically when working under `backend/`). Frontend performance patterns live in `frontend/CLAUDE.md`.

## Review-Flow Policy

- A **professor full-reject is terminal for the professor**: it sets `application.status = rejected`, and the professor **cannot re-review** that application (the review endpoint returns HTTP 403). Only **college/admin** may revert it (回發) — that is a separate, explicit edit path, not a professor re-submit.
