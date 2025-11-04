# Admin API 模組化結構

## 概覽

原先的 `admin.py` (3908 行) 已被模組化為多個職責明確的文件，提高代碼可維護性和團隊協作效率。

## 目錄結構

```
admin/
├── __init__.py              # 聚合所有子路由 (主入口)
├── _helpers.py              # 共用工具函數 (權限檢查、篩選器等)
├── configurations.py        # ✅ 配置管理 (已遷移)
├── dashboard.py             # ✅ 儀表板與統計 (已遷移)
├── system_settings.py       # ✅ 系統設定 (已遷移)
└── README.md                # 本文件
```

## 已遷移的模組

### 1. `dashboard.py` - 儀表板與統計
**端點:**
- `GET /dashboard/stats` - **系統統計 (✨ 已修復前端數據格式)**
- `GET /system/health` - 系統健康檢查
- `GET /debug/nycu-employee` - NYCU API 調試
- `GET /recent-applications` - 最近申請
- `GET /scholarships/stats` - 獎學金統計

**重要更新:**
- `/dashboard/stats` 已修復，現在返回前端期望的數據格式：
  - `totalUsers`: 總用戶數
  - `activeApplications`: 進行中申請數
  - `completedReviews`: 已完成審核數
  - `systemUptime`: 系統運行時間
  - `avgResponseTime`: 平均響應時間
  - `storageUsed`: 存儲使用量
  - `pendingReviews`: 待審核數
  - `totalScholarships`: 獎學金總數

### 2. `system_settings.py` - 系統設定
**端點:**
- `GET /system-setting` - 獲取系統設定
- `PUT /system-setting` - 更新系統設定

### 3. `_helpers.py` - 共用工具
**函數:**
- `require_super_admin()` - 要求超級管理員權限
- `get_allowed_scholarship_ids()` - 獲取用戶有權訪問的獎學金 ID
- `apply_scholarship_filter()` - 應用獎學金權限篩選

## 未來遷移計劃

以下端點建議按優先級逐步遷移為獨立模組：

### 優先級 1 - 高頻使用
- [ ] `applications.py` - 申請管理 (8 個端點)
- [ ] `announcements.py` - 公告管理 (5 個端點)
- [ ] `scholarships.py` - 獎學金管理 (11 個端點)

### 優先級 2 - 中等頻率
- [ ] `permissions.py` - 權限管理 (5 個端點)
- [ ] `rules.py` - 規則管理 (11 個端點)
- [ ] `email_templates.py` - 郵件模板 (10 個端點)

### 優先級 3 - 低頻使用
- [ ] `configurations.py` - 配置管理 (5 個端點)
- [ ] `professors.py` - 教授管理 (3 個端點)
- [ ] `bank_verification.py` - 銀行驗證 (2 個端點)

## 遷移指南

### 步驟 1: 創建新模組文件
```python
# 例如: applications.py
from fastapi import APIRouter, Depends
from ._helpers import require_admin, get_allowed_scholarship_ids

router = APIRouter()

@router.get("/applications")
async def get_all_applications(...):
    ...
```

### 步驟 2: 實現端點代碼
- 實現相關的路由函數
- 添加必要的導入語句
- 使用 `_helpers.py` 中的共用函數

### 步驟 3: 更新 `__init__.py`
```python
# 添加新模組的導入
from .applications import router as applications_router

# 包含新路由
router.include_router(applications_router, tags=["Admin - Applications"])

# 更新 MIGRATED_PATHS，排除已遷移的路徑
MIGRATED_PATHS = {
    ...
    "/applications",
    "/applications/history",
}
```

### 步驟 4: 測試
```bash
# 測試導入
python3 -c "from app.api.v1.endpoints import admin; print('OK')"

# 測試應用啟動
python3 -m uvicorn app.main:app --reload
```

## 優點

1. **可維護性** - 每個文件約 200-400 行，易於理解和修改
2. **職責分離** - 清晰的功能劃分
3. **團隊協作** - 減少合併衝突
4. **向後兼容** - 漸進式遷移，不中斷現有功能
5. **代碼重用** - 共用函數統一管理

## 注意事項

- 新端點應直接在相應模組中創建
- 遷移時保持 API 路徑和參數不變，確保前端兼容性
- 所有更改應通過測試驗證

## 相關參考

- College Review 模組: `../college_review/` - 完整的模組化範例
- FastAPI 文檔: https://fastapi.tiangolo.com/tutorial/bigger-applications/
