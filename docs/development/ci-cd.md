# CI/CD Pipeline Documentation

## Overview

This document describes the automated CI/CD pipeline for the Scholarship Management System. The pipeline ensures code quality, runs comprehensive tests, and automates deployment processes.

## Pipeline Architecture

```mermaid
graph TD
    A[Code Push] --> B[GitHub Actions Trigger]
    B --> C[Frontend Tests]
    B --> D[Backend Tests]
    B --> E[Security Scan]
    
    C --> F[E2E Tests]
    D --> F
    E --> F
    
    F --> G[Build & Deploy]
    G --> H[Performance Tests]
    H --> I[Notifications]
```

## Workflows

### 1. Main CI/CD Pipeline (`.github/workflows/ci.yml`)

**Triggers:**
- Push to `main` or `develop` branches
- Pull requests to `main` or `develop` branches

**Jobs:**

#### Frontend Tests
- **Environment**: Ubuntu Latest, Node.js 18
- **Steps**:
  - Install dependencies with `npm ci`
  - Run ESLint for code quality
  - Execute Jest unit tests with coverage
  - Upload coverage to Codecov

#### Backend Tests
- **Environment**: Ubuntu Latest, Python 3.11
- **Services**: PostgreSQL 15, Redis 7
- **Steps**:
  - Install Python dependencies
  - Run Flake8 linting
  - Execute pytest with coverage
  - Upload coverage to Codecov

#### E2E Tests
- **Dependencies**: Frontend and Backend tests must pass
- **Steps**:
  - Start full system with Docker
  - Install Playwright browsers
  - Run end-to-end tests
  - Upload test artifacts on failure

#### Security Scanning
- **Tools**: Trivy vulnerability scanner
- **Scope**: Filesystem scan for vulnerabilities
- **Output**: SARIF format uploaded to GitHub Security

#### Build & Deploy
- **Trigger**: Only on `main` branch after all tests pass
- **Steps**:
  - Build Docker images for frontend and backend
  - Push to GitHub Container Registry
  - Deploy to staging environment
  - Run smoke tests

#### Performance Tests
- **Tools**: k6 load testing
- **Trigger**: After successful deployment
- **Scope**: API performance validation

### 2. Dependency Updates (`.github/workflows/dependency-update.yml`)

**Schedule**: Every Monday at 9 AM UTC

**Features**:
- Automated dependency updates for both frontend and backend
- Security vulnerability fixes
- Automatic PR creation for review
- Security audit with issue creation on vulnerabilities

## Test Coverage Requirements

### Frontend
- **Target**: 70% coverage (branches, functions, lines, statements)
- **Tools**: Jest, React Testing Library
- **Exclusions**: 
  - Type definition files (`.d.ts`)
  - Next.js build files (`.next/`)
  - Node modules

### Backend
- **Target**: 90% coverage
- **Tools**: pytest, pytest-cov
- **Scope**: All application code in `app/` directory

## Quality Gates

### Code Quality
- **Frontend**: ESLint with Next.js configuration
- **Backend**: Flake8 with complexity checks (max 10)
- **Line Length**: 127 characters maximum

### Security
- **Dependency Scanning**: npm audit, Python safety
- **Container Scanning**: Trivy for Docker images
- **SAST**: GitHub CodeQL analysis
- **Secret Detection**: GitHub secret scanning

### Performance
- **API Response Time**: p95 < 600ms
- **Load Testing**: k6 scripts for critical endpoints
- **Bundle Size**: Frontend bundle analysis

## Environment Configuration

### Development
```yaml
services:
  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: scholarship_dev
      POSTGRES_USER: dev_user
      POSTGRES_PASSWORD: dev_password

  redis:
    image: redis:7-alpine
    
  backend:
    build: ./backend
    environment:
      DATABASE_URL: postgresql+asyncpg://dev_user:dev_password@postgres:5432/scholarship_dev
      REDIS_URL: redis://redis:6379/0
      
  frontend:
    build: ./frontend
    environment:
      NEXT_PUBLIC_API_URL: http://localhost:8000
```

### Testing
```yaml
services:
  postgres:
    environment:
      POSTGRES_DB: test_db
      POSTGRES_USER: test_user
      POSTGRES_PASSWORD: test_password
```

### Production
- Environment variables managed through GitHub Secrets
- Container images from GitHub Container Registry
- Health checks and monitoring enabled

## Deployment Strategy

### Staging Deployment
- **Trigger**: Every push to `main` branch
- **Environment**: Staging cluster
- **Validation**: Smoke tests after deployment

### Production Deployment
- **Trigger**: Manual approval after staging validation
- **Strategy**: Blue-green deployment
- **Rollback**: Automatic on health check failure

## Monitoring and Alerting

### Health Checks
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
  interval: 30s
  timeout: 10s
  start_period: 40s
  retries: 3
```

### Notifications
- **Success**: Green checkmark in GitHub
- **Failure**: GitHub issue creation + team notification
- **Security**: Immediate alert for vulnerabilities

## Local Development

### Prerequisites
```bash
# Install dependencies
npm install -g @playwright/test
pip install pytest pytest-cov flake8

# Docker for integration testing
docker --version
docker-compose --version
```

### Running Tests Locally
```bash
# Frontend tests
cd frontend
npm test

# Backend tests
cd backend
python -m pytest

# E2E tests
./test-docker.sh start
cd frontend
npm run test:e2e
./test-docker.sh stop
```

### Validation Script
```bash
# Run comprehensive validation
./scripts/validate-ci.sh
```

## Branch Protection Rules

### Main Branch
- Require pull request reviews (2 reviewers)
- Require status checks to pass:
  - Frontend Tests
  - Backend Tests
  - E2E Tests
  - Security Scan
- Require branches to be up to date
- Require conversation resolution
- Restrict pushes to administrators only

### Develop Branch
- Require pull request reviews (1 reviewer)
- Require status checks to pass:
  - Frontend Tests
  - Backend Tests
- Allow force pushes for administrators

## Secrets Management

### Required Secrets
```bash
# Code Coverage
CODECOV_TOKEN=<codecov-token>

# Container Registry
GITHUB_TOKEN=<automatic-token>

# Deployment
DEPLOY_SSH_KEY=<deployment-key>
STAGING_HOST=<staging-server>
PRODUCTION_HOST=<production-server>

# Notifications
SLACK_WEBHOOK_URL=<slack-webhook>
DISCORD_WEBHOOK_URL=<discord-webhook>

# External Services
SMTP_PASSWORD=<email-password>
MINIO_SECRET_KEY=<object-storage-key>
```

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db
REDIS_URL=redis://host:6379/0

# Security
SECRET_KEY=<jwt-secret>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# File Storage
MINIO_ENDPOINT=storage.example.com
MINIO_ACCESS_KEY=<access-key>
MINIO_SECRET_KEY=<secret-key>
```

## Troubleshooting

### Common Issues

#### Test Failures
```bash
# Check test logs
gh run view <run-id> --log

# Run tests locally
npm test -- --verbose
pytest -v
```

#### Build Failures
```bash
# Check Docker build context
docker build -t test-image ./backend
docker build -t test-image ./frontend

# Validate docker-compose
docker-compose config
```

#### Deployment Issues
```bash
# Check service health
curl -f http://staging.example.com/health

# View container logs
docker logs <container-id>
```

### Performance Issues
```bash
# Run performance tests locally
k6 run tests/performance/load-test.js

# Check API response times
curl -w "@curl-format.txt" -o /dev/null -s http://api.example.com/health
```

## Metrics and KPIs

### Development Velocity
- **Deployment Frequency**: Daily to staging, weekly to production
- **Lead Time**: < 2 hours from commit to staging
- **Mean Time to Recovery**: < 30 minutes

### Quality Metrics
- **Test Coverage**: Frontend 70%+, Backend 90%+
- **Bug Escape Rate**: < 5% to production
- **Security Vulnerabilities**: 0 high/critical in production

### Performance Metrics
- **API Response Time**: p95 < 600ms
- **Frontend Load Time**: < 3 seconds
- **Uptime**: 99.9% availability

## Maintenance

### Weekly Tasks
- Review dependency update PRs
- Check security scan results
- Validate performance metrics
- Update documentation

### Monthly Tasks
- Review and update CI/CD pipeline
- Performance optimization
- Security audit
- Disaster recovery testing

### Quarterly Tasks
- Technology stack updates
- Pipeline performance review
- Security penetration testing
- Capacity planning

## Support and Contacts

### Team Responsibilities
- **DevOps Team**: Pipeline maintenance, infrastructure
- **Frontend Team**: Frontend tests, build optimization
- **Backend Team**: Backend tests, API performance
- **QA Team**: E2E tests, test strategy

### Escalation Path
1. **Level 1**: Team lead review
2. **Level 2**: DevOps team intervention
3. **Level 3**: Architecture team consultation

---

*Last Updated: 2025-01-01*
*Version: 1.0* 