# 造冊（payment roster）matrix 模式：生成時納入全院 — 設計

- 日期：2026-06-21
- 分支：`worktree-fix-roster-matrix-aggregate-all-colleges`
- 相關 issue 脈絡：#1029 / #1034（分發須看見所有學院）的下游延伸

## 1. 問題

管理員對多學院的 matrix 獎學金完成分發後，透過「單一配置／月份」的 `/generate` 造冊流程產生造冊，名單卻只包含**最後一個被鎖定的學院**的學生（實測：博士獎學金 114，4 個學院共 9 人正取，但 `/generate` 產生的 roster 15 只有電機院 2 人）。

完整名單其實存在 —— 來自「獎學金分發 → 生成造冊」按鈕（`generate_rosters_from_distribution`，roster 13+14 共 9 人）。問題只發生在 `/generate` 這條路。

## 2. 根本原因

`backend/app/services/roster_service.py` 的 `_get_eligible_applications()`（約 674–712 行）：matrix 模式且未帶 `ranking_id` 時，用

```python
ranking = (... CollegeRanking ... is_finalized, distribution_executed ...)
    .order_by(CollegeRanking.finalized_at.desc())
    .first()           # ← 只取「最後鎖定」的單一排名
query = query.join(CollegeRankingItem ...).filter(
    CollegeRankingItem.ranking_id == ranking_id,    # ← 僅該排名
    CollegeRankingItem.is_allocated.is_(True))
```

matrix 分發下**每個學院各有一份 `CollegeRanking`**，`.first()` 只挑一份 → 其他學院的正取者被靜默忽略。

延伸問題：`backend/app/api/v1/endpoints/payment_rosters.py` 的 `preview_roster_students()`（約 591–606 行）**另外自寫一份**單一排名自動偵測，且用 `created_at.desc()`、未過濾 `academic_year` / `is_finalized`，與實際產生用的 `finalized_at.desc()` 不一致 → **預覽看到的人可能與最終造冊不同**。

## 3. 目標行為（決議）

- **B1**：matrix 模式 `/generate` 未指定 `ranking_id` 時，**聚合所有** `is_finalized + distribution_executed` 的排名，把全院正取者納入**單一一張**造冊（混合 sub_type，沿用 `STD_UP_MIXLISTA` 範本）。
- 造冊只含**已分發（`is_allocated=True`）**者；不納入未分發/備取者。
- 預覽與產生**保證一致**（走同一段邏輯）。
- 管理員若**明確指定** `ranking_id`（從 `available-rankings` 選）→ 維持只做該排名（刻意選擇，不變）。

## 4. 設計

### 4.1 核心修正 — `_get_eligible_applications()`（roster_service.py）

matrix 分支、`ranking_id is None` 時，把「挑單一排名」改為「聚合全部排名」：

```python
if ranking_id is None:
    rankings = (
        self.db.query(CollegeRanking)
        .filter(and_(
            CollegeRanking.scholarship_type_id == config.scholarship_type_id,
            CollegeRanking.academic_year == academic_year,
            CollegeRanking.is_finalized.is_(True),
            CollegeRanking.distribution_executed.is_(True),
        ))
        .all()
    )
    if not rankings:
        raise ValueError("找不到已執行分發的排名…")   # 維持原錯誤
    ranking_ids = [r.id for r in rankings]
    query = query.join(CollegeRankingItem, CollegeRankingItem.application_id == Application.id).filter(and_(
        CollegeRankingItem.ranking_id.in_(ranking_ids),
        CollegeRankingItem.is_allocated.is_(True),
    ))
else:
    # 明確指定排名 → 維持單一排名行為（現狀）
    query = query.join(CollegeRankingItem, ...).filter(and_(
        CollegeRankingItem.ranking_id == ranking_id,
        CollegeRankingItem.is_allocated.is_(True),
    ))
```

- 去重：`.in_(ranking_ids)` + join 可能讓同一 application 出現多列（理論上一個 application 只會在一個排名被分配，但仍以 `.distinct()` 或結果集去重保險）。實作時用 `query.distinct()` 或在 Python 端依 `application.id` 去重。
- 不加 semester 過濾（與目前單張路徑現狀一致；見 §6 已知差異）。

### 4.2 逐項 sub_type 正確性（無需改）

`_create_roster_item()`（roster_service.py:850–883）在 `roster.ranking_id` 為 NULL 時，已會**針對每個學生**從其所屬「同學年度已分發排名」查 `allocated_sub_type`。因此聚合後單張造冊的每一列 sub_type 各自正確 —— **此處不需修改**。

> 註：`roster.ranking_id` 在 `/generate` 月份造冊本就為 NULL（roster 15 即如此），故走的就是這條逐項查 sub_type 的分支。

### 4.3 預覽一致性 — `preview_roster_students()`（payment_rosters.py）

刪除其自寫的單一排名自動偵測（約 591–606 行），改為直接把 `ranking_id`（前端未選時為 `None`）丟進 `roster_service._get_eligible_applications(...)`。如此預覽與產生共用 §4.1 同一段邏輯 → 全院、且與最終造冊一致。下游的 `allocation_map` 查詢（payment_rosters.py:621–650）本就跨排名依 `is_allocated + academic_year` 查詢，無需改。

### 4.4 不變更

- `generate_rosters_from_distribution()`（分發面板路徑）：本就正確，不動。
- 帶明確 `ranking_id` 的所有流程：不動。
- `RosterCreateRequest` schema、前端 API 形狀：不動（仍是「一次 generate 一張」）。

## 5. 行為矩陣

| 觸發 | 已分發排名數 | 修正後 |
|---|---|---|
| `/generate`，未帶 ranking_id | 0 | 維持報錯「找不到已執行分發的排名」 |
| `/generate`，未帶 ranking_id | 1 | 該排名全部正取（等同現狀） |
| `/generate`，未帶 ranking_id | ≥2（多院）| **全院正取，單張混合造冊**（本次修正重點）|
| `/generate`，帶 ranking_id | 任意 | 僅該排名正取（不變）|
| 預覽 preview-students | ≥2（多院）| 與產生一致：全院正取 |
| 分發面板 生成造冊 | ≥2 | 依 sub_type 拆多張（不變）|

## 6. 已知差異 / 本次不做（明確標註）

- **semester 過濾**：分發面板路徑用 `_build_semester_filter()`，本路徑現狀不過濾；本次維持不過濾以免改變行為。若日後要對齊，於 §4.1 查詢加 semester 條件。
- **backup_info（備取資訊）**：ranking_id 為 NULL 的造冊本就不帶；依「不放未分發/備取者」決議，**不做**。
- **borrowed quota 逐項 allocation_year 快照**：單張造冊路徑本就無逐項快照（分發面板路徑才有）。同學年度情境不受影響；跨年度借用配額屬邊界，沿用現狀。

## 7. 測試計畫

### 7.1 後端單元測試（pytest，主要驗證層）
新增於 `backend/app/tests/`（沿用既有 `test_roster_service_generation.py` / `test_roster_service_core.py` 模式與 fixtures）：

1. **多院聚合**：建立 ≥2 個 `is_finalized+distribution_executed` 排名、各有正取 item，`generate_roster(ranking_id=None)` → 造冊 item 數 = 全部排名正取總和；涵蓋多個學院。
2. **未分發者排除**：排名含 `is_allocated=False` 的 item → 不得進入造冊。
3. **明確 ranking_id**：帶單一 `ranking_id` → 僅該排名正取（回歸保護）。
4. **單一排名**：只有一個排名時，結果與現狀相同（回歸保護）。
5. **0 排名**：維持 `ValueError`。
6. **逐項 sub_type**：跨排名/跨 sub_type 學生 → 每列 `scholarship_subtype` 各自正確。
7. **預覽=產生**：`preview_roster_students` 與 `generate_roster` 對同一情境回傳相同學生集合。

### 7.2 端到端（既有腳本）
`/.claude/skills/playwright-test-and-debug/scripts/verify-multi-college-distribution.js` 已涵蓋 ranking→distribution→roster 全鏈；修正後，把斷言由 `payment_rosters` 批數擴充為「roster items 涵蓋全部學院正取人數」。

### 7.3 對既有資料的人工驗證
dev DB（4 院、9 人正取）：以 `force_regenerate` 重生 roster 15（period 114-09）→ 期望 item 數由 2 變 9，涵蓋 A/B/C/E 四院。

## 8. 風險

- **混合 sub_type 的 Excel 匯出**：`STD_UP_MIXLISTA` 範本名稱即「混合清單」，預期支援；測試 7.1/7.3 後以實際 Excel 匯出檢查金額/欄位正確。
- **去重**：join `.in_()` 需確保不重複計列（§4.1）。
- **與分發面板路徑並存**：兩條路徑可能對重疊學生各產一張造冊（period_label 不同：`114` vs `114-09`）。屬既有狀況，非本次引入；如需防雙重撥款另議。

## 9. 範圍外

- 重構兩條造冊路徑為單一實作。
- semester 對齊、borrowed-quota 逐項快照、backup_info 補齊。
- 前端 UI 變更（本次純後端邏輯修正，前端行為自動受益）。
