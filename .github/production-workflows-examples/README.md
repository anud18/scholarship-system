# Production Workflows Examples

這個目錄包含用於 **production repository** 的 workflows。

## 🚚 自動安裝（2026-06-13 起）

**不需要再手動複製。** `mirror-to-production.yml` 是進入私有 prod repo 的唯一通道，
因此它會在每次 mirror 時自動把本目錄的 workflows 安裝到 prod repo 的
`.github/workflows/`：

- prod repo **還沒有**的檔案 → 自動安裝（首次 mirror 即完成 CI/CD bootstrap）
- prod repo 已有、且內容與**某個歷史版範本逐字節相同**的檔案（= 從未被 prod
  端客製，只是舊版範本）→ **自動更新**到現行範本，讓範本修正（如 #1282 的
  permissions 區塊）能經由 mirror 送達 prod。release notes 會列出
  「Workflows updated from templates」清單;若 prod 端剛刻意 rollback 某個
  workflow、暫時不想被升回來，dispatch mirror 時勾選 `freeze_workflows`
- prod repo 已有、但**比對不到任何歷史版範本**的檔案（= prod 端有客製,
  如 `auto-tag-on-merge.yml`）→ 一律不覆寫;mirror log 會以 notice 提示,
  由人工決定是否移植

> 📦 **只帶必要的可執行 CI/CD（.yml workflows）過去。** prod repo 資安掃描嚴格，
> 因此本目錄的設定指南（`SECRETS-SETUP-GUIDE.md` 等含大量 example secret 值與
> `gh secret set` 指令，會被 secret scanner 誤報）**不會**推到 prod repo。
> 操作者請在 **dev repo 的本目錄**閱讀這些指南（dispatch mirror 即代表已有存取權）。

> ⚠️ 前提：`GH_PAT` secret 必須具備 **`workflow` scope**，否則推送
> `.github/workflows/**` 會被 GitHub 拒絕（"refusing to allow a Personal
> Access Token to create or update workflow"）。

以下原手動安裝說明保留作參考（適用於需要在 prod repo 直接修改的情境）。

## ⚠️ 重要：關於 Here-Document 錯誤

如果你在生產倉庫看到以下錯誤：
```
warning: here-document at line 10 delimited by end-of-file (wanted `FOOTER_EOF')
```

**解決方案**：從此目錄複製最新版本的 `auto-tag-on-merge.yml` 到生產倉庫。舊版本使用了 heredoc 語法，新版本已修正為使用 echo 命令。

詳見下方「🔄 更新 Workflows」章節。

## 📁 檔案說明

| 檔案 | 用途 | 觸發時機 | 狀態 |
|------|------|----------|------|
| `bootstrap-ap-runner.sh` 🅾️ | **兩台空 VM 的步驟 0** — 把 bare AP VM 變成可跑 action 的 self-hosted runner | 在 AP VM 手動執行一次 | **必要(前置)** |
| `setting-env.yml` | 在 AP VM 裝 Docker、SSH 到 DB VM 裝 Docker+傳 image、建部署目錄 | runner 就緒後手動觸發 | **必要** |
| `auto-tag-on-merge.yml` ⭐ | 自動建立 Git tag 和 Release | PR merge 到 main | **必要** |
| `deploy-test.yml` | 部署 **test AP VM**，需一位 reviewer 核准 | **只能手動觸發**（push to main 不會部署） | **必要** |
| `deploy-production.yml` | 部署 **production AP VM**，需一位 reviewer 核准 | **只能手動觸發**（push to main 不會部署） | **必要** |
| `deploy-stack.yml` | 上面兩個 workflow 共用的 reusable workflow（實際的部署腳本本體） | 由兩個 deploy workflow 呼叫，不單獨觸發 | **必要**（三個要一起複製） |
| `stop-test.yml` | **停掉 test AP VM** 的站台，需一位 reviewer 核准 | 只能手動觸發 | **必要** |
| `stop-production.yml` | **停掉 production AP VM** 的站台（正式站會離線），需一位 reviewer 核准 | 只能手動觸發 | **必要** |
| `stop-stack.yml` | 上面兩個 stop workflow 共用的 reusable workflow（實際的停機腳本本體） | 由兩個 stop workflow 呼叫，不單獨觸發 | **必要**（三個要一起複製） |
| `deploy-monitoring-test.yml` | 在 **test AP VM** 起 Grafana/Loki/Prometheus（監控儀表板本體），需一位 reviewer 核准 | **只能手動觸發**（同步進 `monitoring/**` 的變更後自己跑） | **必要**（要看儀表板就必裝） |
| `deploy-monitoring-production.yml` | 在 **production AP VM** 起 Grafana/Loki/Prometheus，需一位 reviewer 核准 | **只能手動觸發**（同上） | **必要**（同上） |
| `deploy-monitoring-stack.yml` | 上面兩個 monitoring workflow 共用的 reusable workflow（實際的部署腳本本體） | 由兩個 monitoring workflow 呼叫，不單獨觸發 | **必要**（三個要一起複製） |
| `health-check.yml` | 監控應用程式健康狀態 | 每 15 分鐘 / 手動觸發 | 選用 |
| `backup.yml` | 備份資料庫和檔案 | 每日 2AM UTC / 手動觸發 | 選用 |
| `fortify-scan.yml` | Fortify SAST 掃描（Python + JS/TS + config），產出 `.fpr` 與 BIRT PDF 報告。掃描約 2.5 小時且獨佔共用 Fortify runner，故**只能手動觸發**——要交報告時才跑，不隨 push/PR 啟動 | **只能手動觸發** | 選用 |

### 🅾️ 步驟 0：bare VM 的 bootstrap（雞生蛋問題）

所有 workflow 都跑在 self-hosted runner 上,而且是**兩台** AP VM:test 與 production。兩台都會註冊成 `[self-hosted, linux]`,因此**必須**再加上 stage label 才分得開:

| VM | labels | 由誰使用 |
|----|--------|----------|
| test AP VM | `[self-hosted, linux, test]` | `deploy-test.yml`、`stop-test.yml`、`setting-env.yml`(stage=test) |
| production AP VM | `[self-hosted, linux, production]` | `deploy-production.yml`、`stop-production.yml`、`backup.yml`、`health-check.yml`、`setting-env.yml`(stage=production) |

**沒有 stage label 的 runner 收不到任何 job**(workflow 指定的是三個 label 的組合);label 貼錯則會把 production 的部署跑到 test VM 上。

**空的 AP VM 上沒有 runner,任何 action 都跑不了** —— 必須先手動把 runner 裝起來。`bootstrap-ap-runner.sh` 就是這一步:裝 Docker + 把 GitHub Actions runner 註冊成 systemd service。**每台 VM 各跑一次,`--stage` 帶對應的值**。

> 此 `.sh` **只存在於 dev repo 的本目錄**(mirror 只帶可執行的 `.yml` 過去,且空 VM 本來也收不到)。操作者直接從這裡複製到 AP VM 執行。

```bash
# 1) 在 prod repo 取得 runner 註冊 token(約 1 小時有效)
gh api -X POST repos/<OWNER>/<PROD_REPO>/actions/runners/registration-token --jq .token

# 2) 把本目錄的 bootstrap-ap-runner.sh 複製到 AP VM,然後:
chmod +x bootstrap-ap-runner.sh
# test AP VM:
./bootstrap-ap-runner.sh --repo-url https://github.com/<OWNER>/<PROD_REPO> --token <TOKEN> --stage test
# production AP VM(另外再取一次 token):
./bootstrap-ap-runner.sh --repo-url https://github.com/<OWNER>/<PROD_REPO> --token <TOKEN> --stage production
```

腳本特性:`set -euo pipefail` + ERR trap(失敗會印出**確切失敗行號與指令**)、全程輸出同時寫入 `/tmp/bootstrap-ap-runner-*.log`、可重複執行(idempotent)。跑完 AP VM 就能跑 action;DB VM **不需要** runner(`setting-env.yml` 透過 SSH 操作它)。

完成步驟 0 後,執行 `setting-env.yml`(action=`full-check`)。它在開頭有 **pre-flight 關卡**,會把會造成反覆 debug 的坑一次抓完(DB VM 連不上、沒有 sudo、AP/DB 架構或 Ubuntu 版本不一致導致 .deb 裝不上、磁碟不足),全部以可行動的 `::error::` 訊息回報,在動任何長指令之前就擋下。

### ⭐ Auto-Tag Workflow (推薦必裝)

**功能**：
- ✅ 自動從 PR 標題提取版本號（格式：`Release v1.2.3`）
- ✅ 建立 annotated Git tag
- ✅ 自動建立 GitHub Release（包含完整 release notes）
- ✅ 自動偵測 pre-release 版本（alpha, beta, rc）
- ✅ 完整錯誤處理和日誌

**為什麼需要**：
當 Mirror to Production workflow 建立的 PR 被 merge 後，此 workflow 會自動：
1. 從 PR 標題提取版本號
2. 建立 tag 指向 squash merge commit
3. 建立 GitHub Release 包含完整的 release notes

## 🚀 使用方式

### 1. 安裝 Auto-Tag Workflow（必要）

**快速安裝**：

```bash
# 在生產倉庫
mkdir -p .github/workflows

# 從開發倉庫複製最新版本
cp /path/to/development-repo/.github/production-workflows-examples/auto-tag-on-merge.yml \
   .github/workflows/auto-tag-on-merge.yml

# Commit 並 push
git add .github/workflows/auto-tag-on-merge.yml
git commit -m "feat: add auto-tag workflow for release automation"
git push
```

**或使用 GitHub Web UI**：

1. 前往生產倉庫
2. 建立新檔案：`.github/workflows/auto-tag-on-merge.yml`
3. 複製 `auto-tag-on-merge.yml` 的完整內容
4. Commit 變更

**驗證安裝**：

```bash
# 驗證 YAML 語法
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/auto-tag-on-merge.yml'))"

# 查看 workflow
gh workflow list
```

### 2. 安裝其他 Workflows（選用）

```bash
# Clone production repository
git clone https://github.com/your-org/scholarship-production.git
cd scholarship-production

# Create workflows directory (if not exists)
mkdir -p .github/workflows

# Copy optional workflows
# 三個 deploy 檔必須一起複製 —— 兩個 caller 都用
# `uses: ./.github/workflows/deploy-stack.yml` 呼叫同一份 reusable workflow，
# 少了它任一個 caller 都無法解析。
cp /path/to/development-repo/.github/production-workflows-examples/deploy-test.yml \
   .github/workflows/deploy-test.yml

cp /path/to/development-repo/.github/production-workflows-examples/deploy-production.yml \
   .github/workflows/deploy-production.yml

cp /path/to/development-repo/.github/production-workflows-examples/deploy-stack.yml \
   .github/workflows/deploy-stack.yml

# stop 三件組同理：兩個 caller 都用
# `uses: ./.github/workflows/stop-stack.yml`，少了它一樣無法解析。
cp /path/to/development-repo/.github/production-workflows-examples/stop-test.yml \
   .github/workflows/stop-test.yml

cp /path/to/development-repo/.github/production-workflows-examples/stop-production.yml \
   .github/workflows/stop-production.yml

cp /path/to/development-repo/.github/production-workflows-examples/stop-stack.yml \
   .github/workflows/stop-stack.yml

# monitoring 三件組同理：兩個 caller 都用
# `uses: ./.github/workflows/deploy-monitoring-stack.yml`，少了它一樣無法解析。
cp /path/to/development-repo/.github/production-workflows-examples/deploy-monitoring-test.yml \
   .github/workflows/deploy-monitoring-test.yml

cp /path/to/development-repo/.github/production-workflows-examples/deploy-monitoring-production.yml \
   .github/workflows/deploy-monitoring-production.yml

cp /path/to/development-repo/.github/production-workflows-examples/deploy-monitoring-stack.yml \
   .github/workflows/deploy-monitoring-stack.yml

cp /path/to/development-repo/.github/production-workflows-examples/health-check.yml \
   .github/workflows/health-check.yml

cp /path/to/development-repo/.github/production-workflows-examples/backup.yml \
   .github/workflows/backup.yml
```

### 2. 配置 Secrets

在 production repository 設定以下 secrets（Settings → Secrets and variables → Actions）：

> 沒有任何 workflow 使用 SSH。deploy-test.yml / deploy-production.yml / backup.yml / health-check.yml 都跑在
> AP VM 上的 self-hosted runner（labels `[self-hosted, linux, <stage>]`），
> 直接操作本機 docker 與 DB VM 的 5432 埠。GitHub-hosted runner 連不到校內 VM。
>
> ⚠️ **test 與 production 用的是不同的 env variable / secret**。作法是把值放進
> GitHub **Environments**（`test` 與 `production`），而不是全部放在 repository 層。
> Repository 層的 secret 是 **production 的值**（backup.yml / health-check.yml 這類
> 排程 workflow 沒有 `environment:`，仍從這裡取值）；`test` environment 則把每一個
> 值覆寫成測試環境的。**沒有被 test environment 覆寫的 secret 會自動 fallback 到
> repository 層 = production 的值**，所以 `test` environment 必須把下表的 secret
> 全部各自設一份。deploy-stack.yml 的 "Assert stage identity" 步驟就是用來擋這個
> 漏設的（詳見 SECRETS-SETUP-GUIDE.md § Environments）。

#### Repository Variables（Settings → Variables → Actions）

| Variable | 必填 | 說明 |
|----------|------|------|
| `IMAGE_OWNER` | ✅ | 發布映像檔的 GHCR namespace，也就是**開發 repo 的 owner**（例：`anud18`）。production repo 不建置映像檔，只取用開發流程已經發布、staging 驗過的那一份。兩個 stage 共用。 |

#### Environment Variables（Settings → Environments → `test` / `production` → Variables）

以下每一項都要在 **兩個 environment 各設一份**（值不同）：

| Variable | 必填 | `test` 範例 | `production` 範例 |
|----------|------|-------------|-------------------|
| `DEPLOY_STAGE` | ✅ | `test` | `production` | 
| `EXPECT_DOMAIN` | test 必填 | 測試站網域 | 正式站網域 |
| `EXPECT_DB_HOST` | test 必填 | test DB VM 的位址 | production DB VM 的位址 |
| `DEPLOY_URL` | ✅ | `https://<測試站網域>` | `https://<正式站網域>` |
| `ENV_FILE` | — | 該台 VM 上既有 `.env` 的絕對路徑（安裝手冊 5.1）。**設了就用它**，GitHub 完全不存這些值。留空則由 deploy-stack.yml 依下方 secrets 產生 `~/scholarship-<stage>/.env`（權限 600）。 | 同左 |

`DEPLOY_STAGE` / `EXPECT_DOMAIN` / `EXPECT_DB_HOST` 是防呆用的：deploy 一開始就會比對「這個 environment 宣告自己是哪個 stage」與「secret 解析出來的 DOMAIN / DB_HOST」，對不上就直接失敗，避免 test 部署因為漏設 secret 而打到 production 的資料庫。

#### 部署相關 (deploy-stack.yml)

**設了 `ENV_FILE` 就不需要下面這些 secrets** — 值放在 AP VM 的 `.env` 裡，
deploy 時會直接驗證該檔案（缺 key、`portal.test`、`ss-test`、`測試` 等都會擋下）。

留空 `ENV_FILE` 時才需要設定以下 secrets（會被寫成 AP VM 上的 `.env`）。
另外若上游 packages 是 private，需要 `GH_PAT`（`read:packages`）才能 pull：

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `DOMAIN` | 對外網域 | `<正式站網域>` |
| `SECRET_KEY` | JWT signing key（≥ 32 字元，且必須與 staging 不同） | `openssl rand -hex 32` |
| `CORS_ORIGINS` | 允許的前端來源 | `https://<正式站網域>` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | DB VM 的 PostgreSQL 連線資訊 | `10.x.x.x` / `5432` / … |
| `REDIS_PASSWORD` | Redis 密碼（prod compose 強制要求） | `openssl rand -base64 24` |
| `MINIO_HOST` / `MINIO_PORT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET_NAME` / `MINIO_SECURE` | 物件儲存 | `10.x.x.x` / `9000` / … |
| `PII_ENCRYPTION_KEYS` / `PII_ENCRYPTION_ACTIVE_VERSION` | PII 加密金鑰 JSON | `{"v1":"<key>"}` / `v1` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | 寄信設定 | `smtp.<校內網域>` / `587` |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | 寄件者（不可含 `FORBIDDEN_MARKERS` 列出的字串） | `noreply@<校內網域>` |
| `PORTAL_JWT_SERVER_URL` | Portal SSO（不可含 `FORBIDDEN_MARKERS` 列出的字串） | `https://portal.<校內網域>/jwt/portal` |
| `NEXT_PUBLIC_NYCU_PORTAL_URL` | 前端 Portal 連結 | `https://portal.<校內網域>` |
| `STUDENT_API_BASE_URL` | 學籍 API（不可是 localhost/mock） | `http://<ip>/api/SoAA` |
| `SUPER_ADMIN_NYCU_ID` | 可升級為 super_admin 的職編 | `E00001` |

### Container Registry / 映像檔來源

production repo **不建置也不推送映像檔**。開發 repo 的 pipeline 建好推到 GHCR，
production 只是把同一份 artifact 拉下來跑，確保上線的東西跟 staging 驗過的是
同一個 image，而不是從 mirror 過來的原始碼重新 build 出的另一份。

部署指定版本：`Deploy to Production` → Run workflow → 填 `tag`
（例：`main-2c2b89d6` 或 `v1.2.3`）。不填預設 `latest`；`latest` 會浮動，
無法回滾，正式上線請指定明確 tag。

兩種 tag 的來源不同：

| Tag | 誰產生 | 何時 |
|---|---|---|
| `main-<sha>` | 開發 repo 的 `deploy-pipeline.yml` | 每次 push 到 main 建置完就有 |
| `vX.Y.Z` | 開發 repo 的 `mirror-to-production.yml` | 開 release PR 時，把該 commit 的 `main-<sha>` 映像**複製 manifest** 標上版本號 |

版本 tag 不是重新 build 出來的，內容與同一 commit 的 `main-<sha>` 逐位元相同。
版本號要等 release PR 合併、prod repo 的 auto-tag 建立 git tag 後才算定案，
在那之前 `vX.Y.Z` 仍可能被下一次 mirror 重指到新的 commit；要絕對釘死某份
artifact（例如回滾）時用 `main-<sha>`。release PR 的內文會同時列出這兩個 tag。

#### 環境建置相關 (setting-env.yml)

| Secret Name | Description |
|-------------|-------------|
| `DB_VM_USER` / `DB_VM_SSH_KEY` / `DB_VM_SSH_PORT` | 從 AP VM 佈署 DB VM 用（僅此 workflow 需要） |

#### 備份相關 (backup.yml)

不需要額外 secrets——直接重用上面的 `DB_HOST` / `DB_PORT` / `DB_USER` /
`DB_PASSWORD` / `DB_NAME`。備份檔留在 AP VM 的 `/var/backups/scholarship-system`
供 IT 轉存（DB VM 無對外網路）。

#### 健康檢查 (health-check.yml)

重用 `DOMAIN` 與 `REDIS_PASSWORD`；失敗時自動開 issue，恢復後自動關閉。

#### 監控儀表板 (deploy-monitoring-stack.yml)

`docker-compose.prod.yml` 只帶**採集端**（Alloy、node-exporter、cAdvisor、
nginx-exporter、redis-exporter）。Alloy 把資料推到
`http://monitoring_loki:3100` 與 `http://monitoring_prometheus:9090` —— 這是
**docker DNS 名稱**，只有當 Grafana/Loki/Prometheus 也是同一台 VM 上的容器並掛在
`scholarship_prod_network` 時才解析得到。在那之前 Alloy 會一路重試然後丟掉每一批
資料（log 裡是 `no retries left, dropping data`），nginx 的
`location ^~ /monitoring` 也沒有上游可打（502）。這組 workflow 就是負責把
`monitoring/docker-compose.monitoring.yml` 起起來的那一步。

**每個 stage 各有一份自己的監控堆疊**，跑在自己的 AP VM 上，不共用。

| Secret（Environments → `test` / `production` → Secrets） | 必填 | 說明 |
|---|---|---|
| `GRAFANA_ADMIN_USER` | ✅ | Grafana 管理者帳號。正式站請勿用 `admin`。 |
| `GRAFANA_ADMIN_PASSWORD` | ✅ | ≥ 12 字元。這個儀表板是從正式站網域對外開的，沒設好等於公開。 |
| `GRAFANA_SECRET_KEY` | 建議 | Grafana 用它加密 `secureJsonData`（這裡就是 Loki 的 `X-Scope-OrgID` tenant header）。**要在第一次部署就設好**：對一個「已經存在、且是用別把 key（含 Grafana 內建預設 key，也就是沒設這個 secret 時用的那把）加密過」的 `grafana_data` volume 換 key，所有存起來的 secret 都會解成亂碼——provisioning 不會修好它（datasource 已存在就不會重寫 secure 欄位），畫面上只會看到 `Unable to connect with Loki`。真的撞到只有兩條路：把舊 key 換回來，或用 `reset_grafana_volume=true` 重建。`openssl rand -base64 32`，每個 stage 一把。 |
| `GH_PAT` | 選用 | 只給「告警 → 開 GitHub issue」用（webhook-bridge）。沒設也能跑，只是告警只留在 Grafana 裡。 |

| Variable | 必填 | 說明 |
|---|---|---|
| `GRAFANA_ROOT_URL` | — | 例 `https://<該 stage 網域>/monitoring`。留空時由 `EXPECT_DOMAIN` 推導；兩者都沒有就直接失敗（Grafana 在 sub-path 下必須知道自己的絕對網址，否則所有連結與登入導向都會指到錯的主機）。 |
| `MONITORING_DIR` | — | 監控堆疊放在 VM 上的位置，預設 `/opt/scholarship/monitoring`。 |
| `MONITORING_ALERT_REPO` | — | webhook-bridge 開 issue 的 repo，預設就是 production repo 自己。 |

前置條件與注意事項：

- **只能手動 dispatch**。這兩個 caller 已移除 `push:` 觸發：mirror 同步進
  `monitoring/**` 的變更後，自己跑 `gh workflow run deploy-monitoring-<stage>.yml`
  才會重新部署（每次都會重啟 Grafana 約 30 秒，站台不受影響）。
- **先跑過一次 `deploy-<stage>.yml`**。這組 workflow 需要 `scholarship_prod_network`
  已存在（app stack 建的），最後一步的「透過 nginx 驗證 `/monitoring`」也需要 nginx 在跑。
- **VM 上需要免密碼 sudo**，或事先把 `/opt/scholarship/monitoring` 與
  `/opt/scholarship/secrets` 建好並 chown 給 runner 使用者。
  `/opt/scholarship/secrets/gh_pat` 的路徑寫死在共用的 compose 檔裡（dev/prod 兩邊共用），
  不能按 stage 搬家。
- **⚠️ 防火牆**：共用的 compose 檔會把 Loki `3100` 與 Prometheus `9090`
  publish 到 host（`0.0.0.0`），因為 DB VM 的 Alloy 要跨機推資料進來。**這兩個埠沒有任何
  認證**，請用防火牆只開給該 stage 的 DB VM。
- **DB VM 的採集端不在這組 workflow 範圍內**。`docker-compose.prod-db-monitoring.yml`
  （alloy + node-exporter + postgres-exporter）要在 DB VM 上另外起，並把
  `MONITORING_SERVER_URL` 指向該 stage 的 AP VM。
- `reset_grafana_volume=true` 會**刪掉 `grafana_data`**：手動存的 dashboard、annotation、
  告警靜音全部消失（provisioning 帶的內容會從檔案重建）。平時不要勾。
- `stop-test.yml` / `stop-production.yml` **不會**停監控堆疊（不同的 compose project）。
  站台停機期間 Grafana 仍會繼續跑，這是刻意的——正好用來看停機當下的狀況。

### 3. 自訂配置

#### 修改部署目標

編輯 `deploy-stack.yml`（兩個 stage 共用的腳本本體）:

```yaml
# 修改 Docker image 名稱
tags: |
  your-org/your-app:latest
  your-org/your-app:${{ github.sha }}

# 修改 server 連線資訊
env:
  SERVER_HOST: ${{ secrets.YOUR_SERVER_HOST }}
  SERVER_USER: ${{ secrets.YOUR_SERVER_USER }}
```

#### 調整健康檢查頻率

編輯 `health-check.yml`:

```yaml
on:
  schedule:
    - cron: '*/5 * * * *'  # 每 5 分鐘（更頻繁）
    # - cron: '*/30 * * * *'  # 每 30 分鐘（較少）
```

#### 修改備份保留天數

編輯 `backup.yml`:

```bash
# 修改保留天數（預設 30 天）
CUTOFF_DATE=$(date -d '90 days ago' +%Y%m%d)  # 改為 90 天
```

## 🔐 安全最佳實踐

### Self-hosted Runner

部署與維運 workflow 都跑在 AP VM 上的 self-hosted runner，不使用 SSH 金鑰。
安裝方式見安裝手冊第 6 節；註冊時 labels 需包含 `self-hosted`、`linux`，
**以及該台 VM 的 stage label（`test` 或 `production`）**，並以 service 方式常駐：

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

runner 使用者需要 passwordless sudo（deploy-stack.yml 與 backup.yml 都會用到）。

### Container Registry

映像檔推到 GHCR，登入使用 workflow 內建的 `GITHUB_TOKEN`，
不需要 Docker Hub 帳號或額外 token。

### AWS IAM 權限

為備份創建專用的 IAM user：

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::your-backup-bucket",
        "arn:aws:s3:::your-backup-bucket/*"
      ]
    }
  ]
}
```

## 📋 檢查清單

在啟用 workflows 之前：

### Deploy Workflow

- [ ] `deploy-test.yml`、`deploy-production.yml`、`deploy-stack.yml` 三個都已複製到 prod repo
- [ ] 已知道 deploy **只能手動 dispatch**：merge 到 main 不會部署，release 要自己跑 `gh workflow run deploy-<stage>.yml -f tag=<tag>`
- [ ] test AP VM 的 runner labels 含 `test`；production AP VM 含 `production`
- [ ] GitHub Environments `test` 與 `production` 都已建立
- [ ] 兩個 environment 都設了 **Required reviewers（1 人）**
- [ ] `test` environment 已把所有 secret 各設一份（沒設的會 fallback 到 production 的值）
- [ ] 兩個 environment 的 `DEPLOY_STAGE` / `EXPECT_DOMAIN` / `EXPECT_DB_HOST` 已設定
- [ ] `SECRET_KEY`、`PII_ENCRYPTION_KEYS` 兩邊不同
- [ ] Repository variable `IMAGE_OWNER` 已設定
- [ ] 兩台 VM 都有 TLS 憑證（`fullchain.pem` / `privkey.pem` / `chain.pem`）
- [ ] 兩台 VM 都有足夠的磁碟空間，且 runner 使用者有 passwordless sudo

### Stop Workflow

- [ ] `stop-test.yml`、`stop-production.yml`、`stop-stack.yml` 三個都已複製到 prod repo
- [ ] 兩個 environment 的 **Required reviewers** 已設定（stop 與 deploy 共用同一道關卡）
- [ ] 已知道恢復方式：`gh workflow run deploy-<stage>.yml -f tag=<tag>`
- [ ] 已知道 stop **不會**阻止任何人 dispatch deploy 把站台開回來（push to main 本身已不會部署；需要持續離線時，在 Actions 頁把該 stage 的 deploy workflow disable 掉）

### Health Check Workflow

- [ ] API 和 Frontend URL 正確
- [ ] SSH 憑證已設定（用於檢查 DB/Redis）
- [ ] Notification webhooks 已配置（可選）
- [ ] GitHub token 有建立 issue 的權限

### Backup Workflow

- [ ] AWS 憑證已設定
- [ ] S3 bucket 已創建
- [ ] Bucket 政策允許上傳/刪除
- [ ] SSH 憑證已設定
- [ ] 測試備份和還原流程

## 🔍 測試 Workflows

### 手動測試部署

> ⚠️ **部署只能手動 dispatch**：`deploy-test.yml` / `deploy-production.yml` 都
> 已移除 `push:` 觸發，merge 到 main（含 mirror 同步的 release PR）**不會**部署
> 任何東西。要上線就自己跑下面的指令。

```bash
# In production repo；建議帶明確 tag，兩個 workflow 才會部署到同一份 image
gh workflow run deploy-test.yml -f tag=v1.2.3
gh workflow run deploy-production.yml -f tag=v1.2.3

# Monitor progress（會停在各自的核准）
gh run watch

# Check logs
gh run view --log
```

`tag` 留空會部署 GHCR 上當下的 `latest`，兩次 dispatch 各自解析、可能拿到不同
image；要可重現就一定帶明確 tag。

兩個 workflow 各自獨立：各自 dispatch、各自停在自己 environment 的
"Review deployments" 等核准，reviewer 按下 **Approve and deploy** 才會跑到對應
的 AP VM。

**沒有誰否決誰**：test 失敗不會擋下 production，production 卡在核准也不會擋下
test。順序完全由人決定 —— 先放行 test、看完結果再 dispatch production，要停就
按 Reject 或乾脆不 dispatch。

> ⚠️ 現在擋在 merge 與正式機之間的有兩道，兩道都是人：① 有人手動 dispatch
> `deploy-production.yml`；② `production` environment 的 required reviewer（不再
> 有前置的 test 階段）。上線前務必先把 reviewer 設好。

### 停止站台（stop-test.yml / stop-production.yml）

deploy 的反向操作，兩個 stage 各一個 workflow，共用 `stop-stack.yml`：

```bash
# 停 test（confirm 必須逐字打 stage 名稱）
gh workflow run stop-test.yml -f confirm=test -f mode=stop -f reason="maintenance window"

# 停 production（正式站會離線！）
gh workflow run stop-production.yml -f confirm=production -f mode=stop -f reason="incident #123"
```

| 項目 | 說明 |
|------|------|
| 觸發方式 | **只有手動 dispatch**，沒有 `push:` —— 「有人 push code」從來不代表「該關站」 |
| 兩道關卡 | ① `confirm` 必須逐字等於 stage 名稱（dispatch 會記住上次輸入，打字才擋得住手殘）② 該 environment 的 required reviewer，跟 deploy 同一道 |
| `mode=stop`（預設） | `docker compose stop`，容器保留，之後幾秒就能恢復 |
| `mode=down` | `docker compose down --remove-orphans`，移除容器與 compose 網路 |
| 資料 | **兩種模式都不會刪 volume**（檔案裡沒有任何 `-v`）。PostgreSQL / MinIO 在 DB VM，這個 workflow 根本碰不到 |
| concurrency | 自己的 group（`stop-test` / `stop-production`），**不與 deploy 共用**：等待核准中的 deploy 會佔住它自己的 group，共用的話「關站」會被卡到有人去審那個 deploy 為止。stop 與 deploy 的先後由人（同一道核准關卡）決定 |
| 恢復 | `gh workflow run deploy-<stage>.yml -f tag=<tag>`，會照常跑 migration + health + smoke checks |

> ⚠️ **stop 不等於 hold。** 這兩個 workflow 只是把「當下正在跑的」關掉，不會在
> VM 上留下任何標記。merge 到 main 已經不會自動把站台開回來（deploy 已改成
> 只能手動 dispatch），但**任何人 dispatch 一次 deploy 就會開回來**。若該 stage
> 必須持續離線（維護時段、incident 處理中），除了公告之外，請到 Actions 頁面把
> 對應的 deploy workflow 暫時 disable 掉。

### 測試健康檢查

```bash
gh workflow run health-check.yml
```

### 測試備份

```bash
# Test backup workflow
gh workflow run backup.yml

# Verify S3
aws s3 ls s3://your-backup-bucket/database/
aws s3 ls s3://your-backup-bucket/files/
```

## 📊 監控

### Workflow 執行歷史

```bash
# List recent workflow runs
gh run list --workflow=deploy-test.yml --limit=10
gh run list --workflow=deploy-production.yml --limit=10

# View specific run
gh run view <run-id>

# Download logs
gh run download <run-id>
```

### 檢查 Secrets

```bash
# List configured secrets (won't show values)
gh secret list
```

## 🐛 故障排除

### Deploy 失敗: SSH Connection Refused

```bash
# Test SSH connection manually
ssh -i ~/.ssh/production_deploy user@production-server

# Check SSH service on server
sudo systemctl status ssh

# Verify firewall allows SSH (port 22)
sudo ufw status
```

### Backup 失敗: S3 Access Denied

```bash
# Test AWS credentials
aws s3 ls s3://your-backup-bucket/

# Verify IAM permissions
aws iam get-user
aws iam list-attached-user-policies --user-name backup-user
```

### Health Check 持續失敗

```bash
# Manual health check
curl -v https://api.production.example.com/health
curl -v https://production.example.com

# Check application logs
ssh production-server
cd /opt/scholarship-system
docker compose logs --tail=100
```

## 🔄 更新 Workflows

當 development repo 的範例更新時：

```bash
# In production repo
# Review changes first
for f in deploy-test.yml deploy-production.yml deploy-stack.yml; do
  diff ".github/workflows/$f" \
       "/path/to/dev-repo/.github/production-workflows-examples/$f"
done

# Update if needed
for f in deploy-test.yml deploy-production.yml deploy-stack.yml; do
  cp "/path/to/dev-repo/.github/production-workflows-examples/$f" \
     ".github/workflows/$f"
done

# 舊版單一檔 deploy.yml 已拆成上面兩個 caller —— prod repo 若還留著它，
# 刪掉，否則它自己的 push to main 觸發還會多跑一條舊的 promotion。
git rm -f .github/workflows/deploy.yml 2>/dev/null || true

# Commit
git add .github/workflows/
git commit -m "Update production workflows"
git push
```

## 📚 延伸閱讀

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Docker Compose Production Guide](https://docs.docker.com/compose/production/)
- [AWS S3 Backup Best Practices](https://docs.aws.amazon.com/AmazonS3/latest/userguide/backup-best-practices.html)
- [PostgreSQL Backup and Restore](https://www.postgresql.org/docs/current/backup.html)

## 💡 提示

1. **定期測試還原**：每月至少測試一次備份還原流程
2. **監控磁碟空間**：確保 server 有足夠空間儲存備份
3. **更新憑證**：定期更新 SSH keys 和 access tokens
4. **檢查 logs**：定期查看 workflow logs 發現潛在問題
5. **文件化**：記錄任何自訂配置和操作程序

## ⚠️ 重要提醒

- ❗ **不要**在 production repo 手動修改 application code（應在 development repo 修改）
- ❗ **只**在 production repo 管理 `.github/workflows/` 和 production-specific configs
- ❗ Development repo 的 sync workflow 會**覆蓋** application code，但**不會**影響 workflows
- ❗ 確保所有 secrets 都有設定，否則 workflows 會失敗
