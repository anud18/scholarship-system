#!/usr/bin/env bash
# Write local-dev .env files for `make dev`. Values mirror
# docker-compose.dev.yml so the host-run backend can talk to the
# Dockerised postgres / redis / minio / mock-student-api.
#
# Usage: ./scripts/write_dev_env.sh {backend|frontend}
#
# These are NOT secrets — they're the same dev defaults already in
# docker-compose.dev.yml. They MUST NOT be used outside local dev.

set -euo pipefail

case "${1:-}" in
  backend)
    cat > backend/.env <<'EOF'
# Local-dev defaults written by scripts/write_dev_env.sh.
# Replace each value with your own for staging/prod, e.g.:
#   SECRET_KEY=your-generated-key  (run: openssl rand -hex 32)

ENVIRONMENT=development
DEBUG=true

DATABASE_URL=postgresql+asyncpg://scholarship_user:scholarship_pass@localhost:5432/scholarship_db  # pragma: allowlist secret
DATABASE_URL_SYNC=postgresql://scholarship_user:scholarship_pass@localhost:5432/scholarship_db  # pragma: allowlist secret
REDIS_URL=redis://localhost:6379/0

SECRET_KEY=dev-secret-key-for-development-only

CORS_ORIGINS=http://localhost:3000,http://localhost:8000

MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123
MINIO_BUCKET=scholarship-documents
MINIO_SECURE=false

ENABLE_MOCK_SSO=true
MOCK_SSO_DOMAIN=dev.university.edu
PORTAL_SSO_ENABLED=false

STUDENT_API_ENABLED=true
STUDENT_API_BASE_URL=http://localhost:8080
STUDENT_API_ACCOUNT=scholarship
STUDENT_API_HMAC_KEY=4d6f636b4b657946726f6d48657841424344454647484a4b4c4d4e4f505152535455565758595a
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
