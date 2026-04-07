# College Ranking Import Validation & Template Sorting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enhance the existing college ranking import with strict validation (no duplicate/gap ranks, strict student matching, "N" = reject) and sort template downloads by department code then student ID.

**Architecture:** Dual-layer validation (frontend + backend). Frontend validates format/sequence immediately after Excel parse; backend re-validates and adds strict student matching. Template download sorted by `department_code` → `student_id` with added `系所` column.

**Tech Stack:** Python/Pydantic (backend schema + endpoint), TypeScript/React + xlsx library (frontend)

---

## File Structure

| File | Responsibility |
|------|----------------|
| `backend/app/schemas/college_review.py` | `RankingImportItem` schema — accept `int \| "N"` for `rank_position` |
| `backend/app/api/v1/endpoints/college_review/ranking_management.py` | Import endpoint — strict validation + "N" handling |
| `frontend/components/college-ranking-table.tsx` | Template sort, upload validation, "N" support |

No new files. No database migrations.

---

### Task 1: Backend Schema — Accept "N" in rank_position

**Files:**
- Modify: `backend/app/schemas/college_review.py:137-142`

- [ ] **Step 1: Update RankingImportItem schema**

Open `backend/app/schemas/college_review.py`. Replace the `RankingImportItem` class (lines 137–142) with:

```python
class RankingImportItem(BaseModel):
    """Schema for importing ranking data from Excel"""

    student_id: str = Field(..., description="Student ID (學號)")
    student_name: str = Field(..., description="Student name (姓名)")
    rank_position: Any = Field(..., description="Ranking position (排名): positive integer or 'N' for rejected")

    @field_validator("rank_position", mode="before")
    @classmethod
    def validate_rank(cls, v):
        if isinstance(v, str):
            if v.strip().upper() == "N":
                return "N"
            # Try parsing numeric strings like "3"
            try:
                v = int(v)
            except ValueError:
                raise ValueError(f"排名格式無效：'{v}'，只接受正整數或 'N'")
        if isinstance(v, (int, float)):
            v = int(v)
            if v < 1:
                raise ValueError(f"排名必須為正整數，收到：{v}")
            return v
        raise ValueError(f"排名格式無效：'{v}'")
```

Also add the missing imports at the top of the file. The current imports are:

```python
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
```

Add `field_validator`:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

And add `Any` to typing if not already present (it is).

- [ ] **Step 2: Verify schema parses correctly**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-ranking-import/backend
python -c "
from app.schemas.college_review import RankingImportItem

# Test valid integer
item = RankingImportItem(student_id='A001', student_name='Test', rank_position=1)
assert item.rank_position == 1

# Test 'N' string
item = RankingImportItem(student_id='A002', student_name='Test', rank_position='N')
assert item.rank_position == 'N'

# Test 'n' lowercase
item = RankingImportItem(student_id='A003', student_name='Test', rank_position='n')
assert item.rank_position == 'N'

# Test numeric string
item = RankingImportItem(student_id='A004', student_name='Test', rank_position='3')
assert item.rank_position == 3

# Test invalid
try:
    RankingImportItem(student_id='A005', student_name='Test', rank_position='abc')
    assert False, 'Should have raised'
except Exception:
    pass

# Test zero
try:
    RankingImportItem(student_id='A006', student_name='Test', rank_position=0)
    assert False, 'Should have raised'
except Exception:
    pass

print('All schema tests passed')
"
```

Expected: `All schema tests passed`

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/college_review.py
git commit -m "feat: accept 'N' (reject) in ranking import schema"
```

---

### Task 2: Backend Endpoint — Strict Validation Logic

**Files:**
- Modify: `backend/app/api/v1/endpoints/college_review/ranking_management.py:898-976`

- [ ] **Step 1: Replace the import endpoint**

Replace the `import_ranking_from_excel` function (lines 898–976) with the following. The function signature stays the same; the body changes to add validation and "N" handling:

```python
@router.post("/rankings/{ranking_id}/import-excel")
async def import_ranking_from_excel(
    ranking_id: int,
    import_data: List[RankingImportItem],
    current_user: User = Depends(require_college),
    db: AsyncSession = Depends(get_db),
):
    """
    Import ranking data from Excel.

    Expected columns: 學號, 姓名, 排名
    rank_position accepts positive integers (1-based, consecutive, no duplicates) or "N" (rejected).
    Student IDs must exactly match the ranking's application set.
    """
    try:
        logger.info(f"User {current_user.id} importing {len(import_data)} rankings for ranking_id={ranking_id}")

        # Load ranking with items
        stmt = (
            select(CollegeRanking)
            .options(selectinload(CollegeRanking.items).selectinload(CollegeRankingItem.application))
            .where(CollegeRanking.id == ranking_id)
        )
        result = await db.execute(stmt)
        ranking = result.scalar_one_or_none()

        if not ranking:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ranking not found")

        if ranking.is_finalized:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot modify finalized ranking")

        # --- Validation ---
        errors = []

        # 1. Collect ranking system student IDs
        system_student_ids = set()
        student_id_to_item = {}
        for rank_item in ranking.items:
            app = rank_item.application
            if not app or not app.student_data:
                continue
            sid = app.student_data.get("std_stdcode") or app.student_data.get("student_id")
            if sid:
                system_student_ids.add(sid)
                student_id_to_item[sid] = rank_item

        # 2. Collect import student IDs
        import_student_ids = {item.student_id for item in import_data}

        # 3. Strict student matching
        extra_ids = import_student_ids - system_student_ids
        missing_ids = system_student_ids - import_student_ids
        if extra_ids:
            errors.append(f"以下學號不在申請清單中：{', '.join(sorted(extra_ids))}")
        if missing_ids:
            errors.append(f"以下學號未包含在匯入檔案中：{', '.join(sorted(missing_ids))}")

        # 4. Validate rank sequence
        integer_ranks = []
        for item in import_data:
            if isinstance(item.rank_position, int):
                integer_ranks.append(item.rank_position)

        # Check duplicates
        rank_counts: Dict[int, int] = {}
        for r in integer_ranks:
            rank_counts[r] = rank_counts.get(r, 0) + 1
        duplicates = [str(r) for r, count in sorted(rank_counts.items()) if count > 1]
        if duplicates:
            errors.append(f"排名重複：{', '.join(duplicates)}")

        # Check consecutive from 1
        if integer_ranks and not duplicates:
            expected = set(range(1, len(integer_ranks) + 1))
            actual = set(integer_ranks)
            missing_ranks = expected - actual
            if missing_ranks:
                errors.append(f"排名不連續：缺少第 {', '.join(str(r) for r in sorted(missing_ranks))} 名")

        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="\n".join(errors),
            )

        # --- Apply updates ---
        updated_count = 0
        rejected_count = 0

        import_map = {item.student_id: item for item in import_data}

        for sid, rank_item in student_id_to_item.items():
            if sid not in import_map:
                continue
            import_item = import_map[sid]
            if import_item.rank_position == "N":
                rank_item.rank_position = None
                rank_item.status = "rejected"
                rejected_count += 1
            else:
                rank_item.rank_position = import_item.rank_position
                rank_item.status = "ranked"
            updated_count += 1

        ranking.total_applications = len(ranking.items)
        await db.flush()

        return ApiResponse(
            success=True,
            message=f"排名匯入成功。更新 {updated_count} 筆（其中 {rejected_count} 筆拒絕）。",
            data={
                "ranking_id": ranking_id,
                "updated_count": updated_count,
                "rejected_count": rejected_count,
                "total_imported": len(import_data),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing ranking data: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to import ranking data: {str(e)}",
        )
```

Make sure `Dict` is imported from `typing` at the top of the file (check existing imports).

- [ ] **Step 2: Verify the import compiles**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-ranking-import/backend
python -c "from app.api.v1.endpoints.college_review.ranking_management import router; print('Import OK')"
```

Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/v1/endpoints/college_review/ranking_management.py
git commit -m "feat: add strict validation to ranking import endpoint"
```

---

### Task 3: Frontend — Template Download Sorting + 系所 Column

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx:78-104` (Application interface)
- Modify: `frontend/components/college-ranking-table.tsx:530-564` (handleTemplateDownload)
- Modify: `frontend/components/college/ranking/RankingManagementPanel.tsx:104` (add department_code mapping)

- [ ] **Step 1: Add department_code to Application interface**

In `frontend/components/college-ranking-table.tsx`, add `department_code` to the `Application` interface (after line 86 `department_name`):

```typescript
interface Application {
  id: number;
  app_id: string;
  student_name: string;
  student_id: string;
  academy_name?: string;
  academy_code?: string;
  department_name?: string;
  department_code?: string;  // NEW: for template sorting
  scholarship_type: string;
  // ... rest unchanged
```

- [ ] **Step 2: Map department_code in RankingManagementPanel**

In `frontend/components/college/ranking/RankingManagementPanel.tsx`, line 104, add `department_code` to the transformation:

```typescript
department_name: item.application?.department_name,
department_code: item.application?.department_code,  // NEW
```

- [ ] **Step 3: Update handleTemplateDownload with sorting and 系所 column**

In `frontend/components/college-ranking-table.tsx`, replace the `handleTemplateDownload` function (lines 530–564) with:

```typescript
  const handleTemplateDownload = () => {
    try {
      // Sort by department code, then student ID
      const sorted = [...localApplications].sort((a, b) => {
        const deptA = a.department_code || a.department_name || "";
        const deptB = b.department_code || b.department_name || "";
        if (deptA !== deptB) return deptA.localeCompare(deptB);
        return (a.student_id || "").localeCompare(b.student_id || "");
      });

      const templateData = sorted.map(app => ({
        學號: app.student_id || "",
        姓名: app.student_name || "",
        系所: app.department_name || "",
        排名: "", // Blank for user to fill in (integer or N)
      }));

      // Create worksheet
      const worksheet = XLSX.utils.json_to_sheet(templateData);

      // Set column widths for better readability
      worksheet["!cols"] = [
        { wch: 15 }, // 學號
        { wch: 20 }, // 姓名
        { wch: 25 }, // 系所
        { wch: 10 }, // 排名
      ];

      // Create workbook
      const workbook = XLSX.utils.book_new();
      XLSX.utils.book_append_sheet(workbook, worksheet, "排名範本");

      // Generate filename
      const filename = `排名範本_${subTypeCode}_${academicYear}.xlsx`;

      // Download file
      XLSX.writeFile(workbook, filename);

      toast.success(`已下載範本檔案：${filename}`);
    } catch (error) {
      console.error("Template download error:", error);
      toast.error(error instanceof Error ? error.message : "無法產生範本檔案");
    }
  };
```

- [ ] **Step 4: Commit**

```bash
git add frontend/components/college-ranking-table.tsx frontend/components/college/ranking/RankingManagementPanel.tsx
git commit -m "feat: sort ranking template by department code then student ID, add dept column"
```

---

### Task 4: Frontend — Upload Validation + "N" Support

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx:473-528` (handleFileUpload)

- [ ] **Step 1: Replace handleFileUpload with validation logic**

In `frontend/components/college-ranking-table.tsx`, replace the `handleFileUpload` function (lines 473–528) with:

```typescript
  const handleFileUpload = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const file = event.target.files?.[0];
    if (!file) return;

    // Validate file type
    if (!file.name.endsWith(".xlsx") && !file.name.endsWith(".xls")) {
      toast.error("請上傳 Excel 檔案 (.xlsx 或 .xls)");
      return;
    }

    setIsImporting(true);

    try {
      // Read Excel file
      const data = await file.arrayBuffer();
      const uint8Array = new Uint8Array(data);
      const workbook = XLSX.read(uint8Array, { type: "array" });
      const worksheet = workbook.Sheets[workbook.SheetNames[0]];
      const jsonData = XLSX.utils.sheet_to_json(worksheet);

      // Parse Excel data - expected columns: 學號, 姓名, 排名
      const errors: string[] = [];
      const importData: Array<{
        student_id: string;
        student_name: string;
        rank_position: number | string;
      }> = [];

      jsonData.forEach((row: any, index: number) => {
        const rowNum = index + 2; // Excel row (header = row 1)
        const studentId = String(row["學號"] || row["student_id"] || "").trim();
        const studentName = String(row["姓名"] || row["student_name"] || row["name"] || "").trim();
        const rawRank = row["排名"] ?? row["rank_position"] ?? row["rank"];

        if (!studentId) return; // Skip empty rows

        // Validate rank value
        if (rawRank === undefined || rawRank === null || String(rawRank).trim() === "") {
          errors.push(`第 ${rowNum} 行排名欄位為空（學號：${studentId}）`);
          return;
        }

        const rankStr = String(rawRank).trim();

        if (rankStr.toUpperCase() === "N") {
          importData.push({ student_id: studentId, student_name: studentName, rank_position: "N" });
        } else {
          const rankNum = Number(rankStr);
          if (!Number.isInteger(rankNum) || rankNum < 1) {
            errors.push(`第 ${rowNum} 行排名格式無效：'${rankStr}'（學號：${studentId}）`);
          } else {
            importData.push({ student_id: studentId, student_name: studentName, rank_position: rankNum });
          }
        }
      });

      // Validate: no duplicate integer ranks
      const integerRanks = importData
        .filter(item => typeof item.rank_position === "number")
        .map(item => item.rank_position as number);

      const rankCounts = new Map<number, number>();
      integerRanks.forEach(r => rankCounts.set(r, (rankCounts.get(r) || 0) + 1));
      rankCounts.forEach((count, rank) => {
        if (count > 1) {
          errors.push(`排名 ${rank} 重複出現（${count} 次）`);
        }
      });

      // Validate: consecutive from 1
      if (integerRanks.length > 0 && errors.length === 0) {
        const sorted = [...integerRanks].sort((a, b) => a - b);
        const missing: number[] = [];
        for (let i = 1; i <= sorted.length; i++) {
          if (!sorted.includes(i)) missing.push(i);
        }
        if (missing.length > 0) {
          errors.push(`排名不連續：缺少第 ${missing.join(", ")} 名`);
        }
      }

      if (errors.length > 0) {
        toast.error(errors.join("\n"), { duration: 10000 });
        setIsImporting(false);
        event.target.value = "";
        return;
      }

      if (importData.length === 0) {
        toast.error("Excel 檔案中沒有找到有效的排名資料");
        setIsImporting(false);
        event.target.value = "";
        return;
      }

      // Call import handler if provided
      if (onImportExcel) {
        await onImportExcel(importData);
        const rejectedCount = importData.filter(item => item.rank_position === "N").length;
        const rankedCount = importData.length - rejectedCount;
        toast.success(
          `成功匯入 ${importData.length} 筆排名資料（排名 ${rankedCount} 筆，拒絕 ${rejectedCount} 筆）`
        );
        setIsImportDialogOpen(false);
      }
    } catch (error) {
      console.error("Excel import error:", error);
      toast.error(
        error instanceof Error ? error.message : "無法讀取 Excel 檔案"
      );
    } finally {
      setIsImporting(false);
      // Reset file input
      event.target.value = "";
    }
  };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/components/college-ranking-table.tsx
git commit -m "feat: add ranking import validation - consecutive check, duplicate check, N support"
```

---

### Task 5: Update Import Dialog Help Text

**Files:**
- Modify: `frontend/components/college-ranking-table.tsx` (import dialog UI section)

- [ ] **Step 1: Find and update the import dialog info text**

Locate the import dialog section (around lines 715–811 area) that shows format requirements. Update the info text to mention "N" for rejection. Search for the blue info box that describes the format.

Update the help text to say:
- 排名欄位填入正整數（從 1 開始連續排名）或 N（代表拒絕）
- 排名數字不可重複、不可跳號
- N 代表拒絕該申請，可重複
- 所有學生都必須有排名

This is a UI-only change — find the relevant JSX and update the text accordingly.

- [ ] **Step 2: Commit**

```bash
git add frontend/components/college-ranking-table.tsx
git commit -m "feat: update import dialog help text to describe N rejection and validation rules"
```

---

### Task 6: Verify End-to-End

- [ ] **Step 1: Start dev environment**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/college-ranking-import
docker compose -f docker-compose.dev.yml up -d
```

- [ ] **Step 2: Verify backend compiles and starts**

```bash
docker compose -f docker-compose.dev.yml logs -f backend 2>&1 | head -50
```

Look for `Application startup complete` or similar success message.

- [ ] **Step 3: Verify frontend compiles**

```bash
docker compose -f docker-compose.dev.yml logs -f frontend 2>&1 | head -30
```

Look for successful compilation with no TypeScript errors.

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git log --oneline -5
```

Verify all commits are clean and properly ordered.
