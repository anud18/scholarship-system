# Deployment Pipeline Documentation

## Overview

This document describes the deployment pipeline for the Scholarship System, which uses GitHub Actions to automate deployments to staging and production environments.

## Architecture

### Deployment Flow

```
Push to main → Build Images → Deploy to Staging → Staging Tests → Complete
```

**Note**: This repository only deploys to the staging environment. Production deployment is handled separately.

### Self-Hosted Runner

- **Runner Name**: `scholarship-test`
- **Labels**: `self-hosted`, `scholarship-test`
- **Location**: Staging server
- **Purpose**: Execute staging deployments directly on the staging machine

## Deployment Pipeline Jobs

### 1. Pre-deployment Checks
- Determines deployment target (staging/production)
- Generates version tag
- Creates deployment plan summary

### 2. Build Images
- Builds Docker images for backend and frontend
- Pushes to GitHub Container Registry (ghcr.io)
- Tags images with version and commit SHA

### 3. Deploy to Staging
- **Runs on**: Self-hosted runner (`scholarship-test`)
- Pulls latest Docker images
- Stops old containers
- Runs database migrations (Alembic)
- Seeds database with initial data
- Starts new containers
- Performs health checks
- Runs smoke tests

### 4. Staging Validation
- Integration tests against staging environment
- Performance checks
- Response time validation


## Required Secrets

### Staging Environment

| Secret | Description |
|--------|-------------|
| `STAGING_DATABASE_URL` | Async PostgreSQL connection string |
| `STAGING_DATABASE_URL_SYNC` | Sync PostgreSQL connection string (for Alembic) |
| `STAGING_REDIS_URL` | Redis connection string |
| `STAGING_SECRET_KEY` | Application secret key |
| `STAGING_API_URL` | Backend API URL |
| `STAGING_CORS_ORIGINS` | Allowed CORS origins |
| `STAGING_MINIO_ENDPOINT` | MinIO endpoint |
| `STAGING_MINIO_ACCESS_KEY` | MinIO access key |
| `STAGING_MINIO_SECRET_KEY` | MinIO secret key |
| `STAGING_ADMIN_EMAIL` | Admin user email for seeding |

### General

| Secret | Description |
|--------|-------------|
| `GH_PAT` | GitHub Personal Access Token for registry access |

## Triggering Deployments

### Automatic Deployment (Staging)
```bash
git push origin main
```
Automatically deploys to staging when code is pushed to main branch.

### Manual Deployment (Staging)
1. Go to Actions tab in GitHub
2. Select "Deployment Pipeline" workflow
3. Click "Run workflow"
4. Optionally skip tests

## Database Management

### Migrations

The deployment pipeline automatically runs Alembic migrations:

```bash
docker run --rm \
  -e DATABASE_URL_SYNC="${DATABASE_URL_SYNC}" \
  -e APP_ENV="${APP_ENV}" \
  ghcr.io/your-user/scholarship-system-backend:version \
  alembic upgrade head
```

### Seeding Data

For staging environment, the pipeline seeds test data:

```bash
docker run --rm \
  -e DATABASE_URL="${DATABASE_URL}" \
  -e APP_ENV="${APP_ENV}" \
  -e ADMIN_EMAIL="${ADMIN_EMAIL}" \
  ghcr.io/your-user/scholarship-system-backend:version \
  python -m app.seed
```

## Health Checks

### Backend Health Check
```bash
curl -f http://localhost:8000/health
```

### Frontend Health Check
```bash
curl -f http://localhost:3000/api/health
```

### API Documentation
```bash
curl -f http://localhost:8000/docs
```

## Rollback Procedure

### Staging Rollback

1. Find previous successful deployment version:
   ```bash
   docker images | grep scholarship-system-backend
   ```

2. Update docker-compose.yml with previous version
3. Restart containers:
   ```bash
   cd ~/scholarship-staging
   docker-compose down
   docker-compose up -d
   ```


## Monitoring

### Container Logs

```bash
# Staging backend logs
docker logs scholarship_staging_backend -f

# Staging frontend logs
docker logs scholarship_staging_frontend -f
```

### Health Status

```bash
# Check container health
docker ps --filter "name=scholarship_staging"

# Check service health
curl http://localhost:8000/health
curl http://localhost:3000
```

## Troubleshooting

### Deployment Fails at Migration Step

**Problem**: Alembic migrations fail
**Solution**:
1. Check migration files in `backend/alembic/versions/`
2. Verify DATABASE_URL_SYNC secret is correct
3. Manually run migration to see detailed error:
   ```bash
   docker run --rm -it \
     -e DATABASE_URL_SYNC="postgresql://..." \
     ghcr.io/your-user/scholarship-system-backend:version \
     alembic upgrade head
   ```

### Health Check Timeout

**Problem**: Container health check fails
**Solution**:
1. Check container logs:
   ```bash
   docker logs scholarship_staging_backend --tail 100
   ```
2. Verify environment variables are set correctly
3. Check database connectivity
4. Ensure ports are not blocked by firewall

### Image Pull Fails

**Problem**: Cannot pull images from registry
**Solution**:
1. Verify GH_PAT secret has correct permissions
2. Check registry authentication:
   ```bash
   docker login ghcr.io -u USERNAME -p $GH_PAT
   ```
3. Ensure images exist in registry

## Self-Hosted Runner Setup

### Installing the Runner

1. On staging server, install GitHub Actions runner:
   ```bash
   mkdir actions-runner && cd actions-runner
   curl -o actions-runner-linux-x64-2.311.0.tar.gz -L \
     https://github.com/actions/runner/releases/download/v2.311.0/actions-runner-linux-x64-2.311.0.tar.gz
   tar xzf ./actions-runner-linux-x64-2.311.0.tar.gz
   ```

2. Configure the runner:
   ```bash
   ./config.sh --url https://github.com/your-org/scholarship-system \
     --token YOUR_REGISTRATION_TOKEN \
     --name scholarship-test \
     --labels self-hosted,scholarship-test
   ```

3. Install as service:
   ```bash
   sudo ./svc.sh install
   sudo ./svc.sh start
   ```

### Runner Requirements

- **OS**: Linux (Ubuntu 20.04+)
- **Docker**: Installed and running
- **Docker Compose**: v2.0+
- **Network**: Access to GitHub and database servers
- **Disk**: At least 50GB free space
- **RAM**: Minimum 4GB

## Deployment Checklist

### Before Deployment

- [ ] All tests pass in CI
- [ ] Database migrations tested locally
- [ ] Environment secrets configured
- [ ] Self-hosted runner is online
- [ ] Backup created (for production)

### After Deployment

- [ ] Health checks pass
- [ ] Smoke tests pass
- [ ] Monitor logs for errors
- [ ] Verify key functionality
- [ ] Update deployment documentation

## Environment URLs

- **Staging**: https://staging.scholarship.nycu.edu.tw

## Support

For deployment issues:
1. Check GitHub Actions logs
2. Review container logs on staging server
3. Consult this documentation
4. Contact DevOps team

---

**Last Updated**: 2025-09-25
**Maintained By**: DevOps Team