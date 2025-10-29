#!/bin/bash
# API Type Generation Script
# Generates TypeScript types from backend OpenAPI schema
#
# Usage:
#   ./scripts/generate-api-types.sh                  # Use default backend URL
#   ./scripts/generate-api-types.sh http://localhost:8000  # Custom backend URL
#   ./scripts/generate-api-types.sh --check          # Verify types are up-to-date (CI mode)

set -e

BACKEND_URL="${1:-http://localhost:8000}"
CI_MODE=false

if [[ "$1" == "--check" ]]; then
  CI_MODE=true
  BACKEND_URL="${2:-http://backend:8000}"
fi

OPENAPI_ENDPOINT="${BACKEND_URL}/api/v1/openapi.json"
OUTPUT_FILE="./lib/api/generated/schema.d.ts"

echo "🔧 API Type Generation"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "OpenAPI Endpoint: ${OPENAPI_ENDPOINT}"
echo "Output File: ${OUTPUT_FILE}"
echo ""

# Wait for backend to be ready (max 30 seconds)
echo "⏳ Waiting for backend to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while ! curl -sf "${OPENAPI_ENDPOINT}" > /dev/null 2>&1; do
  RETRY_COUNT=$((RETRY_COUNT + 1))
  if [[ $RETRY_COUNT -ge $MAX_RETRIES ]]; then
    echo "❌ Error: Backend not responding after ${MAX_RETRIES} seconds"
    echo "   Make sure the backend is running at ${BACKEND_URL}"
    exit 1
  fi
  echo "   Waiting... (${RETRY_COUNT}/${MAX_RETRIES})"
  sleep 1
done

echo "✅ Backend is ready"
echo ""

# Backup existing file if in check mode
if [[ "$CI_MODE" == "true" ]] && [[ -f "$OUTPUT_FILE" ]]; then
  echo "📋 CI Mode: Backing up existing types for comparison..."
  cp "$OUTPUT_FILE" "${OUTPUT_FILE}.backup"
fi

# Generate types
echo "🚀 Generating TypeScript types..."
npx openapi-typescript "${OPENAPI_ENDPOINT}" -o "${OUTPUT_FILE}"

if [[ $? -ne 0 ]]; then
  echo "❌ Error: Type generation failed"
  [[ "$CI_MODE" == "true" ]] && [[ -f "${OUTPUT_FILE}.backup" ]] && mv "${OUTPUT_FILE}.backup" "$OUTPUT_FILE"
  exit 1
fi

echo "✅ Types generated successfully"

# Check mode: verify types haven't changed
if [[ "$CI_MODE" == "true" ]]; then
  echo ""
  echo "🔍 Verifying types are up-to-date..."

  if ! diff -q "$OUTPUT_FILE" "${OUTPUT_FILE}.backup" > /dev/null 2>&1; then
    echo "❌ Error: Generated types differ from committed types!"
    echo ""
    echo "The OpenAPI schema has changed. Please run:"
    echo "  npm run api:generate"
    echo ""
    echo "Then commit the updated types:"
    echo "  git add lib/api/generated/schema.d.ts"
    echo "  git commit -m 'chore: update API types'"
    echo ""

    # Show diff
    echo "Differences:"
    diff -u "${OUTPUT_FILE}.backup" "$OUTPUT_FILE" || true

    # Cleanup
    mv "${OUTPUT_FILE}.backup" "$OUTPUT_FILE"
    exit 1
  fi

  echo "✅ Types are up-to-date"
  rm "${OUTPUT_FILE}.backup"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Done!"
