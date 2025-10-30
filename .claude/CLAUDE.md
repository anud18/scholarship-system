# Scholarship System Development Guidelines

Please use English for git commit messages.

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

```typescript
// ✅ CORRECT
export enum Semester {
    FIRST = 'first',
    SECOND = 'second',
    ANNUAL = 'annual'
}
```

#### PostgreSQL Database
- Enum values are always **lowercase**
- Match Python enum values exactly

```sql
CREATE TYPE semester AS ENUM ('first', 'second', 'annual');
```

#### Current System Enums
- **Semester**: `first`, `second`, `annual`
- **UserRole**: `student`, `professor`, `college`, `admin`, `super_admin`
- **ApplicationCycle**: `semester`, `yearly`
- **QuotaManagementMode**: `none`, `simple`, `college_based`, `matrix_based`
- **SubTypeSelectionMode**: `single`, `multiple`, `hierarchical`
- **UserType**: `student`, `employee`
- **EmployeeStatus**: `在職`, `退休`, `在學`, `畢業` (Chinese values)

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

**CRITICAL**: All API endpoints MUST return a consistent ApiResponse format for frontend compatibility.

#### Standard Format
```python
{
    "success": bool,
    "message": str,
    "data": any  # Can be dict, list, Pydantic model, or None
}
```

#### Backend Implementation Rules

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

**Converting Pydantic Schemas**:
```python
# For Pydantic v2 (preferred)
response_data.model_dump()

# Fallback for v1
response_data.dict()

# Safe universal conversion
response_data.model_dump() if hasattr(response_data, "model_dump") else response_data.dict()
```

**Wrapping PaginatedResponse**:
```python
# ❌ WRONG - Direct return
return PaginatedResponse(items=items, total=total, page=page, size=size)

# ✅ CORRECT - Wrapped in ApiResponse
response_data = PaginatedResponse(items=items, total=total, page=page, size=size)
return {
    "success": True,
    "message": "Data retrieved successfully",
    "data": response_data.model_dump(),
}
```

#### Frontend Compatibility
The frontend `api.ts` automatically detects ApiResponse format:
```typescript
// Frontend auto-detection (already implemented)
if ("success" in data && "message" in data) {
    return data as ApiResponse<T>;
}
```

#### Migration Checklist
When standardizing existing endpoints:
- [ ] Remove `response_model=` parameter from `@router` decorator
- [ ] Wrap return statement in `{success, message, data}` dict format
- [ ] Convert Pydantic schemas using `.model_dump()` or `.dict()`
- [ ] Remove unused imports (MessageResponse, specific response models)
- [ ] Run `python -m black` for auto-formatting
- [ ] Verify with `python -m flake8` (check F401 unused imports)
- [ ] Test endpoint returns expected format

#### Common Issues & Solutions

**1. Syntax errors after regex replacement**:
```bash
# Fix double commas
python -c "import re; content = open('file.py').read(); \
    content = re.sub(r',,+', ',', content); \
    open('file.py', 'w').write(content)"

# Fix trailing commas before closing brackets
python -c "import re; content = open('file.py').read(); \
    content = re.sub(r',(\s*[}\]\)])', r'\1', content); \
    open('file.py', 'w').write(content)"
```

**2. Decorator missing commas**:
```python
# ❌ WRONG (after response_model removal)
@router.post("/announcements"
    status_code=status.HTTP_201_CREATED)

# ✅ CORRECT
@router.post("/announcements",
    status_code=status.HTTP_201_CREATED)
```

**3. Auto-formatting solution**:
```bash
# Let black handle all formatting issues
python -m black path/to/file.py
```

**4. Unused imports after migration**:
```python
# Remove these if no longer used:
from app.schemas.common import MessageResponse  # Old single-field response
from app.schemas.application import ApplicationResponse  # Replaced by dict wrapping
```

#### Batch Migration Script Template
```python
import re

with open('endpoint.py', 'r') as f:
    content = f.read()

# Remove response_model parameters
content = re.sub(r',?\s*response_model\s*=\s*[^\n\)]*(?:\[[^\]]*\])?[^\n\)]*', '', content)

# Clean up formatting
content = re.sub(r',,+', ',', content)
content = re.sub(r',(\s*[}\]\)])', r'\1', content)

with open('endpoint.py', 'w') as f:
    f.write(content)

# Then run black to fix all formatting
# python -m black endpoint.py
```

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
- `0`: Annual/Yearly Scholarships (`annual`)

#### Implementation Details
- **Sequence Management**: Each (academic_year, semester) combination has an independent sequence counter
- **Database Table**: `application_sequences` stores the last used sequence number
- **Concurrency Safety**: Uses database-level row locking (`FOR UPDATE`) to prevent duplicate numbers
- **Auto-Creation**: Sequence records are created automatically when first application is made

#### Key Components
```python
# Model: app/models/application_sequence.py
class ApplicationSequence(Base):
    academic_year = Column(Integer, primary_key=True)
    semester = Column(String(20), primary_key=True)
    last_sequence = Column(Integer, default=0)

# Service: app/services/application_service.py
async def _generate_app_id(self, academic_year: int, semester: Optional[str]) -> str:
    # Uses database locking for thread-safe sequence generation
    # Returns formatted app_id: APP-{year}-{code}-{seq:05d}
```

#### Migration
Migration `6b5cb44d2fe3` creates the `application_sequences` table and initializes sequences from existing applications.

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

**Schema Definition**: `backend/app/schemas/student_snapshot.py`

```python
# Example student_data structure
{
    # API 1: 學生基本資料
    "std_stdcode": "310460031",
    "std_cname": "王小明",
    "com_email": "nctutest@g2.nctu.edu.tw",
    "std_academyno": "A",
    "std_depno": "4460",
    # ... all API 1 fields

    # API 2: 學生學期資料 (申請當時)
    "trm_year": 114,
    "trm_term": 1,
    "trm_academyname": "人社院",
    "trm_depname": "教育博",
    "trm_ascore_gpa": 3.8,
    # ... all API 2 fields

    # Internal metadata
    "_api_fetched_at": "2025-10-22T17:27:08Z",
    "_term_data_status": "success"
}
```

#### submitted_form_data (JSON Field)
**Purpose**: Student-filled dynamic form data.

**Contents**:
- Dynamic form fields (bank_account, contact_phone, etc.)
- Uploaded document metadata

**Schema**: See `ApplicationFormData` in `backend/app/schemas/application.py`

```python
# Example submitted_form_data structure
{
    "fields": {
        "bank_account": {
            "field_id": "bank_account",
            "field_type": "text",
            "value": "123456789",
            "required": true
        }
    },
    "documents": [
        {
            "document_id": "bank_account_cover",
            "file_path": "...",
            "upload_time": "2024-03-19T10:00:00Z"
        }
    ]
}
```

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
cd frontend && npm run api:generate
git add lib/api/generated/schema.d.ts
```

CI validates type sync automatically. Backend must be running on `localhost:8000` during generation.

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

**CRITICAL**: When accepting regex patterns from users (e.g., for configuration validation), never use `re.escape()` as it would break functionality. Instead, use comprehensive validation.

### Use Case
Administrators need to define custom regex patterns for validating configuration values (emails, API keys, port numbers, etc.). These patterns must remain functional while being secure against regex injection and ReDoS attacks.

### Security Architecture

**Core Module**: `backend/app/core/regex_validator.py`

This module provides secure wrapper functions for regex operations:
- `validate_regex_pattern()` - Validates pattern before use
- `safe_regex_match()` - Safe pattern matching
- `safe_regex_search()` - Safe pattern searching
- `validate_and_sanitize_pattern()` - JSON round-trip sanitization

### Multi-Layer Validation

```python
# ✅ CORRECT - Use safe wrappers
from app.core.regex_validator import validate_regex_pattern, safe_regex_match

# Validate pattern first
validate_regex_pattern(user_pattern, timeout_seconds=1)

# Use safe wrapper (includes re-validation)
match = safe_regex_match(user_pattern, value, timeout_seconds=1)
```

### Validation Layers

1. **Length Check**: Maximum 200 characters
2. **ReDoS Detection**: 6 dangerous patterns checked:
   - Multiple unbounded wildcards: `.*.*`
   - Multiple unbounded plus: `.+.+`
   - Nested quantified groups: `(a*)*`, `(a+)+`
   - Quantifiers on quantified groups
3. **Timeout Protection**: Signal-based (1 second max)
4. **Syntax Validation**: Compilation test
5. **JSON Sanitization**: Round-trip to break taint flow

### CodeQL Suppression

**IMPORTANT**: CodeQL does NOT support inline comment suppressions (e.g., `# lgtm[...]`). The correct way to suppress false positives is using the `filter-sarif` GitHub Action.

**Implementation** (`.github/workflows/codeql.yml`):

```yaml
- name: Perform CodeQL Analysis
  uses: github/codeql-action/analyze@v4
  with:
    output: sarif-results
    upload: false  # Filter before upload

- name: Filter Python SARIF (Remove False Positives)
  if: matrix.language == 'python'
  uses: advanced-security/filter-sarif@v1
  with:
    patterns: |
      -backend/app/core/regex_validator.py:py/regex-injection
    input: sarif-results/python.sarif
    output: sarif-results/python.sarif

- name: Upload SARIF to Code Scanning
  uses: github/codeql-action/upload-sarif@v4
  with:
    sarif_file: sarif-results/${{ matrix.language }}.sarif
```

**Pattern Syntax**:
- `-<file-path>:<query-id>` - Exclude specific query from specific file
- `+<file-path>:<query-id>` - Include only this query for this file

**Documentation**:
- All suppression justifications are in `.github/codeql/codeql-config.yml`
- The filter-sarif action is the official supported method

### Test Coverage

See `backend/tests/test_regex_validator.py` for comprehensive test suite:
- 22 test cases covering all security scenarios
- Dangerous pattern rejection tests
- ReDoS attack prevention tests
- Edge case coverage (unicode, empty strings, long inputs)

### DO NOT Use re.escape()

```python
# ❌ WRONG - Breaks regex functionality
safe_pattern = re.escape(user_pattern)  # Turns "^\d{3}$" into "\\^\\d\\{3\\}\\$"
re.match(safe_pattern, "123")  # Won't match!

# ✅ CORRECT - Use validation wrapper
validate_regex_pattern(user_pattern)
safe_regex_match(user_pattern, "123")  # Works correctly!
```

### Integration Example

```python
# In config_management_service.py
if validation_regex:
    try:
        # SECURITY: Validate regex pattern first
        validate_regex_pattern(validation_regex, timeout_seconds=1)

        # Pattern is now safe to use
        match = safe_regex_match(validation_regex, string_value, timeout_seconds=1)
        if not match:
            raise ValueError(f"Value does not match pattern: {validation_regex}")
    except RegexValidationError as e:
        raise ValueError(f"Invalid validation pattern: {str(e)}")
```

### Security Checklist
- [ ] Use `validate_regex_pattern()` before any regex operation with user input
- [ ] Use `safe_regex_match()` or `safe_regex_search()` wrappers (not direct `re.match()`)
- [ ] Never use `re.escape()` for admin-provided validation patterns
- [ ] Suppress false positives via `filter-sarif` in CodeQL workflow (not inline comments)
- [ ] Set appropriate timeout (default: 1 second)
- [ ] Test with malicious patterns in unit tests

## File Upload & Preview Architecture

### Three-Layer Architecture
```
Frontend → Next.js Proxy → FastAPI → MinIO
```

**Why Next.js Proxy?**
- Token authentication handling
- Internal Docker network communication
- CORS management
- Centralized error handling

### Critical Implementation Rules
1. **Store object_name, not full URL** in database
2. **Always use Next.js proxy** for file access (never direct MinIO URLs)
3. **Pass token via query parameter** for authentication
4. **Use INTERNAL_API_URL** for Docker network communication
5. **Preserve all headers** from backend when proxying

### Required HTTP Headers for PDF Preview
When proxying files through Next.js, preserve these headers:

```typescript
return new NextResponse(fileBuffer, {
  headers: {
    "Content-Type": contentType,                           // File type
    "Content-Disposition": contentDisposition,             // Preserve from backend
    "Content-Length": fileBuffer.byteLength.toString(),    // File size (REQUIRED)
    "Accept-Ranges": "bytes",                              // Range support
    "Cache-Control": "private, max-age=3600",
  },
});
```

**CRITICAL**: Missing `Content-Length` or incomplete `Content-Disposition` can cause PDF viewer errors (including false "password protected" errors).

### Environment Variables
```bash
# Backend
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET=scholarship-system

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
INTERNAL_API_URL=http://backend:8000  # Docker internal network
```

---

**Remember**: Create a flexible, maintainable system where new scholarship types can be added through database configuration without code changes.
