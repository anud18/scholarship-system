# Production Workflows Examples

這個目錄包含用於 **production repository** 的 workflow 範例。這些 workflows 是專門為 production 環境設計的，不會從 development repository 同步過去。

## 📁 檔案說明

| 檔案 | 用途 | 觸發時機 |
|------|------|----------|
| `deploy.yml` | 部署應用程式到 production | Push to main / 手動觸發 |
| `health-check.yml` | 監控應用程式健康狀態 | 每 15 分鐘 / 手動觸發 |
| `backup.yml` | 備份資料庫和檔案 | 每日 2AM UTC / 手動觸發 |

## 🚀 使用方式

### 1. 複製到 Production Repo

```bash
# Clone production repository
git clone https://github.com/your-org/scholarship-production.git
cd scholarship-production

# Create workflows directory
mkdir -p .github/workflows

# Copy the workflows you need
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

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS access key | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | AWS region (optional) | `us-east-1` |
| `BACKUP_S3_BUCKET` | S3 bucket name | `production-backups` |

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
