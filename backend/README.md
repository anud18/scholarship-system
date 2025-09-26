# Scholarship Management System - Backend

## 🎯 Project Overview
FastAPI-based backend for a comprehensive scholarship application and approval management system.

## ✅ Current Implementation Status

### Phase 1: Core Setup (COMPLETED)
- ✅ **Project Structure**: Complete directory structure following best practices
- ✅ **Dependencies**: All required Python packages defined and installed
- ✅ **Configuration**: Environment-based configuration with Pydantic Settings
- ✅ **Database Setup**: SQLAlchemy 2.0 async engine configuration
- ✅ **FastAPI App**: Basic application with middleware and exception handling
- ✅ **Exception Handling**: Comprehensive custom exception classes
- ✅ **Docker Setup**: Dockerfile and docker-compose.yml for development

### Verified Working Components
- ✅ FastAPI application initialization
- ✅ Configuration loading from environment variables
- ✅ Custom exception handling system
- ✅ CORS middleware configuration
- ✅ Request tracing middleware
- ✅ Health check endpoint

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis (optional, for caching)

### Database Initialization Pattern

This project uses a modern database initialization pattern:
1. **DB Schema Defaults**: All default values are defined at database level (`server_default`)
2. **Alembic Migrations**: Schema and reference data managed through version control
3. **Idempotent Seeds**: Environment-specific data with advisory locks

### Installation (Development)

#### Option 1: Using Docker (Recommended)
```bash
# Copy environment file
cp .env.example .env

# Start all services with docker-compose
docker-compose -f docker-compose.dev.yml up -d

# Wait for database to be ready, then run migrations
docker-compose -f docker-compose.dev.yml exec backend alembic upgrade head

# Seed development data (test users, etc.)
docker-compose -f docker-compose.dev.yml exec backend python -m app.seed

# View logs
docker-compose -f docker-compose.dev.yml logs -f backend
```

#### Option 2: Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Set up environment variables (copy from .env.example)
export APP_ENV=development
export DATABASE_URL="postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db"
export DATABASE_URL_SYNC="postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db"
export SECRET_KEY="dev-secret-key-for-development-only"

# Run Alembic migrations
alembic upgrade head

# Seed development data
python -m app.seed

# Run the application
uvicorn app.main:app --reload
```

### Production Deployment
```bash
# Set production environment variables
export APP_ENV=production
export DATABASE_URL_SYNC="postgresql://..."  # Production DB
export ADMIN_EMAIL="admin@yourdomain.edu.tw"

# Run migrations
alembic upgrade head

# Seed production data (admin user only)
python -m app.seed --prod

# Start application
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## 📁 Project Structure

```
backend/
├── app/
│   ├── api/v1/endpoints/     # API route handlers
│   ├── core/                 # Core configuration and utilities
│   │   ├── config.py         # Application settings
│   │   ├── exceptions.py     # Custom exception classes
│   │   └── deps.py           # FastAPI dependencies (TODO)
│   ├── db/                   # Database configuration
│   │   ├── base.py           # SQLAlchemy setup
│   │   └── session.py        # Database session management
│   ├── models/               # SQLAlchemy ORM models (TODO)
│   ├── schemas/              # Pydantic validation schemas (TODO)
│   ├── services/             # Business logic layer (TODO)
│   └── tests/                # Test files (TODO)
├── alembic/                  # Database migrations (TODO)
├── requirements.txt          # Python dependencies
├── Dockerfile               # Docker configuration
└── docker-compose.yml      # Development environment
```

## 🎯 Next Steps (Implementation Phases)

### Phase 2: Data Models (NEXT)
- [ ] User model (students, faculty, admins)
- [ ] Scholarship model (types, requirements, deadlines)
- [ ] Application model (student applications)
- [ ] Document model (file attachments)
- [ ] Database migrations with Alembic

### Phase 3: API Schemas
- [ ] User validation schemas
- [ ] Application request/response schemas
- [ ] Scholarship schemas
- [ ] Authentication token schemas

### Phase 4: Business Logic
- [ ] Authentication service (JWT, password handling)
- [ ] User management service
- [ ] Application service (CRUD, validation)
- [ ] Email notification service
- [ ] File upload service

### Phase 5: API Endpoints
- [ ] Authentication endpoints (`/api/v1/auth`)
- [ ] User management endpoints (`/api/v1/users`)
- [ ] Application endpoints (`/api/v1/applications`)
- [ ] Scholarship endpoints (`/api/v1/scholarships`)

### Phase 6: Advanced Features
- [ ] OCR document processing
- [ ] Email notifications
- [ ] Admin dashboard endpoints
- [ ] Reporting and analytics
- [ ] File virus scanning

## 🔧 Configuration

Key environment variables:
- `SECRET_KEY`: JWT secret (min 32 characters)
- `DATABASE_URL`: Async PostgreSQL connection string
- `DATABASE_URL_SYNC`: Sync PostgreSQL connection string (for migrations)
- `CORS_ORIGINS`: Comma-separated list of allowed origins
- `DEBUG`: Enable debug mode
- `UPLOAD_DIR`: File upload directory
- `MAX_FILE_SIZE`: Maximum file size in bytes

## 🗄️ Database Architecture

### Modern Initialization Pattern

This project follows a production-ready database initialization pattern:

#### 1. Database-Level Defaults (`server_default`)
- All default values defined at PostgreSQL level
- Ensures consistency across all database clients
- Examples: `CURRENT_TIMESTAMP`, `GENERATED BY DEFAULT AS IDENTITY`

#### 2. Alembic Migrations for Schema & Reference Data
- **Schema migrations**: Table structure, indexes, constraints
- **Reference data migrations**: Lookup tables (degrees, departments, etc.)
- Version controlled and reproducible

#### 3. Idempotent Seed Scripts
- **Advisory locks**: Prevents concurrent seed execution
- **ON CONFLICT**: Idempotent upserts for all data
- **Environment-aware**:
  - Development: Full test data (users, applications, etc.)
  - Production: Admin user only

### Migration Structure
```
alembic/versions/
├── 4f0a9ad1219f_initial_schema_and_lookup_tables.py  # Lookup data
├── 91f7e98e5d0a_scholarship_reference_data.py        # Handled by seed script
└── ...
```

### Seed Script Usage
```bash
# Development: Full test data
python -m app.seed

# Production: Admin user only
python -m app.seed --prod

# Environment auto-detection
APP_ENV=production python -m app.seed  # Uses production mode
```

## 🏗️ Architecture Decisions

### Naming Conventions
- **API Endpoints**: camelCase (`/getApplications`, `/submitApplication`)
- **Python Variables/Functions**: camelCase (`getUserById`, `applicationData`)
- **Database Tables**: snake_case (`student_applications`, `created_at`)
- **Classes**: PascalCase (`ApplicationService`, `UserModel`)

### Response Format
All API responses follow a standardized format:
```json
{
  "success": true,
  "message": "Operation successful",
  "data": {...},
  "trace_id": "req_abc123"
}
```

### Error Handling
- Custom exception hierarchy for different error types
- Automatic trace ID generation for debugging
- Structured error responses with detailed messages

## 🧪 Testing Strategy

### Planned Test Coverage (90% target)
- Unit tests for business logic
- Integration tests for API endpoints
- Database transaction tests
- File upload tests
- Authentication flow tests

## 🧹 Code Quality

### Formatting
- Run `black app` followed by `isort app` to keep imports and layout consistent with the pre-commit hooks.

### Linting Baseline
- Run `flake8 app/core app/db app/middleware app/utils app/main.py`.
- The current lint pass intentionally focuses on the shared infrastructure modules. The API endpoints, services, and large legacy test suites still require refactors before we can enable linting for them without an overwhelming amount of noise.

## 📚 API Documentation

Once implemented, API documentation will be available at:
- Swagger UI: `http://localhost:8000/api/v1/docs`
- ReDoc: `http://localhost:8000/api/v1/redoc`
- OpenAPI JSON: `http://localhost:8000/api/v1/openapi.json`

## 🚦 Development Status

| Component | Status | Priority |
|-----------|--------|----------|
| Core Setup | ✅ Complete | High |
| Data Models | 🔄 Next | High |
| Authentication | ⏳ Pending | High |
| API Endpoints | ⏳ Pending | High |
| File Upload | ⏳ Pending | Medium |
| Email Service | ⏳ Pending | Medium |
| OCR Processing | ⏳ Pending | Low |
| Admin Features | ⏳ Pending | Medium |

## 🤝 Contributing

Follow the established patterns:
1. Use the defined project structure
2. Follow naming conventions
3. Add comprehensive docstrings
4. Include unit tests for new features
5. Update this README for significant changes

---

**Target Launch Date**: July 3, 2025
**Current Progress**: Core Foundation Complete ✅
