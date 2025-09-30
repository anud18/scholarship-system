#!/bin/bash

# Regenerate frontend dependencies script
# This script cleans up existing dependencies and regenerates package-lock.json

echo "🧹 Cleaning up existing dependencies..."

# Remove existing lock files and node_modules
rm -rf node_modules/
rm -f package-lock.json
rm -f pnpm-lock.yaml
rm -f yarn.lock

echo "📦 Installing fresh dependencies..."

# Install dependencies fresh
npm install

echo "✅ Dependencies regenerated successfully!"
echo "📝 Don't forget to commit the new package-lock.json file:"
echo "   git add package-lock.json"
echo "   git commit -m 'fix: regenerate package-lock.json with updated dependencies'"
