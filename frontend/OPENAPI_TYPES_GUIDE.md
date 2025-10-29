# OpenAPI Type Generation Guide

This document explains the OpenAPI-based type generation system for the Scholarship System frontend.

## Overview

The frontend uses **openapi-typescript** and **openapi-fetch** to generate TypeScript types directly from the backend's OpenAPI schema. This provides:

- ✅ **100% type safety** - All API endpoints, parameters, and responses are typed
- ✅ **Zero runtime overhead** - Pure TypeScript types, no additional runtime code
- ✅ **Automatic synchronization** - Types stay in sync with backend changes
- ✅ **Better DX** - IDE autocomplete for all API methods
- ✅ **Compile-time validation** - Catch API contract violations before deployment

## Architecture

```
Backend (FastAPI)
    ↓ generates
OpenAPI Schema (/api/v1/openapi.json)
    ↓ consumed by
openapi-typescript (CLI)
    ↓ generates
TypeScript Types (schema.d.ts)
    ↓ used by
openapi-fetch (runtime)
    ↓ provides
Type-safe API Client
```

## Quick Start

### Prerequisites

1. Backend must be running at `http://localhost:8000`
2. Node.js 22+ and npm installed
3. All npm dependencies installed (`npm ci`)

### Generate Types

```bash
cd frontend

# Generate types once
npm run api:generate

# Watch mode (regenerate on backend changes)
npm run api:watch
```

### Using Type-safe API Client

```typescript
import { api } from '@/lib/api';

// All parameters and responses are fully typed!
const response = await api.auth.login('username', 'password');

// TypeScript will show autocomplete for all methods:
await api.scholarships.getScholarships();
await api.applications.getMyApplications();
await api.users.getUserProfile(123);

// Response type is inferred automatically
if (response.success) {
  const user = response.data; // Fully typed User object
}
```

## CI/CD Integration

### Pre-commit Hook

The project includes a pre-commit hook that automatically regenerates types when backend API files change:

```bash
# Install pre-commit hooks
pip install pre-commit
pre-commit install

# Now types will be checked on every commit
git commit -m "feat: add new API endpoint"
```

If types are out of sync, the commit will fail with instructions to regenerate.

### GitHub Actions

The `.github/workflows/api-types-check.yml` workflow runs on every push/PR:

1. Starts backend server with test database
2. Generates types from OpenAPI schema
3. Checks if generated types match committed types
4. Fails if types are outdated
5. Comments on PR with fix instructions

## Development Workflow

### 1. Backend Changes

When you modify backend API endpoints, models, or schemas:

```bash
# Backend changes committed
git add backend/app/api/v1/endpoints/users.py
git commit -m "feat: add user profile endpoint"

# Pre-commit hook runs and regenerates types
# If types changed, commit will fail with instructions

# Regenerate types
cd frontend
npm run api:generate

# Commit updated types
git add lib/api/generated/schema.d.ts
git commit -m "chore: update API types"
```

### 2. Frontend Changes

When you modify frontend API module code:

```bash
# No type regeneration needed
git add frontend/lib/api/modules/users.ts
git commit -m "feat: add getUserProfile method"
```

### 3. Troubleshooting Type Errors

If you encounter type errors after backend changes:

1. **Regenerate types**: `npm run api:generate`
2. **Check backend is running**: `curl http://localhost:8000/api/v1/openapi.json`
3. **Restart backend**: Sometimes OpenAPI schema needs a server restart
4. **Check TypeScript**: `npm run type-check`

## Type Generation Scripts

### `scripts/generate-api-types.sh`

Robust script with backend health checks and CI mode:

```bash
# Standard generation
./scripts/generate-api-types.sh

# Custom backend URL
./scripts/generate-api-types.sh http://backend:8000

# CI mode (checks if types are up-to-date)
./scripts/generate-api-types.sh --check
```

### npm Scripts

```json
{
  "api:generate": "openapi-typescript http://localhost:8000/api/v1/openapi.json -o ./lib/api/generated/schema.d.ts",
  "api:watch": "openapi-typescript http://localhost:8000/api/v1/openapi.json -o ./lib/api/generated/schema.d.ts --watch"
}
```

## Migration Status

All 19 API modules have been migrated to use OpenAPI-typed clients:

- ✅ auth (6 methods)
- ✅ users (10 methods)
- ✅ scholarships (12 methods)
- ✅ applications (14 methods)
- ✅ notifications (4 methods)
- ✅ quota (7 methods)
- ✅ professor (6 methods)
- ✅ college (10 methods)
- ✅ whitelist (7 methods)
- ✅ system-settings (9 methods)
- ✅ bank-verification (2 methods)
- ✅ professor-student (4 methods)
- ✅ email-automation (6 methods)
- ✅ batch-import (11 methods)
- ✅ reference-data (4 methods)
- ✅ application-fields (11 methods)
- ✅ user-profiles (11 methods)
- ✅ email-management (11 methods)
- ✅ admin (74 methods)

**Total**: ~200+ methods with full type safety

## Type Generation Configuration

### openapi-typescript Options

The CLI supports many options. Current configuration:

```bash
openapi-typescript <url> -o <output-file>
  --help                Show help
  --version             Show version
  --auth <token>        Authorization token
  --header <header>     Additional headers
  --watch              Watch mode
```

### Custom Type Overrides

If you need to override generated types:

```typescript
// lib/api/types-overrides.ts
import type { paths } from './generated/schema';

// Override specific endpoint types
export type CustomUserResponse = paths['/api/v1/users/{user_id}']['get']['responses']['200']['content']['application/json'] & {
  customField: string;
};
```

## Best Practices

### 1. Always Regenerate After Backend Changes

```bash
# Pull latest backend changes
git pull origin main

# Start backend
cd backend && uvicorn app.main:app

# Regenerate types
cd ../frontend && npm run api:generate
```

### 2. Commit Generated Types

Generated types **MUST** be committed to version control:

```bash
git add lib/api/generated/schema.d.ts
```

This ensures:
- CI/CD can validate types without running backend
- All developers have consistent types
- Type changes are visible in PRs

### 3. Use Type-safe Client Everywhere

```typescript
// ❌ BAD - Direct fetch without types
const response = await fetch('/api/v1/users/123');
const data = await response.json();

// ✅ GOOD - Type-safe client
const response = await api.users.getUserProfile(123);
if (response.success) {
  const user = response.data; // Fully typed
}
```

### 4. Handle Type Errors Properly

```typescript
// TypeScript will catch these at compile time:

// ❌ Wrong parameter type
await api.users.getUserProfile("123"); // Error: Expected number

// ❌ Missing required parameter
await api.applications.createApplication({}); // Error: Missing required fields

// ❌ Wrong endpoint
await api.users.getNonExistentEndpoint(); // Error: Property does not exist
```

## Troubleshooting

### Backend Not Running

```bash
Error: Failed to fetch OpenAPI schema
```

**Solution**: Start the backend server:
```bash
cd backend
uvicorn app.main:app --reload
```

### Types Out of Sync

```bash
Error: Generated types differ from committed types
```

**Solution**: Regenerate and commit:
```bash
npm run api:generate
git add lib/api/generated/schema.d.ts
git commit -m "chore: update API types"
```

### TypeScript Errors After Regeneration

If you get TypeScript errors after regenerating types, the backend API contract has changed:

1. **Check the diff**: `git diff lib/api/generated/schema.d.ts`
2. **Update affected modules**: Fix type errors in `lib/api/modules/`
3. **Update components**: Fix type errors in React components
4. **Test thoroughly**: Ensure API calls still work

### Pre-commit Hook Failing

```bash
# Skip pre-commit hooks (not recommended)
git commit --no-verify

# Or fix the issue
npm run api:generate
git add lib/api/generated/schema.d.ts
```

## Resources

- [openapi-typescript Documentation](https://openapi-ts.pages.dev/)
- [openapi-fetch Documentation](https://openapi-ts.pages.dev/openapi-fetch/)
- [FastAPI OpenAPI Documentation](https://fastapi.tiangolo.com/advanced/extending-openapi/)
- [TypeScript Handbook](https://www.typescriptlang.org/docs/handbook/intro.html)

## Support

For questions or issues:
- Check this guide first
- Review CI/CD logs for type check failures
- Create an issue with the `typescript` label
- Consult the team lead for complex type issues
