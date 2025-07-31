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

# Make scripts executable
chmod +x test-docker.sh
chmod +x test-developer-profiles.sh
```

### 2. Start Development Environment

```bash
# Start all services
./test-docker.sh start

# Verify services are running
./test-docker.sh status
```

### 3. Development Commands

#### Database Operations
```bash
# Run migrations
./test-docker.sh migrate

# Seed test data
./test-docker.sh seed

# Reset database
./test-docker.sh reset-db
```

#### Testing
```bash
# Run all tests
./test-docker.sh test

# Backend tests only
./test-docker.sh test-backend

# Frontend tests only
./test-docker.sh test-frontend

# E2E tests
./test-docker.sh test-e2e
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
Create isolated test user profiles:

```bash
# Create basic profiles for your dev ID
./test-developer-profiles.sh your-dev-id

# Available profile types:
# - Student profiles (freshman, graduate, phd)
# - Staff profiles (professor, admin, super_admin)
# - Custom profiles for specific testing
```

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
./test-docker.sh logs backend

# Debug mode
DEBUG=true uvicorn app.main:app --reload

# Database debugging
./test-docker.sh logs postgres
```

### Frontend Debugging
```bash
# View frontend logs
./test-docker.sh logs frontend

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
./test-docker.sh reset-db

# Check database status
./test-docker.sh logs postgres
```

### File Permission Issues
```bash
# Fix script permissions
chmod +x test-docker.sh
chmod +x test-developer-profiles.sh
```

## Next Steps

1. Read the [Testing Guide](../development/testing.md)
2. Explore [User Management Features](../features/user-management.md)
3. Set up your [Developer Profiles](../features/developer-profiles.md)
4. Review the [CI/CD Pipeline](../development/ci-cd.md)