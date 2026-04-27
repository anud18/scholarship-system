# Auto-Default Allocation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Auto-fill allocation suggestions when entering the manual distribution page, based on renewal priority, student sub-type preferences, and year-based quota logic.

**Architecture:** New `sub_type_preferences` field on Application model stores student preference ordering. New backend endpoint `/auto-allocate-preview` runs the allocation algorithm in-memory and returns suggestions. Frontend applies suggestions to checkbox state on page load.

**Tech Stack:** FastAPI (async), SQLAlchemy, Alembic, Next.js/React/TypeScript

**Spec:** `.claude/plans/auto-default-allocation-design.md`

---

## Chunk 1: Backend Data Model & Migration

### Task 1: Add `sub_type_preferences` column to Application model

**Files:**
- Modify: `backend/app/models/application.py`
- Create: `backend/alembic/versions/add_sub_type_preferences_001.py`

- [ ] **Step 1: Add column to Application model**

In `backend/app/models/application.py`, after `scholarship_subtype_list` (line 86), add:

```python
sub_type_preferences = Column(JSON, nullable=True)  # Ordered preference list: ["nstc", "moe_1w"]
```

- [ ] **Step 2: Create Alembic migration**

Create `backend/alembic/versions/add_sub_type_preferences_001.py`:

```python
"""Add sub_type_preferences to applications table

Revision ID: add_sub_type_prefs_001
Revises: add_roster_item_dist_001
Create Date: 2026-03-16
"""

from alembic import op
import sqlalchemy as sa

revision = "add_sub_type_prefs_001"
down_revision = "add_roster_item_dist_001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]

    if "sub_type_preferences" not in columns:
        op.add_column(
            "applications",
            sa.Column("sub_type_preferences", sa.JSON, nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c["name"] for c in inspector.get_columns("applications")]

    if "sub_type_preferences" in columns:
        op.drop_column("applications", "sub_type_preferences")
```

- [ ] **Step 3: Test migration**

Run:
```bash
docker compose -f docker-compose.dev.yml exec backend alembic upgrade head
```
Expected: Migration applies without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/app/models/application.py backend/alembic/versions/add_sub_type_preferences_001.py
git commit -m "feat: add sub_type_preferences column to applications table"
```

### Task 2: Update Application schemas with validation

**Files:**
- Modify: `backend/app/schemas/application.py`

- [ ] **Step 1: Add `sub_type_preferences` to ApplicationCreate with validator**

In `backend/app/schemas/application.py`, in `ApplicationCreate` class (around line 177), add the field and a validator:

```python
sub_type_preferences: Optional[List[str]] = Field(None, description="Ordered sub-type preference list")

@field_validator("sub_type_preferences")
@classmethod
def validate_sub_type_preferences(cls, v):
    if v is None:
        return v
    if len(v) == 0:
        return None  # Empty list treated as null
    if len(v) != len(set(v)):
        raise ValueError("sub_type_preferences must not contain duplicates")
    return v
```

Ensure `field_validator` is imported from `pydantic`. Check existing imports at the top of the file.

- [ ] **Step 2: Add `sub_type_preferences` to ApplicationUpdate**

In `ApplicationUpdate` class (around line 217), add:

```python
sub_type_preferences: Optional[List[str]] = Field(None, description="Ordered sub-type preference list")
```

- [ ] **Step 3: Add `sub_type_preferences` to ApplicationResponse**

In `ApplicationResponse` class (around line 279), add:

```python
sub_type_preferences: Optional[List[str]] = Field(None, description="Ordered sub-type preference list")
```

- [ ] **Step 4: Verify backend starts without errors**

Run:
```bash
docker compose -f docker-compose.dev.yml restart backend
docker compose -f docker-compose.dev.yml logs backend --tail=20
```
Expected: No import or startup errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/application.py
git commit -m "feat: add sub_type_preferences to application schemas with validation"
```

---

## Chunk 2: Backend Auto-Allocate Preview Endpoint

### Task 3: Implement `auto_allocate_preview()` in ManualDistributionService

**Files:**
- Modify: `backend/app/services/manual_distribution_service.py`

- [ ] **Step 1: Add helper method to get default preferences from config**

Add this method to `ManualDistributionService`:

```python
async def _get_default_preferences(self, scholarship_type_id: int) -> list[str]:
    """Get default sub-type preference order from ScholarshipSubTypeConfig.display_order."""
    query = (
        select(ScholarshipSubTypeConfig)
        .where(
            and_(
                ScholarshipSubTypeConfig.scholarship_type_id == scholarship_type_id,
                ScholarshipSubTypeConfig.is_active == True,
            )
        )
        .order_by(ScholarshipSubTypeConfig.display_order)
    )
    result = await self.db.execute(query)
    configs = result.scalars().all()
    return [c.sub_type_code for c in configs]
```

- [ ] **Step 2: Add helper method to batch-load previous allocation years for renewal students**

```python
async def _batch_load_previous_allocation_years(
    self, previous_app_ids: list[int]
) -> dict[int, Optional[int]]:
    """For renewal students, load their previous application's allocation_year.
    Query path: previous_application_id -> CollegeRankingItem.application_id -> allocation_year
    Returns: {previous_application_id: allocation_year}
    """
    if not previous_app_ids:
        return {}

    query = (
        select(
            CollegeRankingItem.application_id,
            CollegeRankingItem.allocation_year,
        )
        .where(
            and_(
                CollegeRankingItem.application_id.in_(previous_app_ids),
                CollegeRankingItem.allocation_year.isnot(None),
            )
        )
    )
    result = await self.db.execute(query)
    rows = result.all()
    return {row.application_id: row.allocation_year for row in rows}
```

- [ ] **Step 3: Add the `auto_allocate_preview()` method**

This method reuses the existing `_load_config()` helper (line 330) for loading ScholarshipConfiguration. It loads prior-year configs with their actual quota values (not assuming they equal current-year quotas).

```python
async def auto_allocate_preview(
    self,
    scholarship_type_id: int,
    academic_year: int,
    semester: str,
) -> list[dict[str, Any]]:
    """Generate auto-allocation suggestions without persisting.

    Algorithm:
    1. Load ranked students, quota status, and preferences
    2. Sort: renewal first, then by rank_position (global order)
    3. For each student, try preferences in order with year/college quota logic
    4. Return suggestions (not persisted)
    """
    # --- Step 0: Load data ---
    ranking_query = select(CollegeRanking).where(
        and_(
            CollegeRanking.scholarship_type_id == scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
            _ranking_semester_condition(semester),
            CollegeRanking.is_finalized == True,
        )
    )
    result = await self.db.execute(ranking_query)
    rankings = result.scalars().all()
    if not rankings:
        return []

    ranking_ids = [r.id for r in rankings]

    items_query = (
        select(CollegeRankingItem)
        .options(selectinload(CollegeRankingItem.application))
        .where(CollegeRankingItem.ranking_id.in_(ranking_ids))
    )
    result = await self.db.execute(items_query)
    items = result.scalars().all()

    # Deduplicate by application_id (student may appear in multiple rankings).
    # Keep any one item — we only need ranking_item_id for the suggestion response.
    seen_apps: dict[int, CollegeRankingItem] = {}
    for item in items:
        if not item.application:
            continue
        app_id = item.application_id
        if app_id not in seen_apps:
            seen_apps[app_id] = item

    unique_items = list(seen_apps.values())

    # Get default preferences from config (display_order)
    default_prefs = await self._get_default_preferences(scholarship_type_id)

    # Batch-load previous allocation years for renewal students
    previous_app_ids = [
        item.application.previous_application_id
        for item in unique_items
        if item.application.is_renewal and item.application.previous_application_id
    ]
    prev_alloc_years = await self._batch_load_previous_allocation_years(previous_app_ids)

    # --- Load configs for current year + all prior years ---
    current_config = await self._load_config(scholarship_type_id, academic_year, semester)

    prior_years_map: dict[str, list[int]] = {}
    if current_config and current_config.prior_quota_years:
        raw = current_config.prior_quota_years
        if isinstance(raw, str):
            import json as _json
            try:
                raw = _json.loads(raw)
            except (ValueError, TypeError):
                raw = {}
        if isinstance(raw, dict):
            prior_years_map = raw

    # Collect all years we need configs for
    all_prior_years: set[int] = set()
    for years_list in prior_years_map.values():
        if isinstance(years_list, list):
            all_prior_years.update(years_list)
    years_to_check = sorted([academic_year] + list(all_prior_years), reverse=True)

    # Load configs for all years in a single query
    configs_by_year: dict[int, Optional[ScholarshipConfiguration]] = {}
    if years_to_check:
        configs_stmt = (
            select(ScholarshipConfiguration)
            .where(
                and_(
                    ScholarshipConfiguration.scholarship_type_id == scholarship_type_id,
                    ScholarshipConfiguration.academic_year.in_(years_to_check),
                    _config_semester_condition(semester),
                )
            )
            .order_by(ScholarshipConfiguration.id.desc())
        )
        configs_result = await self.db.execute(configs_stmt)
        for cfg in configs_result.scalars().all():
            if cfg.academic_year not in configs_by_year:
                configs_by_year[cfg.academic_year] = cfg

    # --- Step 0b: Initialize in-memory quota tracker ---
    # Structure: {(sub_type, year, college_code): remaining}
    quota_tracker: dict[tuple[str, int, str], int] = {}

    for year in years_to_check:
        cfg = configs_by_year.get(year)
        if not cfg:
            continue
        quotas_raw = cfg.quotas
        if isinstance(quotas_raw, str):
            import json as _json
            try:
                quotas_raw = _json.loads(quotas_raw)
            except (ValueError, TypeError):
                quotas_raw = {}

        for sub_type, college_quotas in (quotas_raw or {}).items():
            # Only include this sub_type for this year if:
            # - It's the current year, OR
            # - This year is in prior_quota_years for this sub_type
            if year != academic_year and year not in prior_years_map.get(sub_type, []):
                continue
            for college_code, total in college_quotas.items():
                quota_tracker[(sub_type, year, college_code)] = total

    # Subtract existing allocations
    for item in items:
        if item.allocated_sub_type and item.allocation_year:
            app = item.application
            if app:
                college = (app.student_data or {}).get("std_academyno", "")
                key = (item.allocated_sub_type, item.allocation_year, college)
                if key in quota_tracker:
                    quota_tracker[key] = max(0, quota_tracker[key] - 1)

    # --- Step 2: Sort students ---
    # Global order: renewal first, then by rank_position ascending.
    # Per-college quota constraints are enforced during allocation, not via grouping.
    def sort_key(item: CollegeRankingItem):
        app = item.application
        is_renewal = app.is_renewal if app else False
        return (0 if is_renewal else 1, item.rank_position)

    unique_items.sort(key=sort_key)

    # --- Step 3: Allocate sequentially ---
    suggestions = []
    for item in unique_items:
        app = item.application

        # Skip already allocated
        if item.allocated_sub_type is not None:
            continue

        college = (app.student_data or {}).get("std_academyno", "")

        # Determine target year
        if app.is_renewal and app.previous_application_id:
            target_year = prev_alloc_years.get(app.previous_application_id, academic_year)
        else:
            target_year = academic_year

        # Get preferences (config-driven default if null)
        preferences = app.sub_type_preferences or default_prefs

        # For each preference, try target_year first, then fallback to current year
        allocated = False
        for sub_type in preferences:
            # Check if target_year is valid for this sub_type
            if target_year != academic_year:
                allowed_prior = prior_years_map.get(sub_type, [])
                if target_year not in allowed_prior:
                    # Prior year not configured for this sub_type, try current year
                    key_current = (sub_type, academic_year, college)
                    if quota_tracker.get(key_current, 0) > 0:
                        quota_tracker[key_current] -= 1
                        suggestions.append({
                            "ranking_item_id": item.id,
                            "sub_type_code": sub_type,
                            "allocation_year": academic_year,
                        })
                        allocated = True
                        break
                    continue

            # Try target year
            key = (sub_type, target_year, college)
            if quota_tracker.get(key, 0) > 0:
                quota_tracker[key] -= 1
                suggestions.append({
                    "ranking_item_id": item.id,
                    "sub_type_code": sub_type,
                    "allocation_year": target_year,
                })
                allocated = True
                break

            # Fallback: renewal with different target_year -> try current year for same sub_type
            if app.is_renewal and target_year != academic_year:
                key_current = (sub_type, academic_year, college)
                if quota_tracker.get(key_current, 0) > 0:
                    quota_tracker[key_current] -= 1
                    suggestions.append({
                        "ranking_item_id": item.id,
                        "sub_type_code": sub_type,
                        "allocation_year": academic_year,
                    })
                    allocated = True
                    break

        if not allocated:
            suggestions.append({
                "ranking_item_id": item.id,
                "sub_type_code": None,
                "allocation_year": None,
            })

    return suggestions
```

- [ ] **Step 4: Add necessary imports**

At the top of `manual_distribution_service.py`, ensure this import exists (it likely already does since `get_quota_status` uses it):

```python
from app.models.scholarship import ScholarshipSubTypeConfig
```

Also verify these are imported (should be already): `ScholarshipConfiguration`, `_config_semester_condition`.

- [ ] **Step 5: Verify backend compiles**

Run:
```bash
docker compose -f docker-compose.dev.yml restart backend
docker compose -f docker-compose.dev.yml logs backend --tail=20
```
Expected: No import or syntax errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/manual_distribution_service.py
git commit -m "feat: add auto_allocate_preview method to ManualDistributionService"
```

### Task 4: Add the API endpoint

**Files:**
- Modify: `backend/app/api/v1/endpoints/manual_distribution.py`

- [ ] **Step 1: Add the `/auto-allocate-preview` endpoint**

Add after the existing `/quota-status` endpoint (around line 161):

```python
@router.get("/auto-allocate-preview")
async def auto_allocate_preview(
    scholarship_type_id: int,
    academic_year: int,
    semester: str,
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_admin_user),
):
    """Generate auto-allocation suggestions without persisting."""
    service = ManualDistributionService(db)
    suggestions = await service.auto_allocate_preview(
        scholarship_type_id=scholarship_type_id,
        academic_year=academic_year,
        semester=semester,
    )
    return {
        "success": True,
        "message": "Auto-allocation preview generated",
        "data": {"suggestions": suggestions},
    }
```

- [ ] **Step 2: Verify endpoint is accessible**

Run:
```bash
docker compose -f docker-compose.dev.yml restart backend
```
Then check the endpoint appears in OpenAPI docs at `http://localhost:8000/docs`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/manual_distribution.py
git commit -m "feat: add /auto-allocate-preview API endpoint"
```

---

## Chunk 3: Frontend — Distribution Page Integration

### Task 5: Add API function for auto-allocate preview

**Files:**
- Modify: `frontend/lib/api/modules/manual-distribution.ts`

- [ ] **Step 1: Add interface for suggestion**

Add near the top interfaces section:

```typescript
export interface AllocationSuggestion {
  ranking_item_id: number;
  sub_type_code: string | null;
  allocation_year: number | null;
}
```

- [ ] **Step 2: Add API method inside `createManualDistributionApi()`**

Add inside the return object of `createManualDistributionApi()`, following the existing pattern (e.g., after `getQuotaStatus`):

```typescript
/**
 * Get auto-allocation preview suggestions.
 */
getAutoAllocatePreview: async (
  scholarship_type_id: number,
  academic_year: number,
  semester: string
): Promise<ApiResponse<{ suggestions: AllocationSuggestion[] }>> => {
  const response = await typedClient.raw.GET(
    "/api/v1/manual-distribution/auto-allocate-preview" as any,
    {
      params: {
        query: {
          scholarship_type_id,
          academic_year,
          semester,
        } as any,
      },
    }
  );
  return toApiResponse(response) as ApiResponse<{ suggestions: AllocationSuggestion[] }>;
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/lib/api/modules/manual-distribution.ts
git commit -m "feat: add getAutoAllocatePreview API function"
```

### Task 6: Integrate auto-allocate preview into ManualDistributionPanel

**Files:**
- Modify: `frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx`

- [ ] **Step 1: Add state for preview notice**

Add near other state declarations (around line 92):

```typescript
const [previewApplied, setPreviewApplied] = useState(false);
```

- [ ] **Step 2: Call preview API during data loading (with graceful failure handling)**

In the data loading function (around lines 173-213), load students and quotas in parallel, then call preview separately so a preview failure does not break the page:

```typescript
// Load students and quota in parallel (required)
const [studentsResp, quotaResp] = await Promise.all([
  apiClient.manualDistribution.getStudents(scholarshipTypeId, academicYear, semester),
  apiClient.manualDistribution.getQuotaStatus(scholarshipTypeId, academicYear, semester),
]);

// Load preview separately (optional — failure should not break the page)
let previewSuggestions: AllocationSuggestion[] = [];
try {
  const previewResp = await apiClient.manualDistribution.getAutoAllocatePreview(
    scholarshipTypeId, academicYear, semester
  );
  if (previewResp.success && previewResp.data) {
    previewSuggestions = previewResp.data.suggestions;
  }
} catch {
  // Preview is optional; proceed without it
}
```

- [ ] **Step 3: Apply suggestions to localAllocations**

After initializing `localAllocations` from existing student data, apply preview suggestions for unallocated students:

```typescript
// Initialize from existing saved allocations
const allocMap = new Map<number, LocalAlloc | null>();
for (const s of studentsData) {
  if (s.allocated_sub_type && s.allocation_year) {
    allocMap.set(s.ranking_item_id, {
      sub_type: s.allocated_sub_type,
      year: s.allocation_year,
    });
  }
}

// Apply auto-preview suggestions for unallocated students
let hasPreview = false;
for (const suggestion of previewSuggestions) {
  if (
    suggestion.sub_type_code &&
    suggestion.allocation_year &&
    !allocMap.has(suggestion.ranking_item_id)
  ) {
    allocMap.set(suggestion.ranking_item_id, {
      sub_type: suggestion.sub_type_code,
      year: suggestion.allocation_year,
    });
    hasPreview = true;
  }
}

setLocalAllocations(allocMap);
setPreviewApplied(hasPreview);
```

- [ ] **Step 4: Reset previewApplied on data reload**

At the start of the `fetchData` function (or equivalent data loading function), reset the state:

```typescript
setPreviewApplied(false);
```

- [ ] **Step 5: Add notice banner in the JSX**

Above the distribution table, add:

```tsx
{previewApplied && (
  <div className="mb-4 rounded-md bg-blue-50 p-3 text-sm text-blue-700">
    已自動預設分配，請確認後儲存
  </div>
)}
```

- [ ] **Step 6: Verify the page loads and shows suggestions**

Open the manual distribution page in the browser, select a scholarship type/year/semester. Verify:
- Auto-suggestions appear as pre-checked checkboxes
- Existing saved allocations are NOT overwritten
- The blue notice banner appears
- Checkboxes can still be manually changed
- Switching academic year/semester resets and recalculates

- [ ] **Step 7: Commit**

```bash
git add frontend/components/admin/manual-distribution/ManualDistributionPanel.tsx
git commit -m "feat: integrate auto-allocate preview into distribution page"
```

---

## Chunk 4: Frontend — Application Form Preference UI

### Task 7: Add preference ordering UI to application form

**Files:**
- Modify: `frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx`
- Modify: `frontend/lib/api/modules/applications.ts` (or wherever `ApplicationCreate` type is defined)

- [ ] **Step 1: Add state for sub-type preferences**

Near other state declarations (around line 61):

```typescript
const [subTypePreferences, setSubTypePreferences] = useState<string[]>([]);
```

- [ ] **Step 2: Sync preferences when selectedSubTypes changes**

Add a useEffect to initialize preferences from selected sub-types:

```typescript
useEffect(() => {
  // Keep existing order for items still selected, append new ones at end
  setSubTypePreferences((prev) => {
    const kept = prev.filter((st) => selectedSubTypes.includes(st));
    const newOnes = selectedSubTypes.filter((st) => !prev.includes(st));
    return [...kept, ...newOnes];
  });
}, [selectedSubTypes]);
```

- [ ] **Step 3: Add move-up/move-down handler**

```typescript
const handleMovePreference = (index: number, direction: 'up' | 'down') => {
  setSubTypePreferences((prev) => {
    const newPrefs = [...prev];
    const targetIndex = direction === 'up' ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= newPrefs.length) return prev;
    [newPrefs[index], newPrefs[targetIndex]] = [newPrefs[targetIndex], newPrefs[index]];
    return newPrefs;
  });
};
```

- [ ] **Step 4: Add preference ordering UI in JSX**

After the sub-type selection cards (around line 693), add the preference ordering section. Only show when 2+ sub-types are selected:

```tsx
{selectedSubTypes.length >= 2 && (
  <div className="mt-4">
    <h4 className="text-sm font-medium mb-2">志願排序（第一個為最優先）</h4>
    <div className="space-y-2">
      {subTypePreferences.map((subType, index) => {
        // Find the display name. Check which variable holds the sub-type configs
        // in ScholarshipApplicationStep (may be called subTypeConfigs, availableSubTypes,
        // scholarshipSubTypes, etc.). Adapt accordingly.
        const config = subTypeConfigs.find((c: any) => c.sub_type_code === subType);
        return (
          <div key={subType} className="flex items-center gap-2 p-2 bg-gray-50 rounded">
            <span className="text-sm font-medium w-6">{index + 1}.</span>
            <span className="flex-1 text-sm">{config?.name || subType}</span>
            <button
              type="button"
              disabled={index === 0}
              onClick={() => handleMovePreference(index, 'up')}
              className="p-1 text-gray-500 hover:text-gray-700 disabled:opacity-30"
            >
              ▲
            </button>
            <button
              type="button"
              disabled={index === subTypePreferences.length - 1}
              onClick={() => handleMovePreference(index, 'down')}
              className="p-1 text-gray-500 hover:text-gray-700 disabled:opacity-30"
            >
              ▼
            </button>
          </div>
        );
      })}
    </div>
  </div>
)}
```

**Important:** Verify the variable name holding sub-type display configs in `ScholarshipApplicationStep.tsx`. The name used above (`subTypeConfigs`) is a placeholder — adapt to the actual variable.

- [ ] **Step 5: Include `sub_type_preferences` in submission payload**

In the form submission handler (around lines 423-432 and 496-505), add `sub_type_preferences` to `applicationData`:

```typescript
const applicationData = {
  // ... existing fields ...
  scholarship_subtype_list: selectedSubTypes.length > 0 ? selectedSubTypes : ["general"],
  sub_type_preferences: subTypePreferences.length > 0 ? subTypePreferences : undefined,
  // ... rest of existing fields
};
```

- [ ] **Step 6: Update ApplicationCreate type**

In the frontend type definition for ApplicationCreate (check `frontend/lib/api/modules/applications.ts` or generated types), add:

```typescript
sub_type_preferences?: string[];
```

- [ ] **Step 7: Verify preference UI works**

Open the student application form, select a scholarship with multiple sub-types. Verify:
- After selecting 2+ sub-types, the preference ordering section appears
- Up/down arrows reorder items correctly
- First item cannot move up, last cannot move down
- Submitting the form includes the preference data

- [ ] **Step 8: Commit**

```bash
git add frontend/components/student-wizard/steps/ScholarshipApplicationStep.tsx
git add frontend/lib/api/modules/applications.ts
git commit -m "feat: add sub-type preference ordering UI to application form"
```

---

## Chunk 5: Regenerate Types & Final Verification

### Task 8: Regenerate OpenAPI types

**Files:**
- Modify: `frontend/lib/api/generated/schema.d.ts`

- [ ] **Step 1: Ensure backend is running**

```bash
docker compose -f docker-compose.dev.yml up -d backend
```

- [ ] **Step 2: Regenerate types**

```bash
cd frontend && npm run api:generate
```

- [ ] **Step 3: Commit generated types**

```bash
git add frontend/lib/api/generated/schema.d.ts
git commit -m "chore: regenerate OpenAPI types for sub_type_preferences"
```

### Task 9: End-to-end verification

- [ ] **Step 1: Test the complete flow**

1. Create/edit a student application with 2+ sub-types selected
2. Verify preference ordering UI appears and works
3. Submit the application
4. Go through the ranking flow until distribution
5. Open manual distribution page
6. Verify auto-suggestions pre-fill checkboxes
7. Verify renewal students are prioritized
8. Verify manual override still works
9. Save and finalize to confirm existing flow is not broken

- [ ] **Step 2: Test edge cases**

1. Application with null `sub_type_preferences` → uses config-driven defaults
2. All quotas exhausted → suggestions show null for remaining students
3. Partially saved distribution → existing allocations preserved, only empty slots get suggestions
4. Only 1 sub-type available → no preference UI shown, auto-allocates to that type

- [ ] **Step 3: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address issues found during e2e verification"
```
