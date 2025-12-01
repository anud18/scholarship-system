# 遞補機制系統 (Alternate Promotion System)

## 概述

遞補機制系統設計用來在造冊產生過程中自動用合格的備取學生取代失格的正取學生。這確保當正取學生失去資格時，獎學金名額仍能被完整利用。

**目前狀態**：基礎架構已完成，但**尚未整合**到自動造冊產生流程中。

---

## 架構

### 1. 資料模型

#### CollegeRankingItem.backup_allocations（備取分配記錄）
儲存未被初始錄取之學生的備取分配資訊。

**位置**：`app/models/college_review.py`

**資料結構**：
```python
backup_allocations = Column(JSON, nullable=True)

# 格式：
[
  {
    "sub_type": "nstc",           # 獎學金子類型
    "backup_position": 1,          # 備取排序（第1備取、第2備取等）
    "college": "EE",              # 學院代碼
    "allocation_reason": "備取第1名 nstc-EE"
  },
  {
    "sub_type": "moe_1w",
    "backup_position": 2,
    "college": "CS",
    "allocation_reason": "備取第2名 moe_1w-CS"
  }
]
```

**生成時機**：矩陣分發時產生備取名單
**建立位置**：`matrix_distribution.py:284-295`

#### PaymentRosterItem.backup_info（造冊備取資訊快照）
造冊產生時的備取資訊快照。

**位置**：`app/models/payment_roster.py:228-238`

**資料結構**：同上 `backup_allocations` 格式
**用途**：造冊稽核軌跡的歷史記錄
**填入時機**：造冊產生時的 `_create_roster_item()` 方法

---

### 2. 服務層

#### AlternatePromotionService（遞補服務）
**位置**：`app/services/alternate_promotion_service.py`

**用途**：當正取學生失格時，尋找並遞補合格的備取學生。

**核心方法**：

##### `find_and_promote_alternate()`
遞補的主要進入點。

**參數**：
- `ranking_item`：失格學生的 CollegeRankingItem
- `original_application`：失格學生的申請記錄
- `scholarship_config`：獎學金配置
- `ineligible_reason`：失格原因
- `skip_eligibility_check`：是否跳過特殊資格檢查（用於手動覆蓋）

**處理流程**：
1. 將原學生的 `ranking_item` 標記為 `rejected`（已拒絕），註記失格原因
2. 從 `backup_allocations` 中尋找符合資格的備取學生
3. 更新備取學生的 `ranking_item` 為 `allocated`（已錄取）
4. 回傳遞補結果

**回傳值**：
```python
{
  "promoted_item": CollegeRankingItem,  # 被遞補的備取學生
  "original_student": str,               # 失格學生的姓名
  "promoted_student": str,               # 被遞補學生的姓名
  "checked_count": int                   # 檢查過的備取人數
}
```

##### `_find_eligible_alternate()`
內部方法，用來搜尋符合資格的下一個備取學生。

**搜尋流程**：
1. 取得此排名中所有具有 `backup_allocations` 的 CollegeRankingItem
2. 依 `sub_type` 進行篩選（如需要）
3. 依 `backup_position` 升序排序（備取順序）
4. 進行白名單檢查（如果啟用）
5. 套用獎學金特定資格規則（由外掛程式委派處理）
6. 回傳第一位符合資格的備取學生

**資格檢查項目**：
- ✅ 尚未被錄取（`is_allocated = False`）
- ✅ 未被拒絕（`status != "rejected"`）
- ✅ 在白名單中（若白名單已啟用）
- ✅ 符合獎學金特定規則（如 PhD 要求）

---

### 3. 整合點

#### 矩陣分發（Matrix Distribution）
**時機**：學院排名確定後
**服務**：`MatrixDistributionService.execute_matrix_distribution()`
**動作**：為未被錄取的學生建立 `backup_allocations`

**程式碼位置**：`backend/app/services/matrix_distribution.py:284-295`

```python
# 當名額滿額時，後續學生標記為備取
if item.backup_allocations is None:
    item.backup_allocations = []

item.backup_allocations.append({
    "sub_type": sub_type_code,
    "backup_position": backup_count,
    "college": college_code,
    "allocation_reason": f"備取第{backup_count}名 {sub_type_code}-{college_code}"
})
```

#### 造冊產生（Roster Generation）
**時機**：產生獎學金造冊時
**服務**：`RosterService.generate_roster()`
**目前行為**：
- ✅ 從 CollegeRankingItem 讀取 `backup_allocations`
- ✅ 儲存到 PaymentRosterItem.backup_info
- ❌ **未自動呼叫 AlternatePromotionService**

**程式碼位置**：`backend/app/services/roster_service.py:769-788`

```python
# 目前只儲存備取資訊，沒有自動遞補
if roster.ranking_id:
    ranking_item = db.query(CollegeRankingItem).filter(...).first()

    if ranking_item and ranking_item.backup_allocations:
        backup_info = ranking_item.backup_allocations
        logger.info(f"申請 {application.id} 有 {len(backup_info)} 位備取")

# 缺失：當學生失格時呼叫 AlternatePromotionService
```

---

## 目前工作流程

### 第一階段：矩陣分發（產生備取資料）

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 執行矩陣分發                                                   │
│    execute_matrix_distribution(ranking_id)                       │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 依子類型優先順序 (nstc → moe_1w → moe_2w)                    │
│    依學院別 (EE, CS, ...)                                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. 檢查各學院名額                                                 │
│    - 有名額可用 → 錄取 (is_allocated=True)                       │
│    - 名額已滿 → 加入備取名單                                      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 結果：CollegeRankingItem 已填入資訊                               │
│ - 正取學生：is_allocated=True                                    │
│ - 備取學生：backup_allocations=[{...}]                           │
└─────────────────────────────────────────────────────────────────┘
```

### 第二階段：造冊產生（目前無自動遞補）

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. 產生造冊                                                       │
│    generate_roster(scholarship_configuration_id, period_label)  │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 2. 取得符合條件的申請                                             │
│    - 矩陣模式：只取 is_allocated=True 的學生                     │
│    - 其他模式：所有核准的申請                                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 3. 逐一檢查每位申請者                                             │
│    - 驗證學籍狀態（API 呼叫）                                     │
│    - 驗證獎學金資格規則                                           │
│    - 檢查銀行帳戶資訊                                             │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 4. 建立造冊明細                                                   │
│    - 若失格：is_included=False + 失格原因                        │
│    - 儲存備取資訊                                                 │
│    ❌ 缺失：呼叫 AlternatePromotionService                        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│ 結果：造冊中包含失格學生                                           │
│ - 名額未被充分利用                                               │
│ - 備取學生仍未被錄取                                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## 缺失的整合（需要新增的功能）

要啟用自動遞補機制，需要修改 `RosterService.generate_roster()`：

### 建議的整合點

**位置**：`backend/app/services/roster_service.py` 約 730-742 行

**目前程式碼**：
```python
# 1. 檢查學籍驗證狀態
if verification_status != StudentVerificationStatus.VERIFIED:
    is_included = False
    exclusion_reason = f"學籍驗證未通過: {verification_status.value}"

# 2. 檢查獎學金資格規則
elif eligibility_result and not eligibility_result.get("is_eligible", True):
    is_included = False
    failed_rules = eligibility_result.get("failed_rules", [])
    exclusion_reason = f"不符合獎學金規則: {'; '.join(failed_rules)}"

# 目前只是標記為失格，沒有進行遞補
```

**建議的增強**：
```python
# 在檔案頂部新增 import
from app.services.alternate_promotion_service import AlternatePromotionService

# 在 generate_roster() 方法中
alternate_service = AlternatePromotionService(self.db)

# 判定失格後
if not is_included and roster.ranking_id:
    # 取得此申請對應的排名項目
    ranking_item = self.db.query(CollegeRankingItem).filter(
        and_(
            CollegeRankingItem.application_id == application.id,
            CollegeRankingItem.ranking_id == roster.ranking_id,
            CollegeRankingItem.is_allocated == True
        )
    ).first()

    if ranking_item:
        # 嘗試尋找並遞補備取學生
        promotion_result = alternate_service.find_and_promote_alternate(
            ranking_item=ranking_item,
            original_application=application,
            scholarship_config=scholarship_config,
            ineligible_reason=exclusion_reason,
            skip_eligibility_check=False
        )

        if promotion_result:
            # 記錄遞補日誌
            audit_service.log_roster_operation(
                roster_id=roster.id,
                action=RosterAuditAction.ITEM_UPDATE,
                title=f"自動遞補：{promotion_result['promoted_student']} 遞補 {promotion_result['original_student']}",
                user_id=created_by_user_id,
                user_name=user_name,
                description=f"原學生失格原因：{exclusion_reason}",
                metadata={
                    "original_application_id": application.id,
                    "promoted_item_id": promotion_result["promoted_item"].id,
                    "checked_count": promotion_result["checked_count"]
                },
                level=RosterAuditLevel.INFO,
                tags=["alternate_promotion", "automatic"],
                db=self.db,
            )

            # 跳過為失格學生建立造冊明細
            # 被遞補的學生將在下一個迴圈中被處理
            disqualified_count += 1
            continue
```

---

## 獎學金特定資格規則

系統支援透過外掛程式來實現獎學金特定的資格檢查。

### PhD 獎學金外掛程式

**位置**：`app/services/plugins/phd_eligibility_plugin.py`

**規則**：PhD 獎學金的備取學生必須來自與失格學生相同的系所，且修業年限不超過 36 個月。

**函式**：
- `is_phd_scholarship()`：檢查是否為 PhD 特定獎學金
- `check_phd_alternate_eligibility()`：驗證備取學生資格

**使用方式**（在 AlternatePromotionService 中）：
```python
if is_phd_scholarship(scholarship_config):
    is_eligible, rejection_reason = check_phd_alternate_eligibility(
        db=self.db,
        student_data=alternate_student_data,
        original_student_data=original_student_data,
        scholarship_config=scholarship_config,
        max_months=36
    )

    if not is_eligible:
        logger.info(f"備取學生不符合 PhD 資格：{rejection_reason}")
        continue  # 嘗試下一位備取
```

### 新增獎學金資格規則

若要為其他獎學金新增資格規則：

1. 建立外掛程式檔案：`app/services/plugins/{獎學金名稱}_eligibility_plugin.py`
2. 實作偵測函式：`is_{獎學金名稱}_scholarship(config) -> bool`
3. 實作資格檢查函式：`check_{獎學金名稱}_alternate_eligibility(...) -> Tuple[bool, str]`
4. 在 `AlternatePromotionService._find_eligible_alternate()` 中註冊

---

## API 端點（待實作）

### 手動遞補端點（建議）

```python
@router.post("/rosters/{roster_id}/items/{item_id}/promote-alternate")
async def manually_promote_alternate(
    roster_id: int,
    item_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    手動觸發某個失格造冊明細的遞補機制

    使用場景：管理員檢視造冊並決定遞補備取學生
    """
    # 實作待補
```

### 批次遞補端點（建議）

```python
@router.post("/rosters/{roster_id}/promote-all-alternates")
async def batch_promote_alternates(
    roster_id: int,
    current_user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    批次處理所有失格項目並進行遞補

    使用場景：造冊產生後，自動填補所有空缺名額
    """
    # 實作待補
```

---

## 測試場景

### 測試案例 1：基本遞補
**前提條件**：
- 學生 A 被錄取為 nstc-EE（正取）
- 學生 B 在備取名單中：nstc-EE，位置=1

**事件**：學生 A 失格（已畢業）

**預期結果**：
- 學生 A：`is_allocated=False`，`status="rejected"`
- 學生 B：`is_allocated=True`，`status="allocated"`
- 造冊中包含學生 B，不包含學生 A

### 測試案例 2：PhD 系所限制
**前提條件**：
- 學生 A（EE 系）被錄取為 PhD 獎學金
- 學生 B（CS 系）備取，位置=1
- 學生 C（EE 系）備取，位置=2

**事件**：學生 A 失格

**預期結果**：
- 學生 B 被跳過（系所不符）
- 學生 C 被遞補（系所相同）

### 測試案例 3：無合格備取
**前提條件**：
- 學生 A 被錄取
- 所有備取學生也都失格（已畢業/休學）

**事件**：學生 A 失格

**預期結果**：
- 造冊明細標記為失格
- 名額未被填補
- 稽核日誌記錄「無合格備取學生」

### 測試案例 4：白名單執行
**前提條件**：
- 獎學金已啟用白名單
- 學生 A 被錄取（在白名單中）
- 學生 B 備取，位置=1（不在白名單中）
- 學生 C 備取，位置=2（在白名單中）

**事件**：學生 A 失格

**預期結果**：
- 學生 B 被跳過（不在白名單中）
- 學生 C 被遞補（在白名單中）

---

## 資料庫遷移

### 遷移：新增 backup_allocations 至 CollegeRankingItem
**檔案**：`alembic/versions/cd2d48ec6d34_add_backup_allocations_to_ranking_items.py`
**內容**：新增 JSON 欄位儲存備取分配資訊

### 遷移：新增 backup_info 至 PaymentRosterItem
**檔案**：`alembic/versions/07e9ece93d90_add_backup_info_to_payment_roster_items.py`
**內容**：新增 JSON 欄位儲存造冊時的備取快照

---

## 稽核軌跡

所有遞補動作應透過 `RosterAuditLog` 進行記錄：

```python
audit_service.log_roster_operation(
    roster_id=roster.id,
    action=RosterAuditAction.ITEM_UPDATE,
    title=f"遞補：{被遞補學生} 遞補 {失格學生}",
    user_id=user_id,
    user_name=user_name,
    description=f"原學生失格：{原因}。檢查了 {檢查人數} 位備取",
    old_values={"錄取學生": "原學生"},
    new_values={"錄取學生": "被遞補學生"},
    metadata={
        "original_application_id": 原申請 ID,
        "promoted_application_id": 被遞補申請 ID,
        "backup_position": 備取位置,
        "checked_count": 檢查人數
    },
    level=RosterAuditLevel.INFO,
    tags=["alternate_promotion"],
    db=db
)
```

---

## 未來增強功能

### 1. 多層遞補鏈
若被遞補的備取學生也失格，繼續遞補：
- 位置 1 失格 → 遞補位置 2
- 位置 2 失格 → 遞補位置 3
- 以此類推...

### 2. 通知系統
向以下人員發送通知：
- 失格學生（獎學金已取消）
- 被遞補學生（獲得獎學金）
- 管理員（遞補摘要報告）

### 3. 手動覆蓋介面
前端介面供管理員：
- 查看遞補建議
- 手動核准/拒絕遞補
- 帶有正當理由的覆蓋資格檢查

### 4. 遞補統計儀表板
追蹤並視覺化：
- 遞補成功率
- 平均檢查的備取人數
- 最常見的失格原因
- 遞補前後的名額填補率

---

## 總結

遞補機制系統提供了穩健的框架來管理當正取學生失格時的獎學金名額分配。雖然基礎架構已完成，但整合到自動造冊產生流程仍待進行。

**後續步驟**：
1. 將 `AlternatePromotionService` 整合至 `RosterService.generate_roster()`
2. 實作手動遞補 API 端點
3. 新增前端介面管理遞補
4. 所有獎學金類型的全面測試
5. 使用者文件和培訓教材

**相關參考**：
- `backend/app/services/alternate_promotion_service.py` - 核心遞補邏輯
- `backend/app/services/matrix_distribution.py` - 備取分配產生
- `backend/app/services/roster_service.py` - 造冊產生（整合點）
- `backend/app/models/college_review.py` - CollegeRankingItem 模型
- `backend/app/models/payment_roster.py` - PaymentRosterItem 模型
