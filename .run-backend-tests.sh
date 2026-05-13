#!/bin/bash
# Test runner for backend tests inside an ephemeral container that mounts
# THIS worktree (read-only) and uses pre-installed test deps at /tmp/wtree-deps.
#
# Why this instead of `docker compose exec backend pytest ...`?
# The running scholarship_backend_dev container is mounted to a different
# worktree, so its /app does not reflect changes in this worktree.
#
# Usage:
#   ./.run-backend-tests.sh app/tests/test_supplementary_import_service.py -v
#   ./.run-backend-tests.sh app/tests/some_test.py::TestClass::test_method -v
#
# Args are passed through to pytest verbatim.
set -e

WORKTREE_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKTREE_DIR"

if [ ! -d /tmp/wtree-deps ]; then
    echo "ERROR: /tmp/wtree-deps not found. Run setup first." >&2
    exit 1
fi

exec docker run --rm -t --user root \
    -v /tmp/wtree-deps:/deps:ro \
    -v "$WORKTREE_DIR/backend:/app" \
    -w /app \
    -e PYTHONPATH=/deps:/app \
    -e PYTHONDONTWRITEBYTECODE=1 \
    -e PYTHONUNBUFFERED=1 \
    -e TESTING=true \
    -e PYTEST_CURRENT_TEST=true \
    -e DATABASE_URL=sqlite+aiosqlite:///:memory: \
    -e DATABASE_URL_SYNC=sqlite:///:memory: \
    -e SECRET_KEY=test-secret-key-for-unit-tests \
    -e MINIO_ACCESS_KEY=test \
    -e MINIO_SECRET_KEY=test \
    -e MINIO_ENDPOINT=localhost:9000 \
    -e MINIO_BUCKET_NAME=test-bucket \
    -e STUDENT_API_ENABLED=false \
    ghcr.io/anud18/scholarship-system-backend:latest \
    python -m pytest \
        -o cache_dir=/tmp/pytest-cache \
        --override-ini='addopts=' \
        --override-ini='log_cli=false' \
        --override-ini='console_output_style=classic' \
        "$@"
