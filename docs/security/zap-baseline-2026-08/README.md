# OWASP ZAP 弱點掃描報告（上線前）

**系統**：NYCU 獎學金管理系統
**掃描日期**：2026-08-04
**工具**：OWASP ZAP 2.17.0（`ghcr.io/zaproxy/zaproxy:stable`）
**模式**：Baseline Scan — 被動掃描 + AJAX Spider，**不發送攻擊 payload**
**受測版本**：`main` @ `dae53981`

## 結論

| 受測對象 | FAIL | High | Medium | WARN | PASS |
|---|---|---|---|---|---|
| **正式環境組態**（production build） | 0 | **0** | **0** | 7 | 63 |
| 開發環境（dev build，前端） | 0 | 0 | 4 | 14 | 56 |
| 開發環境（dev build，後端 API） | 0 | 0 | 0 | 4 | 66 |

**繳交時請以 `production/` 為準。** 未發現任何需於上線前修補的實質弱點。

## 目錄

```
production/     ← 正式環境組態（next build && next start）。這是代表上線狀態的報告
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

開發環境的放寬是 Turbopack 熱更新的硬需求（HMR 需要 `eval()` 與 WebSocket），**無法也不應收緊** —— 它對正式環境的安全性沒有任何影響。`development/` 那 4 筆 Medium 全部來自這裡，`production/` 已無任何 CSP 告警。

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
3. **爬取廣度**：前端 AJAX Spider 未登入即被導向登入頁；後端 API 需 Bearer token，故僅掃到根路徑。

若繳交單位要求涵蓋認證後範圍或主動攻擊測試，需另行執行 authenticated full scan（`zap-full-scan.py` + context 認證設定），且必須在可拋棄的測試資料庫上進行。

## 重現方式

```bash
# 正式環境組態
cd frontend && bun run build
PORT=3100 bun run start
docker run --rm --network host -v "$PWD/out:/zap/wrk/:rw" ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py -t http://localhost:3100 -r report.html -J report.json -w report.md -a -j -m 5

# 開發環境
docker compose -f docker-compose.dev.yml up -d
# 前端 http://localhost:3000、後端 http://localhost:8000（後端省略 -j）
```

`frontend/e2e/csp-violation-check.js` 為對 production build 檢查 CSP violation 的可重複腳本（本次結果：0 violations）。
