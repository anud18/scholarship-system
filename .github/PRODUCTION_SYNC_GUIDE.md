# Production Repository Sync Guide

## 📋 Overview

This workflow automatically mirrors the development repository to a separate private production repository while **excluding development workflows**. This allows the production repository to maintain its own independent deployment and monitoring workflows.

## 🎯 Architecture

```
┌─────────────────────────────────────────┐
│  Development Repo (Public/This Repo)    │
│  • CI/CD workflows                      │
│  • Testing workflows                    │
│  • Development tools                    │
└──────────────┬──────────────────────────┘
               │
               │  Sync (main branch)
               │  • Remove .github/workflows/
               │  • Keep all code
               ▼
┌─────────────────────────────────────────┐
│  Production Repo (Private)              │
│  • Deployment workflows ←  Independent  │
│  • Monitoring workflows                 │
│  • Production configs                   │
└─────────────────────────────────────────┘
```

## 🚀 Quick Setup

### Step 1: Create Production Repository

1. Create a new private repository on GitHub
   - Name: `scholarship-system-production` (or your preferred name)
   - Visibility: **Private**
   - Don't initialize with README (we'll push from source)

### Step 2: Create Personal Access Token

1. Go to **GitHub Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)**

2. Click **"Generate new token (classic)"**

3. Configure the token:
   - **Note**: `Production Sync Token`
   - **Expiration**: 90 days (recommended) or based on your security policy
   - **Select scopes**:
     - ✅ **`repo`** (Full control of private repositories)

4. Click **"Generate token"**

5. **Copy the token immediately** (you won't be able to see it again)

### Step 3: Configure Repository Secrets

In **this repository** (development repo):

1. Go to **Settings** → **Secrets and variables** → **Actions**

2. Click **"New repository secret"**

3. Add the following secrets:

#### Required Secrets

| Secret Name | Value | Description |
|-------------|-------|-------------|
| `PRODUCTION_SYNC_PAT` | `ghp_xxxxxxxxxxxx` | Personal Access Token from Step 2 |
| `PRODUCTION_REPO` | `owner/repo-name` | Full repo path, e.g., `jotpalch/scholarship-production` |

#### Optional Secrets

| Secret Name | Value | Default | Description |
|-------------|-------|---------|-------------|
| `PRODUCTION_BRANCH` | `main` | `main` | Target branch in production repo |

### Step 4: Initialize Production Repository

You have two options:

#### Option A: Let the workflow create the first commit

1. The workflow will automatically push on the next commit to `main`
2. Production repo will be initialized with the first sync

#### Option B: Manually initialize (Recommended)

```bash
# Clone the production repo
git clone https://github.com/your-org/scholarship-system-production.git
cd scholarship-system-production

# Create initial commit with production workflows
mkdir -p .github/workflows

# Add your production deployment workflow (see examples below)
cat > .github/workflows/deploy.yml <<'EOF'
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy:
    name: Deploy Application
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Deploy
        run: |
          echo "Deploying to production..."
          # Add your deployment steps here
EOF

# Commit and push
git add .github/workflows/
git commit -m "Add production deployment workflow"
git push origin main
```

## 📖 How It Works

### Automatic Sync (Recommended)

Every time you push to the `main` branch in the development repo:

1. ✅ Workflow detects the push
2. ✅ Creates `production-mirror` branch
3. ✅ Removes all files in `.github/workflows/`
4. ✅ Pushes to production repo
5. ✅ Production workflows remain untouched

```bash
# Normal development workflow
git add .
git commit -m "feat: add new feature"
git push origin main

# Automatic sync happens in background
# Check Actions tab to see sync status
```

### Manual Sync

Trigger a sync manually from GitHub UI:

1. Go to **Actions** tab
2. Select **"Mirror to Production Repo"** workflow
3. Click **"Run workflow"**
4. Choose options:
   - Branch: `main` (or your main branch)
   - Force push: ☐ (usually not needed)
5. Click **"Run workflow"**

## 🔧 Production Repository Management

### Maintaining Independent Workflows

The production repository should have its own workflows that are **never synced from development**:

#### Example Directory Structure

```
production-repo/
├── frontend/           # ← Synced from dev
├── backend/            # ← Synced from dev
├── docker-compose.yml  # ← Synced from dev
├── README.md           # ← Synced from dev
└── .github/
    └── workflows/
        ├── deploy.yml              # ← Production only
        ├── health-check.yml        # ← Production only
        ├── backup.yml              # ← Production only
        └── rollback.yml            # ← Production only
```

### Production Workflow Examples

See the **Examples** section below for complete workflow templates.

## 🔍 Verification

### Check Sync Status

1. **View Actions Tab**
   - Go to Actions → "Mirror to Production Repo"
   - Check the latest run status

2. **Review Mirror Branch**
   - View `production-mirror` branch in source repo
   - This branch shows exactly what was pushed to production

3. **Verify Production Repo**
   - Check production repo has latest code
   - Verify production workflows still exist
   - Confirm no development workflows present

### Common Checks

```bash
# In production repo
git clone https://github.com/your-org/production-repo.git
cd production-repo

# Check workflows
ls .github/workflows/

# Should see ONLY production workflows, NOT:
# - ci.yml (from dev)
# - dev-workflow.yml (from dev)
# - security.yml (from dev)
# etc.

# Verify latest code
git log --oneline -5

# Should see commits from development repo
```

## 🛡️ Security Best Practices

### 1. Token Security

- ✅ Use tokens with **minimum required permissions** (`repo` scope only)
- ✅ Set **expiration dates** on tokens
- ✅ **Rotate tokens regularly** (every 90 days recommended)
- ✅ **Delete tokens** when no longer needed
- ❌ Never commit tokens to git
- ❌ Don't share tokens across multiple workflows

### 2. Repository Access

```yaml
# Limit workflow runs to specific repository
jobs:
  mirror-to-production:
    if: github.repository == 'owner/repo-name'
```

### 3. Branch Protection

Configure branch protection on production repo:

1. Go to Production Repo → Settings → Branches
2. Add rule for `main` branch:
   - ☐ Require pull request reviews (optional, may break sync)
   - ✅ Require status checks (optional)
   - ✅ Require conversation resolution before merging (optional)
   - ☐ Include administrators (recommended)

**Note**: If you enable "Require pull request reviews", the automatic sync won't work (force push will be blocked). Consider using a different branch for sync (e.g., `sync/main`) and manually merging to `main`.

### 4. Audit Trail

Monitor sync activity:

```bash
# Check workflow runs
gh run list --workflow=mirror-to-production.yml --limit=10

# View specific run
gh run view <run-id>
```

## 🔧 Troubleshooting

### Issue: "PRODUCTION_SYNC_PAT not configured"

**Cause**: Secret not set or named incorrectly

**Solution**:
1. Verify secret name is exactly `PRODUCTION_SYNC_PAT` (case-sensitive)
2. Check secret is set in **source repo** (not production repo)
3. Ensure token hasn't expired

### Issue: "Failed to push to production repository"

**Cause**: Permission denied or repository not found

**Solutions**:

1. **Check PAT permissions**:
   ```bash
   curl -H "Authorization: token YOUR_PAT" \
     https://api.github.com/repos/owner/production-repo
   ```
   Should return repository details, not 404

2. **Verify PRODUCTION_REPO format**:
   - Correct: `owner/repo-name`
   - Wrong: `https://github.com/owner/repo-name`
   - Wrong: `owner/repo-name.git`

3. **Check repository visibility**:
   - Ensure PAT has access to private repos if production is private

### Issue: "Production workflows were removed"

**Cause**: Production workflows were in an old commit before sync started

**Solution**:

1. Restore production workflows manually:
   ```bash
   cd production-repo
   git checkout <old-commit-with-workflows> -- .github/workflows/
   git commit -m "Restore production workflows"
   git push
   ```

2. Future syncs will not affect these workflows (they're in separate commits)

### Issue: "Merge conflicts" or "Force push required"

**Cause**: Manual changes made to production repo

**Solution**:

- Production repo should be **read-only** from sync perspective
- All code changes should be made in development repo
- Only modify workflows in production repo
- If conflicts occur:
  1. Use manual trigger with "force push" enabled
  2. Review changes carefully before forcing

## 📊 Monitoring

### Workflow Success Rate

Check workflow reliability:

```bash
# Get last 20 runs
gh run list -w mirror-to-production.yml -L 20 --json status,conclusion

# Count successes
gh run list -w mirror-to-production.yml -L 100 --json conclusion | \
  jq '[.[] | select(.conclusion == "success")] | length'
```

### Sync Lag

Monitor delay between dev commit and production sync:

1. Check Actions tab for workflow run times
2. Typical sync should complete in < 2 minutes
3. If consistently slow, review repository size

### Example: Set up Alerts

```yaml
# In production repo: .github/workflows/health-check.yml
name: Health Check

on:
  schedule:
    - cron: '0 */6 * * *'  # Every 6 hours

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Check sync freshness
        run: |
          LAST_COMMIT_AGE=$(git log -1 --format=%ct)
          NOW=$(date +%s)
          AGE_HOURS=$(( (NOW - LAST_COMMIT_AGE) / 3600 ))

          echo "Last sync: $AGE_HOURS hours ago"

          if [ $AGE_HOURS -gt 48 ]; then
            echo "::error::Production repo not synced in >48 hours"
            exit 1
          fi
```

## 📚 Examples

### Example 1: Production Deployment Workflow

```yaml
# production-repo/.github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      environment:
        description: 'Deployment environment'
        required: true
        type: choice
        options:
          - production
          - staging

jobs:
  deploy:
    name: Deploy Application
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'

      - name: Build frontend
        run: |
          cd frontend
          npm ci
          npm run build

      - name: Deploy to server
        env:
          SSH_PRIVATE_KEY: ${{ secrets.PRODUCTION_SSH_KEY }}
          SERVER_HOST: ${{ secrets.PRODUCTION_SERVER }}
        run: |
          echo "Deploying to $SERVER_HOST..."
          # Your deployment commands here
```

### Example 2: Health Check Workflow

```yaml
# production-repo/.github/workflows/health-check.yml
name: Production Health Check

on:
  schedule:
    - cron: '*/30 * * * *'  # Every 30 minutes
  workflow_dispatch:

jobs:
  check:
    name: Check Application Health
    runs-on: ubuntu-latest

    steps:
      - name: Check API health
        run: |
          RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
            https://api.production.example.com/health)

          if [ "$RESPONSE" != "200" ]; then
            echo "::error::API health check failed (HTTP $RESPONSE)"
            exit 1
          fi

          echo "✅ API is healthy"

      - name: Check frontend
        run: |
          RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
            https://production.example.com)

          if [ "$RESPONSE" != "200" ]; then
            echo "::error::Frontend health check failed (HTTP $RESPONSE)"
            exit 1
          fi

          echo "✅ Frontend is healthy"

      - name: Notify on failure
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: '🚨 Production Health Check Failed',
              body: 'Production application health check has failed. Please investigate immediately.',
              labels: ['production', 'urgent']
            })
```

### Example 3: Backup Workflow

```yaml
# production-repo/.github/workflows/backup.yml
name: Backup Production Data

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC
  workflow_dispatch:

jobs:
  backup:
    name: Create Backup
    runs-on: ubuntu-latest

    steps:
      - name: Backup database
        env:
          DB_HOST: ${{ secrets.PRODUCTION_DB_HOST }}
          DB_NAME: ${{ secrets.PRODUCTION_DB_NAME }}
          AWS_ACCESS_KEY_ID: ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
        run: |
          BACKUP_FILE="backup-$(date +%Y%m%d-%H%M%S).sql"

          # Create backup
          pg_dump -h "$DB_HOST" "$DB_NAME" > "$BACKUP_FILE"

          # Upload to S3
          aws s3 cp "$BACKUP_FILE" "s3://production-backups/$BACKUP_FILE"

          echo "✅ Backup completed: $BACKUP_FILE"
```

## 🔄 Migration Guide

### Migrating Existing Production Setup

If you already have a production repository:

1. **Backup current production repo**:
   ```bash
   git clone https://github.com/org/production-repo.git production-backup
   ```

2. **Extract production-specific files**:
   ```bash
   cd production-backup
   cp -r .github/workflows /tmp/production-workflows
   # Copy any other production-specific configs
   ```

3. **Clear production repo** (optional):
   ```bash
   # If starting fresh
   git rm -rf .
   git commit -m "Clear for sync from development"
   git push --force
   ```

4. **Configure sync** (follow Quick Setup above)

5. **Restore production workflows**:
   ```bash
   cp -r /tmp/production-workflows .github/workflows
   git add .github/workflows
   git commit -m "Restore production workflows"
   git push
   ```

## 📞 Support

### Getting Help

1. **Check workflow logs**: Actions tab → Latest run
2. **Review this guide**: Common issues covered above
3. **Check GitHub Status**: https://www.githubstatus.com/

### Useful Commands

```bash
# View workflow file
cat .github/workflows/mirror-to-production.yml

# Test locally (validate YAML)
npx yaml-lint .github/workflows/mirror-to-production.yml

# Check secrets (won't show values, just names)
gh secret list

# Manual test
gh workflow run mirror-to-production.yml
```

## 📄 License

This workflow is part of the scholarship-system project and follows the same license.
