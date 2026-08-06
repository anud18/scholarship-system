# OWASP ZAP 已認證主動掃描報告（Authenticated Active Scan）

**系統**：NYCU 獎學金管理系統 — 後端 API
**掃描日期**：2026-08-06
**工具**：OWASP ZAP 2.17.0（`ghcr.io/zaproxy/zaproxy:stable`）
**模式**：**Active Scan** — 發送實際攻擊 payload（SQLi / XSS / 路徑遍歷 / 命令注入 / 格式字串等）
**受測版本**：`main` @ `4325315a`
**掃描時間**：activeScan 25 分 14 秒
**認證身分**：admin（Bearer JWT，由 replacer 規則注入所有請求）

> 這份報告補的是 [baseline 被動掃描](../zap-baseline-2026-08-06/README.md) 明列的第 2 項限制
> ——「未發送攻擊 payload，不涵蓋 SQLi、XSS、指令注入等主動測試」。

## 結論（先講重點）

| 項目 | 結果 |
|---|---|
| 確認成立的注入類弱點（SQLi / XSS / 路徑遍歷 / 命令注入 / 格式字串） | **0** |
| ZAP 原始告警中 High / Medium 筆數 | 4 類（Path Traversal、OS Command Injection、Format String、XSS-in-JSON） |
| 上述 4 類經人工逐項驗證後 | **全部為誤報**，理由見第 3 節 |
| **實際發現的問題** | **未處理的例外導致 HTTP 500** — 正式環境可達端點 **4,948 次 / 54 個端點** |
| 堆疊資訊外洩 | **無**（`DEBUG=false` 下僅回傳一般化訊息 + `trace_id`） |
| 授權控制 | **正常**：未帶 token 一律 401、student 角色一律 403 |
| 速率限制 | **有作用**：掃描期間觸發 1,258 次 429 |

**沒有發現可被外部攻擊者利用的注入類弱點。** 但主動掃描揭露了一個 baseline 掃描不可能看到的
**系統性健壯性問題**：大量端點在收到格式不符的參數時直接拋出未捕捉的例外，回傳 500。

## 1. 為什麼這次掃得到，baseline 掃不到

| | baseline（被動） | 本次（主動 + 已認證） |
|---|---|---|
| 爬到的後端 URL 數 | **3**（`/`、`/robots.txt` 404、`/sitemap.xml` 404） | **416**（由 OpenAPI spec 匯入） |
| 認證狀態 | 未登入 | admin JWT |
| 送出的請求 | 僅正常請求 | 攻擊 payload，共 **200,344** 次請求 |

baseline 的癥結從來不是「被動 vs 主動」，而是**爬取覆蓋率**：未登入的爬蟲在登入頁就被擋下，
後端 API 需要 Bearer token，所以只掃到 3 個 URL。本次以 OpenAPI spec 直接餵入 416 個端點，
才讓主動掃描有意義。

掃描期間的 HTTP 狀態碼分布（共 200,344 筆，下表列出主要者）：

| 狀態碼 | 次數 | 意義 |
|---|---|---|
| 422 | 105,820 | Pydantic 參數驗證擋下 —— **這是正常且正確的防線** |
| 404 | 36,639 | 不存在的資源 |
| 403 | 22,300 | 權限不足（授權控制生效） |
| 200 | 19,023 | 正常回應 |
| 400 | 6,270 | 一般化的請求錯誤 |
| **500** | **5,281** | **未捕捉例外 —— 本報告的主要發現** |
| 405 | 2,593 | 方法不允許 |
| 429 | 1,258 | 速率限制生效 |
| 201 | 1,012 | 建立成功 |
| 401 | 125 | 未認證 |
| 204 / 409 | 20 / 3 | — |

## 2. 主要發現：未處理例外導致 HTTP 500

### 2.1 範圍

| 範圍 | 500 次數 | 端點數 |
|---|---|---|
| **正式環境可達** | **4,948** | **54** |
| 開發專屬（`/auth/dev-profiles/*`、`/auth/login`、`/auth/mock-sso/*`，正式環境 404） | 333 | 268 |

正式環境可達的前幾名：

| 次數 | 端點 |
|---|---|
| 1,705 | `POST /api/v1/application-fields/fields` |
| 412 | `POST /api/v1/manual-distribution/allocate` |
| 409 | `GET /api/v1/admin/announcements` |
| 406 | `PUT /api/v1/scholarship-configurations/matrix-quota` |
| 225 | `POST /api/v1/payment-rosters/{id}/dry-run` |
| 220 | `GET /api/v1/manual-distribution/quota-status` |
| 214 | `GET /api/v1/applications/review/list` |
| 212 | `GET /api/v1/admin/bank-verification/tasks` |
| 209 | `GET /api/v1/quota-dashboard/{alerts,overview,export}` |
| 209 | `GET /api/v1/scholarship-management/analytics/dashboard` |
| 205 | `GET /api/v1/notifications` |

### 2.2 三個可重現的根因

後端日誌中的例外型別分布：`DBAPIError` 5,296、`IntegrityError` 3,052、`ValueError` 2,639、
`AttributeError` 428、`InvalidTextRepresentationError` 410、`CharacterNotInRepertoireError` 22。
（另有 `SMTPConnectError` 1,202 次，是掃描環境刻意把 SMTP 指向關閉的埠所致，**非問題**。）

歸納為三類，皆可用一行 curl 重現：

**A. 列舉型參數收到非法值 → `InvalidTextRepresentationError` → 500**

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "$API/api/v1/manual-distribution/quota-status?scholarship_type_id=1&academic_year=114&semester=NOTANENUM"
# → HTTP 500   （semester=first 時為 200）
```
非法字串未在應用層擋下，直接送進 PostgreSQL enum 比對而由資料庫拋錯。
應在 Pydantic 層以 enum 型別約束，回 422。

**B. 字串參數含 NUL byte（`%00`）→ `CharacterNotInRepertoireError` → 500**

```bash
curl -H "Authorization: Bearer $TOKEN" "$API/api/v1/users?search=%00abc"
# → HTTP 500
```
PostgreSQL 的 text 型別不接受 `\x00`。應在輸入邊界剝除或拒絕。

**C. 唯一鍵重複 → `IntegrityError` → 500（而非 409）**

```bash
# 同樣的 field_name 送兩次
curl -X POST -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"field_name":"probe","field_label":"x","field_type":"text","scholarship_type":"nstc"}' \
  "$API/api/v1/application-fields/fields"
# 第 1 次 → 200   第 2 次 → 500（應為 409 Conflict）
```
這一類佔 `POST /application-fields/fields` 1,705 次 500 的絕大多數。

### 2.3 嚴重性評估

**這是健壯性／品質問題，不是可被外部利用的資安弱點**，理由：

1. **需要 admin 權限**。同樣的請求：未帶 token → **401**；student 角色 token → **403**。
   授權層完整生效。
2. **不外洩任何內部資訊**。`DEBUG=false` 下回應僅為
   `{"success":false,"message":"Internal server error","trace_id":"..."}`，
   無堆疊追蹤、無 SQL 片段、無檔案路徑。ZAP 的 *Application Error Disclosure* 與
   *Debug Error Messages* 兩項告警，實際證據就只是 `HTTP/1.1 500` 這行本身。

但仍應修正，理由：違反專案自身的錯誤處理規範（`.claude/CLAUDE.md`：輸入驗證應在邊界失敗並給出
明確訊息），且 500 會污染監控告警、讓真正的故障淹沒在雜訊中。

**建議**：於 Pydantic schema 以 enum 型別約束列舉參數（A）、在輸入邊界統一剝除 NUL byte（B）、
將 `IntegrityError` 統一轉譯為 409（C）。三者皆為集中式修正，不需逐一端點處理。

## 3. High / Medium 告警逐項驗證 —— 全部為誤報

| ZAP 告警 | 風險（信心） | 筆數 | 驗證結果 |
|---|---|---|---|
| Remote OS Command Injection | High (Medium) | 5 | **誤報（掃描器自造）** |
| Path Traversal | High (Low) | 2 | **誤報** |
| Format String Error | Medium (Medium) | 7 | **誤報** |
| XSS (Persistent in JSON Response) | Low (Low) | 11 | **誤報** |

### 3.1 Remote OS Command Injection — 掃描器打到自己造的資料

ZAP 送出 payload `get-help`（PowerShell 命令），並在回應中比對到 `Get-Help` 字樣即判定成立。
實際重現：

```bash
curl -H "Authorization: Bearer $TOKEN" "$API/api/v1/admin/professors?search=get-help"
{"success":true,"message":"Retrieved 1 professors",
 "data":[{"id":257,"name":"Prof. Get-Help","email":"dev_get-help_professor@dev.example.com",...}]}
```

回應裡的 `Get-Help` 是**一位名叫 `Prof. Get-Help` 的教授資料**——這筆資料是 ZAP 自己稍早
用同一個 payload 當作 `developer_id` 去打 `/auth/dev-profiles/get-help/quick-setup` 所建立的。
搜尋功能只是把它原樣回傳。**不存在任何命令執行**；系統沒有呼叫 shell。
（且 `/auth/dev-profiles/*` 在正式環境為 404。）

### 3.2 Path Traversal — 未讀取到任何檔案

告警指向 `POST /api/v1/auth/dev-profiles/quick-setup/quick-setup`，ZAP 把路徑參數換成相鄰的
路徑片段後拿到 200 即判定成立，**證據欄位為空**。實際測試：

```bash
curl -H "Authorization: Bearer $TOKEN" "$API/api/v1/auth/dev-profiles/..%2F..%2F..%2Fetc%2Fpasswd"
# → HTTP 404
```
回應中不含 `root:x:`，未讀出任何檔案內容。該端點僅以參數字串查資料庫，不觸及檔案系統。

### 3.3 Format String Error — Python 無此弱點類別

告警的證據欄位全為空，是依「送出 `%n%s%x` 後回應與基準不同」推論而來。而這些端點的
「不同」正是第 2 節那批 500（`IntegrityError` / `ValueError`）。
C 語言式的格式字串弱點在 CPython 不存在（沒有 `printf` 家族的可變參數解析）。

### 3.4 XSS (Persistent in JSON Response) — 內容型別為 JSON 且未反射

```bash
curl -D- -H "Authorization: Bearer $TOKEN" "$API/api/v1/users?search=%3Cscript%3Ealert(1)%3C/script%3E"
content-type: application/json
{"success":true,"message":"Users retrieved successfully","data":{"items":[],"total":0,...}}
```
以 `application/json` 回傳（瀏覽器不會當 HTML 解析），且本例根本未反射該字串。
前端一律經 React 轉義輸出。

## 4. 掃描設定與隔離措施

主動掃描會發送破壞性請求（`POST`/`PUT`/`DELETE` 帶攻擊 payload），因此**未對開發資料庫執行**：

| 項目 | 措施 |
|---|---|
| 資料庫 | `CREATE DATABASE scholarship_zap TEMPLATE scholarship_db` 複製後掃描複本；`scholarship_db` 全程未被寫入（掃描結束時複本 users 由 16 增至 20，來源仍為 16） |
| 受測服務 | 獨立容器 `scholarship_backend_zap`（`:8100`），與開發用 `:8000` 並存互不影響 |
| 物件儲存 | 獨立 bucket `scholarship-zap-scan` |
| Redis | 獨立 DB index `/9` |
| 郵件 | `SMTP_HOST=127.0.0.1 SMTP_PORT=2525`（關閉的埠），確保掃描不可能寄出真實郵件 |
| `DEBUG` | `false` —— 使錯誤外洩的判定貼近正式環境行為 |

掃描設定：`activeScan` strength=MEDIUM、threshold=MEDIUM、maxScanDuration=120 分（實際 25 分完成）、
`/auth/logout` 排除在外。ZAP proxy 需指定 `-port 8999`（預設 8080 被 mock student API 佔用）。

## 5. 掃描限制（誠實揭露）

1. **僅涵蓋後端 API**，未對前端執行主動掃描。
2. **僅以 admin 單一身分掃描**。未以 student / professor / college 身分重跑，因此
   **越權存取（IDOR / 水平權限提升）未被系統性測試** —— 這類問題需要多身分交叉比對才驗得出來。
   本次只驗證了「未認證 401、student 403」這一層。
3. **業務資料稀疏**：掃描時 `applications` 表為 **0 筆**，因此以申請案 ID 為主的端點多半走到 404，
   **未觸及其背後的商業邏輯**。這些端點的「無發現」應理解為**未充分測試**，而非已測試且乾淨。
4. **認證方式為開發專屬**：本次以 `POST /api/v1/auth/login`（僅需 `username`、無密碼）取得 admin token。
   該端點連同 `/auth/dev-profiles/*`、`/auth/mock-sso/*` 都**硬性擋在 `enable_mock_sso` 之後**，
   `docker-compose.prod.yml` 與 `docker-compose.staging.yml` 皆設為 `false`，且
   `config.py` 在 `environment=production` 且該旗標為真時**直接拒絕啟動**。
   正式環境要做等效掃描，必須改以真實 Portal SSO token 建立 ZAP context。
5. **spider 未執行**：URL 樹完全來自 OpenAPI spec，未在 spec 中宣告的端點不會被掃到。

## 6. 重現方式

```bash
git checkout 4325315a

# 1) 複製資料庫（絕不可直接掃開發庫）
docker exec scholarship_postgres_dev psql -U scholarship_user -d postgres \
  -c "CREATE DATABASE scholarship_zap TEMPLATE scholarship_db;"

# 2) 起一個指向複本的獨立後端（環境變數見第 4 節）
docker run -d --name scholarship_backend_zap --network scholarship-system_scholarship_dev_network \
  -p 8100:8000 -e DATABASE_URL=...scholarship_zap -e DEBUG=false \
  -e MINIO_BUCKET=scholarship-zap-scan -e REDIS_URL=redis://redis:6379/9 \
  -e SMTP_HOST=127.0.0.1 -e SMTP_PORT=2525 \
  ghcr.io/anud18/scholarship-system-backend:latest uvicorn app.main:app --host 0.0.0.0 --port 8000

# 3) 取 token、抓 OpenAPI spec，填入 plan.yaml 的 replacer 規則
curl -s -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin@nycu.edu.tw"}'
curl -s "$API/api/v1/openapi.json" -o openapi.json

# 4) 執行（plan.yaml 隨報告附上）
docker run --network host -v "$PWD:/zap/wrk/:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap.sh -cmd -port 8999 -autorun /zap/wrk/plan.yaml
```

## 7. 檔案清單

| 檔案 | 說明 |
|---|---|
| `zap-active-api-report.pdf` | ZAP 原生報告（繳交用） |
| `zap-active-api-report.html` / `.md` / `.json` | 同上，其他格式；`.json` 為原始資料 |
| `plan.yaml` | ZAP Automation Framework 掃描計畫（token 已遮蔽） |

> 本報告的結論以第 2、3 節的**人工驗證**為準。ZAP 原生報告中的 High / Medium 告警未經驗證，
> 不應直接引用 —— 第 3 節已逐項說明其為誤報的理由。
