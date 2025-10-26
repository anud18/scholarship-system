# Mock SSO Implementation for Development

This document describes the mock SSO (Single Sign-On) implementation for the scholarship management system, designed to simplify development and testing workflows.

## Overview

The mock SSO feature provides predefined test users for different roles without requiring a real OAuth provider. This allows developers to quickly switch between user contexts and test role-based functionality.

## Features

- **Predefined Test Users**: 8 mock users covering all system roles
- **Real JWT Tokens**: Generated tokens work with all protected endpoints
- **Development-Only**: Automatically disabled in production environments
- **Role-Based Testing**: Easy switching between student, professor, college, admin, and super admin roles
- **Bilingual Support**: Chinese and English names for realistic testing

## Backend Implementation

### Configuration

Add these environment variables to enable mock SSO:

```bash
# Enable mock SSO for development
ENABLE_MOCK_SSO=true
MOCK_SSO_DOMAIN=dev.university.edu
```

### API Endpoints

#### GET `/api/v1/auth/mock-sso/users`
Returns list of available mock users for login selection.

**Response:**
```json
{
  "success": true,
  "message": "Mock users retrieved successfully",
  "data": [
    {
      "username": "student001",
      "email": "student001@dev.university.edu",
      "full_name": "張小明",
      "chinese_name": "張小明",
      "english_name": "Ming Zhang",
      "role": "student",
      "description": "Undergraduate student - Good GPA"
    }
  ]
}
```

#### POST `/api/v1/auth/mock-sso/login`
Authenticate as a mock user and receive JWT token.

**Request:**
```json
{
  "username": "student001"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Mock SSO login successful for student001",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
    "expires_in": 3600,
    "user": {
      "id": "1",
      "username": "student001",
      "email": "student001@dev.university.edu",
      "role": "student",
      "full_name": "張小明",
      "is_active": true
    }
  }
}
```

#### POST `/api/v1/auth/mock-sso/init`
Initialize mock users in the database (creates users if they don't exist).

### Mock Users

The system provides 8 predefined mock users:

| Username | Role | Chinese Name | English Name | Description |
|----------|------|--------------|--------------|-------------|
| student001 | student | 張小明 | Ming Zhang | Undergraduate student - Good GPA |
| student002 | student | 李美華 | Mei-Hua Li | Graduate student - Excellent record |
| student003 | student | 王大偉 | David Wang | PhD student - Research focus |
| prof001 | professor | 陳志明 | Professor Chen | Computer Science Professor |
| prof002 | professor | 林雅惠 | Professor Lin | Mathematics Professor |
| college001 | college | 張審核 | College Reviewer | Engineering College Reviewer |
| admin001 | admin | 管理員 | System Admin | System Administrator |
| superadmin | super_admin | 超級管理員 | Super Administrator | Super Admin - Full Access |

### Security Features

- **Environment-Based**: Only enabled when `ENABLE_MOCK_SSO=true`
- **Development Password**: All mock users use password `dev123456`
- **Real Authentication**: Uses same JWT generation as regular login
- **Database Integration**: Mock users are stored in the same user table

## Frontend Implementation

### MockSSOLogin Component

The frontend provides a visual interface for mock SSO login:

```typescript
import { MockSSOLogin } from "@/components/mock-sso-login";

// Component automatically hides in production
<MockSSOLogin />
```

### Features

- **User Selection Grid**: Visual cards showing all available mock users
- **Role Indicators**: Color-coded badges and icons for each role
- **One-Click Login**: Direct login without password entry
- **Error Handling**: Clear feedback for login failures
- **Responsive Design**: Works on mobile and desktop

### Integration

The component integrates with the existing authentication system:

```typescript
// Automatically updates auth state after mock login
const { user, isAuthenticated } = useAuth();

// Mock login sets tokens and refreshes application state
localStorage.setItem("token", access_token);
api.setToken(access_token);
window.location.reload(); // Refresh auth state
```

## Usage Workflows

### Development Testing

1. **Role Switching**: Quickly test features as different user types
2. **Permission Testing**: Verify role-based access controls
3. **UI Testing**: See interface changes for different roles
4. **API Testing**: Test endpoints with various user contexts

### Example Workflow

```bash
# 1. Start the application
docker compose -f docker-compose.dev.yml up -d

# 2. Visit login page - mock SSO interface appears below regular login
http://localhost:3000

# 3. Click "Initialize Mock Users" (first time only)

# 4. Select desired user role and click "Login as this user"

# 5. Application redirects to appropriate dashboard for that role
```

### Testing Different Scenarios

- **Student Access**: Use `student001-003` to test application submission
- **Professor Review**: Use `prof001-002` to test application reviews
- **College Approval**: Use `college001` to test department-level approvals
- **Admin Functions**: Use `admin001` for system administration
- **Super Admin**: Use `superadmin` for full system access

## Production Safety

### Automatic Disabling

```typescript
// Frontend check
if (process.env.NODE_ENV === "production") {
  return null; // Component doesn't render
}

// Backend check
if (!settings.enable_mock_sso) {
  raise HTTPException(status_code=404, detail="Mock SSO is disabled")
}
```

### Environment Detection

The system uses multiple layers to ensure mock SSO is never available in production:

1. **Environment Variable**: `ENABLE_MOCK_SSO=false` in production
2. **Frontend Check**: Component hidden when `NODE_ENV=production`
3. **Backend Validation**: Endpoints return 404 when disabled
4. **Configuration**: Default to disabled in production configs

## Testing

### Backend Tests

```bash
# Run mock SSO tests
pytest backend/app/tests/test_mock_sso.py -v

# Test with mock SSO disabled
pytest backend/app/tests/test_mock_sso.py::TestMockSSO::test_mock_sso_disabled_in_production -v
```

### Frontend Tests

```bash
# Test mock SSO component
npm test -- --testPathPattern=mock-sso

# E2E testing with mock users
npm run e2e:test
```

## Configuration Examples

### Development Environment

```bash
# .env.development
ENABLE_MOCK_SSO=true
MOCK_SSO_DOMAIN=dev.university.edu
SECRET_KEY=dev-secret-key-for-testing-only
DATABASE_URL=postgresql+asyncpg://dev:dev@localhost:5432/scholarship_dev
```

### Production Environment

```bash
# .env.production
ENABLE_MOCK_SSO=false
# Mock SSO completely disabled - endpoints return 404
```

### Docker Development

```yaml
# docker-compose.dev.yml
services:
  backend:
    environment:
      - ENABLE_MOCK_SSO=true
      - MOCK_SSO_DOMAIN=dev.university.edu
  frontend:
    environment:
      - NODE_ENV=development
```

## Troubleshooting

### Common Issues

1. **Mock SSO Not Visible**
   - Check `NODE_ENV` is not set to "production"
   - Verify `ENABLE_MOCK_SSO=true` in backend config

2. **Login Failed**
   - Click "Initialize Mock Users" first
   - Check backend is running and accessible
   - Verify database connection

3. **Token Issues**
   - Clear browser localStorage and try again
   - Check JWT secret key configuration
   - Verify token expiration settings

### Debug Commands

```bash
# Check mock SSO status
curl http://localhost:8000/api/v1/auth/mock-sso/users

# Initialize mock users
curl -X POST http://localhost:8000/api/v1/auth/mock-sso/init

# Test mock login
curl -X POST http://localhost:8000/api/v1/auth/mock-sso/login \
  -H "Content-Type: application/json" \
  -d '{"username": "student001"}'
```

## Security Considerations

### Development Only

- Mock SSO should never be enabled in production
- Default password `dev123456` is intentionally simple for development
- Mock users have elevated privileges for testing purposes

### Database Isolation

- Use separate databases for development and production
- Mock users are clearly identifiable by email domain
- Regular cleanup of development databases recommended

## Best Practices

### Development Workflow

1. **Initialize Once**: Run mock user initialization at project setup
2. **Role Testing**: Systematically test each user role
3. **Clean State**: Reset application state between role switches
4. **Documentation**: Document test scenarios for each role

### Team Collaboration

1. **Shared Users**: Use same mock users across team
2. **Test Data**: Maintain consistent test data with mock users
3. **CI/CD**: Include mock SSO in automated testing pipelines
4. **Documentation**: Keep this documentation updated with new mock users

This mock SSO implementation significantly improves development productivity by eliminating authentication complexity while maintaining security in production environments.
