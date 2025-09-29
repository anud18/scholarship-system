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

---

**Remember**: The goal is to create a flexible, maintainable system where new scholarship types can be added through database configuration without requiring code changes.
