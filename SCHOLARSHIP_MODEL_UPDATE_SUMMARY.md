# Scholarship Model Update Summary

## Overview
Successfully implemented the scholarship model updates according to the proposal to enhance the `ScholarshipType` model with academic year/semester support, application cycle types, distinct review periods, and sub-type selection modes.

## Changes Made

### 1. Model Updates (`backend/app/models/scholarship.py`)

#### New Enums Added:
- `Semester`: FIRST, SECOND
- `CycleType`: SEMESTER, YEARLY  
- `SubTypeSelectionMode`: SINGLE, MULTIPLE, HIERARCHICAL

#### New Fields Added to ScholarshipType:
- `academic_year`: Integer (民國年，如 113 表示 113 學年度)
- `semester`: Enum(Semester) (學期)
- `application_cycle`: Enum(CycleType) (申請週期)
- `professor_review_start/end`: DateTime (教授審查起訖時間)
- `college_review_start/end`: DateTime (學院審查起訖時間)
- `sub_type_selection_mode`: Enum(SubTypeSelectionMode) (子項目選擇模式)

#### New Methods Added:
- `academic_year_label`: Property for display (e.g., "113學年度 第一學期")
- `get_semester_label()`: Get semester label in Chinese
- `is_valid_sub_type_selection()`: Validate sub-type selection based on mode
- `get_semester_key()`: Get unique semester identifier for limit checking
- `can_student_apply()`: Check if student can apply based on semester limits

### 2. Schema Updates (`backend/app/schemas/scholarship.py`)

#### New Enums Added:
- `SemesterEnum`: FIRST, SECOND
- `CycleTypeEnum`: SEMESTER, YEARLY
- `SubTypeSelectionModeEnum`: SINGLE, MULTIPLE, HIERARCHICAL

#### Updated Schemas:
- `ScholarshipTypeBase`: Added all new fields
- `ScholarshipTypeUpdate`: Added optional new fields
- `EligibleScholarshipResponse`: Added new fields for API responses

#### New Validators Added:
- `validate_academic_year()`: Ensures year is between 100-200 (民國年)
- `validate_professor_review_period()`: Ensures end > start
- `validate_college_review_period()`: Ensures end > start

### 3. Database Migration (`backend/alembic/versions/add_scholarship_model_updates.py`)

#### Migration Features:
- Creates new enum types in PostgreSQL
- Adds all new columns to `scholarship_types` table
- Sets default values for existing records (113學年度, first semester, semester cycle, single selection)
- Makes required fields not nullable after setting defaults
- Includes proper downgrade functionality

### 4. Initialization Updates (`backend/app/core/init_db.py`)

#### Updated Scholarship Creation:
- Added new required fields to all test scholarships
- Set academic_year to 113 (民國113年)
- Set semester to FIRST for all scholarships
- Set application_cycle to SEMESTER
- Added review period calculations (professor: +7/+14 days, college: +14/+21 days)
- Set sub_type_selection_mode appropriately (SINGLE for most, MULTIPLE for PhD)
- **Removed `max_applications_per_year`** from all scholarship configurations

### 5. Test Updates

#### New Test File (`backend/app/tests/test_scholarship_model_updates.py`):
- Tests scholarship creation with new fields
- Tests academic_year_label property
- Tests sub-type selection validation for all modes
- Tests semester key generation and application limit checking
- Comprehensive validation of new functionality

#### Updated Existing Tests:
- Updated imports in `test_combined_scholarship.py` to include new enums

### 6. Schema Exports (`backend/app/schemas/__init__.py`)

#### Added Exports:
- `SemesterEnum`, `CycleTypeEnum`, `SubTypeSelectionModeEnum`

## Key Features Implemented

### 1. Academic Year and Semester Support
- Uses ROC calendar format (民國年)
- Supports first and second semesters
- Provides display labels in Chinese
- **Semester-based application limits**: One application per student per semester

### 2. Application Cycle Types
- Semester-based applications
- Yearly applications
- Extensible for future cycle types

### 3. Distinct Review Periods
- Separate professor review periods
- Separate college review periods
- Validation ensures logical time ordering
- All DateTime fields use UTC timezone

### 4. Sub-Type Selection Modes
- **SINGLE**: Only one sub-type can be selected
- **MULTIPLE**: Free selection of multiple sub-types
- **HIERARCHICAL**: Sequential selection (A → AB → ABC)
- Validation logic for each mode

### 5. Application Limit Management
- **Removed `max_applications_per_year`**: No longer needed
- **Semester-based limits**: Students can only apply once per scholarship per semester
- **New methods**: `get_semester_key()` and `can_student_apply()` for limit checking

## Database Schema Changes

### New Columns in `scholarship_types`:
```sql
academic_year INTEGER NOT NULL,
semester semester NOT NULL,
application_cycle cycletype NOT NULL,
professor_review_start TIMESTAMP WITH TIME ZONE,
professor_review_end TIMESTAMP WITH TIME ZONE,
college_review_start TIMESTAMP WITH TIME ZONE,
college_review_end TIMESTAMP WITH TIME ZONE,
sub_type_selection_mode subtypeselectionmode NOT NULL,
```

### Removed Columns:
```sql
-- max_applications_per_year INTEGER (removed - replaced by semester-based limits)
```

### New Enum Types:
```sql
CREATE TYPE semester AS ENUM ('first', 'second');
CREATE TYPE cycletype AS ENUM ('semester', 'yearly');
CREATE TYPE subtypeselectionmode AS ENUM ('single', 'multiple', 'hierarchical');
```

## Backward Compatibility

- All existing scholarships will be updated with default values
- No breaking changes to existing API endpoints
- New fields are optional in update operations
- Existing functionality remains intact

## Testing

### Manual Testing Required:
1. Run database migration: `alembic upgrade head`
2. Test scholarship creation with new fields
3. Test sub-type selection validation
4. Test academic year label display
5. Verify review period validation

### Automated Tests:
- New test file covers all new functionality
- Existing tests updated for compatibility
- Schema validation tests included

## Next Steps

1. **Frontend Updates**: Update frontend components to use new fields
2. **API Documentation**: Update API docs to reflect new fields
3. **Admin Interface**: Update admin interface for new field management
4. **Validation Logic**: Implement business logic for review period enforcement
5. **Reporting**: Add reporting features for academic year/semester analysis

## Files Modified

1. `backend/app/models/scholarship.py` - Model updates
2. `backend/app/schemas/scholarship.py` - Schema updates  
3. `backend/app/core/init_db.py` - Initialization updates
4. `backend/app/schemas/__init__.py` - Export updates
5. `backend/app/tests/test_combined_scholarship.py` - Test updates
6. `backend/app/tests/test_scholarship_model_updates.py` - New tests
7. `backend/alembic/versions/add_scholarship_model_updates.py` - Migration

## Migration Instructions

1. Run the migration: `alembic upgrade head`
2. Verify existing scholarships have correct default values
3. Test new functionality with the provided test suite
4. Update any custom code that creates scholarships to include new required fields
5. **Note**: The migration will remove `max_applications_per_year` column and replace it with semester-based limits 