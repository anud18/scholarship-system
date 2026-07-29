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

**Sequential Application Numbering**: Application IDs follow a structured format for better tracking and management.

#### Format Specification
```
APP-{academic_year}-{semester_code}-{sequence:05d}

Examples:
- APP-113-1-00001 (Academic Year 113, First Semester, Sequence 1)
- APP-113-2-00125 (Academic Year 113, Second Semester, Sequence 125)
- APP-114-0-00001 (Academic Year 114, Annual, Sequence 1)
```

#### Semester Codes
- `1`: First Semester (`first`)
- `2`: Second Semester (`second`)
- `0`: Yearly Scholarships (`yearly`)

#### Implementation Details
- **Sequence Management**: Each (academic_year, semester) combination has an independent sequence counter
- **Database Table**: `application_sequences` stores the last used sequence number
- **Concurrency Safety**: Uses database-level row locking (`FOR UPDATE`) to prevent duplicate numbers
- **Auto-Creation**: Sequence records are created automatically when first application is made

Implementation: `backend/app/models/application_sequence.py` + `_generate_app_id` in `backend/app/services/application_service.py`.

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

**Application Table**:
- ❌ Removed: `review_score`, `review_comments`, `rejection_reason`, `priority_score`, `college_ranking_score`
- ✅ Kept: `final_ranking_position` (position number, not score)

**ApplicationReview Table**:
- ❌ Removed: `score`, `criteria_scores`
- ✅ Kept: `comments`, `recommendation`, `decision_reason` (包含拒絕原因)

**CollegeReview Table**:
- ❌ Removed: `ranking_score`, `academic_score`, `professor_review_score`, etc.
- ✅ Kept: `preliminary_rank`, `final_rank` (positions, not scores)

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

## Path Security & Backslash Handling

**CRITICAL**: Always validate file paths to prevent path traversal attacks.

### Path Traversal Prevention
```python
# ✅ CORRECT - Triple validation
if ".." in filename or "/" in filename or "\\" in filename:
    raise HTTPException(status_code=400, detail="無效的檔案名稱")

if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
    raise HTTPException(status_code=400, detail="檔案名稱包含無效字元")

resolved_path = os.path.abspath(file_path)
expected_dir = os.path.abspath(os.path.join(upload_base, bank_docs_dir))
if not resolved_path.startswith(expected_dir):
    raise HTTPException(status_code=403, detail="存取被拒絕")
```

### Security Checklist
- [ ] Check for `..` (parent directory traversal)
- [ ] Check for `/` (absolute path injection)
- [ ] Check for `\` (Windows path separator)
- [ ] Validate with regex pattern `^[a-zA-Z0-9_\-\.]+$`
- [ ] Verify resolved absolute path is within expected directory

## Regex Injection Prevention

**CRITICAL**: Never use `re.escape()` on admin-provided validation patterns (it breaks them), and never call `re.match()`/`re.search()` on them directly — always use the safe wrappers in `backend/app/core/regex_validator.py` (`validate_regex_pattern()`, `safe_regex_match()`, `safe_regex_search()`). For the full validation architecture, ReDoS rules, CodeQL `filter-sarif` suppression workflow, and integration examples, use the **regex-security** skill.

## File Upload & Preview Architecture

Files flow `Frontend → Next.js proxy → FastAPI → MinIO`. **Never** hand out direct MinIO URLs, and store `object_name` in the DB, not a full URL. For the proxy header contract (the missing-`Content-Length` trap that produces false "password protected" PDF errors) and the rest of the rules, use the **file-upload-preview** skill.

## Backend Testing, Lint, CI & Model Gotchas

Backend test-suite layout, the hard-gated lint commands (black + flake8 `B904,B014` + the `exc_info=True` AST invariant), the recurring test-fixture pitfalls, the ScholarshipType-vs-ScholarshipConfiguration split and the other model/schema gotchas live in `backend/CLAUDE.md` (loaded automatically when working under `backend/`). Frontend performance patterns live in `frontend/CLAUDE.md`.

## Review-Flow Policy

- A **professor full-reject is terminal for the professor**: it sets `application.status = rejected`, and the professor **cannot re-review** that application (the review endpoint returns HTTP 403). Only **college/admin** may revert it (回發) — that is a separate, explicit edit path, not a professor re-submit.
