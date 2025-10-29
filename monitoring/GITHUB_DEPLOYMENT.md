# GitHub Actions Deployment Guide

Complete guide for deploying the monitoring infrastructure using GitHub Actions with self-hosted runner.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Required GitHub Secrets](#required-github-secrets)
- [Self-Hosted Runner Setup](#self-hosted-runner-setup)
- [Deployment Workflow](#deployment-workflow)
- [Manual Deployment](#manual-deployment)
- [Troubleshooting](#troubleshooting)

## Overview

The monitoring stack is deployed using GitHub Actions workflows that:
1. Deploy the central monitoring server (Grafana, Loki, Prometheus, AlertManager) **on Staging AP-VM**
2. Deploy monitoring agents on Staging AP-VM (localhost)
3. Deploy monitoring agents on Staging DB-VM (via SSH)
4. Perform health checks to ensure all services are running
5. Verify Prometheus targets are UP and collecting metrics

**Workflow File**: `.github/workflows/deploy-monitoring-stack.yml`

**Grafana Access**: After deployment, access Grafana at `https://ss.test.nycu.edu.tw/monitoring/` (via nginx reverse proxy on staging AP-VM)

## Architecture

### Deployment Model

```
┌─────────────────────────────────────────────────────────┐
│  Staging AP-VM (localhost)                              │
│  ┌───────────────────────────────────────────────────┐  │
│  │  GitHub Actions Self-Hosted Runner                │  │
│  └───────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Monitoring Stack                                 │  │
│  │  - Grafana, Prometheus, Loki, AlertManager        │  │
│  │  - Grafana Alloy (staging-ap-vm.alloy)            │  │
│  │  - Node Exporter, cAdvisor, Nginx Exporter        │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                          │
                          │ SSH
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Staging DB-VM (remote)                                 │
│  ┌───────────────────────────────────────────────────┐  │
│  │  Monitoring Agents                                │  │
│  │  - Grafana Alloy (staging-db-vm.alloy)            │  │
│  │  - Postgres Exporter, Redis Exporter, MinIO      │  │
│  └───────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

**Key Points**:
- **Self-hosted runner**: GitHub Actions workflow runs ON Staging AP-VM
- **Monitoring server**: Co-located on Staging AP-VM (localhost)
- **No SSH for AP-VM**: All operations on AP-VM use local commands
- **SSH only for DB-VM**: Remote deployment to Staging DB-VM

## Required GitHub Secrets

Configure these in GitHub repository settings → Secrets and variables → Actions → Environment secrets (staging):

### Core Monitoring Secrets (Required)

| Secret Name | Description | Example | Security Notes |
|-------------|-------------|---------|----------------|
| `GRAFANA_ADMIN_USER` | Grafana admin username | `admin` | Avoid using "admin" in production |
| `GRAFANA_ADMIN_PASSWORD` | Grafana admin password | `SuperSecurePassword123!` | Min 16 chars, mixed case, numbers, symbols |
| `GRAFANA_SECRET_KEY` | Grafana signing key for cookies | `openssl rand -hex 32` | **REQUIRED**: Generate unique key, never reuse |
| `GRAFANA_ROOT_URL` | Grafana public URL (via nginx reverse proxy) | `https://ss.test.nycu.edu.tw/monitoring/` | Must match nginx proxy path |

**⚠️ Security Alert**:
- `GRAFANA_SECRET_KEY` is **REQUIRED** and must be unique
- Generate with: `openssl rand -hex 32`
- Never commit secret keys to repository
- Rotate credentials every 90 days

### Database VM Secrets (Required)

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `STAGING_DB_HOST` | Staging database VM hostname or IP | `10.0.2.5` or `staging-db.example.com` |
| `STAGING_DB_USER` | SSH username for staging DB-VM | `ubuntu` |
| `STAGING_DB_SSH_KEY` | Private SSH key for staging DB-VM | `-----BEGIN RSA PRIVATE KEY-----...` |

**Note**: The workflow is configured to use SSH port **8822** for DB-VM connections (not the default port 22).

### Alert Configuration Secrets (Optional)

| Secret Name | Description | Required |
|-------------|-------------|----------|
| `ALERT_EMAIL_FROM` | Email sender address for alerts | No |
| `ALERT_SMTP_HOST` | SMTP server hostname | No |
| `ALERT_SMTP_PORT` | SMTP server port | No |
| `ALERT_SMTP_USER` | SMTP username | No |
| `ALERT_SMTP_PASSWORD` | SMTP password | No |
| `ALERT_SLACK_WEBHOOK` | Slack webhook URL for alerts | No |

### Secrets Summary

**Total Required Secrets**: 7 (4 core + 3 DB-VM)

**Removed from Previous Design**:
- ❌ `MONITORING_SERVER_*` secrets (no longer needed - monitoring server is localhost)
- ❌ `STAGING_AP_*` secrets (no longer needed - AP-VM is localhost)
- ❌ `PROD_*` secrets (production deployment not in this workflow)

## Self-Hosted Runner Setup

### Prerequisites

The GitHub Actions runner must be installed on Staging AP-VM. Follow these steps:

### 1. Install GitHub Actions Runner

```bash
# SSH to Staging AP-VM
ssh user@staging-ap-vm

# Create runner directory
mkdir -p ~/actions-runner && cd ~/actions-runner

# Download latest runner
curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
  https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz

# Extract
tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz

# Configure runner
./config.sh --url https://github.com/YOUR_ORG/YOUR_REPO --token YOUR_TOKEN

# Install as service
sudo ./svc.sh install
sudo ./svc.sh start
```

### 2. Verify Runner Installation

```bash
# Check runner status
sudo ./svc.sh status

# View runner logs
journalctl -u actions.runner.* -f
```

### 3. Verify in GitHub

1. Go to repository settings → Actions → Runners
2. You should see your self-hosted runner listed as "Idle"
3. Label should show "self-hosted"

## Deployment Workflow

### Automatic Deployment

The workflow automatically triggers when:
- Changes are pushed to `main` branch in the `monitoring/` directory
- Changes are made to the workflow file itself

**Automatic deployments deploy to Staging environment only.**

### Manual Deployment

Trigger manual deployment:

1. Go to GitHub Actions tab in your repository
2. Select "Deploy Monitoring Stack" workflow
3. Click "Run workflow"
4. Click "Run workflow" to confirm

### Deployment Steps

The workflow performs these steps in 2 jobs:

#### Job 1: Deploy Monitoring Server (Staging AP-VM)

**Runs on**: Self-hosted runner (localhost operations)

1. **Checkout code**: Clone repository to runner workspace
2. **Create directories**: Create `/opt/scholarship/monitoring` with proper permissions
3. **Deploy configuration**: Copy monitoring configs to `/opt/scholarship/monitoring/`
4. **Set environment variables**: Create `.env.monitoring` from GitHub secrets
5. **Pull images**: Update to latest Docker images
6. **Deploy stack**: Start monitoring services (Grafana, Prometheus, Loki, AlertManager)
7. **Health check**: Verify all 4 services are healthy
8. **Deploy Alloy**: Copy `staging-ap-vm.alloy` config and restart Alloy

#### Job 2: Deploy Staging DB-VM Monitoring

**Runs on**: Self-hosted runner (SSH to remote DB-VM)

1. **Setup SSH**: Configure SSH key for DB-VM access
2. **Deploy Alloy**: Copy `staging-db-vm.alloy` config to DB-VM via SCP
3. **Restart Alloy**: Restart monitoring agent on DB-VM
4. **Verify metrics**: Check Prometheus targets are UP
5. **Check logs**: Verify Loki is receiving logs
6. **Cleanup**: Remove SSH keys
7. **Summary**: Display monitoring access URLs

### Health Verification

The workflow performs comprehensive health checks:

- ✅ Grafana API health check (`/api/health`)
- ✅ Prometheus health check (`/-/healthy`)
- ✅ Loki readiness check (`/ready`)
- ✅ AlertManager health check (`/-/healthy`)
- ✅ Prometheus targets status (all staging targets UP)
- ✅ Loki log ingestion (staging logs being received)

## Manual Deployment

If you prefer to deploy manually without GitHub Actions:

### Step 1: Deploy Monitoring Server (on Staging AP-VM)

```bash
# Already on Staging AP-VM
cd /path/to/repository

# Create monitoring directory
sudo mkdir -p /opt/scholarship/monitoring
sudo chown -R $USER:$USER /opt/scholarship/monitoring

# Copy monitoring configuration
cp -r ./monitoring/* /opt/scholarship/monitoring/

# Create .env file
cd /opt/scholarship/monitoring
cat > .env.monitoring << EOF
# Required Grafana security settings
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=YourSecurePassword123!
GRAFANA_SECRET_KEY=$(openssl rand -hex 32)
GRAFANA_ROOT_URL=https://ss.test.nycu.edu.tw/monitoring/
GF_LOG_LEVEL=info
EOF

# Deploy monitoring stack
docker-compose -f docker-compose.monitoring.yml pull
docker-compose -f docker-compose.monitoring.yml up -d

# Wait for services to start
sleep 30

# Check health
docker ps --filter "name=monitoring_"
curl http://localhost:3000/api/health
curl http://localhost:9090/-/healthy
curl http://localhost:3100/ready
curl http://localhost:9093/-/healthy
```

### Step 2: Deploy Alloy on Staging AP-VM (localhost)

```bash
# Still on Staging AP-VM
sudo mkdir -p /opt/scholarship/monitoring/config/alloy
cp ./monitoring/config/alloy/staging-ap-vm.alloy /opt/scholarship/monitoring/config/alloy/

# Restart Alloy if running
cd /opt/scholarship
docker-compose -f docker-compose.staging.yml restart alloy
```

### Step 3: Deploy Alloy on Staging DB-VM (remote)

```bash
# From Staging AP-VM, deploy to DB-VM (using SSH port 8822)
scp -P 8822 ./monitoring/config/alloy/staging-db-vm.alloy \
  user@staging-db-vm:/opt/scholarship/monitoring/config/alloy/

# Restart Alloy on DB-VM (using SSH port 8822)
ssh -p 8822 user@staging-db-vm "cd /opt/scholarship && docker-compose -f docker-compose.staging-db.yml restart alloy"
```

### Step 4: Verify Deployment

```bash
# On Staging AP-VM
# Check Prometheus targets
curl -s http://localhost:9090/api/v1/targets | \
  jq '.data.activeTargets[] | select(.labels.environment=="staging") | {job: .labels.job, health: .health}'

# Check Loki logs
curl -H "X-Scope-OrgID: staging" -G "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  --data-urlencode 'limit=5'
```

## Troubleshooting

### Self-Hosted Runner Issues

#### Runner Not Picking Up Jobs

**Symptom**: Workflow queued but not starting

**Solution**:
```bash
# Check runner status
sudo systemctl status actions.runner.*

# Restart runner
sudo ./svc.sh restart

# View runner logs
journalctl -u actions.runner.* -f
```

#### Runner Permission Errors

**Symptom**: "Permission denied" when creating directories

**Solution**:
```bash
# Ensure runner user has sudo access
sudo usermod -aG sudo runner-user

# Or set specific permissions for /opt/scholarship
sudo chown -R runner-user:runner-user /opt/scholarship
```

### Deployment Fails - SSH Connection to DB-VM

**Symptom**: GitHub Actions workflow fails with "Permission denied (publickey)" for DB-VM

**Solution**:
1. Verify SSH key is correctly added to GitHub secrets (Environment: staging)
2. Ensure the private key format is correct (no extra line breaks)
3. Check that the public key is added to `~/.ssh/authorized_keys` on DB-VM
4. Verify SSH key permissions on DB-VM:
   ```bash
   ssh user@staging-db-vm
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```

### Services Don't Start After Deployment

**Symptom**: Workflow completes but health checks fail

**Solution**:
```bash
# On Staging AP-VM
cd /opt/scholarship/monitoring

# Check container logs
docker-compose -f docker-compose.monitoring.yml logs --tail=100

# Check specific service
docker logs monitoring_grafana --tail=50
docker logs monitoring_prometheus --tail=50
docker logs monitoring_loki --tail=50

# Restart services
docker-compose -f docker-compose.monitoring.yml restart
```

### Prometheus Targets Showing as DOWN

**Symptom**: Prometheus reports DB-VM targets as "DOWN" in `/targets` page

**Diagnosis**:
```bash
# Check if Alloy is running on DB-VM
ssh user@staging-db-vm "docker ps | grep alloy"

# Check Alloy logs on DB-VM
ssh user@staging-db-vm "docker logs scholarship_alloy_staging_db --tail=100"

# Test exporter endpoints on DB-VM
ssh user@staging-db-vm "curl http://localhost:9187/metrics"  # Postgres Exporter
ssh user@staging-db-vm "curl http://localhost:9121/metrics"  # Redis Exporter
```

**Solution**:
1. Ensure Alloy container is running on DB-VM
2. Check Docker network connectivity between VMs
3. Verify firewall allows connections on exporter ports
4. Restart Alloy on DB-VM

### Loki Not Receiving Logs

**Symptom**: No logs visible in Grafana Explore or Loki queries return empty

**Diagnosis**:
```bash
# Check Alloy on AP-VM is pushing logs
docker logs scholarship_alloy_staging_ap | grep -i loki

# Check Alloy on DB-VM is pushing logs
ssh user@staging-db-vm "docker logs scholarship_alloy_staging_db | grep -i loki"

# Check Loki ingester
curl http://localhost:3100/ingester/ring | jq

# Query Loki directly with tenant header
curl -G -s "http://localhost:3100/loki/api/v1/query" \
  --data-urlencode 'query={environment="staging"}' \
  --data-urlencode 'limit=10' \
  -H "X-Scope-OrgID: staging"
```

**Solution**:
1. Verify `X-Scope-OrgID: staging` header is set in Alloy configs
2. Check Loki has sufficient disk space
3. Verify Alloy can reach Loki (port 3100)
4. Restart Loki and both Alloy instances

### GitHub Secrets Not Being Applied

**Symptom**: Services start with default values instead of secret values

**Solution**:
1. Verify secrets are set in **Environment secrets** (not repository secrets)
2. Environment name must be exactly "staging" (lowercase)
3. Secret names must match exactly (case-sensitive)
4. Re-run workflow after updating secrets
5. Check `.env.monitoring` file was created correctly:
   ```bash
   cat /opt/scholarship/monitoring/.env.monitoring
   ```

### Workflow Cannot Access /opt/scholarship

**Symptom**: Workflow fails with "permission denied" when copying files

**Solution**:
```bash
# On Staging AP-VM
sudo mkdir -p /opt/scholarship/monitoring
sudo chown -R $(whoami):$(whoami) /opt/scholarship

# Or if runner runs as specific user
sudo chown -R runner-user:runner-user /opt/scholarship
```

## Viewing Deployment Logs

### In GitHub Actions

1. Go to "Actions" tab
2. Click on the workflow run
3. Click on individual job steps to see logs
4. Download logs using "Download log archive" button

### On Staging AP-VM (Monitoring Server)

```bash
# View all monitoring services logs
docker-compose -f /opt/scholarship/monitoring/docker-compose.monitoring.yml logs --tail=200

# View specific service logs
docker logs monitoring_grafana -f
docker logs monitoring_prometheus -f
docker logs monitoring_loki -f
docker logs monitoring_alertmanager -f

# View Alloy logs on AP-VM
docker logs scholarship_alloy_staging_ap -f
```

### On Staging DB-VM

```bash
# SSH to DB-VM
ssh user@staging-db-vm

# View Alloy logs
docker logs scholarship_alloy_staging_db -f

# View exporter logs
docker logs postgres_exporter_staging -f
docker logs redis_exporter_staging -f
```

## Rollback Procedure

If deployment causes issues, rollback to previous version:

```bash
# On Staging AP-VM
cd /opt/scholarship/monitoring

# Stop current stack
docker-compose -f docker-compose.monitoring.yml down

# Option 1: Restore from backup (recommended)
# See backup-metrics.sh and restore-monitoring.sh scripts

# Option 2: Checkout previous commit
cd /path/to/repository
git log --oneline monitoring/  # Find previous working commit
git checkout <commit-hash> -- monitoring/

# Copy to deployment directory
cp -r ./monitoring/* /opt/scholarship/monitoring/

# Start stack
cd /opt/scholarship/monitoring
docker-compose -f docker-compose.monitoring.yml up -d

# Verify
docker-compose -f docker-compose.monitoring.yml ps
```

## Security Best Practices

### Credentials & Secrets
1. **Rotate SSH Keys Regularly**: Update GitHub secrets with new DB-VM SSH key every 90 days
2. **Use Strong Passwords**: Grafana admin password should be at least 16 characters with mixed case, numbers, and symbols
3. **Generate Unique Secret Keys**: Always generate `GRAFANA_SECRET_KEY` with `openssl rand -hex 32`
4. **Limit SSH Key Access**: Use a dedicated SSH key for DB-VM deployment (not your personal key)
5. **Monitor Secret Usage**: Review GitHub Actions logs to ensure no secrets are accidentally exposed

### HTTPS & SSL Configuration
6. **Secure Cookies**: Cookie security is enabled (`cookie_secure = true`) for HTTPS deployments
7. **Modern SSL Ciphers**: Nginx uses Mozilla's modern cipher suite (ECDHE-ECDSA/RSA-AES128/256-GCM)
8. **TLS 1.2+**: Only TLSv1.2 and TLSv1.3 are enabled for secure communication

### Access Control
9. **Enable Branch Protection**: Require reviews for changes to monitoring configs before merging to main
10. **Use Environment Protection**: Enable required reviewers for staging deployments in repository settings
11. **Runner Security**: Keep self-hosted runner updated and isolated from production services
12. **Firewall Rules**: Only allow necessary ports between AP-VM and DB-VM

### Configuration Management
13. **Never Commit Secrets**: Always use GitHub secrets or environment variables
14. **Validate Configurations**: Review Grafana and Prometheus configs before deployment
15. **Audit Access**: Regularly review who has access to monitoring dashboards

## Production Deployment

This workflow is designed for **staging only**. When ready for production:

1. Create a separate self-hosted runner on production AP-VM
2. Create new GitHub secrets for production environment
3. Create a new workflow file: `deploy-monitoring-stack-prod.yml`
4. Use `prod-ap-vm.alloy` and `prod-db-vm.alloy` configs
5. Update Prometheus scrape configs for production targets
6. Implement change control and approval process

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitHub Self-Hosted Runners](https://docs.github.com/en/actions/hosting-your-own-runners)
- [GitHub Encrypted Secrets](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [SSH Key Authentication](https://docs.github.com/en/authentication/connecting-to-github-with-ssh)

---

**Last Updated**: 2025-01-11
**Architecture**: Self-hosted runner on Staging AP-VM (localhost deployment)
**Maintained By**: Scholarship System Development Team
