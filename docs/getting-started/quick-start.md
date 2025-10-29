# Quick Start Guide

## Prerequisites

Ensure these ports are available:
- `3000` - Frontend (Next.js)
- `8000` - Backend API (FastAPI)
- `5432` - PostgreSQL
- `6379` - Redis
- `9000` - MinIO API
- `9001` - MinIO Console

## Start the System

```bash
# Start all services
docker compose -f docker-compose.dev.yml up -d

# Check service status
docker compose -f docker-compose.dev.yml ps

# View logs
docker compose -f docker-compose.dev.yml logs -f [service_name]
```

## Access Points

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Documentation**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (admin/admin123)

## Stop Services

```bash
# Stop all services
docker compose -f docker-compose.dev.yml down

# Complete cleanup (removes volumes)
docker compose -f docker-compose.dev.yml down -v
```

## Next Steps

1. Read the [Installation Guide](installation.md) for detailed setup
2. Explore [Development Setup](development-setup.md) for development workflow
3. Check [Testing Guide](../development/testing.md) for running tests
