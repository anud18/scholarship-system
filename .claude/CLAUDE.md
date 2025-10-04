# Scholarship System Development Guidelines

## Development Best Practices

- Dont hardcode data; always retrieve data from database and if there is an issue, throw the error directly instead of using fallback data

## Core Development Principles

### 1. Error Handling Standards
**CRITICAL**: Never return fallback or mock data when database retrieval fails. Always throw errors directly to maintain data integrity and debugging clarity.

```python
# ❌ WRONG - Don't return fallback data
def get_scholarship_data():
    try:
        return db.get_scholarship()
    except:
        return {"name": "Default Scholarship"}  # Fallback data

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

#### Configuration-Driven Approach
```python
# ❌ WRONG - Hardcoded scholarship name logic
if scholarship.name == "Academic Excellence":
    # specific logic
elif scholarship.name == "Research Grant":
    # different logic

# ✅ CORRECT - Configuration-based logic
if scholarship.config.requires_interview:
    # interview logic
if scholarship.config.has_quota_limit:
    # quota logic
```

#### Database Schema for Dynamic Configuration
```sql
-- scholarship_configurations table
CREATE TABLE scholarship_configurations (
    id SERIAL PRIMARY KEY,
    scholarship_type_id INTEGER REFERENCES scholarship_types(id),
    config_code VARCHAR(50) UNIQUE NOT NULL,

    -- Dynamic configuration fields
    requires_interview BOOLEAN DEFAULT FALSE,
    has_quota_limit BOOLEAN DEFAULT FALSE,
    allows_multiple_applications BOOLEAN DEFAULT FALSE,
    requires_recommendation_letter BOOLEAN DEFAULT FALSE,

    -- Custom configuration
    custom_fields JSON,
    eligibility_overrides JSON,

    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 4. Enum Consistency Guidelines
**CRITICAL**: Maintain strict consistency between Python enums, PostgreSQL enums, and TypeScript enums to prevent runtime errors.

#### Enum Definition Standards

##### Python Backend (app/models/enums.py)
- Use **lowercase** enum member names that match database values exactly
- Always include `values_callable` parameter in SQLAlchemy columns

```python
# ✅ CORRECT - Lowercase member names matching database
class Semester(enum.Enum):
    first = "first"
    second = "second"
    annual = "annual"

# SQLAlchemy column definition
semester = Column(
    Enum(Semester, values_callable=lambda obj: [e.value for e in obj]),
    nullable=True
)

# ❌ WRONG - Uppercase member names not matching database
class Semester(enum.Enum):
    FIRST = "first"  # Will cause LookupError!
    SECOND = "second"
```

##### TypeScript Frontend (lib/enums.ts)
- Use **UPPERCASE** enum member names (TypeScript convention)
- Values must match backend/database exactly (lowercase)

```typescript
// ✅ CORRECT - Uppercase members, lowercase values
export enum Semester {
    FIRST = 'first',
    SECOND = 'second',
    ANNUAL = 'annual'
}

// Update label functions when enum changes
export const getSemesterLabel = (semester: Semester, locale: 'zh' | 'en' = 'zh'): string => {
    const labels = {
        zh: {
            [Semester.FIRST]: '第一學期',
            [Semester.SECOND]: '第二學期',
            [Semester.ANNUAL]: '全年'
        }
    }
    return labels[locale][semester]
}
```

##### PostgreSQL Database
- Enum values are always **lowercase**
- Match Python enum values exactly

```sql
-- ✅ CORRECT - Lowercase values matching Python
CREATE TYPE semester AS ENUM ('first', 'second', 'annual');

-- ❌ WRONG - Uppercase values will cause mismatch
CREATE TYPE semester AS ENUM ('FIRST', 'SECOND', 'ANNUAL');
```

#### Enum Synchronization Checklist
When adding/modifying enums:
1. **Update Python enum** in `backend/app/models/enums.py`
2. **Update TypeScript enum** in `frontend/lib/enums.ts`
3. **Create Alembic migration** for database enum changes
4. **Update all code references** using find/replace or bulk sed commands
5. **Test all three layers** together to ensure consistency

#### Current System Enums Reference
- **Semester**: `first`, `second`, `annual`
- **UserRole**: `student`, `professor`, `college`, `admin`, `super_admin`
- **ApplicationCycle**: `semester`, `yearly`
- **QuotaManagementMode**: `none`, `simple`, `college_based`, `matrix_based`
- **SubTypeSelectionMode**: `single`, `multiple`, `hierarchical`
- **UserType**: `student`, `employee`
- **EmployeeStatus**: `在職`, `退休`, `在學`, `畢業` (Chinese values)

#### Troubleshooting Enum Errors
If you see `LookupError: 'value' is not among the defined enum values`:

1. **Check Python enum member names** match database values exactly
2. **Verify `values_callable` parameter** is set in SQLAlchemy columns
3. **Ensure frontend sends lowercase values** to backend APIs
4. **Use bulk find/replace** to update all code references consistently

```bash
# Example: Fix enum references across codebase
find /path/to/backend -name "*.py" -exec sed -i 's/UserRole\.ADMIN/UserRole.admin/g' {} \;
```

#### Enum Migration Best Practices
- **Never change existing enum values** without migration
- **When removing enum values**, check for existing data first
- **Use database transactions** for enum updates
- **Update all layers simultaneously** to avoid inconsistency

## Implementation Standards

### Frontend Configuration Handling
```typescript
// Use configuration objects instead of hardcoded logic
interface ScholarshipConfig {
  requiresInterview: boolean;
  hasQuotaLimit: boolean;
  allowsMultipleApplications: boolean;
  customFields: Record<string, any>;
}

// Configuration-driven component rendering
function ScholarshipForm({ scholarship }: { scholarship: Scholarship }) {
  const config = scholarship.configuration;

  return (
    <div>
      {config.requiresInterview && <InterviewSection />}
      {config.hasQuotaLimit && <QuotaDisplay quota={scholarship.quota} />}
      {config.allowsMultipleApplications && <MultipleApplicationWarning />}
    </div>
  );
}
```

### Backend Service Layer
```python
class ScholarshipService:
    def get_scholarship_config(self, scholarship_id: int) -> ScholarshipConfiguration:
        """Get scholarship configuration from database"""
        config = self.db.get_scholarship_config(scholarship_id)
        if not config:
            raise ScholarshipConfigNotFoundError(f"Configuration not found for scholarship {scholarship_id}")
        return config

    def validate_application_eligibility(self, student_id: int, scholarship_id: int) -> bool:
        """Validate eligibility based on configuration"""
        config = self.get_scholarship_config(scholarship_id)

        # Use configuration-driven validation
        if config.requires_interview and not self.has_completed_interview(student_id):
            raise EligibilityError("Interview required but not completed")

        if config.has_quota_limit and not self.has_available_quota(scholarship_id):
            raise QuotaExceededError("Scholarship quota exceeded")

        return True
```

## Database Initialization & Migration Standards

### Database Volume Recreation (CRITICAL)
**ALWAYS** use the automated script for clean database rebuilds to avoid initialization errors:

```bash
# Clean database rebuild - removes volume and recreates from scratch
./scripts/reset_database.sh

# Preview steps before execution
./scripts/reset_database.sh --dry-run
```

**Why this is necessary**: The database initialization has specific dependencies and potential conflicts that are automatically handled by this script.

### Alembic Migration Development Rules
**CRITICAL**: Always include existence checks in migrations to prevent conflicts with the initial schema:

```python
# ✅ CORRECT - Check before creating tables
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)

# ✅ CORRECT - Check before adding columns
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = [col['name'] for col in inspector.get_columns('table_name')]

    if 'new_column' not in existing_columns:
        op.add_column('table_name', sa.Column('new_column', ...))

# ❌ WRONG - Direct creation without checks
def upgrade() -> None:
    op.create_table('new_table', ...)  # May fail if table exists
    op.add_column('table_name', ...)   # May fail if column exists
```

### Database Constraint Requirements
**CRITICAL**: Ensure all constraints used in seed scripts exist in SQLAlchemy models:

```python
# ✅ CORRECT - Define constraints in models for seed script ON CONFLICT
class ApplicationField(Base):
    __tablename__ = "application_fields"
    __table_args__ = (
        UniqueConstraint('scholarship_type', 'field_name', name='uq_application_field_type_name'),
    )

    scholarship_type = Column(String(50), nullable=False)
    field_name = Column(String(100), nullable=False)

# Corresponding seed script can safely use:
# ON CONFLICT (scholarship_type, field_name) DO UPDATE SET ...
```

### Migration Testing Checklist
Before creating any migration:
- [ ] Test on fresh database (use `./scripts/reset_database.sh`)
- [ ] Include existence checks for all DDL operations
- [ ] Verify seed scripts work with new constraints
- [ ] Test rollback functionality
- [ ] Check for SQLAlchemy model/migration consistency

## Database Migration Strategy

### Adding New Scholarship Types
1. **Insert into `scholarship_types`** with basic information
2. **Create configuration record** in `scholarship_configurations`
3. **No code changes required** - system uses configuration automatically

```sql
-- Example: Adding new scholarship type
INSERT INTO scholarship_types (code, name, category, academic_year, semester, amount)
VALUES ('new_scholarship', 'New Scholarship Type', 'phd', 113, 'first', 50000);

INSERT INTO scholarship_configurations (
    scholarship_type_id,
    config_code,
    requires_interview,
    has_quota_limit,
    allows_multiple_applications
) VALUES (
    (SELECT id FROM scholarship_types WHERE code = 'new_scholarship'),
    'new_scholarship_config',
    TRUE,
    TRUE,
    FALSE
);
```

## Testing Requirements

### Configuration Testing
```python
def test_scholarship_configuration_driven_logic():
    """Test that scholarship logic is driven by configuration"""
    # Arrange
    scholarship = create_test_scholarship()
    config = ScholarshipConfiguration(
        requires_interview=True,
        has_quota_limit=True,
        allows_multiple_applications=False
    )
    scholarship.configuration = config

    # Act & Assert
    assert scholarship.requires_interview() == True
    assert scholarship.has_quota_limit() == True
    assert scholarship.allows_multiple_applications() == False
```

### Error Handling Testing
```python
def test_no_fallback_data_on_database_error():
    """Test that errors are thrown instead of fallback data"""
    with pytest.raises(ScholarshipNotFoundError):
        service.get_scholarship_data()  # Database returns None
```

## Path Security & Backslash Handling

### Security Validation Standards
**CRITICAL**: Always validate file paths and filenames to prevent path traversal attacks and security vulnerabilities.

#### Path Traversal Prevention
```python
# ✅ CORRECT - Dual validation for file paths
@router.get("/files/bank_documents/{filename}")
async def get_bank_document(filename: str, db: AsyncSession = Depends(get_db)):
    """Serve bank documents from MinIO"""
    # Step 1: Check for path traversal patterns
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="無效的檔案名稱"
        )

    # Step 2: Validate filename contains only allowed characters
    if not re.match(r"^[a-zA-Z0-9_\-\.]+$", filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="檔案名稱包含無效字元"
        )

    # Step 3: Verify resolved path is within expected directory
    resolved_path = os.path.abspath(file_path)
    expected_dir = os.path.abspath(os.path.join(upload_base, bank_docs_dir))
    if not resolved_path.startswith(expected_dir):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="存取被拒絕"
        )

# ❌ WRONG - No validation
@router.get("/files/{filename}")
async def get_file(filename: str):
    file_path = f"uploads/{filename}"  # Vulnerable to path traversal!
    return FileResponse(file_path)
```

#### Backslash Handling Rules
1. **Always reject backslashes** (`\`) in user-provided file paths
2. **Use forward slashes** (`/`) for cross-platform compatibility
3. **Validate before any file system operations**
4. **Use regex pattern matching** for additional security

#### Security Checklist for File Operations
- [ ] Check for `..` (parent directory traversal)
- [ ] Check for `/` (absolute path injection)
- [ ] Check for `\` (Windows path separator)
- [ ] Validate with regex pattern `^[a-zA-Z0-9_\-\.]+$`
- [ ] Verify resolved absolute path is within expected directory
- [ ] Log suspicious access attempts

```python
# Recommended regex patterns for different scenarios
SAFE_FILENAME_PATTERN = r"^[a-zA-Z0-9_\-\.]+$"  # Basic files
SAFE_PATH_PATTERN = r"^[a-zA-Z0-9_\-\./]+$"      # Paths with subdirectories (use with caution)
```

## File Upload & Preview Architecture

### Three-Layer Architecture Overview
The system uses a **MinIO → Next.js Proxy → Frontend** architecture for secure file handling:

```
┌─────────┐      ┌──────────────┐      ┌─────────┐      ┌──────────┐
│ Frontend│─────→│ Next.js API  │─────→│ FastAPI │─────→│  MinIO   │
│  React  │      │    Route     │      │ Backend │      │  Storage │
└─────────┘      └──────────────┘      └─────────┘      └──────────┘
   ↑                    ↑                    ↑                ↑
   │                    │                    │                │
Preview URL        Token Proxy         Object Name      Actual File
```

### Layer 1: Backend (FastAPI + MinIO)

#### File Upload Implementation
```python
@router.post("/{scholarship_type}/upload-terms")
async def upload_terms_document(
    scholarship_type: str,
    file: UploadFile = File(...),
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Upload terms document to MinIO"""
    from app.services.minio_service import minio_service

    # Generate object name (NOT full URL)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    object_name = f"terms/{scholarship_type}_terms_{timestamp}.pdf"

    # Upload to MinIO
    file_content = await file.read()
    minio_service.client.put_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name,
        data=io.BytesIO(file_content),
        length=len(file_content),
        content_type=file.content_type or "application/octet-stream",
    )

    # Store ONLY object_name in database (not full URL)
    scholarship.terms_document_url = object_name
    await db.commit()

    return {"terms_document_url": object_name}
```

#### File Download/Proxy Endpoint
```python
@router.get("/{scholarship_type}/terms")
async def get_terms_document(
    scholarship_type: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proxy download from MinIO"""
    from minio_service import minio_service

    # Get object_name from database
    scholarship = await db.get(ScholarshipType, scholarship_type)
    object_name = scholarship.terms_document_url

    # Download from MinIO
    response = minio_service.client.get_object(
        bucket_name=minio_service.default_bucket,
        object_name=object_name
    )

    file_content = response.read()

    # Return as streaming response
    return StreamingResponse(
        io.BytesIO(file_content),
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename*=UTF-8''{scholarship_type}_terms.pdf"}
    )
```

### Layer 2: Next.js API Route Proxy

**Why proxy through Next.js?**
- Token authentication handling
- Internal Docker network communication
- Simplified CORS management
- Centralized error handling

```typescript
// frontend/app/api/v1/preview-terms/route.ts
export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const scholarshipType = searchParams.get("scholarshipType");
  const token = searchParams.get("token");

  // Use internal Docker network URL for backend communication
  const backendUrl = `${process.env.INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL}/api/v1/scholarships/${scholarshipType}/terms`;

  // Fetch from backend with authentication
  const response = await fetch(backendUrl, {
    method: "GET",
    headers: {
      Authorization: `Bearer ${token}`,
    },
  });

  const fileBuffer = await response.arrayBuffer();
  const contentType = response.headers.get("content-type") || "application/pdf";

  // IMPORTANT: Preserve Content-Disposition from backend (includes filename with Chinese support)
  const contentDisposition = response.headers.get("content-disposition") || "inline";

  // Return file to frontend with complete headers for browser PDF viewer
  return new NextResponse(fileBuffer, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Content-Disposition": contentDisposition,  // ✅ Keep backend's filename info
      "Content-Length": fileBuffer.byteLength.toString(),  // ✅ Required for proper rendering
      "Accept-Ranges": "bytes",  // ✅ Support range requests
      "Cache-Control": "private, max-age=3600", // 1 hour cache
    },
  });
}
```

### Layer 3: Frontend Preview Component

```typescript
// Frontend component usage
const handlePreview = () => {
  const token = localStorage.getItem("auth_token");
  const previewUrl = `/api/v1/preview-terms?scholarshipType=${type}&token=${token}`;

  setTermsPreviewFile({
    url: previewUrl,
    filename: `${formConfig?.title || "獎學金"}_申請條款.pdf`,
    type: "application/pdf",
  });
  setShowTermsPreview(true);
};

// FilePreviewDialog component
<FilePreviewDialog
  isOpen={showTermsPreview}
  onClose={handleCloseTermsPreview}
  file={termsPreviewFile}
  locale="zh"
/>
```

#### FilePreviewDialog Component Features
```typescript
// components/file-preview-dialog.tsx
export function FilePreviewDialog({ isOpen, onClose, file, locale }) {
  // PDF preview using iframe
  {file.type.includes("pdf") && (
    <iframe
      src={file.url}
      className="w-full h-[70vh] border rounded"
      title={file.filename}
    />
  )}

  // Image preview
  {file.type.includes("image") && (
    <img
      src={file.url}
      alt={file.filename}
      className="max-w-full max-h-full object-contain"
    />
  )}

  // Download handler
  const handleDownload = () => {
    const link = document.createElement("a");
    link.href = file.downloadUrl || file.url;
    link.download = file.filename;
    link.click();
  };
}
```

### Key Configuration Requirements

#### Environment Variables
```bash
# Backend .env
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=scholarship-system

# Frontend .env
NEXT_PUBLIC_API_URL=http://localhost:8000
INTERNAL_API_URL=http://backend:8000  # Docker internal network
```

#### Critical Implementation Rules
1. **Store object_name, not full URL** in database
2. **Always use Next.js proxy** for file access (never direct MinIO URLs)
3. **Pass token via query parameter** for authentication in Next.js route
4. **Use INTERNAL_API_URL** for Docker network communication
5. **Set appropriate cache headers** (e.g., `max-age=3600`)

### File Upload Flow Diagram
```
Upload Flow:
1. User selects file → FormData
2. Frontend → Next.js → FastAPI
3. FastAPI → MinIO (put_object)
4. FastAPI → Database (save object_name)

Preview Flow:
1. Frontend constructs URL: /api/v1/preview-terms?scholarshipType=X&token=Y
2. Next.js API Route → FastAPI (with Bearer token)
3. FastAPI → MinIO (get_object)
4. MinIO → FastAPI → Next.js → Frontend (streaming)
```

### Security Considerations
- **Never expose MinIO URLs** directly to frontend
- **Always validate file types** before upload
- **Implement file size limits** (e.g., 10MB max)
- **Use authenticated endpoints** for file access
- **Validate object_name** before MinIO operations
- **Set appropriate bucket policies** (private by default)

```python
# File type validation example
ALLOWED_EXTENSIONS = [".pdf", ".doc", ".docx"]
file_extension = file.filename.lower().split(".")[-1]
if f".{file_extension}" not in ALLOWED_EXTENSIONS:
    raise HTTPException(status_code=400, detail="Invalid file type")
```

### HTTP Headers Best Practices for File Preview

**CRITICAL**: Proper HTTP headers are essential for browser PDF viewers to work correctly. Missing or incomplete headers can cause various issues including "password protected" errors on unprotected PDFs.

#### Required Headers for PDF/Document Preview

When proxying files through Next.js API routes, you **MUST** preserve and include these headers:

1. **Content-Type**
   ```typescript
   "Content-Type": "application/pdf"  // Or appropriate MIME type
   ```
   - Tells browser how to interpret the file
   - Must match actual file type

2. **Content-Disposition** (CRITICAL for Chinese filenames)
   ```typescript
   // ✅ CORRECT - Preserve from backend
   const contentDisposition = response.headers.get("content-disposition") || "inline";

   // Backend sets: "inline; filename*=UTF-8''文件名.pdf"
   // Next.js MUST preserve this complete header
   ```
   - `inline` = display in browser (vs `attachment` = force download)
   - `filename*=UTF-8''...` = RFC 5987 encoding for Unicode filenames
   - **DO NOT** override with just `"inline"` - this loses filename information

3. **Content-Length**
   ```typescript
   "Content-Length": fileBuffer.byteLength.toString()
   ```
   - Browser needs file size for proper rendering
   - Some PDF viewers require this for initialization
   - Missing this can cause "password protected" or loading errors

4. **Accept-Ranges**
   ```typescript
   "Accept-Ranges": "bytes"
   ```
   - Enables partial content requests
   - Required by some browser PDF viewers
   - Improves loading performance for large files

#### Common Issues and Solutions

**Problem**: PDF shows "password protected" error but file has no password
- **Cause**: Missing `Content-Length` or incomplete `Content-Disposition` header
- **Solution**: Include all required headers as shown above

**Problem**: Chinese filenames display as garbled text or get lost
- **Cause**: Overriding backend's `Content-Disposition` with simple `"inline"`
- **Solution**: Preserve complete header from backend response

**Problem**: PDF downloads instead of displaying inline
- **Cause**: Missing `inline` in `Content-Disposition` or wrong `Content-Type`
- **Solution**: Ensure `Content-Disposition: inline` and correct `Content-Type`

#### Implementation Checklist for Next.js Proxy Routes

```typescript
// ✅ COMPLETE implementation
export async function GET(request: NextRequest) {
  // ... fetch from backend ...

  const fileBuffer = await response.arrayBuffer();

  // Get headers from backend response
  const contentType = response.headers.get("content-type") || "application/pdf";
  const contentDisposition = response.headers.get("content-disposition") || "inline";

  return new NextResponse(fileBuffer, {
    status: 200,
    headers: {
      "Content-Type": contentType,                           // ✅ File type
      "Content-Disposition": contentDisposition,             // ✅ Preserve from backend
      "Content-Length": fileBuffer.byteLength.toString(),    // ✅ File size
      "Accept-Ranges": "bytes",                              // ✅ Range support
      "Cache-Control": "private, max-age=3600",              // ✅ Caching
    },
  });
}

// ❌ INCOMPLETE - Will cause issues
return new NextResponse(fileBuffer, {
  headers: {
    "Content-Type": contentType,
    "Content-Disposition": "inline",  // ❌ Loses filename from backend
    // ❌ Missing Content-Length
    // ❌ Missing Accept-Ranges
  },
});
```

#### Backend Header Requirements

Backend endpoints MUST set proper headers that Next.js will preserve:

```python
# FastAPI/StreamingResponse
return StreamingResponse(
    io.BytesIO(file_content),
    media_type="application/pdf",
    headers={
        "Content-Disposition": f"inline; filename*=UTF-8''{filename}.pdf"
    }
)
```

#### Testing Preview Functionality

When implementing or modifying file preview:

1. **Test with Chinese filenames** - Verify filename displays correctly
2. **Test in iframe** - Used by FilePreviewDialog component
3. **Test in new tab** - Direct browser navigation
4. **Test different browsers** - Chrome, Firefox, Safari have different PDF viewers
5. **Check browser console** - Look for MIME type or loading errors
6. **Verify download works** - Alternative to preview should always function

## Code Quality Standards

### Error Messages
- Use descriptive error messages
- Include relevant context (IDs, configuration values)
- Provide actionable information when possible

### Configuration Validation
- Validate all configuration values on load
- Provide clear error messages for invalid configurations
- Use type-safe configuration objects

### Documentation
- Document all configuration fields and their purposes
- Include examples of configuration values
- Maintain up-to-date schema documentation

## Deployment Considerations

### Configuration Management
- Use environment-specific configuration files
- Implement configuration validation on startup
- Provide configuration migration tools

### Monitoring
- Log configuration changes
- Monitor configuration-driven feature usage
- Alert on configuration validation failures

## Debug Panel Control

### Environment Variable Configuration
The Debug Panel can be controlled via the `NEXT_PUBLIC_ENABLE_DEBUG_PANEL` environment variable in docker-compose files.

#### Display Logic
```typescript
// components/debug-panel.tsx
const shouldShow =
  isTestMode ||
  process.env.NEXT_PUBLIC_ENABLE_DEBUG_PANEL === "true" ||
  process.env.NODE_ENV === "development";
```

#### Environment-Specific Configuration

**Development Environment** (docker-compose.dev.yml):
```yaml
frontend:
  environment:
    NEXT_PUBLIC_ENABLE_DEBUG_PANEL: "true"  # Always enabled in dev
```

**Staging Environment** (docker-compose.staging.yml):
```yaml
frontend:
  environment:
    NEXT_PUBLIC_ENABLE_DEBUG_PANEL: "true"  # Enabled for testing
```

**Production Environment** (docker-compose.yml):
```yaml
frontend:
  environment:
    NEXT_PUBLIC_ENABLE_DEBUG_PANEL: "false"  # Disabled in production
```

#### Best Practices
- ✅ Use `NEXT_PUBLIC_` prefix for Next.js environment variables
- ✅ Set to `"true"` (string) for enabling, not boolean
- ✅ Always explicitly set the value in docker-compose files
- ✅ Keep disabled in production for security
- ✅ Enable in staging/test environments for debugging

#### Debug Panel Features
- JWT Token inspection
- Portal SSO data viewer
- Student API data inspector
- Environment detection
- Real-time data refresh
- Copy-to-clipboard functionality

---

**Remember**: The goal is to create a flexible, maintainable system where new scholarship types can be added through database configuration without requiring code changes.
