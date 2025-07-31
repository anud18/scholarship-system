# Development Setup

This document describes how to set up the development environment, including the mock student database API.

## Mock Student Database API

⚠️ **DEVELOPMENT/TESTING ONLY** ⚠️

The mock student database API is designed to simulate the real student database during development when the actual database is inaccessible due to network restrictions.

### Starting the Development Environment

1. **Start the main application services:**
   ```bash
   docker-compose up -d
   ```

2. **Start the mock student API (development only):**
   ```bash
   docker-compose -f docker-compose.dev.yml up -d mock-student-api
   ```

3. **Verify the mock API is running:**
   ```bash
   curl http://localhost:8080/health
   ```

### Available Endpoints

- `http://localhost:8080/api/students/{student_id}` - Get student information
- `http://localhost:8080/api/students/{student_id}/semesters` - Get semester records
- `http://localhost:8080/docs` - Interactive API documentation
- `http://localhost:8080/health` - Health check

### Testing the Mock API

Run the test script:
```bash
cd mock-student-api
pip install requests
python test_api.py
```

### Sample Student IDs

The mock API generates 100 students with random IDs. To see available students:
```bash
curl "http://localhost:8080/api/students?limit=10"
```

### Integration with Main Application

To use the mock API in your application code, point your student database queries to:
- Base URL: `http://localhost:8080` (or `http://mock-student-api:8080` from within Docker)
- Student Info: `GET /api/students/{student_id}`
- Semesters: `GET /api/students/{student_id}/semesters`

### Environment Variables

Set these in your application to switch between real and mock APIs:

```bash
# Development
STUDENT_DB_URL=http://localhost:8080
STUDENT_DB_MODE=mock

# Production (real database)
STUDENT_DB_URL=https://real-student-db.university.edu
STUDENT_DB_MODE=production
```

### Important Notes

1. **Never use in production** - This mock API contains fake data and should never be deployed to production environments
2. **Data persistence** - Mock data is stored in Docker volumes and persists between restarts
3. **Network isolation** - The mock API runs in the same Docker network as the main application
4. **No authentication** - The mock API has no authentication for development convenience

### Stopping Services

```bash
# Stop mock API only
docker-compose -f docker-compose.dev.yml down mock-student-api

# Stop all services
docker-compose down
docker-compose -f docker-compose.dev.yml down
```