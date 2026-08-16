# PII 加密與遮罩架構（身分證字號）

> 本文說明系統如何保護**身分證字號**:靜態加密(at rest)與顯示遮罩(masking)
> 的**設計原則與資料流**。金鑰輪替/保存的操作程序見
> [`pii-key-retention-runbook.md`](./pii-key-retention-runbook.md)。
> 實作檔案與驗證指令見文末附錄。源頭:issue #73。

---

## 1. 目標與原則

- **保護對象:身分證字號(`std_pid`,含居留證號)。** 其餘欄位如**學號**
  (`std_stdcode`)是系統學生主鍵、非敏感 PII,不加密。
- **靜態加密**:身分證字號寫進資料庫前一律加密,DB 落地永遠是密文。
- **最小外洩**:只供顯示的資料一律**遮罩**;只有合法需要全碼的流程(撥款造冊)才讀全碼。
- **無 fallback**:解密失敗就明確報錯,絕不回傳假資料或部分明文
  (遵守 CLAUDE.md 錯誤處理原則)。
- **單一整合點**:加解密在「儲存邊界」自動發生,應用層程式碼無需各自處理。

---

## 2. 資料流(high level)

```
SIS API ──┐
          ▼
   寫入 applications.student_data
          │   ← 儲存邊界自動「加密」身分證字號
          ▼
   DB 落地：身分證字號為密文  pii:v1:<…>
          │   ← 讀取時儲存邊界自動「解密」
          ▼
   應用層拿到明文身分證字號
          ├──► 顯示用 API / 前端  →  遮罩  A******789
          └──► 撥款造冊 Excel      →  全碼（合法需求）
```

三個關鍵分界:

1. **儲存邊界**:加解密只發生在這裡(寫入加密、讀取解密),其餘程式碼讀到的都是明文。
2. **顯示邊界**:資料離開伺服器給人看之前,身分證字號遮罩成「首碼 + ***  + 末三碼」。
3. **匯出邊界**:付款造冊明確保留全碼——這是刻意的例外,不套遮罩。

---

## 3. 靜態加密設計

| 面向 | 設計 |
|---|---|
| 演算法 | **AES-256-GCM**(authenticated encryption,可偵測竄改) |
| 落地格式 | 信封字串 `pii:<版本>:<base64url(nonce+密文+tag)>` |
| 為何用 `pii:` 前綴 | ① 可存進 JSON ② 永不與合法身分證(開頭字母)碰撞 ③ O(1) 判斷「是否已加密」→ 加密冪等、遷移可重跑 |
| 整合方式 | 套在 `applications.student_data` 欄位上的儲存型別,**自動**加解密身分證字號;30+ 處讀寫無需改動 |
| 冪等性 | 已加密的值再寫不重複加密;遷移可安全重跑 |
| 失敗行為 | 金鑰錯/竄改/信封壞 → 直接拋錯,無 fallback |

> 既有資料由一支批次遷移從明文轉成信封(冪等);稽核軌跡內的歷史殘留另有一支
> 遷移清成 `[REDACTED]`(見 §6)。

---

## 4. 金鑰模型

- **金鑰由環境變數提供**,與程式碼分離;系統本身不內嵌任何 production 金鑰。
- **版本化**:金鑰是「版本 → 金鑰」的對應表,信封內嵌版本號。可同時保留多版本
  → **支援輪替**(新資料用新版本、舊資料用舊版本解),不需一次性全量重加密。
- **環境差異**:

  | 環境 | 金鑰來源 |
  |---|---|
  | 本機 dev | 由固定種子推導的 **dev key**(僅供開發,會 log 警告) |
  | **test**(正式 repo 的測試部署) | 正式 repo `test` **GitHub Environment** 的 secret |
  | **production** | 同一支 workflow、`production` Environment 的 secret |

  部署鏈:開發 repo(`anud18/scholarship-system`)只負責建置 image;正式 repo
  (`NYCUITSC/naass`,private)鏡像原始碼但**不重建**,由 `deploy-test.yml` /
  `deploy-production.yml` 各自呼叫同一支 `deploy-stack.yml`。stage 只決定
  ①落在哪台 self-hosted runner ②由哪個 GitHub Environment 供 secret,其餘完全
  相同——**test 部署就是 production 部署的排練**,金鑰注入路徑一模一樣。

- **注入方式(兩種,由 Environment 變數 `ENV_FILE` 決定)**:

  | 模式 | 金鑰所在 |
  |---|---|
  | 預設 | 部署時由 Environment secret 產生 AP VM 上的 `.env`(mode 600),再 `--env-file` 餵給 compose |
  | `ENV_FILE` 有設 | 使用 VM 上維運人員自管的 .env,**金鑰完全不經過 GitHub** |

- **test 與 production 的金鑰必須不同**。GitHub 的 fallback 是這裡最危險的一點:
  environment 沒定義的 secret 會自動往上抓 **repository 層(= production 值)**,
  test 部署因此可能拿到 production 金鑰——那等於「測試資料庫的備份足以解開正式
  個資」。防呆是 `deploy-stack.yml` 的 *Assert stage identity*:每個 environment
  自報 `DEPLOY_STAGE` / `EXPECT_DOMAIN` / `EXPECT_DB_HOST`,對不上就拒絕部署。

- **安全閥(兩層)**:部署前 workflow 會檢查 `PII_ENCRYPTION_KEYS` 有值且為合法
  JSON,缺漏或壞掉就中止;容器內兩個 tier 都是 `ENVIRONMENT=production`,所以
  執行期缺金鑰時後端與加密遷移**直接失敗**,不會退回 dev key。test tier 因此在
  結構上不可能誤用 dev key——缺金鑰部署就 fail。
- 輪替/保存/汰除舊金鑰的程序見
  [runbook](./pii-key-retention-runbook.md)(核心鐵律:**舊金鑰在其加密資料超過
  保存年限前絕不移除**,否則含備份在內的舊資料等同銷毀)。

---

## 5. 兩個落地位置(重要區別)

身分證字號在 DB 有兩處,加密狀態**刻意不同**:

| 位置 | 用途 | 狀態 |
|---|---|---|
| 申請資料快照(`applications.student_data`) | 系統內部主要來源 | **加密** |
| 造冊明細(`payment_roster_items`) | 撥款 Excel 直接讀 | **明文(設計如此)** |

造冊明細存全碼,是因為付款流程的 Excel「身分證字號」欄需要完整值;對外顯示時
才透過遮罩處理。**這不是漏洞**,但屬於需要存取控制保護的敏感資料表。

---

## 6. 顯示遮罩與稽核

- **遮罩規則**:保留**首碼 + 末三碼**,中間以 `*` 取代(長度 ≤ 4 只留首碼)。
  例:`A123456789 → A******789`。冪等。
- **前後端一致**:後端與前端各有一份遮罩函式,**必須同步**,確保同一筆 ID 在
  API 回應與畫面上長相一致。
- **套用原則**:顯示端遮罩、匯出端保留全碼(§2 的兩個邊界)。
- **稽核軌跡**:稽核 log 是獨立的 JSON 複本,身分證字號在**寫入時**即被換成
  `[REDACTED]`,歷史殘留也已由遷移清除。因此**金鑰遺失只影響申請資料的可讀性,
  不影響稽核軌跡**。

---

## 7. 信任邊界與待強化點

- **信任邊界**:能存取正式 repo(`NYCUITSC/naass`)`test` / `production`
  Environment secret 的人、能修改或核准部署 workflow 的人(每個 stage 的
  environment 都設有 required reviewer),即可取得對應 tier 的金鑰。改用
  `ENV_FILE` 模式時金鑰只存在 AP VM 上,信任邊界收斂成「能登入該 VM 的人」。
  > 📌 部署設定註解寫「由 KMS sidecar 注入」,**目前實作其實是 GitHub
  > Environment secret(或 VM 上的 .env)**,非真 KMS。若日後升級 KMS,只需
  > 替換金鑰注入方式,加解密程式不需動。
- **待強化:審查預覽端點**。審查對話框目前把**明文**身分證字號送到瀏覽器、由
  前端遮罩;若要落實「全碼不離開伺服器」,應改成該 API 回應就先遮罩。

---

## 附錄 A — 實作檔案索引

| 檔案 | 角色 |
|---|---|
| `backend/app/core/pii_crypto.py` | 加解密 + 稽核 redaction 核心 |
| `backend/app/core/encrypted_json.py` | 儲存邊界自動加解密的型別(`StudentDataJSON`) |
| `backend/app/utils/pii_masking.py` / `frontend/lib/utils/mask.ts` | 後端 / 前端遮罩(必須一致) |
| `backend/alembic/versions/20260512_encrypt_std_pid.py` | 既有資料加密遷移 |
| `backend/alembic/versions/20260513_scrub_pii_from_audit_logs.py` | 清稽核歷史殘留 |
| `backend/alembic/versions/20260529_backfill_roster_national_id.py` | 造冊欄位 backfill |
| `backend/scripts/rotate_pii_keys.py` | 金鑰輪替 / re-encrypt |
| `docs/security/pii-key-retention-runbook.md` | 金鑰保存與輪替程序 |
| `docs/architecture/pii-encryption.md` | 金鑰產生方式(部署失敗訊息會指向這裡) |
| `.github/production-workflows-examples/deploy-stack.yml` | 兩個 stage 共用的部署腳本(金鑰驗證、`.env` 產生、stage 防呆) |
| `.github/production-workflows-examples/SECRETS-SETUP-GUIDE.md` | `test` / `production` Environment 的 secret 設定清單 |

## 附錄 B — test 部署驗證指令（read-only）

> ⚠️ 兩個 tier 都是用 `docker-compose.prod.yml` 部署的,容器名稱**都是
> `scholarship_*_prod`**,差別只在跑在哪台 AP VM(部署目錄預設
> `~/scholarship-test` / `~/scholarship-production`)。下指令前先確認自己登在哪台。
> DB 不在 AP VM 上,是獨立的 DB VM(`docker-compose.prod-db.yml`,容器
> `scholarship_postgres_prod`)。

確認已加密(在 AP VM,透過 backend 容器連該 tier 的 DB;只看前綴,不外洩全碼):
```bash
docker exec -i scholarship_backend_prod python - <<'PY'
from app.db.session import sync_engine
from sqlalchemy import text
with sync_engine.connect() as conn:
    print(conn.execute(text("""
        SELECT count(*) FILTER (WHERE student_data->>'std_pid' LIKE 'pii:%')            AS encrypted,
               count(*) FILTER (WHERE student_data->>'std_pid' NOT LIKE 'pii:%')        AS plaintext
        FROM applications WHERE student_data->>'std_pid' IS NOT NULL""")).one())
PY
```
若人已經在 DB VM 上,同一件事也可以直接查(帳密取自該 tier 的 `.env`):
```bash
docker exec scholarship_postgres_prod psql -U "$DB_USER" -d "$DB_NAME" -c "
SELECT count(*) FILTER (WHERE student_data->>'std_pid' LIKE 'pii:%')                                              AS encrypted,
       count(*) FILTER (WHERE student_data->>'std_pid' IS NOT NULL AND student_data->>'std_pid' NOT LIKE 'pii:%') AS plaintext
FROM applications WHERE student_data->>'std_pid' IS NOT NULL;"
```
驗證可解密 round-trip(backend 容器,輸出遮罩):
```bash
docker exec -i scholarship_backend_prod python - <<'PY'
from app.db.session import sync_engine
from app.core.pii_crypto import decrypt_pii
from sqlalchemy import text
with sync_engine.connect() as conn:
    rows = conn.execute(text("SELECT id, student_data->>'std_pid' FROM applications "
        "WHERE student_data->>'std_pid' LIKE 'pii:%' LIMIT 3")).fetchall()
for app_id, ct in rows:
    pt = decrypt_pii(ct)
    print(f"app#{app_id}: {ct[:18]}... -> {pt[0]}{'*'*(len(pt)-3)}{pt[-2:]}")
PY
```
確認這個 tier 用的**不是** production 金鑰(比對 active version / 金鑰指紋,不印金鑰本身):
```bash
docker exec -i scholarship_backend_prod python - <<'PY'
import hashlib, os
print("active:", os.getenv("PII_ENCRYPTION_ACTIVE_VERSION"))
print("keys sha256[:8]:", hashlib.sha256(os.getenv("PII_ENCRYPTION_KEYS","").encode()).hexdigest()[:8])
PY
```
兩個 tier 跑出來的指紋**必須不同**;相同就代表 `test` environment 漏設 secret、
fallback 到了 repository 層的 production 值(§4)。
