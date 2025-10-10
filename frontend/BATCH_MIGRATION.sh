#!/bin/bash

# Batch migration script for remaining 14 modules
# This script demonstrates the migration pattern for each module

# Remaining modules to migrate:
# 1. quota
# 2. professor
# 3. college
# 4. whitelist
# 5. system-settings
# 6. bank-verification
# 7. professor-student
# 8. email-automation
# 9. batch-import
# 10. reference-data
# 11. application-fields
# 12. user-profiles
# 13. email-management
# 14. admin

echo "OpenAPI Type Migration - Remaining Modules"
echo "=========================================="
echo ""
echo "Migration Pattern for each module:"
echo ""
echo "1. Remove 'client: ApiClient' parameter from createModuleApi()"
echo "2. Import typedClient and toApiResponse"
echo "3. Replace client.request() with typedClient.raw.METHOD()"
echo "4. Remove JSON.stringify() from body"
echo "5. Update index.ts to call createModuleApi() without 'this'"
echo ""
echo "Example transformation:"
echo ""
echo "// Before"
echo "export function createModuleApi(client: ApiClient) {"
echo "  return {"
echo "    method: async () => {"
echo "      return client.request('/endpoint', {"
echo "        method: 'POST',"
echo "        body: JSON.stringify(data),"
echo "      });"
echo "    },"
echo "  };"
echo "}"
echo ""
echo "// After"
echo "import { typedClient } from '../typed-client';"
echo "import { toApiResponse } from '../compat';"
echo ""
echo "export function createModuleApi() {"
echo "  return {"
echo "    method: async () => {"
echo "      const response = await typedClient.raw.POST('/api/v1/endpoint', {"
echo "        body: data,"
echo "      });"
echo "      return toApiResponse(response);"
echo "    },"
echo "  };"
echo "}"
echo ""
echo "Run this for each remaining module."
