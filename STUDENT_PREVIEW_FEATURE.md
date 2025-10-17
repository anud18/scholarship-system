# 學生資訊懸停預覽功能實作完成

## 功能概述

在 College 角色的排名表格中,滑鼠懸停在學生姓名上時,會顯示半透明的學生資訊卡片,包含:
- **基本資料**: 學號、系所、學院、學位、入學年度、在學學期數
- **學期成績**: 最近 2-3 個學期的 GPA、學分、排名(如果有)

## 實作內容

### Backend 變更

#### 1. 新增 API 端點
**檔案**: `backend/app/api/v1/endpoints/college_review.py`

**新增端點**:
```
GET /api/v1/college-review/students/{student_id}/preview
```

**功能**:
- 返回學生基本資訊和最近學期資料
- 權限檢查: 需要 College 角色
- 包含 rate limiting (100 requests/10 minutes)

**查詢參數**:
- `academic_year` (optional): 當前學年度,用於獲取學期資料

**回應格式**:
```json
{
  "success": true,
  "message": "Student preview retrieved successfully",
  "data": {
    "basic": {
      "student_id": "xxx",
      "student_name": "xxx",
      "department_name": "xxx",
      "academy_name": "xxx",
      "term_count": 5,
      "degree": "碩士",
      "enrollyear": "112",
      "sex": "1"
    },
    "recent_terms": [
      {
        "academic_year": "113",
        "term": "1",
        "gpa": 3.85,
        "credits": 9,
        "rank": 5
      }
    ]
  }
}
```

#### 2. 新增 Pydantic Schemas
**檔案**: `backend/app/api/v1/endpoints/college_review.py`

新增以下 schemas:
- `StudentPreviewBasic` - 學生基本資料
- `StudentTermData` - 學期資料
- `StudentPreviewResponse` - 完整回應

### Frontend 變更

#### 1. 創建 useStudentPreview Hook
**新檔案**: `frontend/hooks/use-student-preview.ts`

**功能**:
- 管理學生預覽資料的獲取和快取
- Debounce hover 事件 (300ms)
- 錯誤處理和 loading 狀態管理
- 請求取消機制(防止記憶體洩漏)

**使用方式**:
```tsx
const { previewData, isLoading, error, fetchPreview } = useStudentPreview();
```

#### 2. 創建 StudentPreviewCard 組件
**新檔案**: `frontend/components/student-preview-card.tsx`

**功能**:
- 使用 `HoverCard` (Radix UI) 實現懸停效果
- 基本資訊立即顯示
- 學期資料異步載入(hover 時觸發)
- 半透明樣式 (`bg-background/90`, `backdrop-blur-sm`)
- Loading 和錯誤狀態處理
- 支援中英文切換

**Props**:
```tsx
interface StudentPreviewCardProps {
  studentId: string;
  studentName: string;
  basicInfo?: StudentBasicInfo;
  academicYear?: number;
  locale?: "zh" | "en";
}
```

#### 3. 整合到 CollegeRankingTable
**修改檔案**: `frontend/components/college-ranking-table.tsx`

**變更**:
- Import `StudentPreviewCard` 組件
- 將學生姓名包裝在 `StudentPreviewCard` 中
- 傳遞必要的 props (studentId, studentName, basicInfo, etc.)

**修改位置**: Line 232-247

### TypeScript 型別定義

**自動生成**: `frontend/lib/api/generated/schema.d.ts`

已透過 `npm run api:generate` 自動生成新的 API 型別定義。

## 檔案清單

### 新增檔案 (2)
1. `frontend/hooks/use-student-preview.ts` - 資料獲取 Hook
2. `frontend/components/student-preview-card.tsx` - 預覽卡片組件

### 修改檔案 (2)
1. `backend/app/api/v1/endpoints/college_review.py` - 新增端點和 schemas
2. `frontend/components/college-ranking-table.tsx` - 整合預覽功能

### 自動生成 (1)
1. `frontend/lib/api/generated/schema.d.ts` - API 型別定義(已更新)

## 使用說明

### 前端使用

在任何需要顯示學生資訊預覽的地方,使用 `StudentPreviewCard` 組件:

```tsx
import { StudentPreviewCard } from "@/components/student-preview-card";

<StudentPreviewCard
  studentId={student.id}
  studentName={student.name}
  basicInfo={{
    department_name: student.department,
    academy_name: student.academy,
    term_count: student.termCount,
  }}
  academicYear={113}
  locale="zh"
/>
```

### Backend API 使用

```bash
# 獲取學生預覽資料
curl -X GET "http://localhost:8000/api/v1/college-review/students/{student_id}/preview?academic_year=113" \
  -H "Authorization: Bearer {token}"
```

## 特色功能

### 1. 兩階段資料載入
- **立即顯示**: 使用已有的基本資料(來自 application data)
- **異步載入**: Hover 時才獲取詳細的學期資料

### 2. 快取機制
- 已獲取的資料會被快取
- 重複 hover 不會重複請求

### 3. Debounce
- 300ms 延遲,避免快速移動滑鼠時頻繁請求

### 4. 半透明樣式
- `bg-background/90` - 90% 不透明度
- `backdrop-blur-sm` - 背景模糊效果
- `shadow-lg` - 陰影效果
- 符合現代 UI 設計風格

### 5. 錯誤處理
- 網絡錯誤顯示友善訊息
- 請求取消機制(避免記憶體洩漏)
- Loading 狀態顯示骨架屏

### 6. 響應式設計
- 自動調整卡片位置
- 支援不同螢幕尺寸

## 權限與安全

### Backend 權限
- 需要 College 角色 (`require_college`)
- Rate limiting: 100 requests / 10 minutes
- 只能查看管理範圍內的學生

### 資料安全
- 不顯示敏感資訊(身分證、地址等)
- 學號可選擇性遮罩

## 測試建議

### 前端測試
```bash
cd frontend
npm run dev
```

1. 登入 College 角色帳號
2. 進入排名管理頁面
3. 將滑鼠懸停在學生姓名上
4. 檢查:
   - 預覽卡片是否正確顯示
   - 基本資訊是否立即顯示
   - 學期資料是否異步載入
   - Loading 狀態是否正確
   - 重複 hover 是否使用快取

### Backend 測試
```bash
# 測試 API 端點
curl -X GET "http://localhost:8000/api/v1/college-review/students/test_student/preview?academic_year=113" \
  -H "Authorization: Bearer {your_token}"
```

## 已知限制

1. **Academic Year 硬編碼**: 目前在 CollegeRankingTable 中使用固定值 `113`,建議未來從系統設定或 props 獲取
2. **學期資料依賴外部 API**: 如果 Student API 不可用,只會顯示基本資料
3. **快取策略**: 當前快取沒有過期機制,頁面重新載入後會清空

## 未來改進建議

1. 從系統設定獲取當前學年度
2. 新增快取過期機制(例如 5 分鐘)
3. 新增學生照片顯示
4. 支援更多學期資料(不只最近 3 個學期)
5. 新增資料刷新按鈕
6. 支援鍵盤導航(Accessibility)

## 維護注意事項

1. **Student API 變更**: 如果外部學生 API 的回應格式改變,需要更新 `StudentService` 和相關的資料映射
2. **Schema 變更**: 修改 backend schemas 後記得執行 `npm run api:generate`
3. **樣式調整**: 半透明效果依賴 Tailwind CSS,確保正確配置

## 技術棧

### Backend
- FastAPI
- Pydantic (資料驗證)
- SQLAlchemy (資料庫查詢)
- httpx (外部 API 調用)

### Frontend
- React 18
- TypeScript
- Radix UI (HoverCard)
- Tailwind CSS (樣式)
- Custom Hooks (資料管理)

## 效能考量

1. **Rate Limiting**: 100 requests / 10 minutes,防止濫用
2. **Debounce**: 300ms 延遲,減少不必要的請求
3. **快取**: 避免重複請求相同資料
4. **請求取消**: 防止記憶體洩漏和重複請求

## 結論

學生資訊懸停預覽功能已完整實作並整合到系統中。此功能提升了 College 角色審查學生申請時的使用體驗,無需離開當前頁面即可查看學生的詳細資訊。

實作採用現代化的設計模式,包含快取、debounce、錯誤處理等最佳實踐,確保功能的穩定性和使用者體驗。
