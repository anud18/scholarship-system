# 續領申請設計（含挑戰申請與名額釋出機制）

**日期**: 2026-05-13
**Status**: Draft for review
**Scope**: 為獎學金系統補完續領申請的學生端體驗、資格判定、與一般申請的銜接，以及「挑戰申請」與「名額釋出/遞補」邏輯

---

## 1. 背景與現狀

### 1.1 已實作的部分

- `ScholarshipType` 已有 6 個續領時間欄位（`renewal_application_start/end_date`、`renewal_professor_review_start/end`、`renewal_college_review_start/end`）與 `is_renewal_enabled` 開關
- `Application` 已有 `is_renewal`、`renewal_year`、`previous_application_id` 欄位
- Manual distribution 已能識別 `renewal_year` 將申請對應到指定年度配額池
- 設計文件 `backend/docs/scholarship_renewal_design.md` 涵蓋時序框架

### 1.2 本設計要補完的部分

- 學生端的續領申請與挑戰申請 UX
- 續領資格的自動判定邏輯（依「上期被核可」紀錄）
- 「保底續領 + 挑戰其他 sub_type」的並存模型
- 挑戰成功時的名額釋出與候補遞補演算法
- 跨年度配額池（如 nstc N 年期計畫池）的續領佔用與釋出邏輯

---

## 2. 核心概念與術語

| 術語 | 定義 |
|---|---|
| 續領申請 (renewal application) | 由「上期被核可且該獎學金支援續領」的學生在續領期間提交，鎖定原 sub_type |
| 挑戰申請 (challenge application) | 已有 approved 續領的學生，於一般申請期間提交，嘗試取得**同一 scholarship_type 內不同 sub_type**；中籤則取代續領 |
| 純新申請 (general application) | 一般申請期間由「無續領者」或「續領被拒絕者」提交的新申請 |
| `allocation_year` | 該名額消耗哪一年的配額（如 nstc-113 即 113 年計畫池） |
| `academic_year` | 學生送出申請的學年（學生身分），與 `allocation_year` 可能不同 |
| 配額池 | `(sub_type, allocation_year)` 二維。nstc 為 N 年期計畫池可跨年；MOE 僅當年 |

---

## 3. 核心約束與不變條件

1. **時序**：續領流程（申請→審查→分發）完整結束後才開放一般申請（與現有 design 一致）
2. **變更粒度**：續領鎖定同 scholarship_type 內的同一個 sub_type；挑戰是同 scholarship_type 下換 sub_type
3. **保底+挑戰**：續領通過 = 取得保底；挑戰成功則自動釋出原 sub_type slot 給候補名單第一名遞補
4. **審查深度**：跟著 `scholarship_configurations` 的 review 角色設定走（professor/college 視配置）
5. **續領資格自動判定**：以「上期被核可的 Application 紀錄」自動列出
6. **續領佔用原入選年度配額**：N 年期計畫獎學金（如 nstc-113）由 113 入選者連續多年續領佔同一池 slot；不消耗 academic_year 新配額
7. **每學生每 (scholarship_type, academic_year) 最終只能一筆 approved**

---

## 4. 整體流程與時間軸

```
 113 學年              ──→  114 學年
─────────────────────────────────────────────────────────────
                       │
                       ├─ [續領申請期間] 學生提交 Application_R
                       │
                       ├─ [續領教授審查]   (if 配置要求)
                       ├─ [續領學院審查]   (if 配置要求)
                       │
                       ├─ [續領分發] 審查通過者全部 approved
                       │           Application_R.renewal_year = 原入選年（如 113）
                       │
                       ├═══════ 續領流程結束 ═══════
                       │
                       ├─ [一般申請期間]
                       │    - 純新申請者：建立 Application（is_renewal=False, challenges_application_id=NULL）
                       │    - 續領成功者：可額外建立 Application_C 挑戰其他 sub_type
                       │
                       ├─ [一般教授審查] → [一般學院審查] → [一般 college_ranking]
                       ├─ [一般分發] 包含「挑戰處理 + 名額釋出 + 候補遞補」
                       │
                       └─ 學期/學年正式開始
```

---

## 5. 資料模型

### 5.1 欄位變更摘要

| 模型 | 欄位 | 用途 | 狀態 |
|---|---|---|---|
| `applications` | `is_renewal: bool` | 標識續領申請 | 已存在 |
| `applications` | `renewal_year: int` | 續領佔用的配額年度（= 原入選年） | 已存在 |
| `applications` | `previous_application_id: FK` | 指向上期被核可的紀錄 | 已存在 |
| `applications` | `challenges_application_id: FK` | 挑戰紀錄指向被挑戰的續領紀錄 | **新增** |
| `applications` | `cancelled_due_to_application_id: FK` | 釋出鏈追蹤（被誰挑戰成功取代） | **新增** |
| `applications.status` | enum 新增 `cancelled_by_challenge` | 因挑戰成功被自動 cancel | **新增 enum 值** |
| `scholarship_types` | `is_renewal_enabled: bool` | 該獎學金是否支援續領 | 已存在 |
| `scholarship_types` | 6 個 renewal 時間欄位 | 續領申請/審查期間 | 已存在 |

### 5.2 資料庫約束

```sql
-- 約束 1: 挑戰申請不可同時 is_renewal=True
ALTER TABLE applications
ADD CONSTRAINT chk_challenge_references_renewal CHECK (
    challenges_application_id IS NULL OR is_renewal = FALSE
);

-- 約束 2: 同學生同 scholarship_type 同學年最多一筆續領
CREATE UNIQUE INDEX uq_student_renewal
ON applications (student_id, scholarship_type_id, academic_year)
WHERE is_renewal = TRUE;

-- 約束 3: 同學生同 scholarship_type 同學年最多一筆挑戰
CREATE UNIQUE INDEX uq_student_challenge
ON applications (student_id, scholarship_type_id, academic_year)
WHERE is_renewal = FALSE AND challenges_application_id IS NOT NULL;

-- 約束 4: cancelled_by_challenge 必須有釋出鏈
ALTER TABLE applications
ADD CONSTRAINT chk_cancelled_by_challenge_link CHECK (
    status != 'cancelled_by_challenge' OR cancelled_due_to_application_id IS NOT NULL
);
```

### 5.3 應用層約束

- `challenges_application_id` 必須指向同一 `student_id` + 同一 `scholarship_type_id` + 同一 `academic_year` 的續領紀錄
- 挑戰紀錄的 `sub_type` 必須 ≠ 對應續領紀錄的 `sub_type`

### 5.4 與現有 UNIQUE 約束的整合

本設計允許同 `(student_id, scholarship_type_id, academic_year)` 同時存在「1 筆續領 + 1 筆挑戰」共兩筆 Application。實作時若現有 schema 有 `UNIQUE(student_id, scholarship_type_id, academic_year)`，須改寫為三條 partial unique indexes：

1. `uq_student_renewal`（is_renewal=TRUE）
2. `uq_student_challenge`（is_renewal=FALSE AND challenges_application_id IS NOT NULL）
3. `uq_student_pure_new`（is_renewal=FALSE AND challenges_application_id IS NULL）

實作計畫中需驗證並 migration 改寫該約束。

---

## 6. 狀態機

### 6.1 續領申請 (Application_R) 狀態流轉

```
student_draft → student_submitted
→ (if 配置要求) professor_review → professor_reviewed
→ (if 配置要求) college_review → college_reviewed
→ approved   (跳過 college_ranking，續領是資格驗證不是擇優選拔)

任一審查階段被拒 → rejected
分發後若挑戰中籤 → cancelled_by_challenge
學生主動撤回 → withdrawn
```

### 6.2 挑戰申請 (Application_C) 狀態流轉

```
student_draft → student_submitted
→ (if 配置要求) professor_review → professor_reviewed
→ (if 配置要求) college_review → college_reviewed
→ (if 配置要求) college_ranking → college_ranked
→ 一般分發後：
     ├─ approved (取得新 sub_type，連動將被挑戰續領設為 cancelled_by_challenge)
     └─ rejected (挑戰失敗，續領仍 approved)

學生主動撤回 → withdrawn（不影響續領）
```

---

## 7. 資格識別與申請建立

### 7.1 續領資格判定 Service

```python
def get_eligible_renewals(student_id: int, current_academic_year: int):
    """
    回傳該學生可續領的 (scholarship_type, sub_type, original_renewal_year) 列表
    """
    return query(Application).filter(
        Application.student_id == student_id,
        Application.academic_year == current_academic_year - 1,
        Application.status == "approved",
        Application.scholarship_type.has(is_renewal_enabled=True),
        Application.scholarship_type.has(is_renewal_application_period=True),
        # 檢查該獎學金計畫期未過
        NOT scholarship_type_expired_for_student(student_id, scholarship_type_id)
    ).all()
```

### 7.2 學生端 UX 動線

```
學生「我的申請」頁面
  ├─ 區塊 1: 可續領的獎學金（續領期間才出現）
  │    顯示：上期 scholarship_type + sub_type、目標學年、截止日
  │    [建立續領申請] 按鈕
  │
  ├─ 區塊 2: 可申請的獎學金（一般申請期間才出現）
  │    對「無 approved 續領」的 scholarship_type：自由選 sub_type
  │    對「已有 approved 續領」的 scholarship_type：顯示「挑戰其他 sub_type」入口，
  │      可選 sub_type 不可為原 sub_type
  │
  └─ 區塊 3: 我的申請歷史（含續領/挑戰標記與狀態）
```

### 7.3 API 端點

```
POST /api/v1/applications/renewal
  body: { previous_application_id }
  validations:
    1. previous 屬於該學生且 status=approved
    2. scholarship_type.is_renewal_enabled
    3. 目前在 renewal_application_period
    4. 該學生對此 scholarship_type 在 current_academic_year 尚未建立任何 Application
  creates: Application(is_renewal=True, sub_type=previous.sub_type,
                       previous_application_id=previous.id,
                       renewal_year=previous.renewal_year or previous.academic_year)

POST /api/v1/applications/challenge
  body: { renewal_application_id, target_sub_type }
  validations:
    1. renewal_application 屬於該學生且 status=approved 且 is_renewal=True
    2. target_sub_type ≠ renewal_application.sub_type
    3. target_sub_type 存在於該 scholarship_configuration.quotas
    4. 目前在 general application_period
    5. 該學生對此 (scholarship_type, academic_year) 尚未建立挑戰申請
  creates: Application(is_renewal=False, sub_type=target_sub_type,
                       challenges_application_id=renewal_application.id)
```

---

## 8. 續領階段審查與分發

### 8.1 審查路由

```python
def get_active_review_period(application, stage):
    sch = application.scholarship_type
    if application.is_renewal:
        return getattr(sch, f"renewal_{stage}_start"), getattr(sch, f"renewal_{stage}_end")
    return getattr(sch, f"{stage}_start"), getattr(sch, f"{stage}_end")
```

教授/學院端的待審清單依「目前是哪個審查期間 + Application.is_renewal」過濾。

### 8.2 續領分發

```
規則：審查通過者 → 全部 approved；不需要 college_ranking 與 waitlisted 狀態

理由：續領是「資格驗證」而非「擇優選拔」；實務上續領人數 ≤ 上期配額 ≤ 當年配額池，
     不會出現配額不足。
```

---

## 9. 一般階段分發演算法

### 9.1 演算法總覽

```python
def execute_general_distribution(scholarship_type, academic_year):
    # 步驟 1: 計算各 (sub_type, allocation_year) pool 的可用配額
    #   total_quota[(sub_type, year)] - used_by_renewal[(sub_type, year)]

    # 步驟 2: 對每個 sub_type，收集 college_ranked 候選名單（依排名）
    #   候選人 = is_renewal=False 的 Application（含挑戰 + 純新）

    # 步驟 3: 第一輪分發 — 候選名單依排名分配到該 sub_type 可用 pool
    #   nstc 可分到多個 allocation_year（依政策順序）
    #   moe_1w 僅當年
    #   分到時 set ranking_item.allocation_year = pool_year, application.status = approved

    # 步驟 4: 釋出處理
    for challenge_app in all_approved_challenges:
        renewal_app = challenge_app.challenges_application
        renewal_app.status = 'cancelled_by_challenge'
        renewal_app.cancelled_due_to_application_id = challenge_app.id
        released[(renewal_app.sub_type, renewal_app.renewal_year)] += 1

    # 步驟 5: 候補遞補（同 sub_type 候選名單下一位）
    for (sub_type, year), count in released.items():
        next_candidates = (ranking_items
            .filter(sub_type=sub_type,
                    application.status == 'college_ranked')  # 排除已 approved / rejected / withdrawn
            .order_by(rank)
            .limit(count))
        for c in next_candidates:
            c.application.status = 'approved'
            c.allocation_year = year   # 學生 academic_year 不變

    # 步驟 6: 收尾 — 餘下未中籤的 college_ranked 標記 rejected（依政策）
```

### 9.2 演算法重點

- **候選名單按 sub_type 統一排名**：候選人對「哪一年配額」沒選擇權，分到哪個 allocation_year 由配額池順序決定
- **挑戰申請者只在 challenge 的 sub_type 上排名**：A 想挑戰 moe_1w 就在 moe_1w 候選名單裡
- **遞補不跨 sub_type**：釋出 nstc 只找 nstc 候選人
- **釋出鏈不會無限連鎖**：釋出僅發生在「續領 sub_type」的 pool；該 sub_type 候選名單中不會出現「挑戰該 sub_type 失敗者」（因為挑戰申請的 sub_type 必須 ≠ 續領 sub_type，所以挑戰者不會在自己原 sub_type 的候選名單中）。因此遞補的候選人必定是 `challenges_application_id IS NULL` 的純新申請者，他們被遞補不會觸發新的釋出。

### 9.3 範例追蹤

```
情境：博士生獎學金, 114 學年
配額池:
  nstc[113]: 10 slot (113 年計畫 N 年期)
  nstc[114]: 8 slot
  moe_1w[114]: 6 slot

續領階段 (renewal_year=113)：10 人 approved 佔 nstc[113]
其中 A、B 將在一般階段挑戰 moe_1w

一般階段候選名單 (academic_year=114)：
  nstc 候選: M, N, O, P, Q, R, S, T, U, V (依排名)
  moe_1w 候選: A(挑戰), B(挑戰), X, Y, Z, AA, BB, CC

第一輪分發：
  nstc 配額剩 nstc[113]=0, nstc[114]=8 → M~T 分到 nstc[114]，U、V 暫未中
  moe_1w 配額 6 → A, B, X, Y, Z, AA 中籤

釋出處理：
  A 挑戰中 → A 的 nstc-113 續領 cancelled → released[(nstc, 113)] = 1
  B 挑戰中 → B 的 nstc-113 續領 cancelled → released[(nstc, 113)] = 2

候補遞補：
  U.status=approved, allocation_year=113
  V.status=approved, allocation_year=113
  注意：U、V 的 Application.academic_year 仍是 114

最終：
  nstc[113] approved: 8 原續領 + U + V = 10 ✓
  nstc[114] approved: M~T = 8 ✓
  moe_1w[114] approved: A, B, X, Y, Z, AA = 6 ✓
```

---

## 10. 邊界情境

| # | 情境 | 處理方式 |
|---|---|---|
| 1 | 上期得獎但 scholarship_type.is_renewal_enabled=False | 不顯示續領入口 |
| 2 | N 年期計畫期已到 | RenewalEligibilityService 比對 scholarship_type 設定的續領上限年數；超過則不顯示 |
| 3 | 學生續領期間未送出 | 自動放棄續領；一般申請可走純新申請；失去保底 |
| 4 | 續領審查被拒 | Application_R.status=rejected；可在一般申請以新申請身分參加（不能挑戰） |
| 5 | 續領通過但學生想撤回 | PATCH status=withdrawn；slot 自動進入候補遞補池 |
| 6 | 挑戰申請想撤回 | Application_C.status=withdrawn；不影響續領 |
| 7 | 續領期間想直接申請其他 sub_type | 拒絕；換 sub_type 須在一般申請期間提交挑戰申請 |
| 8 | 嘗試建立第二筆挑戰 | 拒絕；每 (student, scholarship_type, academic_year) 最多一筆挑戰 |
| 9 | 跨 scholarship_type 同時拿兩個獎學金 | 系統層級限制：每學年每學生最多一個 approved |
| 10 | 釋出後候補名單為空 | nstc[113] slot 空缺，留作下次補發 |
| 11 | 跨學年連續續領（114→115） | 115 年 Application_R.previous_application_id 指向 114 年 approved；renewal_year 仍指原計畫年 |
| 12 | 114 挑戰成功 moe_1w，115 想再續領 nstc | 不行：A 的 nstc 計畫已在 114 結束。要走 115 純新申請 |
| 13 | manual distribution 已執行後追加挑戰 | 此設計假設一般分發是一次性 batch，不支援執行後追加 |
| 14 | renewal_year 對應 quota cell 不存在 | 拋出 RenewalQuotaNotFoundError，不靜默 fallback |

---

## 11. 錯誤訊息（給學生）

```
情境 7: "續領期間僅能就上期得獎的 sub_type 申請續領；如需更換 sub_type，請於一般申請期間提交挑戰申請。"
情境 8: "您已對「<scholarship_name>」<academic_year> 學年提交挑戰申請，每個獎學金每學年僅能挑戰一次。"
情境 12: "此 scholarship 的計畫期已結束；如欲繼續申請，請於一般申請期間以新申請身分提交。"
```

---

## 12. 監控與稽核

- 每筆 `cancelled_by_challenge` 必有 `cancelled_due_to_application_id`（資料庫約束 4 強制）
- 背景檢查（cron / health endpoint）：每筆 approved 挑戰申請的 `challenges_application_id` 必須指向 `cancelled_by_challenge` 狀態紀錄
- manual distribution batch 結束輸出統計：
  - 續領通過數
  - 挑戰成功數
  - 釋出 slot 數（依 sub_type × allocation_year 切分）
  - 遞補成功數
  - 留作補發數
  - 不變條件：釋出數 = 遞補數 + 留作補發數

---

## 13. 與現有系統的整合點

- **manual_distribution_service**：需擴充以支援步驟 4-5（挑戰處理與遞補）
- **roster_service**：續領紀錄會依 `renewal_year`（= allocation_year）落入對應的 payment_roster
- **CollegeRankingItem.allocation_year**：已存在，遞補時填入
- **batch import service**：已支援 `renewal_year` 欄位讀取
- **ScholarshipType 期間方法**：已存在 `is_renewal_application_period()` 等；新 endpoint 直接呼叫

---

## 14. Admin UI 設計

本章描述管理員端與學生端的關鍵畫面，重點在「續領的目標年度（renewal_year / allocation_year）」與 sub_type 的視覺化呈現。

### 14.1 續領分發結果頁（新增）

續領分發是自動的（通過審查 = approved），管理員不需要逐筆勾選，但需要結果檢視頁。

```
┌──────────────────────────────────────────────────────────┐
│ 續領分發結果 — 博士生獎學金 — 114 學年                        │
├──────────────────────────────────────────────────────────┤
│ ▌續領通過名單（按 sub_type × renewal_year 分組）             │
│                                                          │
│  nstc · 計畫年度 113  (10/10 slot 已用)                    │
│    ├─ 王小明 (APP-114-0-00001, 原 APP-113-0-00007)         │
│    ├─ 李大華 (APP-114-0-00002, 原 APP-113-0-00009)         │
│    ├─ ...                                                │
│    └─ 林小芳 (APP-114-0-00010) ⚠ 同時提交挑戰 moe_1w        │
│                                                          │
│  nstc · 計畫年度 112  (3/3 slot 已用)                       │
│    ├─ 張三 (APP-114-0-00011, 原 APP-112-0-00003)          │
│    └─ ...                                                │
│                                                          │
│  moe_1w · 計畫年度 114  (0 人續領，moe_1w 僅當年無多年池)    │
│                                                          │
│ ▌續領被拒名單                                                │
│  (空 / 列表)                                              │
│                                                          │
│ ▌總結                                                       │
│  通過: 13  拒絕: 0  撤回: 0                                │
│                                                          │
│ [匯出名單] [回到主面板]                                       │
└──────────────────────────────────────────────────────────┘
```

**呈現要點**

- 依 `sub_type × renewal_year` 分組顯示（讓管理員清楚看到「113 計畫池有幾人、112 計畫池有幾人」）
- 每筆續領紀錄顯示：當期 application_id、原入選年的 application_id（previous_application_id）
- 若該續領者已提交挑戰申請，特別標註 ⚠

### 14.2 一般階段手動分發頁（修改 ManualDistributionPanel）

```
┌────────────────────────────────────────────────────────────────┐
│ 手動分發 — 博士生獎學金 — 114 學年                                │
├────────────────────────────────────────────────────────────────┤
│ ▌續領已佔用（不可改動）                                            │
│                                                                │
│  nstc · 計畫年度 113  10/10 → 王小明、李大華、...、林小芳*       │
│  nstc · 計畫年度 112   3/3 → 張三、...                          │
│  moe_1w · 計畫年度 114  0/0 (續領無佔用)                         │
│                                                                │
│  *林小芳已提交挑戰 moe_1w                                        │
│                                                                │
│ ▌剩餘可分配配額                                                   │
│  nstc · 計畫年度 114 (新核): 0/8                                 │
│  moe_1w · 計畫年度 114    : 0/6                                  │
├────────────────────────────────────────────────────────────────┤
│ ▌一般分發 - 候選名單（含挑戰申請）                                 │
│                                                                │
│ ┌────┬──────┬───────┬─────────────────┬─────┬─────┬─────┐    │
│ │排名│ 學生  │ 類型  │ 保底/註記          │nstc │moe  │... │    │
│ │    │      │       │                  │ 114 │1w   │     │    │
│ │    │      │       │                  │     │114  │     │    │
│ ├────┼──────┼───────┼─────────────────┼─────┼─────┼─────┤    │
│ │ 1  │陳小華│ 純新   │ —                │ ☑  │ ☐  │ ... │    │
│ │ 2  │林小芳│ 挑戰   │ 🛡 保底 nstc-113 │灰禁 │ ☑  │ ... │    │
│ │ 3  │張小明│ 純新   │ —                │ ☑  │ ☐  │ ... │    │
│ │ 4  │許大強│ 純新   │ —                │ ☑  │ ☐  │ ... │    │
│ │... │ ...  │ ...   │ ...              │ ... │ ... │ ... │    │
│ └────┴──────┴───────┴─────────────────┴─────┴─────┴─────┘    │
│                                                                │
│ ▌釋出與遞補預覽（即時計算）                                         │
│  ⚠ 林小芳 挑戰 moe_1w 成功                                       │
│     ↳ 釋出 nstc · 計畫年度 113 slot                              │
│     ↳ 自動遞補：黃小強（純新申請，排 #9）→ 分配至 nstc · 113       │
│                                                                │
│ [儲存配置] [預覽分發結果] [確認分發]                                │
└────────────────────────────────────────────────────────────────┘
```

**呈現與互動規則**

1. **「續領已佔用」區塊唯讀**：清楚列出每個 `(sub_type, renewal_year)` 的佔用情況；管理員無法勾選或取消
2. **挑戰申請者識別**：候選名單列「類型」欄顯示「挑戰」+ 「保底/註記」欄顯示 `🛡 保底 <sub_type>-<renewal_year>`
3. **挑戰者的保底 sub_type 欄禁用**：林小芳的 nstc 欄灰色 disabled（她已有 nstc-113 保底，分到自己原 sub_type 沒意義）
4. **配額欄位的 allocation_year 標示**：欄位 header 顯示「nstc · 114」、「nstc · 113 補發」等，讓管理員清楚每個 slot 屬於哪一年配額池
5. **即時釋出與遞補預覽**：勾選變動時系統即時計算釋出鏈與建議遞補對象
6. **儲存後仍可調整**：直到「確認分發」前都可改動；確認後鎖定

### 14.3 學生「我的申請紀錄」頁

```
┌──────────────────────────────────────────────────────────────┐
│ 我的申請紀錄                                                    │
├──────────────────────────────────────────────────────────────┤
│ 114 學年 - 博士生獎學金 - 續領申請 (sub_type: nstc)              │
│   APP-114-0-00010                                            │
│   狀態：已取消（因挑戰升級）                                       │
│   原計畫年度：113                                                │
│   ├─ 銜接自：APP-113-0-00007 (113 學年 nstc 續領核可)            │
│   └─ 被取代於：APP-114-0-00xxx（挑戰申請 moe_1w 成功）            │
│                                                              │
│ 114 學年 - 博士生獎學金 - 挑戰申請 (sub_type: moe_1w)            │
│   APP-114-0-00xxx                                            │
│   狀態：已核可                                                    │
│   分發計畫年度：114                                                │
│   └─ 取代之續領：APP-114-0-00010 (nstc, 計畫年度 113)            │
│                                                              │
│ 113 學年 - 博士生獎學金 - 續領申請 (sub_type: nstc)              │
│   APP-113-0-00007                                            │
│   狀態：已核可（已被 114 學年續領延續）                              │
│   原計畫年度：113                                                  │
└──────────────────────────────────────────────────────────────┘
```

**呈現要點**

- 每筆都明示 `sub_type` 與 `renewal_year / allocation_year`
- 「銜接自」「被取代於」雙向鏈接，串起跨學年的續領鏈與當期的挑戰取代關係
- `cancelled_by_challenge` 狀態以「已取消（因挑戰升級）」表達，加上對應的取代紀錄連結

### 14.4 顏色與圖示規範

- 🛡 = 已有保底（適用挑戰申請者）
- ⚠ = 需注意的情境（挑戰已提交、釋出待處理）
- 灰禁 = 不可勾選的欄位（已被續領佔用 / 自己原 sub_type）
- 綠底 = 已分配/已核可
- 黃底 = 候補預覽（即將遞補）
- 紅底 = 釋出對象（即將 cancel）

### 14.5 API 變更摘要（支援上述 UI）

```
GET  /api/v1/admin/renewal/distribution-result
  query: scholarship_type_id, academic_year
  returns: 按 (sub_type, renewal_year) 分組的續領通過/拒絕名單

GET  /api/v1/admin/manual-distribution/state
  query: scholarship_type_id, academic_year
  returns: {
    renewal_allocations: [{sub_type, renewal_year, applications: [...]}],
    available_quotas: [{sub_type, allocation_year, total, used}],
    candidates: [{rank, application_id, student, is_challenge, renewal_app_id, ...}]
  }

POST /api/v1/admin/manual-distribution/preview
  body: {allocations: [{application_id, sub_type, allocation_year}]}
  returns: {
    release_chain: [{cancelled_application_id, freed_slot, suggested_fill: {application_id}}]
  }
```

---

## 15. 未涵蓋（未來工作）

- **半路加入續領**：學生轉學/重考導致中途進入系統，無上期紀錄但有舊系統續領資格 → 需管理者手動匯入續領名單（現有 batch import 已支援）
- **多 scholarship_type 之間的優先序**：同學生在不同 scholarship_type 都有續領+挑戰，跨 scholarship 的衝突處理（目前限制為「每學年每學生最多一個 approved」即可，不需特殊處理）
- **挑戰失敗的告知與補救**：UI 上的通知/解釋頁面（屬 UX 範疇，不在此設計）
