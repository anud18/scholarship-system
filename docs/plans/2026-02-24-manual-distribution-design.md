# Manual Scholarship Distribution System Design

**Date**: 2026-02-24
**Status**: Approved
**Replaces**: Automated quota-based and matrix-based distribution

## Overview

Replace the existing automated distribution algorithms with a manual distribution UI where the scholarship administrator (承辦人) hand-selects which scholarship sub-type each student receives. The college ranking (學院初審排序) remains as the prerequisite step.

## Requirements

| Requirement | Decision |
|---|---|
| Replaces | Completely replaces existing auto-distribution |
| Checkbox columns | Dynamically generated from `scholarship_configurations.quotas` keys |
| Ranking source | Uses existing `CollegeRankingItem.rank_position` |
| Application identity | New field - system auto-determines (新申請 vs XXX年續領) |
| Quota scope | Per-college independent quotas |
| Selection mode | Single-select per student (one scholarship type only) |
| Operator | Admin/super_admin only |

## Workflow

```
1. Student submits application (submitted)
2. Professor reviews (professor_review) - approve/reject
3. College ranks students (college_ranking) - rank_position per student
4. Admin manual distribution (quota_distribution) ← NEW
   - Admin views students grouped by college
   - Admin checks one scholarship sub-type checkbox per student
   - Real-time quota sidebar shows remaining slots
   - Admin saves selections, then finalizes
5. Payment roster (roster_preparation → completed)
```

## Data Model Changes

### New field on Application
```python
application_identity = Column(String(50), nullable=True)
# e.g., "114新申請", "112續領"
# System-determined based on prior approved applications
```

### Existing fields reused
- `CollegeRankingItem.rank_position` - college ranking order
- `CollegeRankingItem.is_allocated`, `allocated_sub_type` - stores manual allocation
- `CollegeRankingItem.status` - 'ranked' → 'allocated' or 'rejected'
- `CollegeRanking.distribution_executed`, `allocated_count` - tracking
- `ScholarshipConfiguration.quotas` - dynamic checkbox columns + per-college quota limits

### Removed
- `execute_quota_distribution()` in college_review_service.py
- `matrix_distribution.py` entirely
- `QuotaDistribution` model
- Related automated distribution API endpoints

## Backend API

### `GET /api/v1/manual-distribution/students`

Query params: `scholarship_type_id`, `academic_year`, `semester`, `college_code` (optional)

Returns students with:
- `rank_position` (from CollegeRankingItem)
- `applied_sub_types` (what student applied for)
- `allocated_sub_type` (current allocation or null)
- Student info: college, department, grade, name, nationality, enrollment_date, student_id
- `application_identity` (e.g., "112續領")

Sorted by college, then rank_position.

### `GET /api/v1/manual-distribution/quota-status`

Query params: `scholarship_type_id`, `academic_year`, `semester`

Returns per sub-type per college remaining quota:
```json
{
  "nstc_112": {
    "total": 12,
    "allocated": 4,
    "remaining": 8,
    "by_college": {
      "EE": {"total": 3, "allocated": 1, "remaining": 2}
    }
  }
}
```

### `POST /api/v1/manual-distribution/allocate`

Body:
```json
{
  "scholarship_type_id": "...",
  "academic_year": 114,
  "semester": "second",
  "allocations": [
    {"ranking_item_id": "uuid", "sub_type_code": "nstc_112"},
    {"ranking_item_id": "uuid", "sub_type_code": null}
  ]
}
```

Validates:
- Each student gets at most one sub-type (single-select)
- Per-college quota not exceeded
- Admin permission check

### `POST /api/v1/manual-distribution/finalize`

Locks distribution, updates application statuses to approved/rejected, sends notifications.

## Frontend UI

### Layout (4-column grid)
- Left 3/4: Filter bar + main table + pagination
- Right 1/4: Real-time quota sidebar (即時剩餘名額)

### Filter Bar
- 所屬學院 (college dropdown)
- 系所名稱 (department text input)
- 學生姓名/學號 (search input)

### Main Table Columns
| Column | Source |
|---|---|
| 學院初審排序 | CollegeRankingItem.rank_position |
| 申請獎學金類別 | Applied sub-types list |
| 獲獎獎學金類別 (N radio-like checkboxes) | Dynamic from quotas keys |
| 學院 | student_data.trm_academyname |
| 系所 | student_data.trm_depname |
| 年級 | student_data grade info |
| 學生中文姓名 | student_data.std_cname |
| 國籍 | student_data nationality |
| 註冊入學日期(民國年.月.日) | student_data enrollment date |
| 學號 | student_data.std_stdcode |
| 申請身份 | application_identity |

### Key UI Behaviors
1. **Radio-like checkboxes**: Checking one auto-unchecks others in same row (single-select)
2. **Real-time quota**: Sidebar updates immediately on check/uncheck (optimistic UI)
3. **Quota exceeded prevention**: Disable checkbox if that sub-type's college quota is full
4. **Save button**: Batch-saves all selections
5. **Finalize button**: Locks distribution, updates application statuses
6. **Dynamic columns**: Generated from quotas keys, display names from ScholarshipSubTypeConfig

### New Files
- `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

## Cleanup

### Files/code to remove
- `backend/app/services/matrix_distribution.py`
- `execute_quota_distribution()` in `college_review_service.py`
- `QuotaDistribution` model in `college_review.py`
- Automated distribution API endpoints in `distribution.py`
- Related frontend components for automated distribution results

### Database migration
- Add `application_identity` column to `applications` table
- Remove `quota_distributions` table (or keep for historical data)
