# Production Deployment Guide

## Overview

This guide covers the deployment of the Scholarship Management System to production environments with high availability, security, and performance considerations.

## Prerequisites

### Infrastructure Requirements
- **Server**: Ubuntu 20.04+ or RHEL 8+
- **Memory**: 8GB RAM minimum, 16GB recommended
- **Storage**: 100GB SSD minimum
- **CPU**: 4 cores minimum, 8 cores recommended
- **Network**: Public IP with SSL certificate

### Software Requirements
- Docker 20.10+
- Docker Compose 2.0+
- NGINX 1.18+
- PostgreSQL 15+
- Redis 7+

## Production Architecture

```mermaid
graph TD
    subgraph "Load Balancer"
        LB[NGINX/HAProxy]
    end

    subgraph "Application Tier"
        API1[FastAPI Instance 1]
        API2[FastAPI Instance 2]
        FE1[Frontend Instance 1]
        FE2[Frontend Instance 2]
    end

    subgraph "Data Tier"
        DB[(PostgreSQL Primary)]
        DB_R[(PostgreSQL Replica)]
        REDIS[(Redis Cluster)]
        MINIO[(MinIO Cluster)]
    end

    subgraph "Monitoring"
        PROM[Prometheus]
        GRAF[Grafana]
        ALERT[AlertManager]
    end

    LB --> API1
    LB --> API2
    LB --> FE1
    LB --> FE2

    API1 --> DB
    API2 --> DB
    API1 --> DB_R
    API2 --> DB_R
    API1 --> REDIS
    API2 --> REDIS
    API1 --> MINIO
    API2 --> MINIO

    PROM --> API1
    PROM --> API2
    PROM --> DB
    GRAF --> PROM
    ALERT --> PROM
```

## Environment Configuration

### Production Environment Variables

```bash
# Application Settings
NODE_ENV=production
PYTHON_ENV=production
DEBUG=false

# Security
SECRET_KEY=<strong-production-secret-64-chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@prod-db:5432/scholarship_prod
DATABASE_URL_SYNC=postgresql://user:pass@prod-db:5432/scholarship_prod
DB_POOL_SIZE=20
DB_MAX_OVERFLOW=30

# Redis
REDIS_URL=redis://prod-redis:6379/0
REDIS_PASSWORD=<redis-password>

# File Storage
MINIO_ENDPOINT=prod-minio:9000
MINIO_ACCESS_KEY=<minio-access-key>
MINIO_SECRET_KEY=<minio-secret-key>
MINIO_BUCKET_NAME=scholarship-documents

# Email
SMTP_HOST=smtp.university.edu
SMTP_PORT=587
SMTP_USERNAME=<smtp-username>
SMTP_PASSWORD=<smtp-password>
SMTP_USE_TLS=true

# Monitoring
SENTRY_DSN=<sentry-dsn>
PROMETHEUS_ENABLED=true
```

### SSL/TLS Configuration

```nginx
server {
    listen 80;
    server_name scholarship.university.edu;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name scholarship.university.edu;

    ssl_certificate /etc/ssl/certs/scholarship.crt;
    ssl_certificate_key /etc/ssl/private/scholarship.key;

    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA384:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;

    location / {
        proxy_pass http://frontend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /api/ {
        proxy_pass http://backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Deployment Process

### 1. Prepare Production Environment

```bash
# Create production directory
sudo mkdir -p /opt/scholarship-system
cd /opt/scholarship-system

# Clone repository
git clone https://github.com/your-org/scholarship-system.git .

# Create production environment file
sudo cp .env.production.example .env.production
sudo nano .env.production
```

### 2. Build Production Images

```bash
# Build backend image
docker build -t scholarship-backend:prod ./backend

# Build frontend image
docker build -t scholarship-frontend:prod ./frontend

# Tag images for registry
docker tag scholarship-backend:prod registry.university.edu/scholarship-backend:latest
docker tag scholarship-frontend:prod registry.university.edu/scholarship-frontend:latest

# Push to registry
docker push registry.university.edu/scholarship-backend:latest
docker push registry.university.edu/scholarship-frontend:latest
```

### 3. Database Setup

```bash
# Create production database
sudo -u postgres createuser scholarship_prod
sudo -u postgres createdb scholarship_prod -O scholarship_prod

# Run migrations
docker-compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# Create initial admin user
docker-compose -f docker-compose.prod.yml run --rm backend python -c "
from app.core.init_db import create_initial_admin
create_initial_admin()
"
```

### 4. Deploy Services

```bash
# Start production services
docker-compose -f docker-compose.prod.yml up -d

# Verify deployment
docker-compose -f docker-compose.prod.yml ps
```

### 5. Configure NGINX

```bash
# Copy NGINX configuration
sudo cp nginx/production.conf /etc/nginx/sites-available/scholarship
sudo ln -s /etc/nginx/sites-available/scholarship /etc/nginx/sites-enabled/

# Test configuration
sudo nginx -t

# Reload NGINX
sudo systemctl reload nginx
```

## Monitoring and Logging

### Health Checks

```yaml
# docker-compose.prod.yml
services:
  backend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      start_period: 40s
      retries: 3

  frontend:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      start_period: 40s
      retries: 3
```

### Logging Configuration

```yaml
# Centralized logging
logging:
  driver: "json-file"
  options:
    max-size: "10m"
    max-file: "3"
    labels: "production"
```

### Monitoring Stack

```bash
# Deploy monitoring stack
docker-compose -f docker-compose.monitoring.yml up -d

# Access monitoring dashboards
# Grafana: https://monitoring.university.edu:3000
# Prometheus: https://monitoring.university.edu:9090
```

## Backup and Recovery

### Database Backup

```bash
#!/bin/bash
# backup-db.sh
BACKUP_DIR="/opt/backups/postgresql"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="scholarship_prod_${TIMESTAMP}.sql"

# Create backup
pg_dump -h prod-db -U scholarship_prod scholarship_prod > "${BACKUP_DIR}/${BACKUP_FILE}"

# Compress backup
gzip "${BACKUP_DIR}/${BACKUP_FILE}"

# Upload to remote storage
aws s3 cp "${BACKUP_DIR}/${BACKUP_FILE}.gz" s3://backups/postgresql/

# Clean old backups (keep 30 days)
find "${BACKUP_DIR}" -name "scholarship_prod_*.sql.gz" -mtime +30 -delete
```

### File Storage Backup

```bash
#!/bin/bash
# backup-files.sh
BACKUP_DIR="/opt/backups/files"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# Sync MinIO data
mc mirror minio/scholarship-documents "${BACKUP_DIR}/${TIMESTAMP}/"

# Upload to remote storage
aws s3 sync "${BACKUP_DIR}/${TIMESTAMP}/" s3://backups/files/

# Clean old backups
find "${BACKUP_DIR}" -type d -mtime +7 -exec rm -rf {} +
```

### Automated Backup Schedule

```bash
# Add to crontab
0 2 * * * /opt/scripts/backup-db.sh >> /var/log/backup.log 2>&1
0 3 * * * /opt/scripts/backup-files.sh >> /var/log/backup.log 2>&1
```

## Security Hardening

### System Security

```bash
# Firewall configuration
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 8000/tcp  # Block direct API access
sudo ufw deny 3000/tcp  # Block direct frontend access
sudo ufw enable

# Fail2ban configuration
sudo systemctl enable fail2ban
sudo systemctl start fail2ban
```

### Container Security

```dockerfile
# Use non-root user in containers
FROM python:3.11-slim

RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs --gid 1001

USER nextjs
```

### Database Security

```postgresql
-- Create read-only user for monitoring
CREATE USER monitoring WITH PASSWORD 'monitoring_password';
GRANT CONNECT ON DATABASE scholarship_prod TO monitoring;
GRANT USAGE ON SCHEMA public TO monitoring;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO monitoring;

-- Revoke unnecessary permissions
REVOKE ALL ON DATABASE scholarship_prod FROM PUBLIC;
```

## Performance Optimization

### Database Optimization

```sql
-- Add database indexes
CREATE INDEX CONCURRENTLY idx_applications_student_id ON applications(student_id);
CREATE INDEX CONCURRENTLY idx_applications_status ON applications(status);
CREATE INDEX CONCURRENTLY idx_applications_created_at ON applications(created_at);

-- Update statistics
ANALYZE;

-- Configure PostgreSQL
-- postgresql.conf
shared_buffers = 2GB
effective_cache_size = 6GB
maintenance_work_mem = 512MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
```

### Application Optimization

```yaml
# Scale services based on load
services:
  backend:
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '1'
          memory: 1G

  frontend:
    deploy:
      replicas: 2
      resources:
        limits:
          cpus: '1'
          memory: 1G
```

## Disaster Recovery

### Recovery Procedures

```bash
#!/bin/bash
# disaster-recovery.sh

# 1. Restore database
pg_restore -h new-db -U scholarship_prod -d scholarship_prod latest_backup.sql

# 2. Restore file storage
mc mirror s3/backups/files/latest/ minio/scholarship-documents/

# 3. Deploy application
docker-compose -f docker-compose.prod.yml up -d

# 4. Verify system health
curl -f https://scholarship.university.edu/health
```

### RTO/RPO Targets

- **Recovery Time Objective (RTO)**: 4 hours
- **Recovery Point Objective (RPO)**: 1 hour
- **Backup Frequency**: Daily database, hourly file sync
- **Failover**: Automated with health checks

## Maintenance Procedures

### Rolling Updates

```bash
#!/bin/bash
# rolling-update.sh

# Update backend
docker-compose -f docker-compose.prod.yml pull backend
docker-compose -f docker-compose.prod.yml up -d --no-deps backend

# Wait for health check
sleep 30

# Update frontend
docker-compose -f docker-compose.prod.yml pull frontend
docker-compose -f docker-compose.prod.yml up -d --no-deps frontend

# Verify deployment
docker-compose -f docker-compose.prod.yml ps
```

### Database Maintenance

```sql
-- Weekly maintenance tasks
VACUUM ANALYZE;
REINDEX DATABASE scholarship_prod;

-- Monthly maintenance
VACUUM FULL pg_stat_user_tables;
```

## Troubleshooting

### Common Issues

#### High Memory Usage
```bash
# Check container memory usage
docker stats

# Scale down services if needed
docker-compose -f docker-compose.prod.yml scale backend=2
```

#### Database Connection Issues
```bash
# Check database connections
docker-compose -f docker-compose.prod.yml logs postgres

# Monitor connection pool
SELECT state, count(*) FROM pg_stat_activity GROUP BY state;
```

#### File Upload Issues
```bash
# Check MinIO status
mc admin info minio

# Verify disk space
df -h
```

### Emergency Contacts

- **System Administrator**: admin@university.edu
- **Database Administrator**: dba@university.edu
- **Security Team**: security@university.edu
- **On-call Engineer**: +1-555-0123

---

*Last Updated: 2025-01-01*
*Version: 1.0*
