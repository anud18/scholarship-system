# Development Setup Guide

## Prerequisites

- **Docker & Docker Compose**: For containerized development
- **Node.js 18+**: For frontend development
- **Python 3.11+**: For backend development
- **Git**: Version control

## Development Workflow

### 1. Initial Setup

```bash
# Clone the repository
git clone <repository-url>
cd scholarship-system

# Copy environment file
cp .env.example .env
```

### 2. Start Development Environment

```bash
# Start all services
docker compose -f docker-compose.dev.yml up -d

# Verify services are running
docker compose -f docker-compose.dev.yml ps
```

### 3. Development Commands

#### Database Operations
```bash
# Reset database (includes migrations and seed data)
./scripts/reset_database.sh

# Run migrations only
docker exec scholarship_backend_dev alembic upgrade head

# Run seed scripts
docker exec scholarship_backend_dev python -m app.db.init_db
```

#### Testing
```bash
# Backend tests
docker exec scholarship_backend_dev python -m pytest --disable-warnings -v

# Frontend tests
cd frontend && npm test

# E2E tests
cd frontend && npm run test:e2e
```

## Local Development (Without Docker)

### Backend Setup
```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export SECRET_KEY="your-secret-key"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/db"

# Run development server
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend

# Install dependencies
npm install

# Run development server
npm run dev
```

## Development Tools

### Code Quality
- **Backend**: Flake8 for Python linting
- **Frontend**: ESLint for TypeScript/React
- **Pre-commit hooks**: Automated code formatting

### Testing Tools
- **Backend**: pytest with coverage
- **Frontend**: Jest + React Testing Library
- **E2E**: Playwright for end-to-end testing

### Development Features

#### Developer Profiles
Create isolated test user profiles using the frontend Developer Profile Manager:

- Access at http://localhost:3000 (development mode only)
- Use the Developer Profile Manager component below the login form
- Available profile types:
  - Student profiles (freshman, graduate, phd)
  - Staff profiles (professor, admin, super_admin)
  - Custom profiles for specific testing

#### Hot Reloading
- **Frontend**: Automatic reload on file changes
- **Backend**: Uvicorn auto-reload for Python changes
- **Database**: Alembic migrations for schema changes

## Environment Variables

### Required Variables
```bash
# Security
SECRET_KEY=your-jwt-secret-at-least-32-characters
ALGORITHM=HS256

# Database
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/db
DATABASE_URL_SYNC=postgresql://user:pass@localhost:5432/db

# File Storage
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=10485760

# External Services
REDIS_URL=redis://localhost:6379/0
MINIO_ENDPOINT=localhost:9000
```

### Optional Variables
```bash
# Development
DEBUG=true
CORS_ORIGINS=http://localhost:3000,http://localhost:3001

# Email (for notifications)
SMTP_HOST=localhost
SMTP_PORT=587
SMTP_USERNAME=your-email
SMTP_PASSWORD=your-password

# Monitoring
SENTRY_DSN=your-sentry-dsn
```

## Debugging

### Backend Debugging
```bash
# View API logs
docker compose -f docker-compose.dev.yml logs -f backend

# Debug mode (local development)
DEBUG=true uvicorn app.main:app --reload

# Database debugging
docker compose -f docker-compose.dev.yml logs -f postgres
```

### Frontend Debugging
```bash
# View frontend logs
docker compose -f docker-compose.dev.yml logs -f frontend

# Debug mode
npm run dev

# Browser developer tools
# React DevTools extension recommended
```

## Common Issues

### Port Conflicts
Ensure these ports are available:
- 3000 (Frontend)
- 8000 (Backend)
- 5432 (PostgreSQL)
- 6379 (Redis)
- 9000/9001 (MinIO)

### Database Connection Issues
```bash
# Reset database
./scripts/reset_database.sh

# Check database status
docker compose -f docker-compose.dev.yml logs -f postgres
```

### File Permission Issues
```bash
# Fix script permissions
chmod +x scripts/reset_database.sh
```

## Next Steps

1. Read the [Testing Guide](../development/testing.md)
2. Explore [User Management Features](../features/user-management.md)
3. Set up your [Developer Profiles](../features/developer-profiles.md)
4. Review the [CI/CD Pipeline](../development/ci-cd.md)
