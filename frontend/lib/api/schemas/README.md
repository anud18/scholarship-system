# API Schemas (Zod Validation)

Runtime validation for API responses to catch backend schema drift.

## Features

- **Automatic validation in development**: Validates all responses by default in `NODE_ENV=development`
- **Optional validation in production**: Use `validateResponse: true` to force validation
- **Detailed error reporting**: Console logs show exactly what went wrong
- **Type inference**: TypeScript types automatically inferred from Zod schemas

## Usage

### Basic Usage

```typescript
import { UserSchema } from '@/lib/api/schemas/user.schema';
import { api } from '@/lib/api';

// Automatically validates in development
const response = await api.request('/users/me', {
  schema: UserSchema,
});
```

### Force Validation in Production

```typescript
const response = await api.request('/users/me', {
  schema: UserSchema,
  validateResponse: true,  // Throws ApiValidationError if validation fails
});
```

### Catch Validation Errors

```typescript
import { ApiValidationError } from '@/lib/api/client';

try {
  const response = await api.request('/users/me', {
    schema: UserSchema,
    validateResponse: true,
  });
} catch (error) {
  if (error instanceof ApiValidationError) {
    console.error('Validation failed:', error.zodError.errors);
    console.error('Endpoint:', error.endpoint);
    console.error('Received data:', error.responseData);
  }
}
```

## Creating New Schemas

1. Create a new schema file: `lib/api/schemas/feature.schema.ts`
2. Define Zod schemas for your API responses:

```typescript
import { z } from 'zod';

export const MyDataSchema = z.object({
  id: z.string(),
  name: z.string(),
  created_at: z.string(),
});

export type MyData = z.infer<typeof MyDataSchema>;
```

3. Use in API modules:

```typescript
import { MyDataSchema } from '@/lib/api/schemas/feature.schema';

export function createMyApi(client: ApiClient) {
  return {
    getData: async (id: string): Promise<ApiResponse<MyData>> => {
      return client.request(`/my-data/${id}`, {
        schema: MyDataSchema,
      });
    },
  };
}
```

## Benefits

- ✅ **Catch backend changes early**: Know immediately when backend API changes
- ✅ **Development safety**: Validation runs automatically in dev mode
- ✅ **Production performance**: Opt-in validation in production (no overhead by default)
- ✅ **Type safety**: Zod schemas generate TypeScript types automatically
- ✅ **Debugging**: Detailed error messages show exactly what's wrong

## Example Error Output

```
❌ API Response Validation Failed: {
  endpoint: '/users/me',
  errors: [
    {
      code: 'invalid_type',
      expected: 'string',
      received: 'undefined',
      path: ['email'],
      message: 'Required'
    }
  ],
  received: {
    id: '123',
    name: 'John Doe',
    // email is missing!
  }
}
```

## Migration Guide

Gradually add schemas to existing API methods:

1. **High priority endpoints** (auth, user data): Add schemas first
2. **Frequently used endpoints**: Add schemas next
3. **Less critical endpoints**: Add schemas as needed

No breaking changes - schemas are optional and backward compatible.
