# ZAP 掃描設定

檢查進版控的 ZAP 掃描設定，讓主動掃描可重現、誤報判定可追溯。

| 檔案 | 用途 |
|---|---|
| `active-scan-plan.yaml` | 已認證主動掃描的 Automation Framework 計畫 |
| `alert-filters.yaml` | 已驗證的誤報清單（含逐項證據），是 plan 裡 `alertFilter` job 的來源 |

歷次掃描報告在 `docs/security/`。

## ⚠️ 絕對不要對開發資料庫跑主動掃描

主動掃描會對每個發現的端點送出帶攻擊 payload 的 `POST`/`PUT`/`DELETE`，
會刪資料、改狀態、觸發寄信。**一定要先複製一份可拋棄的資料庫。**

## 完整流程

```bash
# 1) 複製資料庫（來源庫全程不被寫入）
docker exec scholarship_postgres_dev psql -U scholarship_user -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity
      WHERE datname='scholarship_db' AND pid<>pg_backend_pid();"
docker exec scholarship_postgres_dev psql -U scholarship_user -d postgres \
  -c "CREATE DATABASE scholarship_zap TEMPLATE scholarship_db;"

# 2) 起一個指向複本的獨立後端（:8100），與開發用 :8000 並存
#    隔離重點：獨立 bucket、獨立 Redis index、SMTP 指向關閉的埠
docker run -d --name scholarship_backend_zap \
  --network scholarship-system_scholarship_dev_network -p 8100:8000 \
  -e DATABASE_URL="postgresql+asyncpg://scholarship_user:scholarship_pass@postgres:5432/scholarship_zap" \
  -e DATABASE_URL_SYNC="postgresql://scholarship_user:scholarship_pass@postgres:5432/scholarship_zap" \
  -e REDIS_URL="redis://redis:6379/9" \
  -e MINIO_BUCKET="scholarship-zap-scan" \
  -e SMTP_HOST="127.0.0.1" -e SMTP_PORT="2525" \
  -e DEBUG="false" -e ENVIRONMENT="development" \
  -e ACCESS_TOKEN_EXPIRE_MINUTES="2880" \
  -e SECRET_KEY="dev-secret-key-for-development-only" \
  -e ENABLE_MOCK_SSO="true" \
  ghcr.io/anud18/scholarship-system-backend:latest \
  uvicorn app.main:app --host 0.0.0.0 --port 8000
  # （其餘 env 比照 docker-compose.dev.yml 的 backend）

# 3) 取 token 與 OpenAPI spec
mkdir -p /tmp/zapwrk
export ZAP_BEARER_TOKEN=$(curl -s -X POST http://localhost:8100/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin@nycu.edu.tw"}' \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["data"]["access_token"])')
curl -s http://localhost:8100/api/v1/openapi.json -o /tmp/zapwrk/openapi.json

# 4) 展開 plan 並執行
envsubst < security/zap/active-scan-plan.yaml > /tmp/zapwrk/plan.yaml
docker run --rm --network host -v /tmp/zapwrk:/zap/wrk/:rw \
  ghcr.io/zaproxy/zaproxy:stable zap.sh -cmd -port 8999 -autorun /zap/wrk/plan.yaml

# 5) 收尾（務必執行）
docker rm -f scholarship_backend_zap
docker exec scholarship_postgres_dev psql -U scholarship_user -d postgres \
  -c "DROP DATABASE IF EXISTS scholarship_zap;"
```

## 三個會讓掃描結果騙人的坑

**1. `-port 8999` 不能省。** ZAP proxy 預設 8080，而 mock student API 佔著這個埠。
綁定失敗時 **ZAP 會 exit 0**，看起來和掃描成功一模一樣，只有讀 log 才看得出
`Failed to start the main proxy: Address already in use`。

**2. 一定要餵 OpenAPI spec。** 未認證的爬蟲在後端只爬得到 3 個 URL（`/` 與兩個 404），
spec 匯入則有 416 個。少了這步會得到一份「乾淨但幾乎什麼都沒測」的報告 ——
**那比不掃更危險**，因為它會被當成保證。

**3. `outputSummary` 不含主動掃描告警。** console 最後那行
`FAIL-NEW: 0  WARN-NEW: 4` 只涵蓋被動規則。主動掃描的 High/Medium 只出現在
**報告檔**裡。判讀請一律以 `zap-active-api-report.json` 為準。

## 誤報處理原則

看 `alert-filters.yaml` 開頭的四條規則。摘要：**沒有書面重現證據就不准加**，
而且用 `newRisk: "False Positive"` 重新標記而非刪除 —— 稽核者仍看得到該筆並可提出異議。

## 已知限制（報告請一併揭露）

- **僅單一 admin 身分** → 越權存取（IDOR / 水平提權）未被系統性測試
- **業務資料稀疏**：`applications` 為空時，以申請案 ID 為主的端點多半走到 404，
  未觸及背後商業邏輯 —— 這些端點的「無發現」是**未充分測試**，不是已測試且乾淨
- **僅後端 API**，前端未做主動掃描
- **認證走開發專屬端點**（`/auth/login` 僅需 username，硬性擋在 `enable_mock_sso` 之後，
  prod/staging 皆為 false）。正式環境要做等效掃描需改用真實 Portal SSO token
