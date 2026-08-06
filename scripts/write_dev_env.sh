#!/usr/bin/env bash
# Write local-dev .env files for `make dev`. Database and object-storage
# credentials are read from docker-compose.dev.yml at run time so the
# host-run backend always matches the Dockerised postgres / redis / minio /
# mock-student-api — and so no credentials are hardcoded in this script.
#
# Usage: ./scripts/write_dev_env.sh {backend|frontend}
#
# The generated files hold local-dev values only. They are gitignored and
# MUST NOT be used outside local dev.

set -euo pipefail

COMPOSE_FILE="docker-compose.dev.yml"

# First `KEY: value` occurrence in docker-compose.dev.yml.
compose_value() {
  local value
  value=$(sed -n "s/^[[:space:]]*$1:[[:space:]]*//p" "$COMPOSE_FILE" | head -n 1 | tr -d '"')
  if [ -z "$value" ]; then
    echo "error: $1 not found in $COMPOSE_FILE" >&2
    exit 1
  fi
  printf '%s' "$value"
}

case "${1:-}" in
  backend)
    DB_NAME="$(compose_value POSTGRES_DB)"
    DB_USER="$(compose_value POSTGRES_USER)"
    DB_PASSWORD="$(compose_value POSTGRES_PASSWORD)"
    S3_ACCESS_KEY="$(compose_value RUSTFS_ACCESS_KEY)"
    S3_SECRET_KEY="$(compose_value RUSTFS_SECRET_KEY)"

    cat > backend/.env <<EOF
# Local-dev defaults written by scripts/write_dev_env.sh.
# DB / MinIO values are read from docker-compose.dev.yml.
# Replace each value with your own for staging/prod, e.g.:
#   SECRET_KEY=your-generated-key  (run: openssl rand -hex 32)

ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
DATABASE_URL_SYNC=postgresql://${DB_USER}:${DB_PASSWORD}@localhost:5432/${DB_NAME}
REDIS_URL=redis://localhost:6379/0

SECRET_KEY=dev-secret-key-for-development-only

CORS_ORIGINS=http://localhost:3000,http://localhost:8000

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=${S3_ACCESS_KEY}
MINIO_SECRET_KEY=${S3_SECRET_KEY}
MINIO_BUCKET=scholarship-documents
MINIO_SECURE=false

ENABLE_MOCK_SSO=true
MOCK_SSO_DOMAIN=dev.university.edu
PORTAL_SSO_ENABLED=false

STUDENT_API_ENABLED=true
STUDENT_API_BASE_URL=http://localhost:8080
STUDENT_API_TIMEOUT=10.0
STUDENT_API_ENCODE_TYPE=UTF-8

FRONTEND_URL=http://localhost:3000
FRONTEND_INTERNAL_URL=http://localhost:3000
EOF
    echo "  ✓ wrote backend/.env"
    ;;

  frontend)
    cat > frontend/.env.local <<'EOF'
# Local-dev defaults written by scripts/write_dev_env.sh.

NEXT_PUBLIC_API_URL=http://localhost:8000
INTERNAL_API_URL=http://localhost:8000
MOCK_STUDENT_API_URL=http://localhost:8080
NEXT_TELEMETRY_DISABLED=1
EOF
    echo "  ✓ wrote frontend/.env.local"
    ;;

  *)
    echo "usage: $0 {backend|frontend}" >&2
    exit 2
    ;;
esac
