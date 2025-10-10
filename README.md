# Scholarship Management System

A full-stack platform for managing scholarship applications, reviews, and system configuration. The repository contains a FastAPI backend, a Next.js 15 frontend, shared infrastructure for file storage and messaging, and tooling for local development, testing, and deployment.

## Table of Contents
- [Project Overview](#project-overview)
- [Architecture Highlights](#architecture-highlights)
- [Directory Structure](#directory-structure)
- [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Option A: Run Everything with Docker](#option-a-run-everything-with-docker)
  - [Option B: Run Services Manually](#option-b-run-services-manually)
- [Environment Configuration](#environment-configuration)
- [Database & Seed Data](#database--seed-data)
- [Testing & Quality](#testing--quality)
- [Frontend Overview](#frontend-overview)
- [Backend Overview](#backend-overview)
- [Supporting Services](#supporting-services)
- [Useful Tooling](#useful-tooling)
- [Deployment](#deployment)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Project Overview
- Multi-role access for students, professors, college staff, admins, and super admins.
- End-to-end scholarship lifecycle: application authoring, configurable review pipelines, quota and rule management, automated notifications, and historical reporting.
- Bilingual student experience (Traditional Chinese and English) with dynamic content switching.
- Secure file handling via MinIO, optional OCR, and mock SSO / mock student-information services for development.

## Architecture Highlights
- **Frontend**: Next.js 15 (App Router) with TypeScript, shadcn/ui component system, Tailwind CSS, React Query for data fetching, and SWR for realtime counters.
- **Backend**: FastAPI with async SQLAlchemy, Alembic migrations, Pydantic v2 schemas, granular service layer, and MinIO integration for file storage.
- **Infrastructure**: PostgreSQL, Redis, MinIO, optional Nginx reverse proxy, and a mock student API for local development scenarios.
- **Tooling**: Makefile targets, Docker Compose stacks for dev/staging/prod, scripts for lookup-table bootstrapping, k6 smoke tests, and rich documentation under `docs/`.

## Directory Structure
```
.
├─ backend/                # FastAPI service (APIs, models, services, Alembic)
├─ frontend/               # Next.js application and shared UI primitives
├─ docs/                   # Architecture, feature, and setup documentation
├─ mock-student-api/       # Mock NYCU student-information service used in dev
├─ nginx/                  # Nginx configuration for container deployments
├─ perf/                   # k6 smoke/performance scripts
├─ scripts/                # Helper scripts (migrations, maintenance, etc.)
├─ test-docker.sh          # Convenience launcher for Docker-based dev stack
├─ docker-compose*.yml     # Compose definitions for dev/staging/production
├─ Makefile                # Unified developer workflows (setup, lint, test)
└─ SECRETS_SETUP.md        # Guidance for managing secrets across environments
```

## Getting Started

### Prerequisites
- Docker Engine & Docker Compose v2 (recommended for the quickest setup)
- Python 3.10+ (if running the backend locally without Docker)
- Node.js 22+ and npm 10+ (if running the frontend locally)
- pnpm/yarn are optional; npm scripts are the source of truth

### Option A: Run Everything with Docker
```bash
# Start the full stack (PostgreSQL, Redis, MinIO, mock student API, backend, frontend)
./test-docker.sh start

# Check service status and health endpoints
./test-docker.sh status

# Stop and remove containers/volumes
./test-docker.sh stop
```
By default the development stack exposes:
- Frontend: http://localhost:3000
- Backend API & OpenAPI docs: http://localhost:8000 and http://localhost:8000/docs
- Mock student API: http://localhost:8080
- MinIO console: http://localhost:9001 (access keys in backend `.env`)
- PostgreSQL: localhost:5432, Redis: localhost:6379

Use the helper commands `./test-docker.sh init-lookup` and `./test-docker.sh init-testdata` after the stack is up to populate reference data and demo users.

### Option B: Run Services Manually
1. **Install dependencies and scaffold env files**
   ```bash
   make setup       # installs backend + frontend dependencies and copies env templates
   ```
2. **Start both servers with one command**
   ```bash
   make dev         # spawns uvicorn + next dev with live reload
   ```
   or run them individually:
   ```bash
   # Backend
   cd backend
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

   # Frontend
   cd frontend
   npm run dev
   ```
3. Ensure PostgreSQL, Redis, and MinIO are available locally (Docker compose or native installs). Update the backend `.env` if you use non-default ports.

## Environment Configuration
- `backend/.env.example` – copy to `backend/.env` and adjust database credentials, MinIO keys, JWT secret, and feature toggles. Many optional integrations (OCR, employee API, SSO) are disabled by default.
- `frontend/.env.local` – create manually if it does not exist. Minimum configuration:
  ```
  NEXT_PUBLIC_API_URL=http://localhost:8000
  ```
- `mock-student-api/README.md` describes environment variables for the mock service.
- See `SECRETS_SETUP.md` for recommended secret-management workflows in staging/production.

## Database & Seed Data
- Alembic migrations live under `backend/alembic`. Apply them with `alembic upgrade head` (or `make`/Docker helpers).
- `test-docker.sh init-lookup` populates lookup tables (departments, degrees, etc.).
- `test-docker.sh init-testdata` loads sample users, scholarships, application fields, and announcements (requires the dev stack to be running).
- `python -m app.seed` provides additional seeding utilities if you prefer running them manually.

## Testing & Quality
- `make test` runs backend pytest suites followed by frontend Jest tests (`npm run test:ci`).
- `make test-backend` / `make test-frontend` run each side independently.
- `make lint` formats code (Black + isort + ESLint + Prettier). `make check-types` runs mypy and TypeScript checks.
- `make security-scan` executes Bandit, Safety, and npm audit.
- `perf/smoke.js` is a k6 script that hits the health endpoint; execute with `k6 run perf/smoke.js` (`BASE_URL` env overrides the host).

## Frontend Overview
- Next.js App Router app under `frontend/app`, with global providers defined in `frontend/app/layout.tsx` (AuthProvider, React Query provider, SWR defaults, notification context, debug panel).
- Feature modules and composite components live in `frontend/components/`, with admin-specific panels grouped under `frontend/components/admin/`.
- Shared UI primitives (shadcn/ui) are in `frontend/components/ui/`; domain-specific hooks (`frontend/hooks/`) cover auth, admin dashboards, notification polling, etc.
- The REST client resides in `frontend/lib/api.ts` (hand-written wrapper) and `frontend/lib/api/typed-client.ts` (OpenAPI-generated helper).
- State/data fetching leverages React Query for standard queries/mutations and SWR for lightweight counters (e.g., notifications).
- Unit tests live beside code (`__tests__` folders) and use Testing Library; Jest configuration files are in the project root (`frontend/jest.config.js`, etc.).

## Backend Overview
- FastAPI routers organized under `backend/app/api/v1/`; each endpoint delegates to service modules under `backend/app/services/`.
- Domain models (`backend/app/models/`) expose SQLAlchemy ORM entities with async session support (`backend/app/db/session.py`).
- Schemas in `backend/app/schemas/` use Pydantic v2 for validation/serialization.
- Core infrastructure (`backend/app/core/`) handles configuration, security, background scheduler initialisation, MinIO client management, and exception handling.
- Integrations (SSO, student API, bank verification) are abstracted in `backend/app/integrations/`.
- Tests are located in `backend/app/tests/`, covering API endpoints, services, and critical workflows.

## Supporting Services
- **PostgreSQL** – primary relational database; credentials configurable via `.env`.
- **Redis** – caching and background job assistance.
- **MinIO** – S3-compatible storage for uploaded documents and roster exports.
- **Mock Student API** – standalone FastAPI service emulating NYCU student data responses for local testing (`mock-student-api/`).
- **Nginx** – optional reverse proxy for production/staging (`nginx/nginx.conf`).

## Useful Tooling
- `Makefile` – central entry point for setup, dev, testing, linting, building, and scanning.
- `test-docker.sh` – spins up/shuts down the entire dev stack and initializes reference data.
- `docker-manager.sh` – helper for production/staging Docker hosts.
- `perf/smoke.js` – k6 smoke test.

## Deployment
- Docker Compose blueprints: `docker-compose.prod.yml`, `docker-compose.staging.yml`, and `docker-compose.prod-db.yml` cover multi-service deployments.
- `DEPLOYMENT.md` outlines production considerations, including Nginx routing, SSL termination, and scaling tips.
- Container images can be built via `make build-docker` or the individual Dockerfiles located in `backend/` and `frontend/`.

## Documentation
Key entry points under `docs/`:
- `docs/architecture/system-overview.md` – high-level architecture and data flow.
- `docs/getting-started/quick-start.md` and `docs/getting-started/development-setup.md` – detailed setup guides.
- `docs/features/` – feature-specific walkthroughs (user management, authentication, etc.).
- `docs/deployment/` – staging/production deployment guidance.
- `Table_Description.md` – database table reference.

## Contributing
1. Fork the repository and create a feature branch (`git checkout -b feature/my-change`).
2. Ensure your environment passes `make lint`, `make check-types`, and `make test`.
3. Submit a pull request with context and testing notes.
4. For significant changes, update relevant documentation under `docs/`.

## License
A dedicated license file is not bundled with this repository. Contact the project maintainers for guidance before redistributing or using the code outside the intended environments.
