#!/usr/bin/env bash
# Verify Playwright global install + browser cache.
# Exit non-zero with the fix command if anything is missing.
set -e

if ! command -v playwright >/dev/null 2>&1; then
  echo "ERR: 'playwright' not found in PATH." >&2
  echo "FIX: npm install -g playwright" >&2
  exit 1
fi

VERSION=$(playwright --version 2>/dev/null || echo "unknown")
LIB_PATH="$(npm root -g)/playwright"
CACHE_DIR="$HOME/Library/Caches/ms-playwright"

echo "Playwright: $VERSION"
echo "Library:    $LIB_PATH"
echo "CLI:        $(command -v playwright)"

if [ -d "$CACHE_DIR" ]; then
  echo "Browser cache ($CACHE_DIR):"
  ls "$CACHE_DIR" 2>/dev/null | sed 's/^/  /'
else
  echo "ERR: browser cache missing at $CACHE_DIR" >&2
  echo "FIX: playwright install" >&2
  exit 1
fi

if ! ls "$CACHE_DIR" 2>/dev/null | grep -q '^chromium-'; then
  echo "ERR: chromium browser not downloaded" >&2
  echo "FIX: playwright install chromium" >&2
  exit 1
fi

echo "OK: Playwright ready"
