# OWASP ZAP 掃描報告 — `main` @ `e79d8f33`（複掃）

**系統**：NYCU 獎學金管理系統
**掃描日期**：2026-08-06
**工具**：OWASP ZAP 2.17.0（`ghcr.io/zaproxy/zaproxy:stable`）
**受測版本**：`main` @ `e79d8f33`
**涵蓋**：Baseline（被動）+ **Authenticated Active Scan**（主動，後端 API）

> 這是對 `4325315a` 全套掃描的複掃。**方法、隔離措施、誤報分析、限制說明完全沿用前次**，
> 完整內容請見：
> - Baseline：[`zap-baseline-2026-08-06/README.md`](../zap-baseline-2026-08-06/README.md)
> - Active：[`zap-active-2026-08-06/README.md`](../zap-active-2026-08-06/README.md)
>
> 本檔只記錄**與前次的差異**，不重複已寫過的分析。

## 1. 這次 main 改了什麼

`4325315a..e79d8f33` 共 5 個 commit（含 Fortify OWASP Top 10 掃描修補）：

| commit | 內容 |
|---|---|
| `c2a12770` | fix(security): 修正 Fortify SCA 12 項發現 |
| `3d939970` | fix(security): 修正驗證發現與 review 回饋 |
| `17e381e8` | chore(mirror): production 同步排除 dev-only e2e 與 env bootstrap |
| `a6ee59f2` | revert(e2e): 還原 `E2E_DATABASE_URL` fallback 與 CI 接線 |
| `e79d8f33` | Merge PR #1289 |

**變更範圍：`.github/` workflow、`monitoring/` 文件與腳本、`scripts/write_dev_env.sh`、
`frontend/Dockerfile`（釘住 `nodejs=22.23.2-r0`）。**

**`backend/` 與前端應用程式碼（`app/`、`components/`、`lib/`、`middleware.ts`）零變更**，
相依套件（`requirements.txt`、`package.json`、`bun.lock`）亦零變更。
因此本次結果**預期與前次相同**；相同即代表**無回歸**，而非新資訊。

## 2. 結果總表

| 受測對象 | FAIL | High | Medium | WARN | PASS | 與 `4325315a` 比較 |
|---|---|---|---|---|---|---|
| **正式環境組態**（production build） | 0 | **0** | **0** | 7 | 63 | **完全相同** |
| 開發環境（前端） | 0 | 0 | 4 | 14 | 56 | WARN 13→14（見 2.1） |
| 開發環境（後端 API） | 0 | 0 | 0 | 4 | 66 | **完全相同** |
| **主動掃描**（後端 API，已認證） | 0 | 0※ | 0※ | 4 | 57 | **實質相同**（見 2.2） |

※ ZAP 原始告警含 High×2 類、Medium×1 類，**經人工逐項驗證全部為誤報**，
詳見 [active README 第 3 節](../zap-active-2026-08-06/README.md)。本表的 High/Medium 欄位為驗證後數字。

### 2.1 開發環境前端 WARN 13 → 14

差異僅一筆 `Session Management Response Identified`（Informational，識別到 session 管理機制，非弱點）。

**這正是前次報告中「消失」的那一筆**。前次 README 已註明其為 AJAX Spider 爬取不具決定性所致、
不應解讀為改善；本次它又出現，**反向印證了該判斷**。除此之外告警類型集合完全相同。

### 2.2 主動掃描：逐項比對

| 項目 | `4325315a` | `e79d8f33` |
|---|---|---|
| activeScan 耗時 | 25:14 | 25:06 |
| 匯入 URL 數 | 416 | 416 |
| 總請求數 | 200,344 | 199,964 |
| 告警類型集合 | — | **完全相同**（9 類） |
| 正式環境可達 500 | 4,948 / 54 端點 | **4,950 / 54 端點** |
| 開發專屬 500 | 333 / 268 端點 | 328 / 267 端點 |

告警類型逐一對應，連 500 排行前 13 名的端點與順序都一致。唯一數值差異是
`XSS (Persistent in JSON Response)` 由 11 筆變 10 筆 —— 屬掃描器取樣浮動，非行為變化。

**前次的三個 500 根因在本版本仍完整重現**（皆為未修正狀態）：

```
A. GET /manual-distribution/quota-status?...&semester=NOTANENUM  → 500
B. GET /users?search=%00abc                                      → 500
C. POST /application-fields/fields（同一 field_name 送第 2 次）   → 500（應為 409）
```

授權控制同樣仍然正確：未帶 token → **401**。

**Remote OS Command Injection (High) 的誤報成因也一模一樣**：

```json
GET /api/v1/admin/professors?search=get-help
{"success":true,"message":"Retrieved 1 professors",
 "data":[{"id":254,"name":"Prof. Get-Help","email":"dev_get-help_professor@dev.example.com",...}]}
```

回應中的 `Get-Help` 仍是 ZAP 自己用同一 payload 當 `developer_id` 建出來的教授資料。

## 3. 結論

1. **無任何回歸。** 三份 baseline 與主動掃描的告警類型集合與前次一致，
   Fortify 修補未對執行時期行為造成任何可觀測的影響（該批修補本就集中在 CI/文件/mirror 設定）。
2. **仍無確認成立的注入類弱點。**
3. **前次發現的 4,950 個 500 仍未修正** —— 三個根因（列舉值、NUL byte、`IntegrityError`）
   在本版本原樣重現。修正建議見 [active README 第 2.3 節](../zap-active-2026-08-06/README.md)。
4. 掃描限制與前次完全相同（未涵蓋越權測試、業務資料稀疏、僅後端主動掃描、
   認證走開發專屬端點），逐項說明見前次報告，**繳交時必須一併附上**。

## 4. 檔案

```
baseline-production/    ← 正式環境組態被動掃描（繳交請用這份）
baseline-development/   ← 開發環境被動掃描（前端 + 後端 API）
active/                 ← 已認證主動掃描（後端 API）+ plan.yaml（token 已遮蔽）
```

每組皆含 `.pdf` / `.html` / `.md` / `.json`。
