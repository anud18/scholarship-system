# Scholarship Management System

A comprehensive, configuration-driven platform for managing scholarship applications, reviews, and administrative workflows. Built with FastAPI backend and Next.js 15 frontend, featuring multi-role access control, bilingual support, and complete observability.

## Table of Contents

- [Project Overview](#project-overview)
- [Core Features](#core-features)
- [Technology Stack](#technology-stack)
- [Directory Structure](#directory-structure)
- [Quick Start](#quick-start)
  - [Prerequisites](#prerequisites)
  - [Option A: Complete Setup with Makefile (Recommended)](#option-a-complete-setup-with-makefile-recommended)
  - [Option B: Docker Compose Only](#option-b-docker-compose-only)
  - [Option C: Manual Setup](#option-c-manual-setup)
- [Environment Configuration](#environment-configuration)
- [Development Workflow](#development-workflow)
- [Makefile Commands Reference](#makefile-commands-reference)
- [Database Management](#database-management)
- [Testing](#testing)
- [Monitoring & Observability](#monitoring--observability)
- [Deployment](#deployment)
- [Development Guidelines](#development-guidelines)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Project Overview

This scholarship management system provides a complete lifecycle solution for academic scholarship programs:

- **Multi-Role Access**: Supports students, professors, college staff, administrators, and super administrators
- **End-to-End Workflow**: Application creation, configurable review pipelines, quota management, automated notifications, and historical reporting
- **Bilingual Support**: Traditional Chinese and English with dynamic content switching
- **Configuration-Driven**: Add new scholarship types through database configuration without code changes
- **Secure File Handling**: Three-layer file architecture with MinIO object storage
- **Development-Friendly**: Mock SSO and student information services for local development

## Core Features

### 1. Configuration-Driven Scholarship System
- Define scholarship types, rules, and workflows in the database
- No code changes required when adding new scholarship programs
- Flexible quota management (none, simple, college-based, matrix-based)
- Dynamic application fields per scholarship type

### 2. Sequential Application ID System
- Structured format: `APP-{academic_year}-{semester_code}-{sequence:05d}`
- Example: `APP-113-1-00001` (Academic Year 113, First Semester, Sequence 1)
- Concurrency-safe sequence generation with database locking
- Independent sequences per academic year and semester

### 3. Three-Layer File Upload Architecture
```
Frontend → Next.js Proxy → FastAPI → MinIO
```
- Token authentication via Next.js proxy
- Internal Docker network communication
- Secure path validation and virus scanning
- Support for PDF preview with proper headers

### 4. Strict Type Safety
- Enum consistency across Python, TypeScript, and PostgreSQL
- Automatic OpenAPI type generation for frontend
- Pydantic v2 validation on backend
- Zod validation on frontend

### 5. Standardized API Responses
All endpoints return consistent format:
```json
{
  "success": true,
  "message": "Operation successful",
  "data": { }
}
```

### 6. Built-in Observability
- Prometheus metrics for performance monitoring
- Grafana dashboards for visualization
- Database connection pool metrics
- Request latency tracking

## Technology Stack

### Backend
- **Python 3.11** - Modern async/await support
- **FastAPI** - High-performance async web framework
- **PostgreSQL 15** - Primary relational database with async support
- **Redis** - Caching and session management
- **MinIO** - S3-compatible object storage
- **SQLAlchemy 2.0** - Async ORM
- **Alembic** - Database migrations
- **Pydantic v2** - Data validation and serialization

### Frontend
- **Next.js 15** - React framework with App Router
- **React 18** - UI library with TypeScript
- **shadcn/ui** - Component library built on Radix UI
- **Tailwind CSS** - Utility-first CSS framework
- **React Hook Form** - Form state management
- **Zod** - Schema validation
- **React Query (TanStack Query)** - Data fetching and caching
- **SWR** - Real-time data synchronization

### DevOps & Infrastructure
- **Docker** & **Docker Compose** - Containerization
- **NGINX** - Reverse proxy
- **Prometheus** - Metrics collection
- **Grafana** - Metrics visualization
- **pytest** - Backend testing
- **Jest** - Frontend testing
- **k6** - Performance testing

### Development Tools
- **Makefile** - Unified developer workflows
- **Mock Student API** - Standalone FastAPI service for development
- **pre-commit** - Git hooks for code quality
- **Black** - Python code formatting
- **ESLint** & **Prettier** - JavaScript/TypeScript linting

## Directory Structure

```
scholarship-system/
├── backend/                    # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/  # API route handlers
│   │   ├── core/              # Configuration, auth, scheduler
│   │   ├── db/                # Database session management
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic schemas
│   │   ├── services/          # Business logic layer
│   │   ├── integrations/      # External service clients
│   │   ├── middleware/        # Custom middleware
│   │   └── tests/             # Backend test suite
│   ├── alembic/               # Database migrations
│   └── requirements.txt       # Python dependencies
│
├── frontend/                   # Next.js 15 application
│   ├── app/                   # App Router pages
│   ├── components/            # React components
│   │   ├── ui/               # shadcn/ui primitives
│   │   └── admin/            # Admin-specific components
│   ├── hooks/                 # Custom React hooks
│   ├── lib/                   # Utilities and API clients
│   │   └── api/              # Typed API client
│   └── styles/                # Global styles
│
├── docs/                       # Documentation
│   ├── architecture/          # System design docs
│   ├── development/           # Development guides
│   └── specifications/        # Requirements
│
├── mock-student-api/          # Mock NYCU student API
├── monitoring/                 # Grafana & Prometheus configs
├── nginx/                      # NGINX configuration
├── perf/                       # k6 performance tests
├── scripts/                    # Utility scripts
│   ├── reset_database.sh      # Database rebuild automation
│   └── validate_enum_consistency.py  # Enum validation
│
├── .claude/                    # Development guidelines
│   └── CLAUDE.md              # Core development principles
│
├── docker-compose.dev.yml      # Development environment
├── docker-compose.staging.yml  # Staging environment
├── docker-compose.prod.yml     # Production environment
├── Makefile                    # Unified developer commands
└── README.md                   # This file
```

## Quick Start

### Prerequisites

- **Docker Engine** & **Docker Compose v2** (recommended for fastest setup)
- **Python 3.11+** (if running backend locally)
- **Node.js 22+** and **npm 10+** (if running frontend locally)
- **Make** (optional, for Makefile commands)

### Option A: Complete Setup with Makefile (Recommended)

The fastest way to get everything running:

```bash
# Initialize entire development environment (Docker + Database + Test Data)
make init-all
```

This single command will:
1. Start all Docker services (PostgreSQL, Redis, MinIO, backend, frontend)
2. Initialize lookup tables (degrees, departments, enrollment types)
3. Create test users and sample scholarships
4. Wait 10-15 minutes for complete initialization

After initialization completes:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001

Test user accounts (see [Database Management](#database-management) for credentials).

### Option B: Docker Compose Only

For manual control over initialization:

```bash
# Start all services
docker compose -f docker-compose.dev.yml up -d

# Initialize lookup tables (reference data)
make init-lookup

# Initialize test data (users, scholarships)
make init-testdata
```

Check service health:
```bash
docker compose -f docker-compose.dev.yml ps
make health-check
```

Stop services:
```bash
docker compose -f docker-compose.dev.yml down
```

### Option C: Manual Setup

For development without Docker:

```bash
# 1. Install dependencies
make install

# 2. Setup environment files
make setup

# 3. Start PostgreSQL, Redis, and MinIO
# (Use Docker Compose for infrastructure only)
docker compose -f docker-compose.dev.yml up -d postgres redis minio

# 4. Run database migrations
cd backend && alembic upgrade head

# 5. Start development servers
make dev
```

The `make dev` command starts both backend (port 8000) and frontend (port 3000) with hot reload.

## Environment Configuration

### Security First Approach

This project follows security best practices for credential management:

- ✅ **Environment-Specific Files**: `.env.dev`, `.env.staging`, `.env.prod`
- ✅ **No Hardcoded Credentials**: All secrets via environment variables
- ✅ **Git Protection**: All `.env` files (except `.example`) are `.gitignore`d
- ✅ **Automated Validation**: Pre-commit hooks and CI/CD checks
- ✅ **Template Files**: `.env.example` and `.env.prod.example` for setup guidance

📖 **See [SECURITY.md](./SECURITY.md) for comprehensive security guidelines**

### Quick Setup

**For Local Development:**
```bash
# Copy pre-configured development environment
cp .env.dev .env

# Or create from template
cp .env.example .env
# Edit .env with your local configuration
```

**For Production:**
```bash
# Start from production template
cp .env.prod.example .env.prod

# Replace ALL CHANGEME values with actual secrets
# Generate SECRET_KEY: openssl rand -hex 32
vim .env.prod

# Validate security before deployment
./scripts/validate_security.sh
```

### Environment File Structure

```bash
.env.example          # Template with documentation (committed)
.env.dev              # Development defaults (committed, safe values)
.env.staging          # Staging credentials (NOT committed)
.env.prod.example     # Production template (committed, no secrets)
.env.prod             # Production credentials (NOT committed)
```

### Required Environment Variables

**Critical Security Settings:**
```bash
SECRET_KEY=generate-with-openssl-rand-hex-32  # Min 32 characters
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=strong_password_here
MINIO_ACCESS_KEY=your_minio_access_key
MINIO_SECRET_KEY=your_minio_secret_key
```

**See `.env.example` for complete configuration documentation**

### Security Validation

Before committing or deploying:

```bash
# Validate security configuration
./scripts/validate_security.sh

# Run pre-commit checks
pre-commit run --all-files

# Check for secrets
detect-secrets scan --baseline .secrets.baseline
```

## Development Workflow

### Starting Development

```bash
# Start all services and watch for changes
make dev
```

This starts:
- Backend on http://localhost:8000 (with auto-reload)
- Frontend on http://localhost:3000 (with hot module replacement)

### Code Quality

```bash
# Format and lint all code
make lint

# Type checking
make check-types

# Security scan
make security-scan
```

### Database Operations

```bash
# Create new migration
cd backend && alembic revision -m "description"

# Apply migrations
make db-migrate

# Reset database (WARNING: deletes all data)
./scripts/reset_database.sh
```

### OpenAPI Type Generation

After modifying backend schemas or endpoints:

```bash
# Ensure backend is running
cd frontend && npm run api:generate
git add lib/api/generated/schema.d.ts
```

## Makefile Commands Reference

### Setup Commands
- `make install` - Install all dependencies (backend + frontend)
- `make setup` - Complete project setup with env files
- `make init-all` - Full initialization (Docker + DB + test data)
- `make init-lookup` - Initialize lookup tables only
- `make init-testdata` - Initialize test users and data

### Development Commands
- `make dev` - Start both backend and frontend with hot reload
- `make dev-backend` - Start backend only
- `make dev-frontend` - Start frontend only
- `make dev-safe` - Test API connection before starting frontend

### Testing Commands
- `make test` - Run all tests (backend + frontend)
- `make test-backend` - Run backend tests only
- `make test-frontend` - Run frontend tests only
- `make test-coverage` - Run tests with coverage reports
- `make test-e2e` - Run end-to-end tests

### Code Quality Commands
- `make lint` - Lint and format all code
- `make check-types` - Check TypeScript and Python types
- `make security-scan` - Run security scans

### Docker Commands
- `make docker-up` - Start all services with Docker Compose
- `make docker-down` - Stop all services
- `make docker-restart` - Restart all services
- `make docker-logs` - Show logs from all services
- `make docker-clean` - Clean up Docker resources

### Database Commands
- `make db-migrate` - Run database migrations
- `make db-reset` - Reset database (with confirmation)
- `make db-seed` - Seed database with sample data

### Utility Commands
- `make clean` - Clean up generated files and caches
- `make health-check` - Check if all services are running
- `make version` - Show version information
- `make env-check` - Check environment configuration
- `make help` - Show all available commands

## Database Management

### Alembic Migrations

Always include existence checks in migrations:

```python
# ✅ CORRECT - Safe migration
def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'new_table' not in existing_tables:
        op.create_table('new_table', ...)
```

### Database Reset

Use the automated script for clean rebuilds:

```bash
# Preview steps
./scripts/reset_database.sh --dry-run

# Execute reset
./scripts/reset_database.sh
```

### Lookup Tables Initialization

The system requires reference data before test data:

```bash
make init-lookup
```

This initializes:
- 3 degree types (博士, 碩士, 學士)
- 16 student identity types
- 11 studying status types
- 8 school identity types
- 29 NYCU academies/colleges
- 16 departments
- 27 enrollment types

### Test Data

After lookup tables are initialized:

```bash
make init-testdata
```

**Test User Accounts:**
| Role | Username | Password |
|------|----------|----------|
| Admin | admin | admin123 |
| Super Admin | super_admin | super123 |
| Professor | professor | professor123 |
| College | college | college123 |
| Student (學士) | stu_under | stuunder123 |
| Student (博士) | stu_phd | stuphd123 |
| Student (逕讀博士) | stu_direct | studirect123 |
| Student (碩士) | stu_master | stumaster123 |
| Student (陸生) | stu_china | stuchina123 |

## Testing

### Backend Tests

```bash
# Run all backend tests
cd backend && python -m pytest app/tests -v

# Run with coverage
python -m pytest app/tests --cov=app --cov-report=html

# Run specific test file
python -m pytest app/tests/test_auth.py -v
```

### Frontend Tests

```bash
# Run all frontend tests
cd frontend && npm run test:ci

# Watch mode for development
npm run test:watch

# Debug mode
npm run test:debug
```

### Performance Testing

```bash
# Run k6 smoke test
k6 run perf/smoke.js

# Custom base URL
BASE_URL=http://localhost:8000 k6 run perf/smoke.js
```

## Monitoring & Observability

### Prometheus Metrics

The backend exposes metrics at:
- **Endpoint**: http://localhost:8000/metrics
- **Metrics**: Request latency, database pool stats, custom business metrics

### Grafana Dashboards

Access Grafana at http://localhost:3001 (when monitoring stack is running):

```bash
docker compose -f docker-compose.prod-db-monitoring.yml up -d
```

Default credentials: admin/admin

### Health Checks

```bash
# Check all services
make health-check

# Backend health endpoint
curl http://localhost:8000/health

# Database connection check
curl http://localhost:8000/health/db
```

## Deployment

### Development Environment
```bash
docker compose -f docker-compose.dev.yml up -d
```

### Staging Environment
```bash
docker compose -f docker-compose.staging.yml up -d
```

### Production Environment
```bash
docker compose -f docker-compose.prod.yml up -d
```

### Production Considerations

1. **SSL/TLS**: Configure NGINX with valid certificates
2. **Environment Variables**: Use secrets management for sensitive data (never commit `.env` files)
3. **Database Backups**: Set up automated PostgreSQL backups
4. **Monitoring**: Deploy full monitoring stack with Prometheus and Grafana
5. **Logging**: Configure centralized logging
6. **Resource Limits**: Set appropriate container resource limits

See `monitoring/PRODUCTION_RUNBOOK.md` and `monitoring/GITHUB_DEPLOYMENT.md` for detailed deployment guides.

## Development Guidelines

**IMPORTANT**: Read `.claude/CLAUDE.md` before contributing. Key principles:

### 1. Error Handling
Never return fallback data. Always throw errors:

```python
# ✅ CORRECT
def get_scholarship_data():
    scholarship = db.get_scholarship()
    if not scholarship:
        raise ScholarshipNotFoundError("No scholarship data available")
    return scholarship
```

### 2. Configuration-Driven Logic
Use database configuration instead of hardcoded logic:

```python
# ✅ CORRECT
if scholarship.config.requires_interview:
    # interview logic
```

### 3. Enum Consistency
Maintain consistency across all layers:
- **Python**: Lowercase enum values
- **TypeScript**: UPPERCASE member names, lowercase values
- **PostgreSQL**: Lowercase enum values

Run validation script:
```bash
python scripts/validate_enum_consistency.py
```

### 4. API Response Format
All endpoints must return:
```python
{
    "success": bool,
    "message": str,
    "data": any
}
```

### 5. Path Security
Always validate file paths:
```python
if ".." in filename or "/" in filename or "\\" in filename:
    raise HTTPException(status_code=400, detail="無效的檔案名稱")
```

### 6. OpenAPI Type Generation
After schema changes:
```bash
cd frontend && npm run api:generate
```

## Documentation

### Architecture Documentation
- `docs/architecture/system-overview.md` - High-level architecture
- `docs/architecture/database-schema.md` - Database design
- `docs/architecture/api-design.md` - API design principles

### Development Guides
- `docs/development/migration-guides.md` - Database migration guides
- `.claude/CLAUDE.md` - Core development principles (MUST READ)

### Database Reference
- `docs/Table_Description.md` - Complete database table reference

### API Documentation
- **OpenAPI Docs**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Contributing

1. **Fork & Branch**: Create feature branch from `main`
   ```bash
   git checkout -b feature/my-feature
   ```

2. **Read Guidelines**: Review `.claude/CLAUDE.md` thoroughly

3. **Code Quality**: Ensure all checks pass
   ```bash
   make lint
   make check-types
   make test
   ```

4. **Enum Consistency**: If modifying enums, validate:
   ```bash
   python scripts/validate_enum_consistency.py
   ```

5. **Type Generation**: If modifying schemas:
   ```bash
   cd frontend && npm run api:generate
   ```

6. **Commit**: Use English commit messages
   ```bash
   git commit -m "feat: add new feature"
   ```

7. **Pull Request**: Submit PR with:
   - Clear description
   - Testing notes
   - Documentation updates (if applicable)

## License

This project does not include a public license. Contact the maintainers for usage permissions before redistributing or deploying outside the intended environments.

---

**Quick Links:**
- [Makefile Commands](#makefile-commands-reference)
- [Development Guidelines](/.claude/CLAUDE.md)
- [API Documentation](http://localhost:8000/docs)
- [Architecture Overview](/docs/architecture/system-overview.md)
- [Database Schema](/docs/Table_Description.md)
