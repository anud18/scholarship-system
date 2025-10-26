# Installation Guide

## System Requirements

- Docker & Docker Compose
- Node.js 18+ (for local development)
- Python 3.11+ (for local development)

## Environment Setup

```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

## Database Management

```bash
# Reset database (recommended for clean setup)
./scripts/reset_database.sh

# Or manually run migrations
docker exec scholarship_backend_dev alembic upgrade head

# Run seed scripts
docker exec scholarship_backend_dev python -m app.db.init_db
```

## Local Development Setup

### Backend Setup
```bash
cd backend
pip install -r requirements.txt
export SECRET_KEY="your-secret-key-at-least-32-characters-long"
export DATABASE_URL="postgresql+asyncpg://user:pass@localhost:5432/scholarship_db"
uvicorn app.main:app --reload
```

### Frontend Setup
```bash
cd frontend
npm install
npm run dev
```

## Production Deployment

```bash
# Build production images
docker compose -f docker-compose.prod.yml build

# Deploy with secrets
docker compose -f docker-compose.prod.yml up -d
```
