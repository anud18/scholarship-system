# GitHub Secrets Setup Guide

This guide explains how to configure GitHub Secrets for the NYCU Scholarship System production deployment.

## ℹ️ Workflow Focus

The `setting-env.yml` workflow now **focuses on system prerequisites and Docker installation**:
- **System Prerequisites** (requires 4 secrets):
  - LVM disk extension (extends storage on both VMs)
  - NTP time synchronization (configures `time.stdtime.gov.tw`)
- **Docker Setup** (requires 4 secrets): Installs Docker on AP VM and DB VM
- **Environment Setup** (requires all secrets): Creates directories and generates `.env` file

**Simplified validation**: Only Docker-related secrets are validated upfront. Other secrets (database credentials, email config, etc.) are validated when generating the `.env` file.

## 📋 Table of Contents

- [Environments：兩個部署 workflow 與核准閘門](#environments兩個部署-workflow-與核准閘門) ⭐ **先讀這個**
- [Quick Start](#quick-start)
- [Required Secrets](#required-secrets)
  - [Database VM SSH Access](#database-vm-ssh-access-secrets) ⭐ **Required for Docker setup**
  - [Database Connection](#database-connection-secrets)
  - [MinIO Object Storage](#minio-object-storage-secrets)
  - [Application Secrets](#application-secrets)
  - [Email Configuration](#email-configuration-secrets)
  - [SSO Configuration](#sso-configuration-secrets)
  - [Student API Configuration](#student-api-configuration-secrets)
  - [General Configuration](#general-configuration-secrets)
- [How to Add Secrets](#how-to-add-secrets-to-github)
- [Security Best Practices](#security-best-practices)
- [Validation](#validating-secrets)
- [Troubleshooting](#troubleshooting)

---

## Environments：兩個部署 workflow 與核准閘門

部署拆成**兩個各自獨立的 workflow**，觸發條件相同（push to main）：

```
push to main ─┬─▶ deploy-test.yml ──────▶ deploy-stack.yml (stage: test)
              │                            resolve-images ──▶ deploy
              │                            (ubuntu-latest)    runner: [self-hosted, linux, test]
              │                                               environment: test
              │                                               🔒 需 1 位 reviewer 核准
              │
              └─▶ deploy-production.yml ▶ deploy-stack.yml (stage: production)
                                           resolve-images ──▶ deploy
                                           (ubuntu-latest)    runner: [self-hosted, linux, production]
                                                              environment: production
                                                              🔒 需 1 位 reviewer 核准
```

- 兩者**互不等待、互不否決**：test 失敗不會擋下 production，production 卡在核准
  也不會擋下 test。test tier 有它自己會壞的理由（它的 DB、憑證、portal），那些
  不該卡住 production 的 hotfix。
- **順序由人決定**：production 的 reviewer 在 Actions 頁面看得到同一個 push
  觸發的 test run，可以先看結果再決定核准或 Reject。
- 唯一會自動否決的是各自的 `resolve-images` —— 沒解析出 tag 就沒東西可部署。
- 兩者共用同一份腳本（`deploy-stack.yml`），差別只有 **runner label** 與
  **GitHub Environment**。test 因此是 production 的彩排，不是另一套流程。
- ⚠️ 因為 production 前面不再有 test 階段擋著，`production` environment 的
  required reviewer 就是 push to main 與正式機之間**唯一**的關卡。

> `latest`（不帶 tag 觸發）時兩個 workflow 各自解析一次，中間 tag 可能移動 ——
> 要讓 test 真的能當 production 的證據，就用 `-f tag=<明確 tag>` 手動觸發兩者。

### 1. 建立兩個 Environment 並設定 reviewer（核准閘門）

**這一步是 YAML 做不到的**：`environment:` 這個 key 本身不會擋任何東西，
真正的核准規則在 repo 設定裡。沒設 reviewer 的話，兩個階段都會無人值守直接跑完。

Settings → Environments → New environment，建立 `test` 與 `production`，各自：

1. 勾選 **Required reviewers**，加入 **1 位** 有權限的成員（需求：一名 user 同意）。
2. （建議）**Deployment branches**：限制成 `main`。
3. （建議）取消勾選 "Allow administrators to bypass configured protection rules"，
   否則 admin 可以略過核准。

或用 CLI：

```bash
# <OWNER>/<PROD_REPO> 換成 production repo；<REVIEWER_USER_ID> 是數字 user id
# （取得方式：gh api users/<LOGIN> --jq .id）
for ENV in test production; do
  gh api -X PUT "repos/<OWNER>/<PROD_REPO>/environments/$ENV" \
    -F "wait_timer=0" \
    -F "reviewers[][type]=User" -F "reviewers[][id]=<REVIEWER_USER_ID>" \
    -F "deployment_branch_policy[protected_branches]=true" \
    -F "deployment_branch_policy[custom_branch_policies]=false"
done
```

核准流程：兩個 workflow 各自 run，各自停在 "Review deployments"，指定的 reviewer
在 Actions 頁面按 **Approve and deploy** 才會繼續。兩個核准彼此獨立、沒有先後
強制關係 —— 想維持「先 test 再 production」就先核准 test run、看完結果再回頭核准
production run。

`setting-env.yml` 也掛了同樣的 environment（它會改機器、寫 `.env`），
所以它也要先被核准；`backup.yml` / `health-check.yml` 是排程執行、只讀或只寫備份，
**刻意不掛** environment —— 掛了會卡在等人核准，排程等於失效。

### 2. test 與 production 用不同的 env variable

值放在 **Environment secrets / variables**，不是 repository 層：

| 放在哪 | 內容 | 誰讀得到 |
|--------|------|----------|
| Repository secrets | **production 的值** | 所有 workflow（含沒掛 environment 的 `backup.yml`、`health-check.yml`） |
| Environment `production` | 可留空，fallback 到 repository 層 | `deploy-production.yml`、`setting-env.yml`(production) |
| Environment `test` | **測試環境的值，下面清單要全部各設一份** | `deploy-test.yml`、`setting-env.yml`(test) |

> ⚠️ **fallback 陷阱**：environment 沒定義的 secret 會自動往上抓 repository 層的值。
> 也就是說 `test` environment 少設一個 `DB_HOST`，test 部署就會連上 **production 的
> 資料庫**，而且不會有任何錯誤訊息。

`test` environment 必須各自設定的 secret（值與 production 不同）：

```
DOMAIN  SECRET_KEY  CORS_ORIGINS
DB_HOST  DB_PORT  DB_USER  DB_PASSWORD  DB_NAME
REDIS_PASSWORD
MINIO_HOST  MINIO_PORT  MINIO_ACCESS_KEY  MINIO_SECRET_KEY  MINIO_BUCKET_NAME  MINIO_SECURE
PII_ENCRYPTION_KEYS  PII_ENCRYPTION_ACTIVE_VERSION
SMTP_HOST  SMTP_PORT  SMTP_USER  SMTP_PASSWORD  EMAIL_FROM  EMAIL_FROM_NAME
PORTAL_JWT_SERVER_URL  STUDENT_API_BASE_URL  NEXT_PUBLIC_NYCU_PORTAL_URL
SUPER_ADMIN_NYCU_ID
```

`SECRET_KEY` 與 `PII_ENCRYPTION_KEYS` **絕對不要兩邊共用**：共用的 `SECRET_KEY`
等於 test 簽出來的 token 可以拿去打 production；共用的 PII 金鑰則讓測試資料庫
的備份足以解開正式個資。

環境變數（Variables，不是 secret）：

| Variable | `test` | `production` | 作用 |
|----------|--------|--------------|------|
| `DEPLOY_STAGE` | `test` | `production` | 防呆：environment 自報身分，對不上就拒絕部署 |
| `EXPECT_DOMAIN` | 測試網域 | 正式網域 | 防呆：比對 `secrets.DOMAIN`，抓漏設的 fallback |
| `EXPECT_DB_HOST` | 測試 DB 位址 | 正式 DB 位址 | 防呆：比對 `secrets.DB_HOST` |
| `DEPLOY_URL` | `https://<測試站網域>` | `https://<正式站網域>` | Environment 頁面顯示的連結 |
| `SSL_CERT_DIR` | 選填 | 選填 | 該台 VM 上的憑證目錄 |
| `ENV_FILE` | 選填 | 選填 | 該台 VM 上 operator 自管的 `.env` 路徑 |
| `FORBIDDEN_MARKERS` | 選填（設在 repository 層即可） | 同左 | 空白分隔的字串清單，只會出現在非正式值裡（測試網域、測試寄件者……）。production 段只要有任一 secret 命中就拒絕部署；不設就跳過這項檢查 |

`FORBIDDEN_MARKERS` 取代了以前寫死在 workflow 裡的站台字串（測試網域、`測試` 寄件者
名稱等）—— 這份模板會被 mirror 進 production repo，不該帶著站台自己的主機名。

`DEPLOY_STAGE` / `EXPECT_DOMAIN` / `EXPECT_DB_HOST` 在 test 是**必填**：
deploy 的第一個步驟（Assert stage identity，跑在 checkout 之前）會比對它們，
一旦 `test` environment 漏設 secret 而 fallback 到 production 的值，這一步就會
直接失敗，還沒碰到任何 container。

### 3. 兩台 runner 的 label

| VM | labels | bootstrap 指令 |
|----|--------|----------------|
| test AP VM | `self-hosted,linux,test` | `./bootstrap-ap-runner.sh --repo-url … --token … --stage test` |
| production AP VM | `self-hosted,linux,production` | `./bootstrap-ap-runner.sh --repo-url … --token … --stage production` |

兩台都會有 `self-hosted` 與 `linux`，**stage label 是唯一能分辨的依據**。
`bootstrap-ap-runner.sh --stage` 是必填參數，且會擋掉「`--labels` 沒有含 stage label」
這種註冊完卻永遠收不到 job 的情況。

---

## Quick Start

### For Docker Installation Only (Minimal Setup)

If you only want to install Docker on both VMs, configure these 4 secrets:

1. Navigate to your **production repository** on GitHub
2. Go to **Settings** → **Secrets and variables** → **Actions**
3. Add these 4 Docker-related secrets:
   - `DB_HOST` - Database VM hostname/IP
   - `DB_VM_USER` - SSH username for DB VM
   - `DB_VM_SSH_KEY` - SSH private key for DB VM
   - `DB_VM_SSH_PORT` - SSH port number (e.g., `8822`)
4. Run workflow: `gh workflow run setting-env.yml -f action=setup`

### For Complete Environment Setup

To also generate `.env` file and set up directories, configure **all 22 secrets** listed below, then run the workflow.

---

## Required Secrets

### Database Connection Secrets

These secrets configure the connection from AP VM to the PostgreSQL database on DB VM.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `DB_HOST` | Database VM hostname or IP address | `10.x.x.x` or `db.internal.<your-domain>` | ✅ Yes |
| `DB_PORT` | PostgreSQL port | `5432` | ⚠️ Optional (default: 5432) |
| `DB_USER` | PostgreSQL username | `scholarship_user` or `scholar` | ✅ Yes |
| `DB_PASSWORD` | PostgreSQL password | `SecureP@ssw0rd123456` | ✅ Yes |
| `DB_NAME` | PostgreSQL database name | `scholarship_db` or `scholarship` | ✅ Yes |

**How to obtain:**
- Set during DB VM initial setup (Section 4.4 of installation manual: `.env.db`)
- Check `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` in DB VM's `.env.db` file

**Password Requirements:**
- ✅ Minimum 16 characters
- ✅ Include uppercase, lowercase, numbers, and symbols
- ✅ No dictionary words
- ❌ Avoid: `postgres`, `password`, `123456`

---

### Database VM SSH Access Secrets

These secrets enable automated Docker image transfer from AP VM to DB VM (offline installation).

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `DB_VM_USER` | SSH username for DB VM | `ubuntu`, `scholar`, or `debian` | ✅ Yes |
| `DB_VM_SSH_KEY` | SSH private key for DB VM access | Full contents of the dedicated deploy key file (see "SSH Key Format" below) | ✅ Yes |
| `DB_VM_SSH_PORT` | SSH port number | `8822`, `22`, or `2222` | ✅ Yes |

**Purpose:**
- DB VM is **offline** and cannot install Docker or pull images from internet
- Workflow automates complete DB VM setup:
  1. **Install Docker Engine** (if not already installed)
     - Downloads `.deb` packages on AP VM
     - Transfers and installs on DB VM via SSH
     - Enables Docker daemon
  2. **Transfer Docker Images**
     - Pulls `postgres:15-alpine` and `minio/minio:latest` on AP VM
     - Transfers and loads images on DB VM
- Implements Section 3 of installation manual (offline Docker setup)

**How to setup SSH access:**

```bash
# On your local machine or management workstation

# 1. Generate dedicated SSH key pair for automation
ssh-keygen -t ed25519 -C "github-actions-db-vm" -f ~/.ssh/db_vm_deploy

# Output:
# - Private key: ~/.ssh/db_vm_deploy
# - Public key: ~/.ssh/db_vm_deploy.pub

# 2. Copy public key to DB VM
# Replace 8822 with your actual SSH port
ssh-copy-id -p 8822 -i ~/.ssh/db_vm_deploy.pub ubuntu@<DB_VM_IP>

# Or manually:
ssh -p 8822 ubuntu@<DB_VM_IP>
mkdir -p ~/.ssh
chmod 700 ~/.ssh
# Paste public key content into ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
exit

# 3. Test SSH connection
ssh -p 8822 -i ~/.ssh/db_vm_deploy ubuntu@<DB_VM_IP> "echo 'SSH test successful'"

# 4. Add private key to GitHub Secrets
gh secret set DB_VM_SSH_KEY < ~/.ssh/db_vm_deploy

# 5. Add DB VM username to GitHub Secrets
gh secret set DB_VM_USER -b "ubuntu"

# 6. Add SSH port to GitHub Secrets
gh secret set DB_VM_SSH_PORT -b "8822"

# 7. Securely store private key backup (optional but recommended)
# - Store in password manager (1Password, Bitwarden, etc.)
# - Label as "DB VM SSH Key - GitHub Actions"

# 8. Remove local copy (optional, for security)
rm ~/.ssh/db_vm_deploy
# Keep public key for reference: ~/.ssh/db_vm_deploy.pub
```

**SSH Key Format:**

The `DB_VM_SSH_KEY` value should be the **full private key file contents**: the
`BEGIN OPENSSH PRIVATE KEY` header line, every base64 line between, and the
`END OPENSSH PRIVATE KEY` footer line — paste the file verbatim, do not
reformat or strip newlines. (No sample key is shown here so that scanners and
greps never mistake documentation for a committed credential.)

**Important Notes:**
- ⚠️ Use a **dedicated key** for automation (not your personal SSH key)
- ⚠️ `DB_HOST` must be the same host as `DB_VM_USER@DB_HOST` for SSH
- ⚠️ Ensure DB VM's `sshd` allows key-based authentication
- ⚠️ Test SSH connection manually before running workflow
- 🔐 Never commit private keys to git (use GitHub Secrets only)
- 🔐 Use `ed25519` keys (modern, secure, small) or `rsa` (minimum 2048-bit)

**Troubleshooting SSH Connection:**

```bash
# Test SSH connection manually (from AP VM or local machine)
# Replace 8822 with your actual SSH port
ssh -p 8822 -i ~/.ssh/db_vm_deploy -v ubuntu@<DB_VM_IP>

# Common issues:
# 1. Permission denied (publickey)
#    → Verify public key is in ~/.ssh/authorized_keys on DB VM
#    → Check file permissions: chmod 600 ~/.ssh/authorized_keys

# 2. Connection timeout
#    → Verify DB_HOST is correct
#    → Verify DB_VM_SSH_PORT is correct
#    → Check firewall allows SSH on the specified port from AP VM

# 3. Host key verification failed
#    → Add DB_HOST to ~/.ssh/known_hosts:
#      ssh-keyscan -p 8822 -H <DB_VM_IP> >> ~/.ssh/known_hosts
```

**Sudo Requirements for DB VM User:**

The workflow automates Docker installation and image management, which requires sudo privileges. Configure passwordless sudo for the `DB_VM_USER`:

```bash
# On DB VM, add user to sudoers with NOPASSWD for required commands

# Method 1: Full passwordless sudo (simpler, less secure)
sudo visudo
# Add this line:
ubuntu ALL=(ALL) NOPASSWD: ALL

# Method 2: Limited passwordless sudo (more secure, recommended)
sudo visudo
# Add these lines for Docker-specific commands only:
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/apt-get update
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/apt-get install *
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/apt-get -f install *
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/dpkg -i *
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable docker
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl start docker
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl enable --now docker
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/usermod -aG docker *
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/docker *

# System prerequisites: LVM disk extension
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/vgs *
ubuntu ALL=(ALL) NOPASSWD: /usr/sbin/lvextend *
ubuntu ALL=(ALL) NOPASSWD: /usr/sbin/resize2fs *

# System prerequisites: NTP time synchronization
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/tee /etc/systemd/timesyncd.conf
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/cp /etc/systemd/timesyncd.conf*
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart systemd-timesyncd
ubuntu ALL=(ALL) NOPASSWD: /usr/bin/timedatectl *

# Verify passwordless sudo works
sudo -n docker ps  # Should not prompt for password
```

**Why Passwordless Sudo?**
- GitHub Actions workflows cannot provide interactive password input
- Workflow needs sudo to:
  - **System Prerequisites**:
    - Extend LVM disk space (`vgs`, `lvextend`, `resize2fs`)
    - Configure NTP time sync (`tee`, `systemctl restart systemd-timesyncd`, `timedatectl`)
  - **Docker Installation**:
    - Install Docker packages (`apt-get install`, `dpkg -i`)
    - Enable Docker service (`systemctl enable --now docker`)
    - Run Docker commands before user group membership takes effect

**Security Best Practices:**
1. **Least Privilege**:
   - Use Method 2 (limited sudo) instead of full passwordless sudo
   - Only grant sudo for specific Docker-related commands
   - User will be added to `docker` group automatically (but requires re-login)
2. **Key Rotation**: Rotate SSH key every 90 days
3. **Audit Logs**: Monitor SSH access logs on DB VM: `/var/log/auth.log`
4. **Firewall**: Restrict SSH port 22 to only AP VM's IP address
5. **Review Access**: Regularly review sudoers file for unauthorized changes

**Workflow Behavior:**

| Action | Docker Secrets | SSH Required | Sudo Required | What It Does |
|--------|----------------|--------------|---------------|--------------|
| `validate` | ✅ Validates | ❌ No | ❌ No | Only validates Docker-related secrets (DB_HOST, DB_VM_USER, DB_VM_SSH_KEY) |
| `setup` | ✅ Validates | ✅ Yes | ✅ Yes | Validates Docker secrets → Installs Docker on AP VM → Installs Docker on DB VM → Transfers images → Creates directories → Generates .env |
| `full-check` | ✅ Validates | ✅ Yes | ✅ Yes | Same as `setup` (no additional validation steps) |

**Note**: The `full-check` action is now equivalent to `setup` because system prerequisite checks and connectivity tests have been removed. The workflow focuses on Docker installation and environment preparation.

---

### MinIO Object Storage Secrets

These secrets configure the connection from AP VM to MinIO object storage on DB VM.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `MINIO_HOST` | MinIO VM hostname or IP | `10.x.x.x` or `minio.internal.<your-domain>` | ✅ Yes |
| `MINIO_PORT` | MinIO API port | `9000` | ⚠️ Optional (default: 9000) |
| `MINIO_ROOT_USER` | MinIO admin username | `minioadmin` | ✅ Yes |
| `MINIO_ROOT_PASSWORD` | MinIO admin password | `MinIO@Secure2024!` | ✅ Yes |
| `MINIO_BUCKET_NAME` | MinIO bucket name | `scholarship-documents` | ⚠️ Optional (default: scholarship-documents) |

**How to obtain:**
- Set during DB VM initial setup (Section 4.4 of installation manual: `.env.db`)
- Check `MINIO_ROOT_USER`, `MINIO_ROOT_PASSWORD` in DB VM's `.env.db` file

**Password Requirements:**
- ✅ Minimum 16 characters
- ✅ Include uppercase, lowercase, numbers, and symbols
- ❌ Avoid: `minioadmin`, `password123`

**Important Notes:**
- ⚠️ `MINIO_HOST` is typically the **same as `DB_HOST`** (same VM)
- ⚠️ Bucket will be created automatically if it doesn't exist
- ⚠️ For internal network, use private IP (e.g., `10.0.1.100`)

---

### Application Secrets

These secrets are used by the FastAPI backend application.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `SECRET_KEY` | JWT signing secret key | `a1b2c3d4e5f6...` (64+ hex chars) | ✅ Yes |
| `REDIS_PASSWORD` | Redis cache password | `RedisCache@2024Secure!` | ✅ Yes |

**How to generate:**

```bash
# Generate SECRET_KEY (64 random hex characters)
openssl rand -hex 32

# Generate REDIS_PASSWORD (strong random password)
openssl rand -base64 24
```

**Password Requirements:**
- `SECRET_KEY`: ✅ Minimum 32 characters (64 recommended)
- `REDIS_PASSWORD`: ✅ Minimum 16 characters

**Security Notes:**
- 🔐 `SECRET_KEY` is used for JWT token signing - **NEVER expose or reuse**
- 🔐 If `SECRET_KEY` is compromised, all existing JWT tokens will be invalidated when changed
- 🔐 Rotate `SECRET_KEY` every 90 days (will require all users to re-login)

---

### PII Encryption Secrets (REQUIRED — go-live blocker P4)

The backend encrypts 身分證字號 (`std_pid`) at rest with AES-256-GCM. Missing
or malformed keys hard-fail the encrypt migration and every PII read.

| Secret | Description | Example | Required |
|--------|-------------|---------|----------|
| `PII_ENCRYPTION_KEYS` | JSON map of {version: base64url 32-byte key} | `{"v1":"<key>"}` | ✅ Yes |
| `PII_ENCRYPTION_ACTIVE_VERSION` | Version used for NEW encryptions | `v1` | ✅ Yes |

```bash
# Generate a key
python -c 'import os,base64;print(base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode())'
gh secret set PII_ENCRYPTION_KEYS --body '{"v1":"<KEY>"}'
gh secret set PII_ENCRYPTION_ACTIVE_VERSION --body 'v1'
```

- 🔐 **Losing a key version = the PII encrypted with it is permanently
  unreadable.** Keep an offline copy in the team's secure vault.
- 🔐 Old versions stay in the map until the retention period of the LAST row
  (and backup) encrypted with them expires — see
  `docs/security/pii-key-retention-runbook.md` for the rotation procedure.
- 🔐 Production keys MUST differ from staging keys.

### Super Admin Secret (REQUIRED)

| Secret | Description | Example | Required |
|--------|-------------|---------|----------|
| `SUPER_ADMIN_NYCU_ID` | NYCU ID granted super_admin at Portal SSO login | `E12345` | ✅ Yes |

Without it the in-code default `super_admin` applies and no real 承辦人
account can ever elevate.

### Email Configuration Secrets

These secrets configure SMTP for sending system emails (notifications, password resets, etc.).

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `SMTP_HOST` | SMTP server hostname | `smtp.<your-domain>` or `smtp.gmail.com` | ✅ Yes |
| `SMTP_PORT` | SMTP server port | `587` (TLS) or `465` (SSL) | ⚠️ Optional (default: 587) |
| `SMTP_USER` | SMTP authentication username | `scholarship@<your-domain>` | ✅ Yes |
| `SMTP_PASSWORD` | SMTP authentication password | `EmailP@ss2024!` | ✅ Yes |
| `EMAIL_FROM` | "From" email address | `scholarship@<your-domain>` | ✅ Yes |
| `EMAIL_FROM_NAME` | "From" display name | `NYCU Scholarship System` | ⚠️ Optional |

**Common SMTP Providers:**

| Provider | SMTP_HOST | SMTP_PORT | Notes |
|----------|-----------|-----------|-------|
| Gmail | `smtp.gmail.com` | `587` | Requires App Password (not account password) |
| Office 365 | `smtp.office365.com` | `587` | - |
| 校內 Mail | `smtp.<your-domain>` | `587` | Contact IT for credentials |

**For Gmail:**
1. Enable 2-Factor Authentication on your Google account
2. Generate an App Password: https://myaccount.google.com/apppasswords
3. Use the App Password as `SMTP_PASSWORD`

**Testing SMTP:**
```bash
# Test SMTP connection with openssl
openssl s_client -starttls smtp -connect smtp.<your-domain>:587
```

---

### SSO Configuration Secrets

These secrets configure Portal SSO integration for user authentication.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `PORTAL_JWT_SERVER_URL` | Portal SSO JWT verification endpoint | `https://portal.<your-domain>/api/auth` | ✅ Yes |

**How to obtain:**
- Contact NYCU IT Services for Portal SSO endpoint URL
- The endpoint should return JWT tokens for authentication verification

**Important Notes:**
- ⚠️ Must start with `https://` (production) or `http://` (development only)
- ⚠️ In production, `PORTAL_SSO_ENABLED` will be set to `true`
- ⚠️ `PORTAL_TEST_MODE` will be set to `false` in production

---

### Student API Configuration Secrets

These secrets configure integration with NYCU Student Information System (SIS) API.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `STUDENT_API_BASE_URL` | Student API base URL | `https://api.sis.<your-domain>` | ✅ Yes |

> The student API no longer requires authentication; `STUDENT_API_ACCOUNT` and `STUDENT_API_HMAC_KEY` are no longer used.

**How to obtain:**
- Contact NYCU Academic Affairs Office or IT Services
- Request API access for Scholarship System
- They will provide:
  - API endpoint URL
  - Account credentials

**API Purpose:**
- Fetches student basic information (API 1: `ScholarshipStudent`)
- Fetches student semester data (API 2: `ScholarshipStudentTerm`)
- Data is cached in `student_data` field of applications

**Important Notes:**
- ⚠️ In production, `STUDENT_API_ENABLED` will be set to `true`

---

### General Configuration Secrets

These secrets configure general application settings.

> **ℹ️ Validation**: These secrets are validated during `.env` file generation (Step 5). Not required for Docker installation.

| Secret Name | Description | Example Value | Required |
|-------------|-------------|---------------|----------|
| `DOMAIN` | Production domain name | `<your-production-domain>` | ✅ Yes |
| `CORS_ORIGINS` | Allowed CORS origins (comma-separated) | `https://<production-domain>` | ✅ Yes |

**DOMAIN:**
- Must match DNS A record pointing to AP VM
- Used for:
  - Frontend `NEXT_PUBLIC_API_URL`
  - Backend `FRONTEND_URL`
  - SSL certificate validation

**CORS_ORIGINS:**
- List of allowed origins for Cross-Origin Resource Sharing
- Format: Comma-separated URLs (no trailing slash)
- Example: `https://<production-domain>,https://<alt-domain>`
- ⚠️ In production, never use `*` (allow all origins)

---

## How to Add Secrets to GitHub

### Using GitHub Web Interface

1. Go to your **production repository** on GitHub
2. Click **Settings** (top navigation bar)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click the **New repository secret** button (green button)
5. Enter the **Name** (e.g., `DB_PASSWORD`)
6. Enter the **Secret** value
7. Click **Add secret**

![GitHub Secrets UI](https://docs.github.com/assets/cb-27664/images/help/settings/actions-secrets-new.png)

### Using GitHub CLI (`gh`)

```bash
# Set a secret using gh CLI
gh secret set DB_PASSWORD -b "your_secure_password"

# Set secret from file
gh secret set NYCU_EMP_KEY_HEX < emp_key.txt

# Set secret with prompt (hides input)
gh secret set SECRET_KEY

# List all configured secrets (won't show values)
gh secret list
```

### Batch Import Secrets

If you have many secrets, you can script the import:

```bash
#!/bin/bash
# secrets.sh - Batch import secrets to GitHub

# Database secrets
gh secret set DB_HOST -b "10.0.1.100"
gh secret set DB_PORT -b "5432"
gh secret set DB_USER -b "scholarship_user"
gh secret set DB_PASSWORD  # Will prompt for value
gh secret set DB_NAME -b "scholarship_db"

# Database VM SSH access (for offline image transfer)
gh secret set DB_VM_USER -b "ubuntu"
gh secret set DB_VM_SSH_KEY < ~/.ssh/db_vm_deploy  # From file

# MinIO secrets
gh secret set MINIO_HOST -b "10.0.1.100"
gh secret set MINIO_PORT -b "9000"
gh secret set MINIO_ROOT_USER -b "minioadmin"
gh secret set MINIO_ROOT_PASSWORD  # Will prompt

# Application secrets
gh secret set SECRET_KEY  # Will prompt
gh secret set REDIS_PASSWORD  # Will prompt

# Email secrets
gh secret set SMTP_HOST -b "smtp.<your-domain>"
gh secret set SMTP_PORT -b "587"
gh secret set SMTP_USER -b "scholarship@<your-domain>"
gh secret set SMTP_PASSWORD  # Will prompt
gh secret set EMAIL_FROM -b "scholarship@<your-domain>"
gh secret set EMAIL_FROM_NAME -b "NYCU Scholarship System"

# SSO secrets
gh secret set PORTAL_JWT_SERVER_URL -b "https://portal.<your-domain>/api/auth"

# Student API secrets
gh secret set STUDENT_API_BASE_URL -b "https://api.sis.<your-domain>"

# General configuration
gh secret set DOMAIN -b "<production-domain>"
gh secret set CORS_ORIGINS -b "https://<production-domain>"

echo "✅ All secrets configured!"
echo "Verify with: gh secret list"
```

**Make script executable and run:**
```bash
chmod +x secrets.sh
./secrets.sh
```

---

## Security Best Practices

### Password Guidelines

✅ **DO:**
- Use passwords with 16+ characters
- Include uppercase, lowercase, numbers, and symbols
- Use a password manager (e.g., 1Password, Bitwarden)
- Generate random passwords with `openssl rand -base64 24`
- Rotate secrets every 90 days

❌ **DON'T:**
- Reuse passwords across systems
- Use dictionary words or common passwords
- Share secrets via email or chat
- Commit secrets to git (even in private repos)
- Use default passwords (`postgres`, `admin`, etc.)

### Secret Management

🔐 **Best Practices:**

1. **Least Privilege**: Only give GitHub Secrets access to team members who need it
2. **Audit Trail**: Review secret access logs regularly (Settings → Actions → Logs)
3. **Rotation Schedule**: Change passwords every 90 days
4. **Backup**: Store secrets in a secure password manager (separate from GitHub)
5. **Documentation**: Document when secrets were last rotated

### Secret Rotation Checklist

When rotating secrets:

- [ ] Generate new secure password/key
- [ ] Update GitHub Secret in production repository
- [ ] Update corresponding value on target system (DB VM, external services)
- [ ] Run `setting-env.yml` workflow with action `setup` to regenerate `.env.prod`
- [ ] Restart affected services: `docker compose -f docker-compose.prod.yml restart`
- [ ] Verify services are working: `docker compose ps`
- [ ] Document rotation date in password manager

**Example: Rotating DB_PASSWORD**

```bash
# 1. Generate new password
NEW_PASSWORD=$(openssl rand -base64 24)

# 2. Update GitHub Secret
gh secret set DB_PASSWORD -b "$NEW_PASSWORD"

# 3. Update PostgreSQL password on DB VM
ssh db-vm
docker compose exec postgres psql -U postgres -c "ALTER USER scholarship_user PASSWORD '$NEW_PASSWORD';"

# 4. Re-run setup workflow (updates .env.prod on AP VM)
gh workflow run setting-env.yml -f action=setup

# 5. Restart backend service
docker compose -f docker-compose.prod.yml restart backend

# 6. Verify
docker compose logs backend | grep -i "database"
```

---

## Validating Secrets

### Using the Workflow

The `setting-env.yml` workflow provides automatic validation:

```bash
# Trigger validation from GitHub CLI
gh workflow run setting-env.yml -f action=validate

# Monitor workflow execution
gh run watch

# View detailed logs
gh run view --log
```

**What the workflow checks:**
- ✅ All required secrets are set (not empty)
- ✅ Password length requirements (16+ chars)
- ✅ URL format validation (http:// or https://)
- ✅ Port number format validation
- ✅ Network connectivity to DB VM (PostgreSQL, MinIO)

### Manual Validation

**Check secrets are configured:**
```bash
gh secret list
```

**Test database connection from AP VM:**
```bash
# Test PostgreSQL connectivity
PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p 5432 -U "$DB_USER" -d "$DB_NAME" -c "SELECT version();"

# Test MinIO connectivity
curl -I http://$MINIO_HOST:9000/health
```

**Test SMTP:**
```bash
# Install swaks (Swiss Army Knife for SMTP)
sudo apt-get install swaks

# Send test email
swaks --to test@example.com \
  --from "$EMAIL_FROM" \
  --server "$SMTP_HOST:$SMTP_PORT" \
  --auth LOGIN \
  --auth-user "$SMTP_USER" \
  --auth-password "$SMTP_PASSWORD" \
  --tls \
  --header "Subject: SMTP Test" \
  --body "Test email from scholarship system"
```

---

## Troubleshooting

### Secret Not Found Error

**Error:**
```
Error: Secret DB_PASSWORD not found
```

**Solution:**
1. Verify secret is created: `gh secret list`
2. Check secret name spelling (case-sensitive)
3. Ensure you're in the correct repository
4. Add missing secret: `gh secret set DB_PASSWORD`

---

### Password Too Short Warning

**Warning:**
```
⚠️ WARNING: DB_PASSWORD is shorter than 16 characters
```

**Solution:**
```bash
# Generate strong password
NEW_PASSWORD=$(openssl rand -base64 24)

# Update secret
gh secret set DB_PASSWORD -b "$NEW_PASSWORD"

# Update on target system (DB VM)
ssh db-vm
docker compose exec postgres psql -U postgres -c "ALTER USER scholarship_user PASSWORD '$NEW_PASSWORD';"
```

---

### Invalid URL Format

**Error:**
```
❌ ERROR: PORTAL_JWT_SERVER_URL must start with http:// or https://
```

**Solution:**
```bash
# Correct format (include protocol)
gh secret set PORTAL_JWT_SERVER_URL -b "https://portal.<your-domain>/api/auth"

# ❌ Wrong: portal.<your-domain>/api/auth
# ✅ Right: https://portal.<your-domain>/api/auth
```

---

### Database Connection Failed

**Error:**
```
❌ ERROR: Cannot reach PostgreSQL on 10.0.1.100:5432
```

**Solution:**

1. **Check DB VM is running:**
   ```bash
   ssh db-vm
   docker compose -f docker-compose.prod-db.yml ps
   ```

2. **Check PostgreSQL is listening:**
   ```bash
   ssh db-vm
   docker compose exec postgres pg_isready -U scholarship_user
   ```

3. **Check firewall allows connection from AP VM:**
   ```bash
   # On AP VM, test connectivity
   telnet $DB_HOST 5432
   # or
   nc -zv $DB_HOST 5432
   ```

4. **Verify DB_HOST secret is correct:**
   ```bash
   # Should be DB VM's IP or hostname
   gh secret set DB_HOST -b "10.0.1.100"
   ```

5. **Check PostgreSQL allows remote connections:**
   ```bash
   # On DB VM, check postgresql.conf
   docker compose exec postgres grep listen_addresses /var/lib/postgresql/data/postgresql.conf
   # Should be: listen_addresses = '*'

   # Check pg_hba.conf allows AP VM
   docker compose exec postgres grep -v "^#" /var/lib/postgresql/data/pg_hba.conf | grep host
   # Should include: host all all 0.0.0.0/0 md5
   ```

---

### MinIO Connection Failed

**Error:**
```
❌ ERROR: Cannot reach MinIO on 10.0.1.100:9000
```

**Solution:**

1. **Check MinIO is running:**
   ```bash
   ssh db-vm
   docker compose -f docker-compose.prod-db.yml ps minio
   ```

2. **Check MinIO health:**
   ```bash
   ssh db-vm
   curl http://localhost:9000/health
   ```

3. **Verify MINIO_HOST secret:**
   ```bash
   # Should match DB_HOST (same VM)
   gh secret set MINIO_HOST -b "10.0.1.100"
   ```

4. **Test from AP VM:**
   ```bash
   # On AP VM
   curl http://$MINIO_HOST:9000/health
   ```

---

### SMTP Authentication Failed

**Error:**
```
❌ ERROR: SMTP authentication failed
```

**Solution:**

1. **Verify SMTP credentials:**
   ```bash
   # Test SMTP login
   swaks --to test@example.com \
     --from "$EMAIL_FROM" \
     --server "$SMTP_HOST:$SMTP_PORT" \
     --auth LOGIN \
     --auth-user "$SMTP_USER" \
     --auth-password "$SMTP_PASSWORD" \
     --tls \
     --quit-after RCPT
   ```

2. **For Gmail, use App Password:**
   - Enable 2FA on Google account
   - Generate App Password: https://myaccount.google.com/apppasswords
   - Use App Password (not account password)

3. **Check SMTP port:**
   ```bash
   # Port 587 (TLS/STARTTLS) - Most common
   gh secret set SMTP_PORT -b "587"

   # Port 465 (SSL) - Alternative
   gh secret set SMTP_PORT -b "465"

   # Port 25 (Unencrypted) - Not recommended
   ```

---

## Quick Reference

### Complete Secret Checklist

Use this checklist to verify all secrets are configured:

```bash
# Run this script to check all secrets
#!/bin/bash

REQUIRED_SECRETS=(
  "DB_HOST"
  "DB_USER"
  "DB_PASSWORD"
  "DB_NAME"
  "DB_VM_USER"
  "DB_VM_SSH_KEY"
  "MINIO_HOST"
  "MINIO_ROOT_USER"
  "MINIO_ROOT_PASSWORD"
  "SECRET_KEY"
  "REDIS_PASSWORD"
  "SMTP_HOST"
  "SMTP_USER"
  "SMTP_PASSWORD"
  "EMAIL_FROM"
  "PORTAL_JWT_SERVER_URL"
  "STUDENT_API_BASE_URL"
  "DOMAIN"
  "CORS_ORIGINS"
)

echo "Checking GitHub Secrets configuration..."
CONFIGURED_SECRETS=$(gh secret list --json name -q '.[].name')

for SECRET in "${REQUIRED_SECRETS[@]}"; do
  if echo "$CONFIGURED_SECRETS" | grep -q "^$SECRET$"; then
    echo "✅ $SECRET"
  else
    echo "❌ $SECRET (MISSING)"
  fi
done
```

---

## Support

For assistance with secrets configuration:

1. **Workflow Issues**: Check workflow logs at GitHub Actions → setting-env.yml
2. **Secret Configuration**: Review this guide and troubleshooting section
3. **System Access**: Contact NYCU IT Services for:
   - Portal SSO endpoint
   - Student API credentials
   - SMTP credentials
   - Network/firewall issues

---

**Last Updated**: 2025-10-30

**Related Documentation**:
- [Installation Manual](./IT-BACKUP-TRANSFER-GUIDE.md)
- [Production Workflows README](./README.md)
- [Deploy to Test Workflow](./deploy-test.yml)
- [Deploy to Production Workflow](./deploy-production.yml)
- [Deploy Stack (reusable)](./deploy-stack.yml)
- [GitHub Actions Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
