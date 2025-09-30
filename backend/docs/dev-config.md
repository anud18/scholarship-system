# 開發模式配置指南

## 環境變數設定

在 `.env` 檔案中加入以下設定：

```bash
# Development mode settings
DEBUG=true
ENVIRONMENT=development

# Scholarship testing overrides (set to false in production)
ALWAYS_OPEN_APPLICATION=true
BYPASS_WHITELIST=true
MOCK_APPLICATION_PERIOD=true
```

## 申請期間調整

### 1. 自動開放申請期間
設定 `ALWAYS_OPEN_APPLICATION=true` 時，所有獎學金都會跳過申請期間檢查。

### 2. 模擬申請期間
初始化腳本會自動設定當前時間前後30天為申請期間。

### 3. 手動調整申請期間
可以直接在資料庫中修改 `scholarship_types` 表的 `application_start_date` 和 `application_end_date`。

## 白名單機制調整

### 1. 關閉白名單檢查
設定 `BYPASS_WHITELIST=true` 時，所有學生都能申請需要白名單的獎學金。

### 2. 新生獎學金白名單
- 開發模式下，新生獎學金的 `whitelist_enabled` 自動設為 `false`
- 生產模式下，需要手動設定白名單學生ID

### 3. 手動管理白名單
可以透過以下 SQL 更新白名單：

```sql
-- 啟用白名單並新增學生
UPDATE scholarship_types
SET whitelist_enabled = true,
    whitelist_student_ids = '[1, 2, 3]'  -- 學生ID列表
WHERE code = 'undergraduate_freshman';

-- 關閉白名單
UPDATE scholarship_types
SET whitelist_enabled = false
WHERE code = 'undergraduate_freshman';
```

## 快速測試指令

```bash
# 重新初始化資料庫（包含開發友好的獎學金設定）
python -m app.core.init_db

# 檢查當前獎學金狀態
docker exec -it scholarship-backend python -c "
from app.core.init_db import *
from app.models.scholarship import ScholarshipType
async def check():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ScholarshipType))
        scholarships = result.scalars().all()
        for s in scholarships:
            print(f'{s.name}: 申請期間={s.is_application_period}, 白名單={s.whitelist_enabled}')
import asyncio
asyncio.run(check())
"
```

## 開發模式特性

1. **申請期間**: 自動設定為當前時間前後30天
2. **白名單**: 開發模式下預設關閉
3. **日誌**: 詳細記錄資格檢查過程
4. **彈性設定**: 可透過環境變數快速調整
