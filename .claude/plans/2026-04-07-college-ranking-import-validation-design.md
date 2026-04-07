# College Ranking Import Validation & Template Sorting

**Date:** 2026-04-07
**Status:** Draft
**Scope:** Enhancement to existing college ranking import feature

## Problem

The existing college ranking import (`POST /rankings/{ranking_id}/import-excel`) lacks validation logic and the template download generates unsorted data. Specifically:

1. Template download has no sort order — colleges need it sorted by department code then student ID
2. No duplicate rank check — two students can share rank 3
3. No consecutive rank check — ranks can jump from 2 to 5
4. No strict student matching — missing/extra students are silently ignored
5. No "reject" mechanism — colleges cannot indicate a student is rejected via the import

## Requirements

### Template Download Sorting
- Sort rows by department code (`std_depno` or equivalent) ascending, then by student ID (`std_stdcode`) ascending
- Add a read-only `系所` column for reference

### Rank Value Rules
- Each row's rank must be a **positive integer** (≥ 1) or the letter **"N"** (case-insensitive)
- Empty rank values are invalid
- Integer ranks **must not repeat**
- "N" (reject) **may repeat**
- After removing all "N" entries, the remaining integer ranks must form a consecutive sequence starting from 1 (i.e., 1, 2, 3, ..., k with no gaps)

### Strict Student Matching
- The set of student IDs in the Excel file must exactly match the set of student IDs in the ranking
- Extra student IDs in Excel → error listing the extras
- Missing student IDs in Excel → error listing the missing ones

### Handling Rank "N"
- When a student's rank is "N", their `CollegeRankingItem`:
  - `rank_position` = `NULL`
  - `status` = `'rejected'`

## Architecture

### Validation — Dual Layer

**Frontend** (`college-ranking-table.tsx` → `handleFileUpload`):
After parsing the Excel file, before calling the API:

1. Every row must have a non-empty rank value
2. Rank value must be a positive integer or "N"/"n"
3. Integer ranks must not have duplicates
4. Integer ranks must be consecutive from 1

Error messages (Traditional Chinese):
- `"第 {row} 行排名欄位為空"`
- `"第 {row} 行排名格式無效：'{value}'"`
- `"排名 {rank} 重複出現（第 {rows} 行）"`
- `"排名不連續：缺少第 {missing} 名"`

**Backend** (`ranking_management.py` → `import-excel` endpoint):
Re-validates everything the frontend checks (defense in depth), plus:

5. Strict student ID matching (Excel set == ranking set)

Error messages:
- `"以下學號不在申請清單中：{ids}"`
- `"以下學號未包含在匯入檔案中：{ids}"`
- `"排名 {rank} 重複"`
- `"排名不連續：缺少第 {missing} 名"`
- `"排名格式無效：'{value}'（學號：{student_id}）"`

### Schema Change

`RankingImportItem` in `backend/app/schemas/college_review.py`:

```python
class RankingImportItem(BaseModel):
    student_id: str = Field(..., description="Student ID (學號)")
    student_name: str = Field(..., description="Student name (姓名)")
    rank_position: Union[int, str] = Field(..., description="Ranking position (排名), integer >= 1 or 'N' for rejected")

    @field_validator('rank_position')
    @classmethod
    def validate_rank(cls, v):
        if isinstance(v, str):
            if v.upper() != 'N':
                raise ValueError(f"排名格式無效：'{v}'，只接受正整數或 'N'")
            return 'N'
        if isinstance(v, int) and v >= 1:
            return v
        raise ValueError(f"排名格式無效：'{v}'")
```

### Backend Import Logic Change

In `ranking_management.py`, the import endpoint:

1. Parse all import items
2. Validate format (via Pydantic schema)
3. Collect student IDs from import data and from ranking items
4. Compare sets — error if mismatch
5. Validate rank sequence:
   - Collect all integer ranks
   - Check no duplicates
   - Check consecutive from 1 to len(integer_ranks)
6. Apply updates:
   - Integer rank → `rank_position = value`, `status = 'ranked'`
   - "N" → `rank_position = NULL`, `status = 'rejected'`

### Frontend Template Download Change

In `college-ranking-table.tsx`, the `handleTemplateDownload` function:

1. Sort `applications` by:
   - Primary: department code from `student_data` (e.g., `std_depno` or `trm_depname`) ascending
   - Secondary: student ID (`std_stdcode`) ascending
2. Add `系所` column (read-only reference)
3. Output columns: `學號`, `姓名`, `系所`, `排名`

### Frontend Upload Parsing Change

In `college-ranking-table.tsx`, the `handleFileUpload` function:

1. Accept "N"/"n" in rank column (currently filters to `rank_position > 0` only)
2. Run validation checks before calling `onImportExcel()`
3. On validation failure, show error dialog/toast with all errors listed
4. Map "N" to string "N" in the import data sent to backend

## Files to Modify

| File | Change |
|------|--------|
| `backend/app/schemas/college_review.py` | `RankingImportItem.rank_position` → `Union[int, str]` with validator |
| `backend/app/api/v1/endpoints/college_review/ranking_management.py` | Add validation logic in import endpoint |
| `frontend/components/college-ranking-table.tsx` | Template sort, upload validation, "N" support |

## Out of Scope

- Changes to ManualDistributionPanel (it reads existing CollegeRankingItem data)
- Changes to CollegeRanking/CollegeRankingItem models (rank_position already nullable, status already supports 'rejected')
- New API endpoints
- Database migrations
