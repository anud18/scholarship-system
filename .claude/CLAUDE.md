# Scholarship System Development Guidelines

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
