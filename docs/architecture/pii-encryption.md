# 資料庫加密：身分證字號（std_pid）PII 保護機制

本文件介紹獎學金系統如何在資料庫層加密保護台灣身分證字號（`std_pid`，National ID）。此機制源自 Issue #73，目標是確保身分證字號在資料庫「靜態儲存（at rest）」時永遠是密文，同時讓應用層程式碼幾乎不需修改即可透明地讀寫明文。

## 總覽

| 項目 | 內容 |
|---|---|
| 加密演算法 | AES-256-GCM（認證加密，可偵測竄改） |
| 密文格式（envelope） | `pii:<version>:<base64url(nonce(12) ‖ ciphertext ‖ tag(16))>` |
| 金鑰來源 | `PII_ENCRYPTION_KEYS` 環境變數（JSON：`{版本: base64url 32-byte 金鑰}`） |
| 使用中金鑰版本 | `PII_ENCRYPTION_ACTIVE_VERSION`（預設 `v1`） |
| 加密欄位 | `applications.student_data` JSON 中的 `std_pid` |
| 整合方式 | SQLAlchemy `TypeDecorator`，於 ORM 存取邊界自動加解密 |
| 失敗策略 | 解密失敗直接拋出 `PIICryptoError`，**不回傳 fallback 資料** |

## 核心模組

### 1. 加解密工具：`backend/app/core/pii_crypto.py`

提供所有底層加解密函式：

- `encrypt_pii(plaintext)` — 以使用中（active）金鑰版本加密，回傳 envelope 字串。
- `decrypt_pii(ciphertext)` — 解析 envelope、依其內嵌的版本選擇金鑰解密。GCM tag 驗證失敗（遭竄改或金鑰錯誤）會拋出 `PIICryptoError`。
- `encrypt_pii_idempotent(value)` — **冪等加密**：已是 envelope 的值直接通過，`None` / 空字串原樣通過。資料遷移可安全重跑。
- `is_encrypted(value)` — O(1) 的 `pii:` 前綴檢查。
- `redact_dict_pii(data)` — 將 dict 中的 `std_pid` 取代為 `[REDACTED]`，供稽核日誌（audit log）寫入前使用。

#### Envelope 格式設計

```
pii:v1:Aa1Bb2...（base64url 編碼的 nonce + ciphertext + tag）
```

- `pii:` 前綴是純 ASCII，可安全存於 JSON 欄位。
- 台灣身分證字號一定以英文字母 `[A-Z]` 開頭，**永遠不會與 `pii:` 前綴衝突**，因此可用 O(1) 前綴檢查判斷是否已加密。
- 版本號（如 `v1`）內嵌在密文中，解密時自動選對金鑰，支援金鑰輪替。
- nonce 為每次加密隨機產生的 12 bytes，GCM tag 16 bytes 提供完整性驗證。

#### 金鑰載入規則

1. 從 `PII_ENCRYPTION_KEYS` 讀取 JSON 金鑰表，例如 `{"v1": "<base64url 32-byte key>"}`，每把金鑰必須是 32 bytes（AES-256）。
2. 金鑰以 `lru_cache` 每個 process 快取一次；測試可呼叫 `reset_key_cache()` 清除。
3. **開發環境 fallback**：若環境變數為空且 `ENVIRONMENT != production`，會從固定 seed 派生一把確定性的開發金鑰，並記錄 WARNING（`docker compose dev` 無需設定即可運作）。
4. **正式環境強制要求**：`ENVIRONMENT=production` 且未設定金鑰時，啟動直接失敗（`PIICryptoError`）。

### 2. 透明加解密層：`backend/app/core/encrypted_json.py`

`StudentDataJSON` 是一個 SQLAlchemy `TypeDecorator`（`impl = JSON`），套用在 `Application.student_data` 欄位上（見 `backend/app/models/application.py:138`）：

```python
student_data = Column(StudentDataJSON)  # Student 資料
```

- **寫入（`process_bind_param`）**：持久化前自動將 dict 中的 `std_pid` 加密；其他 key 原樣通過。會 shallow-copy，不改動呼叫端的 dict。
- **讀取（`process_result_value`）**：載入時自動把 envelope 解密回明文。
- 這是**唯一的整合點**——30 多個讀寫 `student_data` 的呼叫端完全不需修改，應用層看到的永遠是明文，資料庫存的永遠是密文。
- 冪等設計讓資料遷移在此 TypeDecorator 生效前後都能安全執行。

直接下 raw SQL 查詢 `applications.student_data` 時看到的是 `pii:v1:...` 密文；只有透過 ORM 讀取才會解密。

## 資料遷移（Alembic Migrations）

| Migration | 內容 |
|---|---|
| `20260512_encrypt_std_pid` | 以 500 筆為一批，將既有 `applications.student_data` 中的明文 `std_pid` 就地加密。冪等（已加密的列跳過）。downgrade 刻意為 no-op。 |
| `20260513_scrub_pii_from_audit_logs` | 歷史稽核紀錄清洗：遞迴走訪 `audit_logs` 的 `old_values` / `new_values` / `meta_data` / `request_headers` 四個 JSON 欄位，把任意深度的 `std_pid` 值改寫為 `[REDACTED]`。先用 SQL `LIKE '%std_pid%'` 過濾以降低成本，冪等可重跑。 |
| `20260529_backfill_roster_national_id` | 透過 ORM（自動解密）把 `applications.student_data.std_pid` 回填到 `payment_roster_items.student_id_number`（造冊 Excel 的「身分證字號」欄位需求）。 |

## 金鑰輪替（Key Rotation）

腳本：`backend/scripts/rotate_pii_keys.py`

```bash
# 1. 在 PII_ENCRYPTION_KEYS 同時放入新舊金鑰
#    {"v1": "<舊金鑰>", "v2": "<新金鑰>"}
# 2. 將 PII_ENCRYPTION_ACTIVE_VERSION 設為 v2
# 3. 在 backend container 內執行：
docker compose -f docker-compose.dev.yml exec backend \
    python scripts/rotate_pii_keys.py            # 加 --dry-run 可先預覽
```

流程：分批（500 筆）掃描 `applications`，凡 envelope 版本 ≠ active 版本者，用舊版本金鑰解密、新版本金鑰重新加密後寫回。冪等、可重跑；rollback 只需把 active 版本設回舊版重跑一次。輪替完成後即可從金鑰表移除舊金鑰。

## 部署設定

| 環境 | 設定位置 |
|---|---|
| 開發（`docker-compose.dev.yml`） | `PII_ENCRYPTION_KEYS: ""`（空值 → 使用確定性開發金鑰 + WARNING） |
| Staging（`docker-compose.staging.yml`） | 由環境變數 `${PII_ENCRYPTION_KEYS}` 注入 |
| 正式（`docker-compose.prod.yml`） | 由環境變數注入；缺少時後端啟動失敗 |
| CI/CD（`.github/workflows/deploy-pipeline.yml`） | 從 GitHub Secrets 注入，部署前驗證 secret 存在，否則直接報錯 |

產生新金鑰範例：

```bash
python -c "import os, base64; print(base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode())"
gh secret set PII_ENCRYPTION_KEYS --body '{"v1":"<KEY>"}'
```

對應的 Pydantic 設定在 `backend/app/core/config.py`（`pii_encryption_keys`、`pii_encryption_active_version`）。在 KMS 託管的部署中，環境變數由 sidecar 於開機時填入，本模組本身保持 KMS-agnostic。

## 縱深防禦（Defense in Depth）

加密 at rest 之外，系統還有多層配套：

1. **稽核日誌遮蔽**：稽核寫入端（如 `roster_service.py`）在寫 `old_values` / `new_values` 前先呼叫 `redact_dict_pii()`。因為稽核快照是獨立的 JSON 複本，不會經過 `StudentDataJSON` 的加密，若不遮蔽就會把 ORM 已解密的明文寫進稽核表。
2. **明文存取留痕（`pii_access` 稽核事件）**：業務需求確認部分 Excel 匯出（如學院排名匯出 `college_ranking_export_service.py`）必須顯示完整身分證字號。凡輸出完整明文 `std_pid` 的操作都會寫入 `AuditAction.pii_access` 稽核紀錄（操作者、範圍、`pii_fields: ["std_pid"]`）。
3. **失敗即報錯**：依照專案的錯誤處理準則，解密失敗（金鑰設定錯誤、資料遭竄改）一律拋出 `PIICryptoError`，絕不靜默回傳 fallback 資料。

## 已知的明文邊界

下列位置依業務需求持有解密後的明文，屬於設計上的已知邊界：

- `payment_roster_items.student_id_number`（`String(20)`）：造冊時從 `student_data.std_pid` 快照而來的**明文**身分證字號，因為撥款 Excel 範本的「身分證字號」欄位需要完整值。跨名冊的學生比對（已領月數、36 個月上限等）改用 `student_number`（學號）欄位，不使用身分證字號。
- 匯出的 Excel 檔案本身含明文身分證字號——以 `pii_access` 稽核事件留痕。

## 測試

| 測試檔 | 涵蓋範圍 |
|---|---|
| `backend/app/tests/test_pii_crypto.py`、`test_pii_crypto_helpers.py` | envelope 格式、加解密 round-trip、竄改偵測（GCM tag）、金鑰載入錯誤情境 |
| `backend/app/tests/test_encrypted_json_typedecorator.py` | TypeDecorator 寫入加密 / 讀取解密、冪等性、非 dict 值通過 |
| `backend/app/tests/test_pii_encryption_integration.py` | ORM 端到端整合 |
| `backend/app/tests/test_rotate_pii_envelope_helper.py` | 金鑰輪替輔助函式 |
| `backend/app/tests/test_roster_audit_pii_redaction.py` | 造冊稽核日誌 PII 遮蔽 |

測試注意事項：驗證竄改偵測時要破壞 envelope **中段**的 base64 字元（破壞最後一個字元可能只命中 padding bits 而不改變位元組，導致 flaky `DID NOT RAISE`）。

## 開發者注意事項

- **不要**在新程式碼直接呼叫 `re`/手動處理 `std_pid` 加解密——透過 ORM 讀寫 `Application.student_data` 即自動處理。
- 任何會把 `student_data` 複製到其他表（稽核、快照、匯出）的新程式路徑，必須自行決定：遮蔽（`redact_dict_pii`）、加密（`encrypt_pii_idempotent`），或留痕（`pii_access` 稽核事件）。
- 新增其他需要加密的 PII 欄位時，模式是擴充 TypeDecorator 處理的 key 清單，並比照 `20260512` 撰寫冪等的批次遷移。
