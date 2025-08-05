# Application Service Update Guide

## Changes Required

### 1. Remove all student_id references
- Replace `student_id` parameters with `student_code` (user's nycu_id)
- Remove `student_id` from response objects
- Update database queries to not use Student table

### 2. Update function signatures
- `create_application`: Remove `student_id`, add `student_code`
- `_validate_student_eligibility`: Change `student: Student` to `student_data: Dict[str, Any]`
- Update all internal methods accordingly

### 3. Update response serialization
- Remove `student_id` from ApplicationResponse
- Ensure `student_data` JSON field is properly returned
- Update all places that construct response objects

### 4. Update whitelist logic
- Change from student_id based whitelist to user_id based
- Update `is_student_in_whitelist` to `is_user_in_whitelist`
- Modify scholarship model if needed

### 5. Key replacements needed:
```python
# Old
Application.student_id == student.id
# New
Application.user_id == user.id

# Old
student_id=application.student_id
# New
# Remove this field from responses

# Old
stmt = select(Student).where(Student.id == student_id)
# New
student_data = await self.student_service.get_student_snapshot(student_code)
```

## Testing Notes
- Test application creation without student_id
- Verify student data is fetched from API
- Check whitelist functionality with user_id
- Ensure all endpoints work correctly