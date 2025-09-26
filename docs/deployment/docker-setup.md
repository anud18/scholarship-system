# Docker Testing Guide

This guide will help you test the Scholarship Application and Approval Management System using Docker without affecting your local environment.

## Prerequisites

1. **Docker & Docker Compose**: Ensure you have Docker and Docker Compose installed
   ```bash
   docker --version
   docker compose version
   ```

2. **Available Ports**: The following ports should be available:
   - `3000` - Frontend (Next.js)
   - `8000` - Backend API (FastAPI)
   - `5432` - PostgreSQL Database
   - `6379` - Redis Cache
   - `9000` - MinIO API
   - `9001` - MinIO Console

## Quick Start

### Using the Test Script (Recommended)

1. **Start the entire system:**
   ```bash
   ./test-docker.sh start
   ```

2. **Check service status:**
   ```bash
   ./test-docker.sh status
   ```

3. **View logs:**
   ```bash
   ./test-docker.sh logs           # All services
   ./test-docker.sh logs backend   # Backend only
   ./test-docker.sh logs frontend  # Frontend only
   ```

4. **Stop services:**
   ```bash
   ./test-docker.sh stop
   ```

5. **Complete cleanup:**
   ```bash
   ./test-docker.sh cleanup
   ```

### Manual Docker Compose Commands

If you prefer using Docker Compose directly:

```bash
# Start services
docker compose -f docker-compose.test.yml up --build -d

# Check status
docker compose -f docker-compose.test.yml ps

# View logs
docker compose -f docker-compose.test.yml logs -f

# Stop services
docker compose -f docker-compose.test.yml down

# Cleanup (remove volumes)
docker compose -f docker-compose.test.yml down -v
```

## Service Access

Once all services are running:

| Service | URL | Description |
|---------|-----|-------------|
| **Frontend** | http://localhost:3000 | Student portal and application interface |
| **Backend API** | http://localhost:8000 | REST API endpoints |
| **API Documentation** | http://localhost:8000/docs | Interactive API documentation (Swagger) |
| **Database** | localhost:5432 | PostgreSQL database (scholarship_db) |
| **Redis** | localhost:6379 | Cache and session storage |
| **MinIO API** | http://localhost:9000 | Object storage API |
| **MinIO Console** | http://localhost:9001 | Object storage management UI (minioadmin/minioadmin123) |

## Database Connection

If you need to connect to the PostgreSQL database directly:

```bash
# Using Docker exec
docker exec -it scholarship_postgres_test psql -U scholarship_user -d scholarship_db

# Using external tools
Host: localhost
Port: 5432
Database: scholarship_db
Username: scholarship_user
Password: scholarship_pass
```

## Development Workflow

### 1. Code Changes
- Backend changes: Restart only backend service
  ```bash
  docker compose -f docker-compose.test.yml restart backend
  ```
- Frontend changes: Restart only frontend service
  ```bash
  docker compose -f docker-compose.test.yml restart frontend
  ```

### 2. Database Migrations
```bash
./test-docker.sh migrate
# or
docker exec scholarship_backend_test alembic upgrade head
```

### 3. Running Tests
```bash
./test-docker.sh test
# or
docker exec scholarship_backend_test python -m pytest app/tests/ -v
```

## Troubleshooting

### Port Conflicts
If you get port conflict errors:
```bash
# Find processes using ports
lsof -i :3000
lsof -i :8000
lsof -i :5432
lsof -i :6379
lsof -i :9000
lsof -i :9001

# Stop conflicting services or use different ports
```

### Service Health Checks
```bash
# Check if services are healthy
docker compose -f docker-compose.test.yml ps

# Check individual service logs
./test-docker.sh logs backend
./test-docker.sh logs frontend
./test-docker.sh logs postgres
./test-docker.sh logs redis
./test-docker.sh logs minio
```

### Database Issues
```bash
# Reset database
docker compose -f docker-compose.test.yml down -v
./test-docker.sh start
./test-docker.sh migrate
```

### Build Issues
```bash
# Force rebuild without cache
docker compose -f docker-compose.test.yml build --no-cache
docker compose -f docker-compose.test.yml up -d
```

## File Structure

```
scholarship-system/
├── docker-compose.test.yml     # Simplified testing setup
├── docker-compose.yml          # Full production-like setup with NGINX
├── nginx.conf                  # NGINX reverse proxy configuration
├── test-docker.sh             # Testing helper script
├── backend/
│   ├── Dockerfile             # Backend container configuration
│   └── docker-compose.yml     # Original backend-only setup
└── frontend/
    └── Dockerfile             # Frontend container configuration
```

## Production-like Testing

For testing with NGINX reverse proxy (more production-like):

```bash
# Use the full setup
docker compose up --build -d

# Access via NGINX
# Frontend: http://localhost
# API: http://localhost/api/
```

## Security Notes

⚠️ **Warning**: These configurations are for testing only!

- Default passwords are used
- Debug mode is enabled
- CORS is set to allow all origins
- Do not use in production

## Performance Tips

1. **Resource allocation**: Ensure Docker has enough resources allocated (4GB+ RAM recommended)
2. **Volume mounting**: Backend code is mounted for development, remove for production
3. **Image optimization**: Use multi-stage builds for smaller production images

## Commands Reference

| Command | Description |
|---------|-------------|
| `./test-docker.sh start` | Start all services |
| `./test-docker.sh stop` | Stop all services |
| `./test-docker.sh restart` | Restart all services |
| `./test-docker.sh status` | Show service status |
| `./test-docker.sh logs [service]` | View logs |
| `./test-docker.sh cleanup` | Remove containers and volumes |
| `./test-docker.sh migrate` | Run database migrations |
| `./test-docker.sh test` | Run backend tests |

## Environment Variables

Key environment variables used in Docker setup:

```env
# Database
DATABASE_URL=postgresql+asyncpg://scholarship_user:scholarship_pass@postgres:5432/scholarship_db
REDIS_URL=redis://redis:6379/0

# MinIO Object Storage
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET_NAME=scholarship-documents
MINIO_SECURE=false

# Security
SECRET_KEY=test-secret-key-for-docker-testing-only
DEBUG=true
CORS_ORIGINS=*

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
NODE_ENV=production
```

For any issues or questions, check the logs using `./test-docker.sh logs` or refer to the individual service documentation.
