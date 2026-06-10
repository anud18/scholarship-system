# Production Workflows Examples

這個目錄包含用於 **production repository** 的 workflow 範例。這些 workflows 是專門為 production 環境設計的，不會從 development repository 同步過去。

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
| `auto-tag-on-merge.yml` ⭐ | 自動建立 Git tag 和 Release | PR merge 到 main | **必要** |
| `deploy.yml` | 部署應用程式到 production | Push to main / 手動觸發 | 選用 |
| `health-check.yml` | 監控應用程式健康狀態 | 每 15 分鐘 / 手動觸發 | 選用 |
| `backup.yml` | 備份資料庫（DB VM 備份 → 驗證 → 拉回 AP VM 副本） | 每日 19:30 UTC（台北 03:30）/ 手動觸發 | 選用 |

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

#### 部署相關 (deploy.yml)

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `DOCKER_USERNAME` | Docker Hub 用戶名 | `your-username` |
| `DOCKER_PASSWORD` | Docker Hub 密碼或 token | `dckr_pat_xxxxx` |
| `PRODUCTION_SSH_KEY` | SSH private key for server | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `PRODUCTION_SERVER` | Production server hostname | `production.example.com` |
| `PRODUCTION_USER` | SSH username | `ubuntu` or `deploy` |

#### 備份相關 (backup.yml)

`backup.yml` 在 **AP VM 的 self-hosted runner** 上執行（DB VM 無外網，無法直接被 GitHub-hosted runner 連線），使用與 `setting-env.yml` 相同的 DB VM SSH secrets：

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `DB_HOST` | DB VM 內網 hostname/IP | `10.0.1.100` |
| `DB_VM_USER` | DB VM SSH 使用者 | `ubuntu` |
| `DB_VM_SSH_KEY` | DB VM SSH private key | `-----BEGIN OPENSSH PRIVATE KEY-----` |
| `DB_VM_SSH_PORT` | DB VM SSH port | `8822` |

詳細設定步驟見 `SECRETS-SETUP-GUIDE.md`。

#### 通知相關 (health-check.yml, optional)

| Secret Name | Description |
|-------------|-------------|
| `SLACK_WEBHOOK_URL` | Slack incoming webhook URL |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL |

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

### SSH Key 設定

```bash
# Generate SSH key pair (on your local machine)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/production_deploy

# Add public key to production server
ssh-copy-id -i ~/.ssh/production_deploy.pub user@production-server

# Copy private key content (including BEGIN/END lines)
cat ~/.ssh/production_deploy
# Add to GitHub Secrets as PRODUCTION_SSH_KEY
```

### Docker Hub Token

建議使用 access token 而非密碼：

1. Docker Hub → Account Settings → Security → Access Tokens
2. Create new token with name "GitHub Actions"
3. Copy token and add to secrets as `DOCKER_PASSWORD`

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

- [ ] Self-hosted runner 已安裝在 AP VM 並上線
- [ ] DB VM SSH secrets 已設定（`DB_HOST`、`DB_VM_USER`、`DB_VM_SSH_KEY`、`DB_VM_SSH_PORT`）
- [ ] AP VM `/opt/scholarship/backups` 有足夠磁碟空間
- [ ] DB VM 備份目錄 `/opt/scholarship/postgres/backups` 存在且有足夠空間
- [ ] 測試備份和還原流程（手動觸發並勾選 `verify_restore`）

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
# Test backup workflow (optionally with full restore test)
gh workflow run backup.yml -f verify_restore=true

# Verify the off-server copy on AP VM
ls -lh /opt/scholarship/backups/database/$(date +%Y%m%d)/

# Verify checksum
cd /opt/scholarship/backups/database/$(date +%Y%m%d)
sha256sum -c scholarship_db_backup_*.dump.sha256
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

### Backup 失敗: 無法 SSH 到 DB VM

```bash
# 在 AP VM (runner) 上手動測試 SSH 連線
ssh -p <DB_VM_SSH_PORT> -i ~/.ssh/db_vm_deploy <DB_VM_USER>@<DB_HOST> "echo ok"

# 檢查 DB VM 上 postgres 容器狀態
ssh -p <DB_VM_SSH_PORT> <DB_VM_USER>@<DB_HOST> "docker ps --filter name=scholarship_postgres"

# 檢查 DB VM 備份目錄磁碟空間
ssh -p <DB_VM_SSH_PORT> <DB_VM_USER>@<DB_HOST> "df -h /opt/scholarship/postgres/backups"
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
