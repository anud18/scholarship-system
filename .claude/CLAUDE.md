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

## Debug Panel Control

Control via `NEXT_PUBLIC_ENABLE_DEBUG_PANEL` environment variable:

```yaml
# Development
frontend:
  environment:
    NEXT_PUBLIC_ENABLE_DEBUG_PANEL: "true"

# Production
frontend:
  environment:
    NEXT_PUBLIC_ENABLE_DEBUG_PANEL: "false"
```

---

**Remember**: Create a flexible, maintainable system where new scholarship types can be added through database configuration without code changes.
