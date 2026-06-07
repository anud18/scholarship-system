# 配置層級共用名額池（跨配置國科會額度借用）

- **日期：** 2026-06-08
- **狀態：** 設計已核准 — 待規格審查（已經過對抗式程式碼審查強化）
- **範圍：** 手動分發、獎學金配置、造冊產生
- **分支：** `worktree-config-shared-quota-pools`

> 本檔為英文正本 `2026-06-08-config-shared-quota-pools-design.md` 的繁體中文翻譯。程式碼、欄位名稱、檔案路徑、函式名稱、JSON 一律保留原文；以英文正本為準。

---

## 1. 問題

當為某學年度發放獎學金時（例如 `phd_115`），管理員需要動用**前面幾年剩下的國科會（NSTC）額度**。目前這個「借用前面幾年」的能力以兩種互相矛盾的方式表達，而且都不符合管理員的心智模型：

- 每個配置帶有 `prior_quota_years`，例如 `{"nstc": [113, 112]}` — 一個前面年份的**清單**，且僅限同一獎學金類型。
- 被消耗的年度以一個裸整數 `CollegeRankingItem.allocation_year` 記錄。
- 前面年份的計畫編號（以及死碼中的前面年份名額總數）被**複製到當前年度的配置裡**（`project_numbers["nstc"]["113"]`）。

管理員真正想要的是：**在一個配置上，選擇要與哪些前面年份的配置共用名額 — 用配置代碼選、依子類型 (sub_type)、不指定數量** — 並讓該額度表現為**單一即時共用池**：若來源配置釋出一個名額（某得獎者被撤銷），借用方配置立即多出一個名額。

## 2. 目標

1. 以**明確的配置對配置連結**（`shared_quota_sources`）取代年份清單借用機制（`prior_quota_years`）；以**配置代碼**選取、**依子類型**、**可跨類型**、**僅限前面年份**、**不指定數量**。
2. 讓配置的額度成為**即時、全域、共用的池**：`remaining(config, sub_type) = 總數 − 任何地方對該配置的每一筆消耗`。任一處釋出名額，整個池在所有地方即時更新。
3. 記錄**每個已分發名額消耗了哪個配置**（`allocation_config_id`），並由該被消耗配置驅動造冊的計畫編號 / 金額。
4. 讓管理員能在配置介面**編輯計畫編號（`project_numbers`）**。
5. 不保留向後相容：直接修改 schema 與程式碼；遷移既有資料。

## 3. 非目標（Non-goals）

- **不移除依學院的名額。** `quotas` 維持為依學院的矩陣 `{sub_type:{college:int}}`；學院審查排名、`matrix_based`/`college_based`/`simple` 模式、以及 `MatrixQuotaDisplay` 皆不動。共用池在**每個 (config, sub_type) 的總數**層級運作（§6）。在池的層級借用是與學院無關的；自動分發仍會強制執行每個學院的上限（§6.4）。
- 不改動教授／學院審查流程或挑戰／釋出（challenge/release）的*語意*。（挑戰釋出的**遞補**程式仍會被改鍵到被消耗配置 — 見 §6.3 — 因此屬於修改範圍，只是不是行為變更。）
- 借用連結沒有數量／上限（借用的數量永遠是來源配置的即時剩餘）。

## 4. 詞彙表（修正初始的誤解）

| 詞彙 | 程式碼中的實況 | 範例 |
|---|---|---|
| `ScholarshipType.code` | **穩定、與年份無關** | `phd`、`direct_phd`、`undergraduate_freshman` |
| `ScholarshipConfiguration.config_code` | **帶年份的識別碼** | `phd_112`、`phd_113`、`phd_114` |
| 「選獎學金代碼」（連結鍵） | = **`config_code`** | 連結 `phd_115 → phd_114` |
| `quotas` | 依**學院**的矩陣 | `{"nstc":{"E":15,"C":12,…}}` |
| pool total（池總數） | 依模式而定的每個 (config, sub_type) 總數（§6.1） | 矩陣型配置為 `sum(quotas["nstc"].values())` |

討論中的 `phd115` / `phd114` = 同一 `phd` 類型的**配置** `phd_115` / `phd_114`。

## 5. 資料模型變更

| 物件 | 欄位 | 由 | 改為 |
|---|---|---|---|
| `ScholarshipConfiguration` | `prior_quota_years` | `{"nstc":[113,112]}` | **移除** |
| `ScholarshipConfiguration` | `shared_quota_sources` *(新增, JSON)* | — | `[{"source_config_code":"phd_114","sub_types":["nstc"]}]` |
| `ScholarshipConfiguration` | `project_numbers` | `{"nstc":{"114":"114R…","113":"113R…"}}` | `{"nstc":"114R…"}`（僅自身年度） |
| `ScholarshipConfiguration` | `quotas` | `{"nstc":{"E":15,…}}` | **不變** |
| `CollegeRankingItem` | `allocation_year` (Int) | `114` | **移除**，改為 `allocation_config_id`（FK → `scholarship_configurations.id`，可為 null）+ relationship |
| `CollegeRankingItem` | `allocated_sub_type` | `"nstc"` | **不變** |
| `Application` | `allocation_config_id` *(新增, FK, 可為 null)* | — | 某筆**續領**消耗的配置（§9）；**已核定的續領永不為 NULL** |
| `Application` | `renewal_year` | int | **保留，僅供顯示**（不再是額度鍵） |
| `PaymentRoster` | `allocation_year` | int | 新增 `allocation_config_id` FK；**保留 `allocation_year` 作為非正規化顯示快照** = 被消耗配置的 `academic_year` |
| `PaymentRosterItem` | `allocation_year` | int | 同 `PaymentRoster` |

**`allocation_config_id` 為 NULL 只有一個意義：「全期」哨兵值**（全期／未切片的造冊路徑，`roster.sub_type IS NULL AND allocation_config_id IS NULL`）。一個*切片*的已分發名額絕不可為 NULL — 見 §11 回填（backfill），它會把孤兒列解析到發起配置，而不是留成 NULL。

**儲存方式 — `shared_quota_sources` 用 JSON 欄位**（非關聯表）：與 `quotas`/`project_numbers` 一致，是少量且總是隨配置一起載入的集合。`source_config_code` 沒有資料庫層 FK；於寫入時驗證（§10）。

### `shared_quota_sources` 結構

```json
[
  { "source_config_code": "phd_114", "sub_types": ["nstc"] },
  { "source_config_code": "phd_113", "sub_types": ["nstc"] }
]
```

- `source_config_code` 必須解析到一個**存在**且 `academic_year < this.academic_year`（僅限前面年份）的配置。
- `sub_types` ⊆ 來源配置已定義的 sub_types。
- 允許跨類型（`phd_115` 可列 `direct_phd_114`）。

## 6. 核心演算法 — 即時共用池

`ManualDistributionService` 上的新輔助函式，是供額度表格、分發狀態、finalize 閘門、與造冊驗證共用的單一事實來源。

### 6.1 池總數（依模式而定）

```
pool_total(C, st):
    if C.has_college_quota:            # matrix_based / college_based
        return sum(C.quotas.get(st, {}).values())
    else:                              # simple / none — quotas[st] 是純量（或 total_quota）
        return int(C.quotas.get(st, 0)) or C.total_quota_for(st)
```

> ⚠️ 實作注意：當 `has_college_quota` 為 False 時（例如 seed 的 `direct_phd_114`），`get_sub_type_total_quota` 回傳 0。上述輔助函式**不可**盲目呼叫它 — 必須處理非矩陣型配置，否則跨類型借用這類配置時讀到的會是空池。在依賴前，請對各 `quota_management_mode` 驗證純量路徑。

### 6.2 即時全域消耗者（保證互斥分割）

```
consumers(C, st) =
    count CollegeRankingItem ri
        WHERE ri.is_allocated
          AND ri.allocated_sub_type == st
          AND ri.allocation_config_id == C.id
          AND ri.application.is_renewal == False        # 僅一般／手動得獎者
  + count Application a
        WHERE a.is_renewal
          AND a.status == approved
          AND a.sub_scholarship_type == st
          AND a.allocation_config_id == C.id            # 僅續領

remaining(C, st) = pool_total(C, st) − consumers(C, st)   # 全域、即時
```

**為何需要明確的 `is_renewal == False` 守衛：** `college_review_service` 會為*每一筆*申請（**包含續領**）建立 `CollegeRankingItem`（`college_review_service.py:636-657`，續領排在最前）。續領的排名項目通常維持 `is_allocated=False`，但 `restore_allocation` 會把任何帶有 `allocated_sub_type` 的項目翻成 `is_allocated=True`，且 revoke/suspend/restore 端點**沒有 `is_renewal` 守衛**（`manual_distribution.py:689-759`）。若無此守衛，一筆被撤銷後又還原的續領會在*兩個*半邊都被計入。兩個半邊必須是**保證互斥分割**，而非僅靠假設。

### 6.3 可分發池與挑戰釋出

對某配置 `P`（例如 `phd_115`）的分發：

```
pool(P, st) = remaining(P, st)
            + Σ remaining(S, st)  其中每個連結 {S, sub_types} ∈ P.shared_quota_sources 且 st ∈ sub_types
```

每個池欄位對應**一個特定配置**；一筆分發記錄該 `allocation_config_id`。由於 `consumers` 會計入指向某配置的每一筆已分發名額（不論是哪一輪建立的），撤銷某個 `S` 的得獎者會提高 `remaining(S, st)`，`P` 在下次取狀態時即可看到 — 這正是共用池的需求。

**挑戰釋出／遞補（`execute_general_distribution`）** 必須把釋出名額對照表 `released[]` 以**被取消續領的 `allocation_config_id`** 為鍵（而非 `renewal_year`），且候補遞補必須**重新計算 `remaining(freed_config, st)`**，而非信任裸的釋出計數。`allocation_config_id` 未解析的舊續領會誤判釋出的名額歸屬 — 由 §11.3 緩解（續領永不留為 NULL）。

此設計取代 `_pick_pool`（改為回傳**配置**，優先自身 `P` 再依年份遞減取連結配置）、`_build_remaining_quota`、以及那些死掉的年份鍵讀取器。

### 6.4 自動分發保留每個學院的上限

`auto_allocate_preview` 的追蹤器改鍵為 **`(allocation_config_id, sub_type, college)`**（每個學院的上限取自*被消耗*配置的矩陣），而跨配置的池上限為 `pool(P, st)`。**兩個上限同時生效（取 min）**，使每個學院的矩陣強制保留（滿足 §3）。這是單一最大的演算法改寫。

## 7. 分發流程 + 表格 UI

- 表格欄位由 **(sub_type × 年份)** 改為 **(sub_type × 來源配置)**：自身配置欄位，加上每個連結來源配置各一欄，每欄以配置標示（例如 `nstc · phd_114`）並顯示即時 `remaining`。連結欄位保留既有的「補發」視覺處理。
- `allocate` 請求項目：`{ranking_item_id, sub_type_code, allocation_config_id}`（原為 `allocation_year`）。伺服器驗證 `allocation_config_id ∈ 允許集合` = **{自身配置 P} ∪ {其 `shared_quota_sources` 條目列出此 sub_type 的連結 S}**，並於伺服器端重新推導 `remaining`；前端計數僅供參考。
- 自動分發建議輸出：`{ranking_item_id, sub_type_code, allocation_config_id}`。
- **前端的池表格變更僅限於** `ManualDistributionPanel.tsx` + `lib/api/modules/manual-distribution.ts`。其他前端模組（`student-history`、`payment-rosters`、`PaymentHistoryTable`、`RosterListTable`、`RosterDetailDialog`、`StudentRosterPreview`）只把 `allocation_year` 當作**造冊顯示值**讀取，由 §8 的非正規化快照保留 — 它們無需修改，但仍應稽核（§13）。

## 8. 造冊產生

- 已分發的 `CollegeRankingItem` 改以 **(allocation_config_id, sub_type)** 分組（原為 `(allocation_year, sub_type)`）。`allocation_config_id NULL` ⇒ 全期分組（哨兵值不變）。
- **每組各自解析被消耗配置**（而非單一前置配置）：`generate_rosters_from_distribution` 目前在分組前抓取單一發起配置（`roster_service.py:1494-1503`）；被消耗配置必須改為每個 `allocation_config_id` 分組各自載入，並傳入 `_generate_one_sub_type_roster`。
- **每個被消耗配置：** `project_number = consumed_config.project_numbers.get(sub_type)`（已扁平化、無年份鍵）；`scholarship_amount = application.amount or consumed_config.amount`（保留每筆申請的覆寫；僅將 fallback 由發起配置改為被消耗配置）。`_create_roster_item`（`roster_service.py:819-880`）必須透過 `allocation_config_id` 載入被消耗配置，並把其獨立的分發推導改鍵到它。
- **跨類型借用的欄位來源（已決定）：** 借用名額的 `project_number`、`scholarship_amount`、及 `allocation_year` 顯示快照（= 被消耗配置的 `academic_year`）來自**被消耗**配置；`scholarship_name` 維持**發起**配置的獎學金類型名稱（學生實際持有的獎項）。同類型借用（常見情形）兩者共用同名，故無差異。
- `PaymentRoster`/`PaymentRosterItem` 儲存 `allocation_config_id`；`allocation_year` 設為被消耗配置的 `academic_year` 作為凍結的顯示快照（讓 Excel 匯出／學生歷史／清單檢視免 join 即可運作）。
- **重建唯一索引** `uq_roster_scholarship_period_alloc` = `(scholarship_configuration_id, period_label, COALESCE(allocation_config_id,-1), COALESCE(sub_type,''))` — **保留 sub_type**（兩個造冊可共用同一配置但 sub_type 不同，例如 `nstc` vs `moe_1w`）。
- 對帳（`_resolve_distribution_for_roster`、`get_distribution_diff_for_roster`、`reconcile_roster`）與 `payment_rosters.py:589-637` 的 `allocation_map` 建構器改以 `allocation_config_id` 比對／讀取。
- **候補遞補**（`alternate_promotion_service.py:112-117`）目前只複製 `allocated_sub_type`、**完全不設**年度／配置（既有缺陷）。現在必須從被取代項目複製 `allocation_config_id`；否則被遞補的候補會變成全期 NULL 而落入錯誤造冊。此程式變更必須與遷移一同上線。

## 9. 續領（Renewals）

續領（續領）延續某個特定的前一獎項，因此它**消耗該前一名額所消耗的同一配置**。（續領**是** `CollegeRankingItem` — `is_allocated=False` — 並非與其分離；§6.2 的分割已處理此情況。）

- 在續領建立時（`create_renewal_from_previous`），解析 `previous_application_id → 前一申請的 CollegeRankingItem.allocation_config_id`，並把它快照到新續領的 `Application.allocation_config_id`。**當前一名額無法解析時的 fallback：續領自身的 `scholarship_configuration_id`** — 已核定的續領**永不**留為 NULL（NULL 會使其在 §6.2 未被計入 → 池膨脹 → 超額分發）。
- `consumers()` 以 `Application.allocation_config_id` 計算已核定續領 — 單一索引查詢，無需遞迴走訪 `previous_application_id`。`_count_approved_renewals_per_pool` 由此取代／改鍵。
- `renewal_year` **僅供顯示**（例如 `RenewalOccupiedBlock`、被挑戰續領的 payload），不參與額度計算。
- `_batch_load_previous_allocation_years` 回傳前一名額的 `allocation_config_id`（用以填入續領快照並建議其欄位）。

## 10. 並行（Concurrency）與驗證

- **伺服器端額度閘門（全新）。** 在 commit 前，`allocate` 與 `finalize` 都必須 **`SELECT … FOR UPDATE` 鎖定該輪消耗的 `scholarship_configurations` 列 — 自身配置 `P` 及每個連結來源 `S`**（鎖定配置列才能讓兩個重疊的輪次序列化；鎖定彼此不相交的排名項目無法提供互斥）。在該鎖下，依 §6.2 重新計算 `remaining(C, st)`，若任何被消耗配置超額則拒絕（或以明確錯誤截斷）。今日兩條路徑皆不鎖定亦不重算，故此為全新邏輯。
- **連結寫入驗證**（配置 create/update，於程式中以指令式處理 — 見 §13）：每個 `source_config_code` 必須存在、`academic_year < this.academic_year`、且定義每個列出的 sub_type。否則快速失敗（fail-fast）。

## 11. 遷移計畫

單一 Alembic 遷移，`down_revision = '20260531_perf_indexes'`（已確認為唯一 head），依專案慣例做存在性檢查。**順序很重要** — project_numbers 的資料搬移必須在扁平化之前。

1. **`college_ranking_items`**：新增 `allocation_config_id` INT FK（可為 null）。以 `(ranking.scholarship_type_id, academic_year = allocation_year, semester)` → `ScholarshipConfiguration.id` 回填 `allocation_year`，使用**既有的三向 semester 正規化**（`_ranking_semester_condition`/`_config_semester_condition`：ranking `semester ∈ {NULL,'annual','yearly'}` ↔ config `semester ∈ {NULL,'yearly'}`）— 裸等號 join 會使主要的整學年 PhD 情形變孤兒。若有 `>1` 個配置匹配（NULL semester 並無唯一約束），以 `ORDER BY id DESC LIMIT 1` 決勝（與 `get_quota_status` 一致）。**仍無法解析的切片項目改指向發起配置的 id（絕不留 NULL）** 並計入；記錄孤兒數量。然後從此表**移除 `allocation_year`**。
2. **`payment_roster_items` / `payment_rosters`**：新增 `allocation_config_id`，由 `allocation_year` 回填（同正規化）；**保留 `allocation_year`** 改用途為顯示快照（= 被消耗配置 `academic_year`）。重建 `uq_roster_scholarship_period_alloc` 為 `COALESCE(allocation_config_id,-1)` 並**保留 `COALESCE(sub_type,'')`**。
3. **`applications`**：新增 `allocation_config_id` INT FK（可為 null）。由 `previous_application_id` 的名額配置回填續領；**失敗時 fallback 至續領自身的 `scholarship_configuration_id` — 已核定續領絕不為 NULL**（§9）。
4. **`scholarship_configurations` 的 project_numbers 資料搬移 + 扁平化** *(在移除前)：* 對每個持有借用年份計畫編號的配置（例如 `phd_114.project_numbers["nstc"]["113"] = "113R000001"`），**把該編號推送到來源配置自身年度的條目**（`phd_113.project_numbers["nstc"] = "113R000001"`）— 來源配置 `phd_112/113` 目前 `project_numbers=NULL`，若不做此搬移編號將永久遺失。然後把每個配置的 `project_numbers` 扁平化為 `{sub_type: 自身年度編號}`（僅保留年份 == 自身 `academic_year` 的條目）。
5. **`scholarship_configurations` 連結：** 新增 `shared_quota_sources` JSON。由 `prior_quota_years` 回填（每個年份 → 同類型 `config_code`）。**丟棄（並記錄）任何目標配置不存在的連結**（例如 `phd_114` 的 `prior_quota_years` 列了 `112` 但**沒有 `phd_112` 配置存在**）— 與 §10 一致。**移除 `prior_quota_years`。**
6. **歷史 JSON 改鍵：** `manual_distribution_history.allocations_snapshot` 以每項 `{sub_type, allocation_year, status}` 儲存，而 `restore_from_history` 由它寫回 `item.allocation_year`。把既有 snapshot 由 `allocation_year` 改鍵為 `allocation_config_id`（同樣的 semester 感知解析），並更新 save/restore-history 改讀寫 `allocation_config_id`，否則進行中的還原會悄悄損毀。
7. **Seed**（`seed_scholarship_configs.py`、`seed_distribution_test_data.py`）：建立 seed 的 `shared_quota_sources` 所指向的前面年份兄弟配置（例如 `phd_112`），各自帶有自己的 `quotas` + 自身年度 `project_numbers`；以 `shared_quota_sources` 取代 `prior_quota_years`；單一年度 `project_numbers`；把 `shared_quota_sources` 加入既有配置的重新同步區塊；以 `allocation_config_id` 取代 `CollegeRankingItem(allocation_year=…)`。

**移除前稽核（大聲失敗）：** 計算解析為 NULL 的切片已分發項目數；計算解析為 NULL 的已核定續領數；計算目標配置不存在的 `shared_quota_sources` 連結數。在破壞性移除前對真實資料執行。

## 12. 死碼整併

`quotas` 存在兩種互相矛盾的現行詮釋；本設計予以了結：

- **學院矩陣家族 — 保留**（model 輔助方法、**`get_quota_status` ← 真正在用的額度表格驅動者**、`quota_service`、學院審查、矩陣端點、`MatrixQuotaDisplay`）：讀取 `{sub_type:{college:int}}`。`get_quota_status`（`manual_distribution_service.py:385`）才是面板表格實際呼叫的（`/quota-status` → `by_year`）；它必須改用 `remaining()`/`pool()`（§6）。這是真正的改寫，並帶來續領可見性的行為變更（§17.1）。
- **年份鍵 Phase-6 家族 — 生產環境為死碼、予以改寫**（`_build_remaining_quota`、`_pick_pool`、`compute_distribution_state.available_quotas`、`execute_general_distribution`）：假設 `{sub_type:{year_str:total}}`，會悄悄跳過真實的學院資料 → 今日對真實資料計算出空池。`execute_general_distribution` 只有測試呼叫者（無端點），故其改寫風險較低 — 但它仍是正規的一般階段 + 挑戰釋出演算法，必須在 §6 之上重建。

`get_quota_status` 的前面年份 join（以 `prior_quota_years` 的年份載入兄弟配置）改為載入 `shared_quota_sources` 所列的配置。

## 13. 受影響檔案（完整面向圖 + 對抗式新增）

**後端 models：** `college_review.py`（allocation_config_id）、`scholarship.py`（shared_quota_sources / project_numbers 扁平化；矩陣輔助方法不變）、`payment_roster.py`（鏡射欄 + 唯一索引）、`application.py`（allocation_config_id）。

**後端 services：** `manual_distribution_service.py`（`allocate`、`finalize` + 鎖閘門、`restore_from_history` + save-history 快照、`get_quota_status`、`compute_distribution_state`、`_pick_pool`、`_build_remaining_quota`、`_count_approved_renewals_per_pool`、`_batch_load_previous_allocation_years`、`_compute_suggestions`、`auto_allocate_preview`、`execute_general_distribution`）、`roster_service.py`（`generate_rosters_from_distribution` 每組配置、`_generate_one_sub_type_roster`、`_create_roster_item` 載入被消耗配置、`_resolve_distribution_for_roster`、`get_distribution_diff_for_roster`、`reconcile_roster`）、`alternate_promotion_service.py`（複製 `allocation_config_id` — **新行為**）、`excel_export_service.py`（顯示年度取自快照）、`application_service.py`（`create_renewal_from_previous` 快照 + fallback）、`student_scholarship_history_service.py`、`college_review_service.py`（為 §6.2 分割而對續領排名項目有所感知）。

**後端 endpoints/schemas：** `manual_distribution.py`（`AllocationItem.allocation_config_id`、分組、鎖閘門）、`payment_rosters.py`（`allocation_map` 改用 `allocation_config_id`）、`renewal.py`、`scholarship_configurations.py` — **project_numbers + shared_quota_sources 透過未具型別的 `config_data` dict 在三處寫入**：主要 create constructor（`:757`，目前省略 `project_numbers`）、**複製配置（duplicate-config）** 路徑（`:1208`，完全沒複製 `quotas`/`prior_quota_years`/`project_numbers` — 必須全部帶過）、與 update（`:1032`，為兩個新欄位加上 `flag_modified` 分支）。`scholarship_configuration.py` schema（`quotas` 維持巢狀 `Dict[str,Dict[str,int]]`；新增 `project_numbers: Optional[Dict[str,str]]`、`shared_quota_sources: Optional[List[SharedQuotaSource]]`）。`roster.py` / `payment_roster.py` / `student_scholarship_history.py` schemas。**§10 連結驗證於端點中以指令式實作**（無 schema 層 FK）。

**前端：** `ManualDistributionPanel.tsx`、`lib/api/modules/manual-distribution.ts`、`admin-configuration-management.tsx`（連結選擇器 + project_numbers 欄位；create 與 edit 兩個表單 + `formData` 初始化 + `openEditDialog`）、`lib/api/types.ts`（收斂 `quotas`、新增 `shared_quota_sources`；`project_numbers: Record<string,string>`）、重新產生 `lib/api/generated/schema.d.ts`。

**後端測試（fixture + 斷言改寫 — 先前遺漏）：** `test_distribution_state_endpoint.py`（年份鍵 quotas + prior_quota_years fixture；available_quotas-by-allocation_year 斷言）、`test_challenge_release_distribution.py`、`test_renewal_end_to_end.py`、`test_restore_allocation_service.py`、`test_roster_distribution_reconcile_service.py`、`backend/tests/test_auto_allocate_preview.py`（`_compute_suggestions` allocation_year 輸出 + (sub_type,year,college) 追蹤器）、`test_excel_export*pure_helpers`（顯示年度）。**前端測試：** `lib/api/modules/__tests__/manual-distribution.test.ts`（allocate body 釘住 `allocation_year`）。

**遷移/seed：** 新 Alembic 遷移；`seed_scholarship_configs.py`；`backend/scripts/seed_distribution_test_data.py`。

## 14. 測試策略

- **單元（池計算）：** 矩陣與非矩陣（`has_college_quota=False`）配置的 `pool_total`；`consumers()` 分割（一般得獎者計一次；續領經由 Application 半邊計一次；被撤銷後還原的續領不重複計數）；`remaining()` 全域；`pool()` = 自身 + 連結；撤銷來源得獎者會提高借用方的池；跨類型連結；僅限前面年份 + 目標配置缺失的驗證。
- **整合（async）：** 分發到連結配置 → 造冊消耗該配置的 project_number/amount；finalize 鎖在並行輪次下拒絕超額；續領快照歸屬 + 永不 NULL 的 fallback；候補遞補繼承 `allocation_config_id`。
- **遷移：** 以 `reset_database.sh` 全新資料庫；回填 `allocation_year → allocation_config_id`，含 `'annual'`-semester 整學年 PhD、NULL/全期、renewal_year 推導；**project_numbers 資料搬移保留 `113R000001`/`112R000001`**；`prior_quota_years → shared_quota_sources` 連帶記錄丟棄缺失的 `phd_112` 連結；歷史 JSON 改鍵；移除前稽核計數為零（或符合預期）。
- **造冊對帳：** diff 以 `allocation_config_id` 比對；全期造冊仍持有所有項目。
- **前端：** 表格渲染配置欄位與即時 remaining；allocate payload 帶 `allocation_config_id`；配置編輯器連結選擇器 + project_numbers 欄位來回往返。
- Lint 閘門：`black --line-length=120`、`flake8 --select=B904,B014`、logger-traceback 不變量。

## 15. 待解風險

1. **回填孤兒** — 無法解析的切片項目／已核定續領分別改指向發起／自身配置（絕不 NULL）；稽核必須在移除前確認計數合理。錯誤的決勝（重複的 NULL-semester 配置）可能誤判名額歸屬。
2. **`auto_allocate_preview`** 是最大的改寫（每個學院的追蹤器改鍵為 `(allocation_config_id, sub_type, college)` 同時遵守跨配置池上限）。
3. **顯示快照漂移** — 造冊的 `allocation_year` 快照在產生時凍結；之後編輯配置的 `academic_year` 不會更新它（可接受 — 造冊是時間點快照）。
4. **缺失的兄弟配置** — 借用只在來源配置列存在時可用；seed 必須建立 `phd_112` 等。懸空的 `prior_quota_years` 年份會被丟棄，因此依賴 112 借用的管理員在建立 `phd_112` 配置 + 連結前會失去它。

## 16. 規格審查期間已解決

1. **跨類型造冊命名（§8）：** `scholarship_name` 跟隨**發起**配置；`project_number` / `amount` / 顯示年度跟隨**被消耗**配置。（同類型借用無差異。）
2. **額度閘門（§10）：** 於 **allocate 與 finalize 兩處**強制 — 在被消耗配置列上 `SELECT … FOR UPDATE` + 重新計數。

## 17. 與現況相比的行為變更（QA 注意事項）

1. **續領現在會消耗顯示的池。** 今日表格驅動者 `get_quota_status` 只計 `is_allocated` 排名項目、**從不扣除續領**；`remaining()`（§6）會扣。改動後，任何有已核定續領的配置，其表格 remaining 會**比今日更低**。此為刻意設計 — 續領確實佔用名額。
2. **伺服器端額度強制為全新。** 今日 `_validate_allocations` 把額度檢查交給前端（「Quota validation is done real-time via the quota-status endpoint on the frontend」，`manual_distribution_service.py:918-919`）；allocate/finalize 從不鎖定或重算。§10 新增伺服器閘門。
3. **造冊計畫編號 / 金額來源變更**，由發起配置（以年份字串為鍵）改為被消耗配置。
