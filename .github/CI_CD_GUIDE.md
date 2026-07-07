# CI/CD Pipeline Guide

## Overview

This document describes the CI/CD pipeline for the Scholarship Management System. The pipeline is built using GitHub Actions and includes comprehensive automated testing with coverage requirements, security scanning, dependency updates, and deployment processes.

## Workflows

### 1. Main CI/CD Pipeline (`ci.yml`)

**Trigger**: Push to `main` or `develop` branches, Pull Requests

**Purpose**: Orchestrate the complete CI/CD process

**Jobs** (actual, see `ci.yml`):
- **quick-checks**: black/flake8 (hard on B904/B014), frontend lint, dependency check (`npm audit` hard-gated at high)
- **backend-tests**: matrix of `smoke` / `unit` / `integration` lanes (all hard-gated) against real PostgreSQL
- **frontend-tests**: `jest --coverage` (hard on test failures; coverage not gated)
- **e2e-smoke**: brings up docker-compose.dev and runs `@smoke` Playwright specs (hard-gated since #948)
- **performance-test**: k6 (main-branch push only; advisory)
- **notify**: pipeline status summary

**Key Features**:
- Quick smoke tests for immediate feedback
- Automatic deployment to staging on main branch
- Performance testing with k6
- Comprehensive status reporting

### 2. Test coverage (measured & reported, NOT gated)

> ⚠️ There is **no** `test-coverage.yml` workflow and **no** 90% threshold
> enforcement. An earlier version of this guide described an aspirational
> workflow that was never built; this section documents what actually runs.

Coverage is produced by the backend-test lanes in `ci.yml` (each runs
`pytest --cov=app --cov-fail-under=0`) and the frontend `frontend-tests` job
(`jest --coverage`), then **uploaded to Codecov for reporting only**:

- **`--cov-fail-under=0`** on every backend lane — coverage never fails the
  build. (The local `pytest.ini` sets `--cov-fail-under=20` scoped to
  `app/services`, but CI overrides it to 0.)
- **Codecov upload uses `fail_ci_if_error: false`** with no status gate, so a
  coverage drop is visible in the Codecov PR comment but cannot block a merge.
- The only coverage-shaped *gate* is the per-PR **diff-cover** step
  (changed-lines ≥ 80%), and it is **`continue-on-error: true`** (advisory)
  until the smoke suite is deemed stable.
- `.coveragerc` currently `omit`s several large services from measurement, so
  the reported percentage is not a whole-codebase figure.

Establishing a real ratchet (un-omit the services, set `--cov-fail-under` to a
floor at/below current, drop the `=0` override, promote diff-cover to a hard
gate) is tracked as follow-up work — see the 2026-07 test audit.

### 3. CodeQL Analysis (`codeql.yml`)

**Trigger**: Push to `main`, Pull Requests, Weekly schedule (Thursday 11:34 PM)

**Purpose**: Perform static code analysis for security vulnerabilities

**Languages Analyzed**:
- Python
- TypeScript/JavaScript
- GitHub Actions

**Features**:
- Automated security vulnerability detection
- Integration with GitHub Security tab
- Custom query support

### 4. Dependency Updates (`dependency-update.yml`)

**Trigger**: Weekly (Monday 9 AM UTC), Manual dispatch

**Purpose**: Automatically update dependencies and create PRs

**Jobs**:
- **update-dependencies**: Updates npm and pip packages
- **security-audit**: Runs security audits and creates issues for vulnerabilities

**Features**:
- Separate PRs for frontend and backend updates
- Security vulnerability detection with severity levels
- Automatic issue creation for critical vulnerabilities
- Smart issue updates to avoid duplicates
- Preserves lockfiles for reproducible builds

### 5. Database Maintenance (`database-maintenance.yml`)

**Trigger**: Daily (2 AM UTC), Manual dispatch

**Purpose**: Database backup and maintenance tasks

**Jobs**:
- **database-backup**: Creates daily backups and uploads to S3
- **database-maintenance**: Runs VACUUM, ANALYZE, or REINDEX
- **cleanup-old-data**: Removes old draft applications and orphaned files

**Features**:
- Automated daily backups with 30-day retention
- Manual maintenance task execution
- Old data cleanup to prevent database bloat
- Database statistics reporting

### 6. Release Management (`release.yml`)

**Trigger**: Manual dispatch

**Purpose**: Manage version releases and deployments

**Jobs**:
- **prepare-release**: Version bumping and changelog generation
- **create-release**: Docker image building and GitHub release creation
- **post-release**: Notifications and announcements

**Features**:
- Semantic versioning support
- Automated changelog generation
- Multi-stage release process
- Deployment artifacts creation
- Release announcements

## Testing Infrastructure

### Test Types and Coverage

1. **Unit Tests** (aspirational target 90%; NOT enforced — see §2)
   - Backend: pytest with async support
   - Frontend: Jest with React Testing Library

2. **Integration Tests**
   - Database operations with real PostgreSQL
   - Redis caching tests
   - MinIO file storage tests

3. **API Tests**
   - Endpoint validation
   - Authentication/authorization
   - Rate limiting verification

4. **E2E Tests**
   - Multi-browser support (Chrome, Firefox, Safari)
   - User workflow validation
   - Cross-browser compatibility

5. **Security Tests**
   - Python: Bandit, Safety, Semgrep
   - JavaScript: npm audit
   - Container scanning with Trivy

6. **Performance Tests**
   - k6 load testing
   - Response time validation (p95 < 600ms)
   - Concurrent user simulation

### Local Testing

#### Quick Test Runner
```bash
# Run all tests with coverage
./run-tests.sh all

# Run specific test types
./run-tests.sh backend
./run-tests.sh frontend
./run-tests.sh e2e
./run-tests.sh performance

# Quick smoke tests
./run-tests.sh quick

# Clean test artifacts
./run-tests.sh clean
```

#### Pre-commit Hooks
```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Run hooks manually
pre-commit run --all-files
```

### Test Configuration Files

- **Backend**:
  - `pytest.ini`: pytest configuration with coverage settings
  - `.coveragerc`: Coverage.py config (source=app/services, `fail_under=20`; CI overrides to 0 — not gated)
  - `conftest.py`: Shared fixtures and test utilities

- **Frontend**:
  - `jest.config.js`: Jest configuration
  - `jest.config.standalone.js`: unused alternate config (not referenced by any npm script or CI)

## Environment Variables and Secrets

### Required GitHub Secrets

```yaml
# Authentication
GITHUB_TOKEN         # Automatically provided by GitHub
CODECOV_TOKEN       # For coverage reporting

# Deployment
DEPLOY_KEY          # SSH key for deployment
PRODUCTION_API_URL  # Production API endpoint

# Database
PRODUCTION_DATABASE_URL  # PostgreSQL connection string

# AWS (for backups)
AWS_ACCESS_KEY_ID      # AWS access key
AWS_SECRET_ACCESS_KEY  # AWS secret key
AWS_REGION            # AWS region
BACKUP_S3_BUCKET      # S3 bucket for backups
```

## Troubleshooting

### Common Issues

1. **Test Coverage Reporting** (no hard threshold today — see §2)
   - Check coverage reports in artifacts
   - Add tests for uncovered code paths
   - Use `# pragma: no cover` sparingly for unreachable code

2. **E2E Tests Failing**
   - Check if all services are healthy: `docker ps`
   - View logs: `./test-docker.sh logs`
   - Ensure ports 3000, 8000, 5432, 6379, 9000, 9001 are free
   - Check browser compatibility issues

3. **Performance Tests Failing**
   - Review k6 test results in artifacts
   - Check for N+1 queries in backend
   - Optimize database queries
   - Add caching where appropriate

4. **Security Vulnerabilities**
   - Review security scan results
   - Update vulnerable dependencies
   - Check for false positives
   - Add security exceptions with justification

### Debugging Workflows

```yaml
# Add debug logging to a step
- name: Debug step
  run: |
    echo "::debug::Debug message"
    echo "ENV_VAR=$ENV_VAR"
  env:
    ACTIONS_STEP_DEBUG: true
```

## Best Practices

1. **Maintain High Test Coverage**
   - Write tests for new features before implementation (TDD)
   - Aim to raise coverage (no hard threshold today — see §2)
   - Focus on critical business logic

2. **Use Test Markers**
   - Mark slow tests: `@pytest.mark.slow`
   - Mark smoke tests: `@pytest.mark.smoke`
   - Run specific markers locally for faster feedback

3. **Optimize Test Performance**
   - Use test fixtures efficiently
   - Run tests in parallel where possible
   - Mock external services in unit tests

4. **Security First**
   - Address vulnerabilities immediately
   - Keep dependencies updated
   - Regular security audits

5. **Monitor CI/CD Performance**
   - Track workflow execution times
   - Optimize slow jobs
   - Use caching effectively

## Maintenance Schedule

- **Daily**: Database backups (2 AM UTC)
- **Weekly**: Dependency updates (Monday 9 AM UTC)
- **Weekly**: CodeQL analysis (Thursday 11:34 PM UTC)
- **On-demand**: Performance tests, release management

## Metrics and Monitoring

### Key Metrics
- Test coverage: aspirational 90%+ (measured/reported, not gated — see §2)
- CI/CD pipeline duration: Target < 15 minutes
- Test flakiness: Target < 1%
- Security vulnerabilities: Target 0 critical/high

### Monitoring Dashboard
- GitHub Actions tab for workflow status
- Coverage reports in artifacts
- Security alerts in GitHub Security tab
- Performance test results in artifacts

## Contact

For CI/CD issues or questions:
- Create an issue with the `ci/cd` label
- Check workflow run logs for detailed error messages
- Review test reports in artifacts
- Consult this guide for common solutions