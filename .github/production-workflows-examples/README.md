# Production Workflows Examples

這個目錄包含用於 **production repository** 的 workflows。

## 🚚 自動安裝（2026-06-13 起）

**不需要再手動複製。** `mirror-to-production.yml` 是進入私有 prod repo 的唯一通道，
因此它會在每次 mirror 時自動把本目錄的 workflows 安裝到 prod repo 的
`.github/workflows/`：

- prod repo **還沒有**的檔案 → 自動安裝（首次 mirror 即完成 CI/CD bootstrap）
- prod repo **已有**的檔案 → 一律不覆寫（prod 端客製優先）；若範本與 prod 版本
  不同，mirror log 會以 notice 提示，由人工決定是否移植

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
| `deploy.yml` | 部署應用程式到 production | Push to main / 手動觸發 | **必要** |
| `health-check.yml` | 監控應用程式健康狀態 | 每 15 分鐘 / 手動觸發 | 選用 |
| `backup.yml` | 備份資料庫和檔案 | 每日 2AM UTC / 手動觸發 | 選用 |

### 🅾️ 步驟 0：bare VM 的 bootstrap（雞生蛋問題）

所有 workflow 都 `runs-on: [self-hosted, linux]`。**空的 AP VM 上沒有 runner,任何 action 都跑不了** —— 必須先手動把 runner 裝起來。`bootstrap-ap-runner.sh` 就是這一步:裝 Docker + 把 GitHub Actions runner 註冊成 systemd service。

> 此 `.sh` **只存在於 dev repo 的本目錄**(mirror 只帶可執行的 `.yml` 過去,且空 VM 本來也收不到)。操作者直接從這裡複製到 AP VM 執行。

```bash
# 1) 在 prod repo 取得 runner 註冊 token(約 1 小時有效)
gh api -X POST repos/<OWNER>/<PROD_REPO>/actions/runners/registration-token --jq .token

# 2) 把本目錄的 bootstrap-ap-runner.sh 複製到 AP VM,然後:
chmod +x bootstrap-ap-runner.sh
./bootstrap-ap-runner.sh --repo-url https://github.com/<OWNER>/<PROD_REPO> --token <TOKEN>
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
cp /path/to/development-repo/.github/production-workflows-examples/deploy.yml \
   .github/workflows/deploy.yml

cp /path/to/development-repo/.github/production-workflows-examples/health-check.yml \
   .github/workflows/health-check.yml

cp /path/to/development-repo/.github/production-workflows-examples/backup.yml \
   .github/workflows/backup.yml
```

### 2. 配置 Secrets

在 production repository 設定以下 secrets（Settings → Secrets and variables → Actions）：

> 沒有任何 workflow 使用 SSH。deploy.yml / backup.yml / health-check.yml 都跑在
> production AP VM 上的 self-hosted runner（labels `[self-hosted, linux]`），
> 直接操作本機 docker 與 DB VM 的 5432 埠。GitHub-hosted runner 連不到校內 VM。

#### Repository Variables（Settings → Variables → Actions）

| Variable | 必填 | 說明 |
|----------|------|------|
| `IMAGE_OWNER` | ✅ | 發布映像檔的 GHCR namespace，也就是**開發 repo 的 owner**（例：`anud18`）。production repo 不建置映像檔，只取用開發流程已經發布、staging 驗過的那一份。 |
| `PRODUCTION_URL` | ✅ | 例：`https://ss.aa.nycu.edu.tw` |
| `ENV_FILE` | — | AP VM 上既有 `.env` 的絕對路徑（安裝手冊 5.1，例：`/home/<user>/.env`）。**設了就用它**，GitHub 完全不存這些值。留空則由 deploy.yml 依下方 secrets 產生 `~/scholarship-production/.env`（權限 600）。 |
| `SSL_CERT_DIR` | — | TLS 憑證資料夾的絕對路徑（例：`/home/<user>/ssl`）。留空則用 repo `nginx/ssl/prod`。兩種 `ENV_FILE` 模式下都以這個變數優先。資料夾內需有 `fullchain.pem`、`privkey.pem`、`chain.pem`。 |

#### 部署相關 (deploy.yml)

**設了 `ENV_FILE` 就不需要下面這些 secrets** — 值放在 AP VM 的 `.env` 裡，
deploy 時會直接驗證該檔案（缺 key、`portal.test`、`ss-test`、`測試` 等都會擋下）。

留空 `ENV_FILE` 時才需要設定以下 secrets（會被寫成 AP VM 上的 `.env`）。
另外若上游 packages 是 private，需要 `GH_PAT`（`read:packages`）才能 pull：

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `DOMAIN` | 對外網域 | `ss.aa.nycu.edu.tw` |
| `SECRET_KEY` | JWT signing key（≥ 32 字元，且必須與 staging 不同） | `openssl rand -hex 32` |
| `CORS_ORIGINS` | 允許的前端來源 | `https://ss.aa.nycu.edu.tw` |
| `DB_HOST` / `DB_PORT` / `DB_USER` / `DB_PASSWORD` / `DB_NAME` | DB VM 的 PostgreSQL 連線資訊 | `10.x.x.x` / `5432` / … |
| `REDIS_PASSWORD` | Redis 密碼（prod compose 強制要求） | `openssl rand -base64 24` |
| `MINIO_HOST` / `MINIO_PORT` / `MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY` / `MINIO_BUCKET_NAME` / `MINIO_SECURE` | 物件儲存 | `10.x.x.x` / `9000` / … |
| `PII_ENCRYPTION_KEYS` / `PII_ENCRYPTION_ACTIVE_VERSION` | PII 加密金鑰 JSON | `{"v1":"<key>"}` / `v1` |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` | 寄信設定 | `smtp-prod2.nycu.edu.tw` / `587` |
| `EMAIL_FROM` / `EMAIL_FROM_NAME` | 寄件者（不可含 `ss-test` 或 `測試`） | `noreply@aa.nycu.edu.tw` |
| `PORTAL_JWT_SERVER_URL` | Portal SSO（不可指向 `portal.test`） | `https://portal.nycu.edu.tw/jwt/portal` |
| `NEXT_PUBLIC_NYCU_PORTAL_URL` | 前端 Portal 連結 | `https://portal.nycu.edu.tw` |
| `STUDENT_API_BASE_URL` | 學籍 API（不可是 localhost/mock） | `http://<ip>/api/SoAA` |
| `SUPER_ADMIN_NYCU_ID` | 可升級為 super_admin 的職編 | `E00001` |

### Container Registry / 映像檔來源

production repo **不建置也不推送映像檔**。開發 repo 的 pipeline 建好推到 GHCR，
production 只是把同一份 artifact 拉下來跑，確保上線的東西跟 staging 驗過的是
同一個 image，而不是從 mirror 過來的原始碼重新 build 出的另一份。

部署指定版本：`Deploy to Production` → Run workflow → 填 `tag`
（例：`main-2c2b89d6` 或 `v1.2.3`）。不填預設 `latest`；`latest` 會浮動，
無法回滾，正式上線請指定明確 tag。

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

### 3. 自訂配置

#### 修改部署目標

編輯 `deploy.yml`:

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
安裝方式見安裝手冊第 6 節；註冊時 labels 需包含 `self-hosted` 與 `linux`，
並以 service 方式常駐：

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

runner 使用者需要 passwordless sudo（deploy.yml 與 backup.yml 都會用到）。

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

- [ ] Docker Hub 憑證已設定
- [ ] SSH key 已添加到 production server
- [ ] Server 有足夠的磁碟空間
- [ ] Docker Compose 檔案正確配置
- [ ] 測試 SSH 連線成功
- [ ] 煙霧測試 URL 正確

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

```bash
# In production repo
gh workflow run deploy.yml

# Monitor progress
gh run watch

# Check logs
gh run view --log
```

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
gh run list --workflow=deploy.yml --limit=10

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
diff .github/workflows/deploy.yml \
     /path/to/dev-repo/.github/production-workflows-examples/deploy.yml

# Update if needed
cp /path/to/dev-repo/.github/production-workflows-examples/deploy.yml \
   .github/workflows/deploy.yml

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
