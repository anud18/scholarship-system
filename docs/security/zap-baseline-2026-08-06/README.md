# OWASP ZAP 弱點掃描報告（上線前・複掃）

**系統**：NYCU 獎學金管理系統
**掃描日期**：2026-08-06
**工具**：OWASP ZAP 2.17.0（`ghcr.io/zaproxy/zaproxy:stable`）
**模式**：Baseline Scan — 被動掃描 + AJAX Spider，**不發送攻擊 payload**
**受測版本**：`main` @ `4325315a`

> 本次為 [`zap-baseline-2026-08`](../zap-baseline-2026-08/README.md)（`main` @ `dae53981`）之後的複掃。
> `dae53981..4325315a` 共 7 個 commit，其中 4 個為安全性修補（regex 驗證重寫、移除 fastapi-mail、
> npm/pip 相依套件升級），故重新掃描確認未引入新的告警。

## 結論

| 受測對象 | FAIL | High | Medium | WARN | PASS |
|---|---|---|---|---|---|
| **正式環境組態**（production build） | 0 | **0** | **0** | 7 | 63 |
| 開發環境（dev build，前端） | 0 | 0 | 4 | 13 | 57 |
| 開發環境（dev build，後端 API） | 0 | 0 | 0 | 4 | 66 |

**繳交時請以 `production/` 為準。** 未發現任何需於上線前修補的實質弱點。

### 與前次（`dae53981`）比較

| 受測對象 | 前次 | 本次 | 差異 |
|---|---|---|---|
| 正式環境組態 | 0 FAIL / 0 High / 0 Medium / 7 WARN / 63 PASS | 0 / 0 / 0 / 7 / 63 | **無變化** |
| 開發環境（前端） | 0 FAIL / 0 High / 4 Medium / 14 WARN / 56 PASS | 0 / 0 / 4 / 13 / 57 | WARN −1 |
| 開發環境（後端 API） | 0 FAIL / 0 High / 0 Medium / 4 WARN / 66 PASS | 0 / 0 / 0 / 4 / 66 | **無變化** |

逐項比對告警**類型**（而非筆數）的結果：

- **正式環境組態**：告警類型集合與前次**完全相同**，無新增、無減少。
- **開發環境（後端 API）**：告警類型集合與前次**完全相同**。
- **開發環境（前端）**：唯一差異是前次多一筆 `Session Management Response Identified`（Informational，
  屬「識別到 session 管理機制」的資訊性標記，非弱點）。本次 AJAX Spider 在 5 分鐘內爬到的 URL 集合
  與前次不同而未觸發該規則，**非程式碼修正的結果**，不應解讀為安全性改善。

**三份報告皆無任何新增告警類型 —— 本次安全性修補未引入新的弱點。**

## 目錄

```
production/     ← 正式環境組態（Dockerfile production build + next start）。這是代表上線狀態的報告
development/    ← 開發環境（docker compose dev stack）前端 + 後端 API
```

每組皆含 `.pdf`（繳交用）、`.html`（ZAP 原生）、`.md`、`.json`（原始資料）。

## 為什麼要分兩組 — 開發環境的 4 筆 Medium 不代表正式環境

`frontend/middleware.ts` 依 `NODE_ENV` 輸出兩套**互斥**的 CSP：

| 指令 | 開發環境 | 正式環境 |
|---|---|---|
| `script-src` | `'self' 'unsafe-eval' 'unsafe-inline'` | `'self' 'nonce-{每次請求}' 'strict-dynamic'` |
| `style-src` | `'self' 'unsafe-inline'` | `'self' 'nonce-{每次請求}' {sonner hashes}` |
| `style-src-attr` | （無） | `'unsafe-inline'`（Radix 定位所需） |
| `connect-src` | `'self' ws: wss:` | `'self' https://*.nycu.edu.tw` |

本次掃描實際觀察到的正式環境 CSP（`http://localhost:3100/` 回應標頭）：

```
default-src 'self'; script-src 'self' 'nonce-<每次請求隨機>' 'strict-dynamic';
style-src 'self' 'nonce-<每次請求隨機>' 'sha256-...'; ...
```

開發環境的放寬是 Turbopack 熱更新的硬需求（HMR 需要 `eval()` 與 WebSocket），**無法也不應收緊** ——
它對正式環境的安全性沒有任何影響。`development/` 那 4 筆 Medium 全部來自這裡，
`production/` 已無任何 CSP 告警。

CSP 的完整設計與 nonce 傳遞機制見 [`docs/CSP_IMPLEMENTATION.md`](../../CSP_IMPLEMENTATION.md)。

## 逐項說明（production 報告的 7 筆 WARN）

| 項目 | 風險 | 說明 |
|---|---|---|
| X-Content-Type-Options / Permissions-Policy / COOP / CORP 缺失 | Low | 掃描直連 `next start`，**未經正式環境的 nginx**。`nginx/nginx.prod.conf` 已於各 location 設定這些標頭（含 HSTS）；未被 middleware matcher 涵蓋的 `/_next/static/` 亦由 nginx 補上 |
| Cross-Origin-Embedder-Policy 缺失 | Low | **刻意不啟用**：`require-corp` 會使 `/api/v1/preview` 檔案預覽 iframe 的子資源全數需要 CORP 標頭而損壞，且本系統未使用 SharedArrayBuffer。已評估並接受 |
| Sec-Fetch-* 標頭缺失 | Info | 由**掃描器自身請求**未帶這些標頭所致，非伺服器問題 |
| Base64 Disclosure / Storable Content / Modern Web Application | Info | JS bundle 內的 base64 字串與靜態資源快取行為，符合預期 |

## 掃描限制（誠實揭露）

1. **未認證**：baseline 為未登入狀態，僅涵蓋公開頁面；登入後的管理／學院／教授功能未被爬取。
2. **被動掃描**：未發送攻擊 payload，不涵蓋 SQLi、XSS、指令注入等主動測試。
3. **未經 nginx**：production 報告的安全標頭 Low 告警源於直連 `next start`，不代表正式環境實際組態。
4. **爬取廣度**：前端 AJAX Spider 未登入即被導向登入頁；後端 API 需 Bearer token，故僅掃到根路徑。
5. **爬取不具決定性**：AJAX Spider 每次爬到的 URL 集合會有差異，故 WARN 筆數在兩次掃描間有 ±1 的浮動，
   逐項比較應以「告警類型」而非「筆數」為準（見上方比較表的說明）。

若繳交單位要求涵蓋認證後範圍或主動攻擊測試，需另行執行 authenticated full scan
（`zap-full-scan.py` + context 認證設定），且必須在可拋棄的測試資料庫上進行。

## 重現方式

```bash
git checkout 4325315a

# --- 正式環境組態（繳交用）---
docker build -t scholarship-frontend-zap:prod -f frontend/Dockerfile frontend/
docker run -d --name zap-prod-frontend --network host \
  -e NODE_ENV=production -e PORT=3100 scholarship-frontend-zap:prod
docker run --rm --network host -v "$PWD/out-prod:/zap/wrk/:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:3100 \
  -r zap-frontend-prod-report.html -J zap-frontend-prod-report.json -w zap-frontend-prod-report.md \
  -a -j -m 5

# --- 開發環境 ---
docker compose -f docker-compose.dev.yml up -d
docker run --rm --network host -v "$PWD/out-dev:/zap/wrk/:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:3000 \
  -r zap-frontend-report.html -J zap-frontend-report.json -w zap-frontend-report.md -a -j -m 5
docker run --rm --network host -v "$PWD/out-dev:/zap/wrk/:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:8000 \
  -r zap-backend-report.html -J zap-backend-report.json -w zap-backend-report.md -a -m 5
```

參數：`-a` 啟用 alpha 被動規則、`-j` 啟用 AJAX Spider（Next.js SPA 必要）、`-m 5` 爬蟲上限 5 分鐘。
後端 API 無前端路由，省略 `-j`。

PDF 由 headless Chromium 對 ZAP 產出的 `.html` 列印產生（`--print-to-pdf --no-pdf-header-footer`）。
