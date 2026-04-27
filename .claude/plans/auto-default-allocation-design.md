# Auto-Default Allocation for Manual Distribution

**Date:** 2026-03-16
**Status:** Draft (rev 2 — post-review)
**Feature:** Automatic pre-filling of allocation checkboxes when entering the manual distribution page

## Problem

After college ranking is finalized, admins enter the manual distribution page and must manually check every student's allocation one by one. This is tedious and error-prone, especially when the allocation logic follows predictable rules based on student identity (renewal vs. new application) and sub-type preferences.

## Solution Overview

Add an auto-default allocation mechanism that pre-fills allocation suggestions when the distribution page loads. The system determines each student's allocation based on:

1. **Renewal priority** — renewal students are allocated before new applicants
2. **Student preferences** — students rank sub-types by preference during application
3. **Year determination** — renewal students target their previous allocation year; new applicants target the current year
4. **Fallback logic** — if the target year's quota is exhausted, fall back to the current year

Admins retain full control to modify any allocation before saving.

## Data Model Changes

### Application model — new field

```python
sub_type_preferences = Column(JSON, nullable=True)
# Format: ["nstc", "moe_1w"] (ordered by preference, index 0 = first choice)
```

**Default when null/empty:** Derived from `ScholarshipSubTypeConfig` records (active, sorted by `display_order`). NOT hardcoded.

**Relationship with `scholarship_subtype_list`:** The existing `scholarship_subtype_list` stores which sub-types the student selected (unordered set). The new `sub_type_preferences` stores the same sub-types but **ordered by preference**. On submission, `sub_type_preferences` must be a permutation of `scholarship_subtype_list`.

**Validation rules:**
- Values must be valid active sub-type codes for the scholarship
- Must be a permutation of the student's `scholarship_subtype_list`
- No duplicates
- Empty list treated as null (use config-driven defaults)

**Migration:** Alembic migration to add `sub_type_preferences` column to `applications` table.

## Backend: Auto-Allocate Preview API

### Endpoint

```
GET /api/v1/manual-distribution/auto-allocate-preview
```

**Parameters:** Same as `/students` — `scholarship_type_id`, `academic_year`, `semester`

**Idempotent:** This endpoint is stateless and can be called at any time. After a partial save, re-calling it accounts for newly saved allocations since it reads current quota state from the database.

**Response:**
```json
{
  "success": true,
  "message": "Auto-allocation preview generated",
  "data": {
    "suggestions": [
      {"ranking_item_id": 1, "sub_type_code": "nstc", "allocation_year": 114},
      {"ranking_item_id": 2, "sub_type_code": "moe_1w", "allocation_year": 114},
      {"ranking_item_id": 3, "sub_type_code": null, "allocation_year": null}
    ]
  }
}
```

### Algorithm

**Implementation location:** New method `auto_allocate_preview()` in `ManualDistributionService`.

#### Step 0: Initialize quota tracker

Build an in-memory quota tracker: `Dict[Tuple[sub_type, year, college_code], int]`

1. Load `ScholarshipConfiguration.quotas` for the current year — structure: `{"nstc": {"A": 12, "B": 8}, "moe_1w": {"A": 8}}`
2. Load `prior_quota_years` to determine available prior years per sub-type
3. For each `(sub_type, year, college_code)` combination, set initial remaining = configured quota
4. **Subtract existing allocations:** Query all `CollegeRankingItem` records that already have `allocated_sub_type` and `allocation_year` set, decrement the corresponding bucket

#### Step 1: Load data

- Fetch all ranked students across all `CollegeRanking` records for this (scholarship_type, academic_year, semester)
  - Note: Each `CollegeRanking` has a `sub_type_code`, but a student may appear in multiple rankings. Deduplicate by `application_id` — each student gets one suggestion.
- Eagerly load each student's Application to access `is_renewal`, `previous_application_id`, `sub_type_preferences`, `scholarship_subtype_list`
- For renewal students, **batch-load** their previous application's `CollegeRankingItem` records to obtain the prior `allocation_year`. Query path: `Application.previous_application_id` → `CollegeRankingItem.application_id` → `CollegeRankingItem.allocation_year`
- Load active `ScholarshipSubTypeConfig` records sorted by `display_order` (for default preference fallback)

#### Step 2: Sort students

Sort all students in a single global list (NOT grouped by college):

1. Renewal students (`is_renewal=True`) first
2. New applicants (`is_renewal=False`) second
3. Within each group, sort by `rank_position` ascending

Per-college quota constraints are enforced during allocation (Step 3), not via grouping. This preserves cross-college fairness — a student ranked #1 globally is processed before a student ranked #5, regardless of college.

#### Step 3: Allocate sequentially

For each student in sorted order:

```
# Skip students who already have a saved allocation
if student.allocated_sub_type is not null:
    continue

# Determine target year
if is_renewal and previous_allocation_year is not null:
    target_year = previous_allocation_year
else:
    target_year = academic_year  # current year

# Get preferences (config-driven default if null)
preferences = student.sub_type_preferences
    or [stc.sub_type_code for stc in active_sub_type_configs_sorted_by_display_order]

# Determine student's college from student_data
college = student_data["std_academyno"]

for sub_type in preferences:
    # Verify this year is available for this sub-type
    if target_year != academic_year and target_year not in prior_quota_years.get(sub_type, []):
        # Prior year not configured for this sub-type, skip to fallback
        pass
    elif quota_remaining(sub_type, target_year, college) > 0:
        allocate(student, sub_type, target_year)
        decrement quota(sub_type, target_year, college)
        break

    # Fallback: if renewal and target_year != current year, try current year
    if is_renewal and target_year != academic_year:
        if quota_remaining(sub_type, academic_year, college) > 0:
            allocate(student, sub_type, academic_year)
            decrement quota(sub_type, academic_year, college)
            break

# If no allocation possible → suggestion is (null, null)
```

**Key behaviors:**
- Quota tracking is in-memory during preview calculation (not persisted)
- Each allocation decrements the correct `(sub_type, year, college_code)` bucket immediately
- Preview results are NOT written to database — only returned as suggestions
- Students with existing saved allocations are skipped (their quota is already subtracted in Step 0)

#### Step 4: Return suggestions

Return a list of `{ranking_item_id, sub_type_code, allocation_year}` for every unallocated ranked student. Students with existing allocations are excluded from the list (frontend already has their state). Unallocatable students have null values.

## Frontend: Distribution Page Integration

### Page load flow

```
1. GET /students              → student list (includes existing allocations)
2. GET /quota-status           → quota data
3. GET /auto-allocate-preview  → suggested allocations for unallocated students
4. Apply suggestions to UI state
```

Calls 1-3 can be made in parallel.

### Application logic

- For each student in the suggestion list:
  - If student already has a saved allocation (`allocated_sub_type` is not null from `/students`), **skip** — preserve existing allocation
  - Otherwise, apply the suggested `sub_type_code` and `allocation_year` to the checkbox state
- Display a notice above the table: "已自動預設分配，請確認後儲存"
- Admin can freely modify any checkbox before saving
- Save flow remains unchanged (POST `/allocate`)

## Frontend: Application Form — Preference UI

### Display conditions

- Show preference UI only when the scholarship has **2+ active sub-types** (from `ScholarshipSubTypeConfig`)
- If only 1 active sub-type: auto-set `sub_type_preferences` to that single type, no UI shown

### UI component

- List of available sub-types with display names (from `ScholarshipSubTypeConfig`)
- Up/down arrow buttons to reorder (simple and accessible)
- Saved to `Application.sub_type_preferences` on form submission

### Data flow

```
1. GET scholarship sub-type configs → available sub-types
2. Student reorders → local state ["nstc", "moe_1w"]
3. POST application submit → sub_type_preferences saved in Application record
```

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Renewal student's previous application has no `allocation_year` | Treat as new applicant (use current year) |
| All quotas exhausted for a student | Leave allocation as null (admin decides) |
| Student's preference contains sub-type not in current config | Skip that preference, try next in list |
| Prior year quota not configured in `prior_quota_years` for a sub-type | Skip that year for that sub-type, try current year |
| Distribution page reloaded after partial save | Saved allocations preserved, preview only fills empty slots |
| Student appears in multiple CollegeRanking records | Deduplicate by application_id; use lowest rank_position |
| `sub_type_preferences` is null (legacy applications) | Use config-driven default order from ScholarshipSubTypeConfig.display_order |

## Files to Modify

| Component | File | Change |
|-----------|------|--------|
| Application model | `backend/app/models/application.py` | Add `sub_type_preferences` column |
| Migration | `backend/alembic/versions/` | New migration for column addition |
| Distribution service | `backend/app/services/manual_distribution_service.py` | Add `auto_allocate_preview()` method; extend student query to include `is_renewal`, `previous_application_id` |
| Distribution API | `backend/app/api/v1/endpoints/manual_distribution.py` | Add `/auto-allocate-preview` endpoint |
| Application schemas | `backend/app/schemas/application.py` | Add `sub_type_preferences` to relevant schemas |
| Frontend panel | `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx` | Call preview API on load, apply suggestions to checkbox state |
| Frontend API module | `frontend/lib/api/modules/manual-distribution.ts` | Add `getAutoAllocatePreview()` function |
| Application form | `frontend/components/student/` | Add preference ordering UI (up/down arrows) |
| Application API | Frontend application submission | Include `sub_type_preferences` in payload |

## Not In Scope

- Auto-save or auto-finalize — admin must explicitly save and finalize
- Quota modification — quotas are managed separately in scholarship configuration
- Historical migration of existing applications' preferences — existing apps will have null preferences (use config-driven default order)
- Drag-and-drop reordering — start with up/down arrows for simplicity
