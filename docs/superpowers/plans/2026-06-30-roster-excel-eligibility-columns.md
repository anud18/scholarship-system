# 造冊 Excel 資格驗證欄位 + 紅/琥珀底 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 造冊匯出的 Excel 在既有 30 欄付款格式後附加資格驗證欄位（學籍、整體規則資格、**每條規則各一欄**、納入造冊、排除原因），並對不符合的儲存格上紅底（硬性/學籍/銀行/排除）或琥珀底（警告規則）。

**Architecture:** 全部變更集中於 `backend/app/services/excel_export_service.py`。欄位改為「每次匯出動態計算」：`self.template_columns` 保留為靜態 base 30 欄，匯出時計算 `export_columns = base + 驗證欄 + 逐條規則欄`。逐條規則 pass/fail 直接讀 `PaymentRosterItem.rule_validation_result["details"]` 凍結快照，**不重跑規則引擎**。上色資訊由 `_prepare_excel_data` 與 row data 平行回傳，於 `_create_excel_file` 套用。

**Tech Stack:** Python 3.10, FastAPI, SQLAlchemy, openpyxl, pytest（SimpleNamespace stub，無 DB）。

## Global Constraints

- Black 格式化：`black --line-length=120`（CLAUDE.md：line-length 120）。
- Flake8 硬性 gate：`flake8 --select=B904,B014 --max-line-length=120`。
- 一律使用凍結快照，**不得**呼叫 `roster_service` 重跑驗證/規則。
- 不得破壞既有 30 欄付款內容（既有 pin 測試必須維持綠燈）。
- 規則欄文字固定為 `通過` / `未通過` / `—`；warning 規則未通過用琥珀底，hard 規則未通過用紅底。
- 紅底 `PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")`；琥珀底 `PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")`。

## Test Run Recipe（worktree host，沿用 worktree_test_verify_recipe）

先在 shell export 環境（Settings 無預設值，必須提供）：

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility/backend
export ENVIRONMENT=development \
  DATABASE_URL=postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db \
  DATABASE_URL_SYNC=postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db \
  SECRET_KEY=dev-secret-key-for-development-only \
  REDIS_URL=redis://localhost:6379/0 \
  MINIO_ENDPOINT=localhost:9000 MINIO_ACCESS_KEY=minioadmin MINIO_SECRET_KEY=minioadmin123 \
  MINIO_BUCKET=scholarship-documents MINIO_SECURE=false
```

執行測試請用 `rtk proxy` 前綴以取得真實 pytest 輸出（直接 `python -m pytest` 會被 rtk 摘要成 "No tests collected" 假訊息）：

```bash
rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -p no:cacheprovider --no-cov -q
```

---

## File Structure

- **Modify:** `backend/app/services/excel_export_service.py`
  - 新增 class 常數（欄名、PatternFill）。
  - 新增 pure helper：`_is_manual_removal`、`_collect_rule_columns`、`_build_export_columns`。
  - 改 `_get_roster_items`（範圍過濾）、`_prepare_excel_data`（簽章+內容+回傳 fills）、`_create_excel_file` / `_apply_excel_styling` / `_set_column_widths` / `_set_borders`（吃明確 `columns` + 套色）、`export_roster_to_excel`、`preview_roster_export`（接線）。
- **Modify (Test):** `backend/app/tests/test_excel_export_service_rows.py`
  - 擴充 `_make_item` 預設屬性；既有 call site 改 `data, _ = ...`；新增驗證欄/規則欄/上色/過濾測試。

---

## Task 1: 範圍過濾 — `_is_manual_removal` + `_get_roster_items`

**Files:**
- Modify: `backend/app/services/excel_export_service.py`（`_get_roster_items` 約 347-354；於其上方新增 `_is_manual_removal`）
- Test: `backend/app/tests/test_excel_export_service_rows.py`

**Interfaces:**
- Produces:
  - `ExcelExportService._is_manual_removal(item) -> bool`（staticmethod，pure）
  - `ExcelExportService._get_roster_items(roster, include_excluded: bool) -> List[PaymentRosterItem]`（簽章不變，過濾規則改變）

- [ ] **Step 1: 寫失敗測試**

在 `test_excel_export_service_rows.py` 末端新增（沿用既有 `_make_item`，此時尚無 `exclusion_reason` 參數，所以用 `item.exclusion_reason = ...` 直接設）：

```python
# ---------------------------------------------------------------------------
# Roster item scope filter — auto-excluded shown, manual removals hidden
# ---------------------------------------------------------------------------


def _mk_scope_item(name, *, is_included, exclusion_reason=None):
    it = _make_item(student_name=name, is_included=is_included)
    it.exclusion_reason = exclusion_reason
    return it


def test_is_manual_removal_detects_lock_and_reconcile_prefixes(service):
    assert service._is_manual_removal(_mk_scope_item("a", is_included=False, exclusion_reason="鎖定後移除[停發]：x")) is True
    assert service._is_manual_removal(_mk_scope_item("b", is_included=False, exclusion_reason="比對分發移除：不在分發名單")) is True
    assert service._is_manual_removal(_mk_scope_item("c", is_included=False, exclusion_reason="缺少銀行帳戶資訊")) is False
    assert service._is_manual_removal(_mk_scope_item("d", is_included=True, exclusion_reason=None)) is False


def test_get_roster_items_default_keeps_auto_excluded_hides_manual(service):
    included = _mk_scope_item("納入", is_included=True)
    auto_excluded = _mk_scope_item("自動排除", is_included=False, exclusion_reason="缺少銀行帳戶資訊")
    manual = _mk_scope_item("手動移除", is_included=False, exclusion_reason="鎖定後移除[停發]：x")
    roster = SimpleNamespace(items=[included, auto_excluded, manual])

    names = [i.student_name for i in service._get_roster_items(roster, include_excluded=False)]

    assert "納入" in names
    assert "自動排除" in names
    assert "手動移除" not in names


def test_get_roster_items_include_excluded_shows_everything(service):
    included = _mk_scope_item("納入", is_included=True)
    manual = _mk_scope_item("手動移除", is_included=False, exclusion_reason="鎖定後移除[停發]：x")
    roster = SimpleNamespace(items=[included, manual])

    names = [i.student_name for i in service._get_roster_items(roster, include_excluded=True)]

    assert names == ["手動移除", "納入"]  # sorted by student_name
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -k "manual_removal or roster_items" -p no:cacheprovider --no-cov -q`
Expected: FAIL（`_is_manual_removal` 不存在 / 過濾行為不符）。

- [ ] **Step 3: 實作**

在 `_get_roster_items` 上方新增 staticmethod，並改寫 `_get_roster_items`：

```python
    @staticmethod
    def _is_manual_removal(item) -> bool:
        """True 表示此 item 是「鎖定後手動移除」或「比對分發移除」，
        應排除於資格驗證視圖之外（自動因資格不符排除者則保留並標紅）。"""
        reason = getattr(item, "exclusion_reason", None)
        return bool(reason and reason.startswith(("鎖定後移除", "比對分發移除")))

    def _get_roster_items(self, roster: PaymentRoster, include_excluded: bool) -> List[PaymentRosterItem]:
        """取得造冊明細。

        預設（include_excluded=False）：保留「納入」與「因資格不符自動排除」者，
        隱藏「手動移除」者。include_excluded=True 時回傳全部（含手動移除）。
        """
        items = list(roster.items)

        if not include_excluded:
            items = [item for item in items if item.is_included or not self._is_manual_removal(item)]

        return sorted(items, key=lambda x: x.student_name)
```

- [ ] **Step 4: 跑測試確認通過**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -k "manual_removal or roster_items" -p no:cacheprovider --no-cov -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility
git add backend/app/services/excel_export_service.py backend/app/tests/test_excel_export_service_rows.py
git commit -m "feat(roster-excel): scope filter keeps auto-excluded, hides manual removals"
```

---

## Task 2: 常數 + 規則欄收集 `_collect_rule_columns` / `_build_export_columns`

**Files:**
- Modify: `backend/app/services/excel_export_service.py`（class 內新增常數；新增兩個方法，建議置於 `_format_allocation_display` 附近）
- Test: `backend/app/tests/test_excel_export_service_rows.py`

**Interfaces:**
- Produces:
  - class 常數：`COL_VERIFICATION="學籍驗證"`、`COL_RULE_SUMMARY="規則資格"`、`COL_INCLUDED="納入造冊"`、`COL_EXCLUSION="排除原因"`、`COL_BANK_ACCOUNT="帳號"`
  - `_collect_rule_columns(roster_items) -> List[Tuple[int, str]]`（依 rule_id 升冪、header 去重）
  - `_build_export_columns(rule_columns: List[Tuple[int, str]]) -> List[str]`

- [ ] **Step 1: 寫失敗測試**

```python
# ---------------------------------------------------------------------------
# Rule column collection from frozen rule_validation_result snapshots
# ---------------------------------------------------------------------------


def _item_with_rules(name, details):
    """details: dict like {"rule_5": {"passed": True, "rule_name": "GPA", ...}}"""
    it = _make_item(student_name=name)
    it.rule_validation_result = {"is_eligible": True, "details": details}
    return it


def test_collect_rule_columns_orders_by_rule_id_and_dedupes(service):
    items = [
        _item_with_rules("a", {"rule_5": {"passed": True, "rule_name": "GPA門檻"},
                                "rule_2": {"passed": False, "rule_name": "國籍"}}),
        _item_with_rules("b", {"rule_2": {"passed": True, "rule_name": "國籍"},
                                "no_rules_found": True}),
    ]

    cols = service._collect_rule_columns(items)

    assert cols == [(2, "國籍"), (5, "GPA門檻")]


def test_collect_rule_columns_disambiguates_duplicate_names(service):
    items = [_item_with_rules("a", {"rule_2": {"passed": True, "rule_name": "門檻"},
                                     "rule_7": {"passed": True, "rule_name": "門檻"}})]

    cols = service._collect_rule_columns(items)

    assert cols == [(2, "門檻"), (7, "門檻（#7）")]


def test_collect_rule_columns_ignores_items_without_snapshot(service):
    plain = _make_item(student_name="x")
    plain.rule_validation_result = None
    assert service._collect_rule_columns([plain]) == []


def test_build_export_columns_layout(service):
    cols = service._build_export_columns([(2, "國籍"), (5, "GPA門檻")])

    base = list(service.template_columns)
    assert cols == base + ["學籍驗證", "規則資格", "國籍", "GPA門檻", "納入造冊", "排除原因"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -k "collect_rule_columns or build_export_columns" -p no:cacheprovider --no-cov -q`
Expected: FAIL（方法不存在）。

- [ ] **Step 3: 實作**

在 class 開頭（`ALLOWED_TEMPLATES` 之後）新增常數：

```python
    # 資格驗證欄名（附加於 base 30 欄之後）
    COL_VERIFICATION = "學籍驗證"
    COL_RULE_SUMMARY = "規則資格"
    COL_INCLUDED = "納入造冊"
    COL_EXCLUSION = "排除原因"
    COL_BANK_ACCOUNT = "帳號"  # base 第 3 欄（缺帳號時標紅）
```

新增兩個方法（`_format_allocation_display` 之後）：

```python
    def _collect_rule_columns(self, roster_items: List[PaymentRosterItem]) -> List["tuple[int, str]"]:
        """從所有 item 的凍結快照 rule_validation_result["details"] 收集規則欄。

        回傳依 rule_id 升冪排序的 (rule_id, header)；header 以 rule_name 為主，
        若與 base/驗證欄名或其他規則 header 衝突，加上「（#id）」後綴確保唯一。
        """
        seen: Dict[int, str] = {}
        for item in roster_items:
            rvr = getattr(item, "rule_validation_result", None)
            details = rvr.get("details") if isinstance(rvr, dict) else None
            if not isinstance(details, dict):
                continue
            for key, res in details.items():
                if not key.startswith("rule_"):
                    continue
                suffix = key[len("rule_"):]
                if not suffix.isdigit():
                    continue
                rid = int(suffix)
                if rid in seen:
                    continue
                name = (res.get("rule_name") if isinstance(res, dict) else None) or f"規則{rid}"
                seen[rid] = name

        reserved = set(self.template_columns) | {
            self.COL_VERIFICATION,
            self.COL_RULE_SUMMARY,
            self.COL_INCLUDED,
            self.COL_EXCLUSION,
        }
        columns: List["tuple[int, str]"] = []
        used = set(reserved)
        for rid in sorted(seen):
            header = seen[rid]
            if header in used:
                header = f"{header}（#{rid}）"
            used.add(header)
            columns.append((rid, header))
        return columns

    def _build_export_columns(self, rule_columns: List["tuple[int, str]"]) -> List[str]:
        """組出本次匯出的完整欄位順序：base 30 欄 + 驗證欄 + 逐條規則欄 + 納入/排除。"""
        return (
            list(self.template_columns)
            + [self.COL_VERIFICATION, self.COL_RULE_SUMMARY]
            + [header for _, header in rule_columns]
            + [self.COL_INCLUDED, self.COL_EXCLUSION]
        )
```

- [ ] **Step 4: 跑測試確認通過**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -k "collect_rule_columns or build_export_columns" -p no:cacheprovider --no-cov -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility
git add backend/app/services/excel_export_service.py backend/app/tests/test_excel_export_service_rows.py
git commit -m "feat(roster-excel): collect per-rule columns from frozen snapshots"
```

---

## Task 3: `_prepare_excel_data` — 驗證欄/規則欄/上色 metadata

**Files:**
- Modify: `backend/app/services/excel_export_service.py`（`_prepare_excel_data` 約 401-501）
- Test: `backend/app/tests/test_excel_export_service_rows.py`（擴充 `_make_item`；既有 call site 改 `data, _ =`；新增測試）

**Interfaces:**
- Consumes: `_get_verification_status_label(status)`（既有）、`PaymentRosterItem.is_eligible`（既有 property，stub 以屬性提供）、`_collect_rule_columns`（Task 2）。
- Produces:
  - `_prepare_excel_data(roster, roster_items, rule_columns: Optional[List[tuple[int,str]]] = None) -> tuple[List[Dict], List[Dict[str, str]]]`
    - 回傳 `(excel_data, cell_fills)`；`cell_fills` 與 `excel_data` 等長平行，每筆為 `{header: "red" | "amber"}`。
    - `item.excel_row_data` 仍寫回**乾淨** row dict（不含 fills）。

- [ ] **Step 1: 更新既有 fixture 與 call site（讓既有測試先適配新簽章）**

擴充 `_make_item`，加入驗證相關預設（讓既有測試的「合格」item 不產生紅底、不報錯）：

在 `_make_item` 的參數列尾端（`is_included` 之後）加入：

```python
    verification_status: str = "verified",
    is_eligible: Optional[bool] = True,
    rule_validation_result: Optional[dict] = None,
    exclusion_reason: Optional[str] = None,
```

在 `SimpleNamespace(...)` 內加入對應欄位：

```python
        verification_status=verification_status,
        is_eligible=is_eligible,
        rule_validation_result=rule_validation_result,
        exclusion_reason=exclusion_reason,
```

將既有所有 call site 由 `data = service._prepare_excel_data(...)` 改為 `data, _ = service._prepare_excel_data(...)`：

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility/backend
sed -i -E 's/(^\s*)data = service\._prepare_excel_data\((.*)\)/\1data, _ = service._prepare_excel_data(\2)/' app/tests/test_excel_export_service_rows.py
grep -n "_prepare_excel_data(" app/tests/test_excel_export_service_rows.py
```

預期：所有 `data = service._prepare_excel_data(...)` 變為 `data, _ = service._prepare_excel_data(...)`（docstring 內的提及不受影響）。

> 注意：`test_row_data_written_back_to_item` 斷言 `item.excel_row_data == data[0]`；因 `item.excel_row_data` 仍是乾淨 row dict 且 `data[0]` 也是乾淨 row dict，此 pin 維持成立。`_item_with_rules`（Task 2）所建 item 缺 `is_eligible` 屬性時，實作用 `getattr(item, "is_eligible", None)` 容錯。

- [ ] **Step 2: 寫失敗測試（新驗證欄/規則欄/上色）**

```python
# ---------------------------------------------------------------------------
# Verification columns + per-rule columns + cell fill metadata
# ---------------------------------------------------------------------------


def test_prepare_returns_rows_and_parallel_fills(service):
    roster = _make_roster()
    item = _make_item()
    rows, fills = service._prepare_excel_data(roster, [item], [])
    assert len(rows) == len(fills) == 1


def test_verification_and_rule_columns_values(service):
    roster = _make_roster()
    item = _make_item(student_name="甲")
    item.verification_status = "verified"
    item.is_eligible = True
    item.rule_validation_result = {
        "is_eligible": True,
        "details": {
            "rule_2": {"passed": True, "rule_name": "國籍", "is_hard_rule": True},
            "rule_5": {"passed": False, "rule_name": "GPA門檻", "is_hard_rule": True},
            "rule_8": {"passed": False, "rule_name": "在學", "is_warning": True},
        },
    }
    rule_columns = service._collect_rule_columns([item])  # [(2,國籍),(5,GPA門檻),(8,在學)]

    rows, fills = service._prepare_excel_data(roster, [item], rule_columns)

    r, f = rows[0], fills[0]
    assert r["學籍驗證"] == "已驗證"
    assert r["規則資格"] == "符合"
    assert r["國籍"] == "通過"
    assert r["GPA門檻"] == "未通過"
    assert r["在學"] == "未通過"
    assert r["納入造冊"] == "是"
    # fills: hard fail → red, warning fail → amber, passed → no entry
    assert "國籍" not in f
    assert f["GPA門檻"] == "red"
    assert f["在學"] == "amber"


def test_unverified_and_excluded_and_missing_bank_fills_red(service):
    roster = _make_roster()
    item = _make_item(student_name="乙", bank_account=None, is_included=False)
    item.verification_status = "graduated"
    item.is_eligible = False
    item.exclusion_reason = "學籍驗證未通過: graduated"

    rows, fills = service._prepare_excel_data(roster, [item], [])

    r, f = rows[0], fills[0]
    assert r["學籍驗證"] == "已畢業"
    assert r["規則資格"] == "不符合"
    assert r["納入造冊"] == "否"
    assert r["排除原因"] == "學籍驗證未通過: graduated"
    assert f["學籍驗證"] == "red"
    assert f["規則資格"] == "red"
    assert f["帳號"] == "red"
    assert f["納入造冊"] == "red"
    assert f["排除原因"] == "red"


def test_no_snapshot_item_renders_dashes_without_fill(service):
    roster = _make_roster()
    item = _make_item(student_name="丙")
    item.is_eligible = None
    item.rule_validation_result = None

    rows, fills = service._prepare_excel_data(roster, [item], [(2, "國籍")])

    assert rows[0]["規則資格"] == "—"
    assert rows[0]["國籍"] == "—"
    assert "規則資格" not in fills[0]
    assert "國籍" not in fills[0]


def test_excel_row_data_written_back_is_clean(service):
    """write-back 不含上色 metadata（fills 走平行回傳，不污染 DB JSON）。"""
    roster = _make_roster()
    item = _make_item(student_name="丁")
    rows, _ = service._prepare_excel_data(roster, [item], [])
    assert item.excel_row_data == rows[0]
    assert "__cell_fills__" not in item.excel_row_data
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -p no:cacheprovider --no-cov -q`
Expected: 新測試 FAIL（`_prepare_excel_data` 尚回傳 list 而非 tuple / 無驗證欄）。

- [ ] **Step 4: 實作 `_prepare_excel_data`**

將 `_prepare_excel_data` 全面改寫為（保留既有 base 欄位與 remarks 邏輯，新增驗證/規則欄與 fills）：

```python
    def _prepare_excel_data(
        self,
        roster: PaymentRoster,
        roster_items: List[PaymentRosterItem],
        rule_columns: Optional[List["tuple[int, str]"]] = None,
    ) -> "tuple[List[Dict], List[Dict[str, str]]]":
        """準備 Excel 資料 — base 30 欄 + 資格驗證欄。

        回傳 (excel_data, cell_fills)：cell_fills 與 excel_data 等長平行，
        每筆為 {欄名: "red"|"amber"}，供 _create_excel_file 套色。
        item.excel_row_data 仍寫回乾淨 row dict（不含 fills）。
        """
        rule_columns = rule_columns or []
        excel_data: List[Dict] = []
        cell_fills: List[Dict[str, str]] = []

        for idx, item in enumerate(roster_items, start=1):
            if not item.student_id_number or not item.student_name:
                logger.warning(
                    f"Skipping item {idx} due to missing required fields: "
                    f"ID={item.student_id_number}, Name={item.student_name}"
                )
                continue

            # 說明欄（沿用既有邏輯）
            remarks_parts = []
            if hasattr(roster, "period_label") and roster.period_label:
                remarks_parts.append(f"期間:{roster.period_label}")
            remarks_parts.append(f"獎學金:{item.scholarship_name}")
            if item.application_identity:
                remarks_parts.append(f"身分:{item.application_identity}")
            if item.allocated_sub_type:
                sub_type_display = {
                    "nstc": "國科會",
                    "moe_1w": "教育部(1萬)",
                    "moe_2w": "教育部(2萬)",
                }.get(item.allocated_sub_type, item.allocated_sub_type)
                alloc_label = sub_type_display
                if item.allocation_year:
                    alloc_label = f"{item.allocation_year}年 {sub_type_display}"
                remarks_parts.append(f"分發:{alloc_label}")
            if not item.is_included:
                remarks_parts.append("狀態:不合格")
            if not item.bank_account:
                remarks_parts.append("缺銀行資訊")
            remarks = " ".join(remarks_parts)

            row_data = {
                "身分證字號": item.student_id_number,
                "姓名": item.student_name,
                "帳號": item.bank_account or "",
                "銀行代碼": "700",
                "職別(稱)": "學生",
                "戶籍地址": item.permanent_address or "",
                "身份別代碼": "1",
                "單位(ex:時,月,次...)": "次",
                "數量": "1",
                "單價": float(item.scholarship_amount) if item.scholarship_amount else 0,
                "機關負擔勞保費": "",
                "機關負擔健保費": "",
                "機關負擔補充保費": "",
                "機關負擔勞退金": "",
                "機關負擔離職金": "",
                "機關負擔職災": "",
                "個人自付勞保費": "",
                "個人自付健保費": "",
                "個人自付補充保費": "",
                "個人自付勞退金": "",
                "個人自付離職金": "",
                "代扣所得": "",
                "其他代扣": "",
                "免稅給付": float(item.scholarship_amount) if item.scholarship_amount else 0,
                "說明": remarks,
                "E-MAIL": item.student_email or "",
                "個人身分別(1:本國人,2:外國人,3:大陸人)": "1",
                "居留天數是否滿183天(是/否)": "是",
                "申請身分": item.application_identity or "",
                "分發獎學金": self._format_allocation_display(item),
            }

            fills: Dict[str, str] = {}

            # 銀行帳號缺漏 → 帳號欄紅
            if not item.bank_account:
                fills[self.COL_BANK_ACCOUNT] = "red"

            # 學籍驗證
            status = item.verification_status
            row_data[self.COL_VERIFICATION] = self._get_verification_status_label(status)
            status_value = status.value if hasattr(status, "value") else str(status)
            if status_value != "verified":
                fills[self.COL_VERIFICATION] = "red"

            # 整體規則資格（重用 is_eligible property；stub 以屬性提供）
            elig = getattr(item, "is_eligible", None)
            row_data[self.COL_RULE_SUMMARY] = "符合" if elig is True else ("不符合" if elig is False else "—")
            if elig is False:
                fills[self.COL_RULE_SUMMARY] = "red"

            # 逐條規則欄（讀凍結快照，不重跑）
            rvr = item.rule_validation_result
            details = rvr.get("details") if isinstance(rvr, dict) else None
            for rid, header in rule_columns:
                res = details.get(f"rule_{rid}") if isinstance(details, dict) else None
                if isinstance(res, dict) and "passed" in res:
                    passed = res.get("passed")
                    row_data[header] = "通過" if passed else "未通過"
                    if not passed:
                        if res.get("is_hard_rule"):
                            fills[header] = "red"
                        elif res.get("is_warning"):
                            fills[header] = "amber"
                else:
                    row_data[header] = "—"

            # 納入造冊 / 排除原因
            row_data[self.COL_INCLUDED] = "是" if item.is_included else "否"
            row_data[self.COL_EXCLUSION] = item.exclusion_reason or ""
            if not item.is_included:
                fills[self.COL_INCLUDED] = "red"
                fills[self.COL_EXCLUSION] = "red"

            item.excel_row_data = row_data
            item.excel_remarks = remarks

            excel_data.append(row_data)
            cell_fills.append(fills)

        logger.info(f"Prepared {len(excel_data)} rows for export ({len(rule_columns)} rule columns)")
        return excel_data, cell_fills
```

- [ ] **Step 5: 跑全檔測試確認通過**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -p no:cacheprovider --no-cov -q`
Expected: PASS（既有 + 新測試全綠）。

- [ ] **Step 6: Commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility
git add backend/app/services/excel_export_service.py backend/app/tests/test_excel_export_service_rows.py
git commit -m "feat(roster-excel): add verification + per-rule columns with fill metadata to _prepare_excel_data"
```

---

## Task 4: 套色寫檔 + 接線（`_create_excel_file` / styling / `export_roster_to_excel` / `preview_roster_export`）

**Files:**
- Modify: `backend/app/services/excel_export_service.py`
  - 新增 `RED_FILL` / `AMBER_FILL` class 常數。
  - `export_roster_to_excel`（約 226-341）、`preview_roster_export`（約 897-944）接線。
  - `_create_excel_file`（約 598-666）、`_apply_excel_styling`（668-672）、`_set_column_widths`（674-720）、`_set_borders`（722-733）改吃 `columns` 並套色。
- Test: `backend/app/tests/test_excel_export_service_rows.py`（新增實際寫檔讀 `cell.fill` 的整合測試）

**Interfaces:**
- Consumes: `_collect_rule_columns`、`_build_export_columns`、`_prepare_excel_data`（前述）。
- Produces:
  - `RED_FILL`、`AMBER_FILL`（class 常數）
  - `_create_excel_file(excel_data, cell_fills, file_path, roster, *, template_path, columns, include_header, include_statistics)`
  - `_apply_excel_styling(ws, max_row, include_header, columns)`、`_set_column_widths(ws, columns)`、`_set_borders(ws, max_row, columns)`

- [ ] **Step 1: 寫失敗測試（實際寫檔 + 讀 cell.fill）**

```python
# ---------------------------------------------------------------------------
# End-to-end Excel write — headers, per-rule columns, red/amber cell fills
# ---------------------------------------------------------------------------


def test_create_excel_file_writes_headers_and_fills(service, tmp_path):
    import openpyxl

    roster = _make_roster()
    item = _make_item(student_name="甲", bank_account=None, is_included=False)
    item.verification_status = "withdrawn"
    item.is_eligible = False
    item.exclusion_reason = "學籍驗證未通過: withdrawn"
    item.rule_validation_result = {
        "is_eligible": False,
        "details": {"rule_3": {"passed": False, "rule_name": "GPA", "is_hard_rule": True}},
    }

    rule_columns = service._collect_rule_columns([item])
    columns = service._build_export_columns(rule_columns)
    rows, fills = service._prepare_excel_data(roster, [item], rule_columns)

    out = tmp_path / "roster.xlsx"
    service._create_excel_file(
        rows,
        fills,
        str(out),
        roster,
        template_path="/nonexistent.xlsx",
        columns=columns,
        include_header=True,
        include_statistics=False,
    )

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    header = [ws.cell(row=1, column=c).value for c in range(1, len(columns) + 1)]
    assert header[-4:] == ["學籍驗證", "GPA", "納入造冊", "排除原因"]

    def fill_of(col_name):
        c = columns.index(col_name) + 1
        return ws.cell(row=2, column=c).fill.start_color.rgb

    assert "FFC7CE" in str(fill_of("學籍驗證"))   # red
    assert "FFC7CE" in str(fill_of("GPA"))         # red (hard fail)
    assert "FFC7CE" in str(fill_of("帳號"))         # red (missing bank)
    assert "FFC7CE" in str(fill_of("納入造冊"))      # red
    # 姓名欄不應上色
    assert "FFC7CE" not in str(fill_of("姓名"))


def test_create_excel_file_amber_for_warning_rule(service, tmp_path):
    import openpyxl

    roster = _make_roster()
    item = _make_item(student_name="乙")
    item.rule_validation_result = {
        "is_eligible": True,
        "details": {"rule_9": {"passed": False, "rule_name": "在學狀態", "is_warning": True}},
    }
    rule_columns = service._collect_rule_columns([item])
    columns = service._build_export_columns(rule_columns)
    rows, fills = service._prepare_excel_data(roster, [item], rule_columns)

    out = tmp_path / "roster_amber.xlsx"
    service._create_excel_file(rows, fills, str(out), roster, template_path="/nonexistent.xlsx",
                               columns=columns, include_header=True, include_statistics=False)

    wb = openpyxl.load_workbook(out)
    ws = wb.active
    c = columns.index("在學狀態") + 1
    assert "FFEB9C" in str(ws.cell(row=2, column=c).fill.start_color.rgb)  # amber
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -k "create_excel_file" -p no:cacheprovider --no-cov -q`
Expected: FAIL（`_create_excel_file` 簽章不符 / 未套色）。

- [ ] **Step 3a: 新增 fill 常數**

在 class 常數區（`ALLOWED_TEMPLATES` 或 `COL_*` 附近）新增：

```python
    RED_FILL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
    AMBER_FILL = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
```

- [ ] **Step 3b: 改寫 `_create_excel_file`**

整段取代為（統一在 include_header 時依 `columns` 寫表頭，並用 `cell_fills` 套色）：

```python
    def _create_excel_file(
        self,
        excel_data: List[Dict],
        cell_fills: List[Dict[str, str]],
        file_path: str,
        roster: PaymentRoster,
        *,
        template_path: str,
        columns: List[str],
        include_header: bool,
        include_statistics: bool,
    ):
        """建立 Excel 檔案 — 依 columns 寫表頭/資料並套用紅/琥珀底。"""
        try:
            use_template = include_header and os.path.exists(template_path)

            if use_template:
                wb = load_workbook(template_path)
                ws = wb.active
                logger.info("Using template file for Excel generation: %s", template_path)
            else:
                wb = Workbook()
                ws = wb.active
                ws.title = "印領清冊"
                logger.info("Created new Excel file using default structure (include_header=%s)", include_header)

            # 清掉既有列，統一依 columns 重寫
            if ws.max_row >= 1:
                ws.delete_rows(1, ws.max_row)

            if include_header:
                for col_idx, column_name in enumerate(columns, start=1):
                    cell = ws.cell(row=1, column=col_idx, value=column_name)
                    cell.font = Font(bold=True)
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                    cell.fill = PatternFill(start_color="D3D3D3", end_color="D3D3D3", fill_type="solid")
                start_row = 2
            else:
                start_row = 1

            for row_idx, (row_data, fills) in enumerate(zip(excel_data, cell_fills), start=start_row):
                for col_idx, column_name in enumerate(columns, start=1):
                    value = row_data.get(column_name, "")
                    cell = ws.cell(row=row_idx, column=col_idx, value=value)

                    if column_name in ["金額", "扣繳稅額", "單價", "免稅給付"] and isinstance(value, (int, float)):
                        cell.number_format = "#,##0"
                    elif column_name in ["序號", "流水號"]:
                        cell.alignment = Alignment(horizontal="center")

                    kind = fills.get(column_name)
                    if kind == "red":
                        cell.fill = self.RED_FILL
                    elif kind == "amber":
                        cell.fill = self.AMBER_FILL

            total_rows = max(len(excel_data) + (1 if include_header else 0), 1)
            self._apply_excel_styling(ws, total_rows, include_header, columns)

            if include_statistics:
                self._add_worksheet_info(wb, roster)

            wb.save(file_path)
            logger.info("Excel file created successfully: %s", file_path)

        except Exception as e:
            logger.exception("Failed to create Excel file")
            raise FileStorageError(
                f"Failed to create Excel file: {e}",
                file_name=os.path.basename(file_path),
            ) from e
```

- [ ] **Step 3c: styling 方法吃 `columns`**

```python
    def _apply_excel_styling(self, ws, max_row: int, include_header: bool, columns: List[str]):
        """應用 Excel 樣式"""
        self._set_column_widths(ws, columns)
        self._set_borders(ws, max_row, columns)
        ws.freeze_panes = "A2" if include_header else None
```

`_set_column_widths`：把開頭簽章改為 `(self, ws, columns: List[str])`，在 `default_widths` dict 內補上新欄寬，並把迴圈 `for col_idx, column_name in enumerate(self.template_columns, start=1)` 改為 `enumerate(columns, start=1)`。在 `default_widths` 加入：

```python
            "學籍驗證": 12,
            "規則資格": 10,
            "納入造冊": 10,
            "排除原因": 30,
```

`_set_borders`：簽章改 `(self, ws, max_row: int, columns: List[str])`，內層 `for col in range(1, len(self.template_columns) + 1)` 改為 `range(1, len(columns) + 1)`。

- [ ] **Step 3d: 接線 `export_roster_to_excel`**

於 `roster_items = self._get_roster_items(...)`（約 228）之後、`excel_data = self._prepare_excel_data(...)` 之處改為：

```python
            roster_items = self._get_roster_items(roster, include_excluded)

            file_name = roster.generate_excel_filename()
            file_path = os.path.join(self.export_base_path, file_name)

            rule_columns = self._collect_rule_columns(roster_items)
            export_columns = self._build_export_columns(rule_columns)

            excel_data, cell_fills = self._prepare_excel_data(roster, roster_items, rule_columns)
```

`_validate_export_data(excel_data)` 保持不變。`_create_excel_file(...)` 呼叫改為：

```python
            self._create_excel_file(
                excel_data,
                cell_fills,
                file_path,
                roster,
                template_path=resolved_template_path,
                columns=export_columns,
                include_header=include_header,
                include_statistics=include_statistics,
            )
```

回傳 dict 內 `"template_columns": self.template_columns,` 改為 `"template_columns": export_columns,`。

- [ ] **Step 3e: 接線 `preview_roster_export`**

於 `roster_items = self._get_filtered_roster_items(...)` 之後：

```python
            roster_items = self._get_filtered_roster_items(roster, include_excluded=include_excluded)

            rule_columns = self._collect_rule_columns(roster_items)
            export_columns = self._build_export_columns(rule_columns)

            excel_data, _ = self._prepare_excel_data(roster, roster_items, rule_columns)
```

並把回傳的 `"column_headers": self.template_columns,` 改為 `"column_headers": export_columns,`。

- [ ] **Step 4: 跑測試確認通過**

Run: `rtk proxy python -m pytest app/tests/test_excel_export_service_rows.py -p no:cacheprovider --no-cov -q`
Expected: PASS（全檔，含新整合測試）。

- [ ] **Step 5: Commit**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility
git add backend/app/services/excel_export_service.py backend/app/tests/test_excel_export_service_rows.py
git commit -m "feat(roster-excel): apply red/amber fills and wire dynamic columns into export + preview"
```

---

## Task 5: 回歸 + Lint gate

**Files:** 無新增；驗證整體。

- [ ] **Step 1: 跑相關 Excel 測試全綠**

Run:
```bash
rtk proxy python -m pytest \
  app/tests/test_excel_export_service_rows.py \
  app/tests/test_excel_export_service_pure_helpers.py \
  app/tests/test_excel_export_pure_helpers.py \
  app/tests/test_excel_validate_export_data.py \
  app/tests/test_excel_export_generate_remarks.py \
  -p no:cacheprovider --no-cov -q
```
Expected: PASS（若其他檔案恰好呼叫到改動的內部簽章而失敗，回到對應 Task 修正——預期僅 `test_excel_export_service_rows.py` 觸及這些 internals）。

- [ ] **Step 2: Black 檢查**

Run: `uvx --from "black==26.3.1" black --check --line-length=120 app/services/excel_export_service.py app/tests/test_excel_export_service_rows.py`
Expected: `All done!`（若失敗，去掉 `--check` 重跑一次再 commit）。

- [ ] **Step 3: Flake8 硬性 gate**

Run: `flake8 app/services/excel_export_service.py app/tests/test_excel_export_service_rows.py --select=B904,B014,F401 --max-line-length=120`
Expected: 無輸出（exit 0）。

- [ ] **Step 4: Commit（若 black/flake8 有修）**

```bash
cd /home/howard/scholarship-system/.claude/worktrees/roster-excel-eligibility
git add -A && git commit -m "chore(roster-excel): black + flake8 cleanup" || echo "nothing to commit"
```

---

## Self-Review（plan vs spec）

- **Spec §3.1 動態欄位佈局** → Task 2（`_build_export_columns`）+ Task 4（接線）。✓
- **Spec §3.1 逐條規則欄、rule_id 排序、header 去重** → Task 2（`_collect_rule_columns` + 測試）。✓
- **Spec §3.2 欄位內容（學籍/規則資格/規則/納入/排除）** → Task 3。✓
- **Spec §3.3 紅/琥珀 per-cell、各條件** → Task 3（fills 字串）+ Task 4（實際套色 + 寫檔測試）。✓
- **Spec §3.4 納入範圍（隱藏手動移除）** → Task 1。✓
- **Spec §3.5 重用**：`_get_verification_status_label`（Task 3）、`is_eligible`（Task 3）、`rule_validation_result.details`（Task 2/3）、`_format_allocation_display`（Task 3 沿用）、既有 `PatternFill` import。✓
- **Spec §4 edge cases**：無快照→「—」（Task 3 測試）、`no_rules_found`/`error` 略過（Task 2 測試）、空 roster header-only（既有測試維持）、header 衝突（Task 2 測試）。✓
- **Spec §5 測試** → Task 1-5。✓
- **型別一致性**：`_collect_rule_columns -> List[(int,str)]`、`_build_export_columns(rule_columns)`、`_prepare_excel_data(...) -> (rows, fills)`、`_create_excel_file(excel_data, cell_fills, ..., columns=...)` 全程一致。✓
- **Placeholder scan**：無 TBD/TODO；每個 code step 皆含完整程式碼。✓
