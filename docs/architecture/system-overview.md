# System Architecture Overview

## Technology Stack

### Backend
- **Python 3.11** with FastAPI
- **PostgreSQL 15** with asyncpg
- **SQLAlchemy 2.0** (async)
- **Redis** for caching and sessions
- **MinIO** for object storage
- **Alembic** for database migrations

### Frontend
- **Next.js 15** with App Router
- **React 18** with TypeScript
- **Tailwind CSS** + shadcn/ui
- **React Hook Form** + Zod validation
- **Playwright** for E2E testing

### DevOps
- **Docker** & Docker Compose
- **NGINX** reverse proxy
- **pytest** (backend) + Jest (frontend) testing
- **90% test coverage target**

## Project Structure

```
scholarship-system/
├── backend/                 # FastAPI application
│   ├── app/
│   │   ├── api/v1/endpoints/   # API routes
│   │   ├── core/               # Configuration & auth
│   │   ├── db/                 # Database setup
│   │   ├── models/             # SQLAlchemy models
│   │   ├── schemas/            # Pydantic schemas
│   │   ├── services/           # Business logic
│   │   └── tests/              # Backend tests
│   ├── alembic/             # Database migrations
│   └── requirements.txt     # Python dependencies
├── frontend/                # Next.js application
│   ├── app/                 # App Router pages
│   ├── components/          # React components
│   ├── hooks/               # Custom hooks
│   ├── lib/                 # Utilities
│   └── styles/              # Global styles
├── docs/                    # Documentation
├── infra/                   # Infrastructure configs
└── scripts/                 # Utility scripts
```

## Architecture Diagram

```mermaid
graph TD
    subgraph Client
        UA[Students/Faculty] -- HTTPS --> LB[NGINX/Traefik]
    end
    subgraph App
        API[FastAPI Cluster<br/>(Uvicorn+Gunicorn)]
    end
    subgraph Data
        PG[(PostgreSQL 15 Primary)]
        PG --> Replica[(PostgreSQL Replica)]
        OBJ[(MinIO Object Storage)]
    end
    subgraph Services
        OCR[Tesseract OCR Container]
        SMTP[Campus SMTP Relay]
        OIDC[(OpenID Connect)]
    end
    LB --> API
    API -->|asyncpg| PG
    API -->|Pre-signed URL| OBJ
    API --> OCR
    API --> SMTP
    API --> OIDC
```

## Security Features

- **JWT Authentication** with role-based access control
- **Input Validation** with Pydantic and Zod
- **File Upload Security** with type/size restrictions and virus scanning
- **SQL Injection Protection** with parameterized queries
- **Rate Limiting** on API endpoints