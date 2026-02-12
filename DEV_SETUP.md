# Development Environment Setup

This project uses modern, fast tooling for development:
- **Backend**: [uv](https://github.com/astral-sh/uv) - Ultra-fast Python package installer
- **Frontend**: [Bun](https://bun.sh) - Fast all-in-one JavaScript runtime & toolkit

## Prerequisites

### Install uv (Backend)
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or via pip
pip install uv
```

### Install Bun (Frontend)
```bash
# macOS/Linux
curl -fsSL https://bun.sh/install | bash

# Or via npm
npm install -g bun
```

## Development Workflow

### Using Docker Compose (Recommended)

Start the development environment:
```bash
# Build and start all services
docker compose -f docker-compose.dev.yml up --build

# Or rebuild specific service
docker compose -f docker-compose.dev.yml up --build backend
docker compose -f docker-compose.dev.yml up --build frontend
```

Stop services:
```bash
docker compose -f docker-compose.dev.yml down
```

View logs:
```bash
# All services
docker compose -f docker-compose.dev.yml logs -f

# Specific service
docker compose -f docker-compose.dev.yml logs -f backend
docker compose -f docker-compose.dev.yml logs -f frontend
```

### Local Development (Without Docker)

#### Backend Setup
```bash
cd backend

# Create virtual environment (optional but recommended)
uv venv

# Install dependencies
uv pip install -r pyproject.toml

# Install dev dependencies
uv pip install -r pyproject.toml --extra dev

# Run migrations
alembic upgrade head

# Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup
```bash
cd frontend

# Install dependencies
bun install

# Start development server
bun run dev

# Run tests
bun test

# Type checking
bun run type-check

# Build for production
bun run build
```

## Service URLs

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379
- **MinIO Console**: http://localhost:9001
- **Mock Student API**: http://localhost:8080

## Benefits of uv and Bun

### uv (Backend)
- ⚡ 10-100x faster than pip
- 🔒 Built-in virtual environment management
- 📦 Compatible with existing pip/PyPI ecosystem
- 🎯 Reliable dependency resolution

### Bun (Frontend)
- ⚡ 2-10x faster than npm/yarn
- 🔧 Drop-in replacement for Node.js
- 🧪 Built-in test runner
- 📦 Compatible with npm packages

## Troubleshooting

### Backend Issues

**Dependencies not installing:**
```bash
cd backend
rm -rf .venv
uv venv
uv pip install -r pyproject.toml
```

**Database connection issues:**
```bash
# Check if PostgreSQL is running
docker compose -f docker-compose.dev.yml ps postgres

# Reset database
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d postgres
```

### Frontend Issues

**Dependencies not installing:**
```bash
cd frontend
rm -rf node_modules bun.lockb
bun install
```

**Port already in use:**
```bash
# Kill process on port 3000
lsof -ti:3000 | xargs kill -9
```

## Adding Dependencies

### Backend
```bash
# Add to pyproject.toml [project.dependencies] section
# Then run:
uv pip install -r pyproject.toml
```

### Frontend
```bash
bun add <package>        # Production dependency
bun add -d <package>     # Development dependency
```

## Migration from npm/pip

### Backend (pip → uv)
The migration is complete! Dependencies are now in `pyproject.toml`.
Old `requirements.txt` is kept for reference but is no longer used.

### Frontend (npm → bun)
The migration is complete! Just run:
```bash
cd frontend
bun install  # This will create bun.lockb
```

Bun is compatible with `package.json` and can use existing npm packages.
