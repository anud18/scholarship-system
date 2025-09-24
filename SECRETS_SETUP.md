# GitHub Secrets Configuration Guide

## How to Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each secret below

---

## Required Secrets for Deployment Pipeline

### 1. **GH_PAT** (GitHub Personal Access Token)
**Purpose**: Access GitHub Container Registry to push/pull Docker images

**Value**:
```
# Generate a new PAT at: https://github.com/settings/tokens
# Required scopes:
# - write:packages (to push images)
# - read:packages (to pull images)
# - repo (if private repository)

YOUR_GITHUB_PAT_HERE
```

**How to generate**:
1. Go to https://github.com/settings/tokens
2. Click "Generate new token (classic)"
3. Give it a name like "Scholarship System Registry"
4. Select scopes: `write:packages`, `read:packages`, `repo`
5. Click "Generate token"
6. Copy the token and add it as `GH_PAT` secret

---

### 2. **STAGING_DATABASE_URL** (Async Connection)
**Purpose**: Async PostgreSQL connection for FastAPI

**Format**:
```
postgresql+asyncpg://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

**Example Value**:
```
postgresql+asyncpg://scholarship_user:your_secure_password@localhost:5432/scholarship_staging
```

**Replace with your values**:
- `USERNAME`: Your PostgreSQL username (e.g., `scholarship_user`)
- `PASSWORD`: Your PostgreSQL password
- `HOST`: Database host (use `localhost` if on same machine as runner)
- `PORT`: Usually `5432`
- `DATABASE`: Database name (e.g., `scholarship_staging`)

---

### 3. **STAGING_DATABASE_URL_SYNC** (Sync Connection)
**Purpose**: Sync PostgreSQL connection for Alembic migrations

**Format**:
```
postgresql://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

**Example Value**:
```
postgresql://scholarship_user:your_secure_password@localhost:5432/scholarship_staging
```

**Note**: Same as STAGING_DATABASE_URL but without `+asyncpg`

---

### 4. **STAGING_REDIS_URL**
**Purpose**: Redis cache connection

**Format**:
```
redis://HOST:PORT/DB_NUMBER
```

**Example Value**:
```
redis://localhost:6379/0
```

**Or with password**:
```
redis://:your_redis_password@localhost:6379/0
```

---

### 5. **STAGING_SECRET_KEY**
**Purpose**: JWT token signing and encryption

**Value** (generate a secure random string):
```bash
# Generate a secure secret key (run this command):
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

**Example Output**:
```
xK8dP_3mQ2wNvR7yL5aF9bT4cU1jE6hG0iS-8zV_W2n
```

**Important**:
- Must be at least 32 characters
- Keep this secret and don't share it
- Generate a new one for production

---

### 6. **STAGING_API_URL**
**Purpose**: Backend API URL for frontend to connect

**Value**:
```
https://ss.test.nycu.edu.tw/api
```

**Or if using different port**:
```
https://ss.test.nycu.edu.tw:8000
```

---

### 7. **STAGING_CORS_ORIGINS**
**Purpose**: Allowed origins for CORS

**Value**:
```
https://ss.test.nycu.edu.tw,http://localhost:3000
```

**Note**: Comma-separated list of allowed origins

---

### 8. **STAGING_MINIO_ENDPOINT**
**Purpose**: MinIO object storage endpoint

**Value** (if MinIO on same machine):
```
localhost:9000
```

**Or with domain**:
```
minio.test.nycu.edu.tw:9000
```

---

### 9. **STAGING_MINIO_ACCESS_KEY**
**Purpose**: MinIO access key (username)

**Default Value** (change in production):
```
minioadmin
```

**Or generate secure key**:
```bash
python3 -c "import secrets; print(secrets.token_hex(16))"
```

---

### 10. **STAGING_MINIO_SECRET_KEY**
**Purpose**: MinIO secret key (password)

**Default Value** (change in production):
```
minioadmin123
```

**Generate secure key**:
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

### 11. **STAGING_ADMIN_EMAIL**
**Purpose**: Admin user email for database seeding

**Value**:
```
admin@nycu.edu.tw
```

**Or your admin email**:
```
your_admin_email@nycu.edu.tw
```

---

## Quick Setup Script

Run this script to generate all secret values:

```bash
#!/bin/bash

echo "=== GitHub Secrets Configuration ==="
echo ""
echo "Copy these values to GitHub Secrets:"
echo ""

echo "1. GH_PAT"
echo "   Go to: https://github.com/settings/tokens"
echo "   Generate token with: write:packages, read:packages, repo"
echo ""

echo "2. STAGING_DATABASE_URL"
echo "   postgresql+asyncpg://scholarship_user:PASSWORD@localhost:5432/scholarship_staging"
echo ""

echo "3. STAGING_DATABASE_URL_SYNC"
echo "   postgresql://scholarship_user:PASSWORD@localhost:5432/scholarship_staging"
echo ""

echo "4. STAGING_REDIS_URL"
echo "   redis://localhost:6379/0"
echo ""

echo "5. STAGING_SECRET_KEY (Generated):"
python3 -c "import secrets; print('   ' + secrets.token_urlsafe(32))"
echo ""

echo "6. STAGING_API_URL"
echo "   https://ss.test.nycu.edu.tw/api"
echo ""

echo "7. STAGING_CORS_ORIGINS"
echo "   https://ss.test.nycu.edu.tw,http://localhost:3000"
echo ""

echo "8. STAGING_MINIO_ENDPOINT"
echo "   localhost:9000"
echo ""

echo "9. STAGING_MINIO_ACCESS_KEY (Generated):"
python3 -c "import secrets; print('   ' + secrets.token_hex(16))"
echo ""

echo "10. STAGING_MINIO_SECRET_KEY (Generated):"
python3 -c "import secrets; print('   ' + secrets.token_urlsafe(32))"
echo ""

echo "11. STAGING_ADMIN_EMAIL"
echo "   admin@nycu.edu.tw"
echo ""
```

---

## Verification Checklist

After adding all secrets, verify:

- [ ] All 11 secrets are added to GitHub repository
- [ ] Secret names match exactly (case-sensitive)
- [ ] DATABASE_URL uses correct driver (`postgresql+asyncpg` vs `postgresql`)
- [ ] Database credentials are correct
- [ ] MinIO endpoint is accessible from staging server
- [ ] CORS origins include your domain
- [ ] Admin email is valid

---

## Testing Secrets

To test if secrets are working:

1. **Trigger Manual Deployment**:
   - Go to Actions → Deployment Pipeline
   - Click "Run workflow"
   - Watch for errors in logs

2. **Check Database Connection**:
   ```bash
   # On staging server
   docker logs scholarship_staging_backend | grep -i "database"
   ```

3. **Check MinIO Connection**:
   ```bash
   docker logs scholarship_staging_backend | grep -i "minio"
   ```

---

## Security Best Practices

1. **Never commit secrets to git**
2. **Use different secrets for staging and production**
3. **Rotate secrets regularly (every 90 days)**
4. **Use strong passwords (min 32 characters)**
5. **Limit secret access to necessary team members only**
6. **Monitor secret usage in GitHub Actions logs**

---

## Troubleshooting

### Secret not found error
- Check secret name spelling (case-sensitive)
- Verify secret is added to correct repository
- Ensure workflow has permission to access secrets

### Database connection failed
- Verify DATABASE_URL format
- Check database is running: `docker ps | grep postgres`
- Test connection manually: `psql "postgresql://..."`

### MinIO connection failed
- Verify MinIO is running: `docker ps | grep minio`
- Check endpoint is accessible: `curl http://localhost:9000/minio/health/live`
- Verify access key and secret key are correct

---

**Last Updated**: 2025-09-25
**For Help**: Contact DevOps team or refer to DEPLOYMENT.md