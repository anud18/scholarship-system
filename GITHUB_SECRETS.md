# GitHub Repository Secrets Configuration

This document lists all required secrets for CI/CD pipelines and deployment automation.

## 🔐 Required GitHub Secrets

Configure these secrets in: **Settings → Secrets and variables → Actions**

---

## Database & Cache

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `DB_HOST` | Database server hostname or IP | `db.example.com` or `192.168.1.100` |
| `DB_PORT` | Database port | `5432` |
| `DB_NAME` | Database name | `scholarship_db` |
| `DB_USER` | Database username | `scholarship_user` |
| `DB_PASSWORD` | Database password | `your-strong-password-here` |
| `REDIS_PASSWORD` | Redis authentication password | `your-redis-password` |

---

## Application Security

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `SECRET_KEY` | JWT signing key (min 32 chars) | Generate with: `openssl rand -hex 32` |
| `CORS_ORIGINS` | Allowed frontend origins | `https://example.com,https://www.example.com` |

---

## MinIO Object Storage

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `MINIO_HOST` | MinIO server hostname or IP | `minio.example.com` |
| `MINIO_PORT` | MinIO API port | `9000` |
| `MINIO_ACCESS_KEY` | MinIO access key | `your-minio-access-key` |
| `MINIO_SECRET_KEY` | MinIO secret key | `your-minio-secret-key` |
| `MINIO_BUCKET_NAME` | Storage bucket name | `scholarship-documents-prod` |

---

## Email/SMTP Configuration

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP port | `587` (TLS) or `465` (SSL) |
| `SMTP_USER` | SMTP username/email | `your-email@example.com` |
| `SMTP_PASSWORD` | SMTP password or app password | `your-app-password` |
| `EMAIL_FROM` | Sender email address | `noreply@example.edu.tw` |

---

## NYCU Student API

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `STUDENT_API_BASE_URL` | Student API endpoint | `https://api.university.edu.tw/student` |
| `STUDENT_API_ACCOUNT` | API account ID | `scholarship_system` |
| `STUDENT_API_HMAC_KEY` | HMAC authentication key (hex) | `64-character-hex-string` |

---

## NYCU Employee API

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `NYCU_EMP_ACCOUNT` | Employee API account ID | `scholarship_prod` |
| `NYCU_EMP_KEY_HEX` | HMAC authentication key (hex) | `64-character-hex-string` |
| `NYCU_EMP_ENDPOINT` | Employee API endpoint | `https://api.nycu.edu.tw/employee` |

---

## Portal SSO (Optional)

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `PORTAL_JWT_SERVER_URL` | Portal JWT server URL | `https://portal.nycu.edu.tw/jwt/portal` |
| `PORTAL_SSO_TIMEOUT` | SSO timeout in seconds | `10.0` |

---

## Gemini OCR (Optional)

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `GEMINI_API_KEY` | Google Gemini API key for OCR | `your-gemini-api-key` |

---

## Admin Setup

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `ADMIN_EMAIL` | System administrator email | `admin@nycu.edu.tw` |

---

## GitHub Container Registry

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `GH_PAT` | GitHub Personal Access Token | Token with `read:packages` scope |

---

## 📝 How to Generate Secure Secrets

### Secret Key (32+ characters)
```bash
openssl rand -hex 32
```

### Strong Password
```bash
openssl rand -base64 24
```

### HMAC Key (64 hex characters)
```bash
openssl rand -hex 32
```

---

## 🔒 Security Best Practices

1. **Never commit secrets** to version control
2. **Use different secrets** for staging and production
3. **Rotate secrets periodically** (every 90 days recommended)
4. **Limit secret access** to required workflows only
5. **Monitor secret usage** in GitHub Actions logs
6. **Use organization secrets** for shared values

---

## 🚀 Deployment Workflow Integration

These secrets are automatically injected into deployment workflows:

- `.github/workflows/deploy-pipeline.yml`
- `.github/workflows/ci.yml`
- `.github/workflows/mirror-to-production.yml`

---

## 📚 Related Documentation

- [GitHub Secrets Documentation](https://docs.github.com/en/actions/security-guides/encrypted-secrets)
- [Environment Variables Guide](.claude/CLAUDE.md)
- [Deployment Pipeline](DEPLOYMENT.md)

---

**Last Updated**: 2025-10-26
**Maintained By**: DevOps Team
