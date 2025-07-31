# Developer Profile System Documentation

## Overview

The Developer Profile System extends the Mock SSO authentication to provide each developer with personalized test user accounts. This allows developers to create, manage, and test with their own isolated set of user profiles without interfering with other developers' work.

## Features

### 🔧 Personalized Development Environment
- Each developer gets their own namespace for test users
- Profile format: `dev_[developer-id]_[role]`
- Isolated testing environments per developer
- Persistent profiles across development sessions

### 🚀 Quick Profile Creation
- **Quick Setup**: Create basic profiles (Student, Professor, Admin)
- **Student Suite**: Comprehensive student profiles (Freshman, Graduate, PhD)
- **Staff Suite**: Complete staff profiles (Professor, College Admin, System Admin)
- **Custom Profiles**: Design specific test scenarios

### 🎭 Role-Based Testing
- All user roles supported: Student, Professor, College, Admin, Super Admin
- Bilingual names (Chinese/English) for realistic UI testing
- Custom attributes for specialized testing scenarios
- Automatic GPA and academic data generation

### 🔒 Production Safety
- Automatically disabled in production environments
- Multiple safety layers prevent accidental production use
- Clear development-only indicators in UI

## Quick Start

### 1. Start Development Environment

```bash
# Start all services with mock SSO enabled
./test-docker.sh start

# Verify developer profile system is available
./test-developer-profiles.sh --help
```

### 2. Create Your Test Profiles

```bash
# Quick setup with your developer ID
./test-developer-profiles.sh your-dev-id

# Or just the API endpoints
./test-developer-profiles.sh your-dev-id api

# Frontend UI testing
./test-developer-profiles.sh your-dev-id ui
```

### 3. Use Frontend Interface

1. Open http://localhost:3000
2. Look for "Developer Profile Manager" below the login form
3. Enter your developer ID
4. Use Quick Actions or create custom profiles
5. One-click login with created profiles

## API Reference

### Base URL
```
http://localhost:8000/api/v1/auth/dev-profiles
```

### Endpoints

#### Get All Developers
```http
GET /developers
```
Returns list of all developer IDs that have test profiles.

**Response:**
```json
{
  "success": true,
  "message": "Developer list retrieved successfully",
  "data": ["alice", "bob", "charlie"]
}
```

#### Get Developer Profiles
```http
GET /{developer_id}
```
Get all test profiles for a specific developer.

**Response:**
```json
{
  "success": true,
  "message": "Developer profiles for alice retrieved successfully",
  "data": {
    "developer_id": "alice",
    "profiles": [
      {
        "username": "dev_alice_student",
        "email": "dev_alice_student@dev.local",
        "full_name": "Alice Student",
        "chinese_name": "alice學生",
        "english_name": "Alice Student",
        "role": "student",
        "is_active": true,
        "created_at": "2024-01-01T12:00:00Z"
      }
    ],
    "count": 1
  }
}
```

#### Quick Setup
```http
POST /{developer_id}/quick-setup
```
Create basic test profiles (Student, Professor, Admin) for a developer.

**Response:**
```json
{
  "success": true,
  "message": "Quick setup completed for alice",
  "data": {
    "developer_id": "alice",
    "created_profiles": [
      {
        "username": "dev_alice_student",
        "full_name": "Alice Student",
        "role": "student"
      },
      {
        "username": "dev_alice_professor",
        "full_name": "Prof. Alice",
        "role": "professor"
      },
      {
        "username": "dev_alice_admin",
        "full_name": "Alice Admin",
        "role": "admin"
      }
    ],
    "count": 3
  }
}
```

#### Create Custom Profile
```http
POST /{developer_id}/create-custom
Content-Type: application/json

{
  "full_name": "Alice Custom Student",
  "chinese_name": "alice自定義學生",
  "english_name": "Alice Custom Student",
  "role": "student",
  "email_domain": "custom.dev",
  "custom_attributes": {
    "gpa": 3.9,
    "major": "Computer Science",
    "year": "senior"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Custom profile created for alice",
  "data": {
    "username": "dev_alice_student",
    "email": "dev_alice_student@custom.dev",
    "full_name": "Alice Custom Student",
    "role": "student"
  }
}
```

#### Create Student Suite
```http
POST /{developer_id}/student-suite
```
Create comprehensive student profiles (Freshman, Graduate, PhD).

**Response:**
```json
{
  "success": true,
  "message": "Student suite created for alice",
  "data": {
    "developer_id": "alice",
    "created_profiles": [
      {
        "username": "dev_alice_student",
        "full_name": "Alice Freshman",
        "role": "student",
        "student_type": "undergraduate"
      },
      {
        "username": "dev_alice_student",
        "full_name": "Alice Graduate",
        "role": "student",
        "student_type": "graduate"
      },
      {
        "username": "dev_alice_student",
        "full_name": "Dr. Alice",
        "role": "student",
        "student_type": "phd"
      }
    ],
    "count": 3
  }
}
```

#### Create Staff Suite
```http
POST /{developer_id}/staff-suite
```
Create complete staff profiles (Professor, College Admin, System Admin).

#### Delete All Profiles
```http
DELETE /{developer_id}
```
Delete all test profiles for a developer.

**Response:**
```json
{
  "success": true,
  "message": "Deleted 5 profiles for developer alice",
  "data": {
    "developer_id": "alice",
    "deleted_count": 5
  }
}
```

#### Delete Specific Profile
```http
DELETE /{developer_id}/{role}
```
Delete a specific test profile for a developer.

## Frontend Integration

### Developer Profile Manager Component

The `DeveloperProfileManager` component provides a comprehensive UI for managing developer profiles:

```typescript
import { DeveloperProfileManager } from "@/components/developer-profile-manager";

// Usage in login page
<DeveloperProfileManager />
```

### Features:
- **Tabbed Interface**: Quick Actions, Custom Profile, Manage Profiles
- **Visual Profile Cards**: Role-based color coding and icons
- **One-Click Login**: Direct authentication with created profiles
- **Real-time Updates**: Automatically refreshes after profile operations
- **Responsive Design**: Works on desktop and mobile devices

### Tab Descriptions:

#### Quick Actions Tab
- **Quick Setup**: Create basic Student, Professor, Admin profiles
- **Student Suite**: Create Freshman, Graduate, PhD student profiles
- **Staff Suite**: Create Professor, College Admin, System Admin profiles
- **Cleanup**: Delete all profiles for the developer

#### Custom Profile Tab
- **Full Name**: Required field for the profile
- **Chinese Name**: Optional Chinese name for bilingual testing
- **English Name**: Optional English name
- **Role Selection**: Dropdown for all available roles
- **Email Domain**: Customizable email domain (default: dev.local)

#### Manage Profiles Tab
- **Profile Cards**: Visual representation of all created profiles
- **Role Badges**: Color-coded role indicators
- **Login Buttons**: One-click authentication
- **Profile Information**: Username, email, names, creation date

## Programming Interface

### Service Layer

```python
from app.services.developer_profile_service import DeveloperProfileService, DeveloperProfile

# Initialize service
service = DeveloperProfileService(db_session)

# Create a custom profile
profile = DeveloperProfile(
    developer_id="alice",
    full_name="Alice Test Student",
    chinese_name="alice測試學生",
    role=UserRole.STUDENT,
    custom_attributes={"gpa": 3.8}
)

user = await service.create_developer_user("alice", profile)

# Get all profiles for a developer
profiles = await service.get_developer_users("alice")

# Quick setup
users = await service.quick_setup_developer("alice")
```

### Profile Manager Helpers

```python
from app.services.developer_profile_service import DeveloperProfileManager

# Create custom profile
profile = DeveloperProfileManager.create_custom_profile(
    developer_id="alice",
    role=UserRole.STUDENT,
    full_name="Custom Student",
    gpa=3.9,
    major="Computer Science"
)

# Create student profiles
student_profiles = DeveloperProfileManager.create_student_profiles("alice")

# Create staff profiles
staff_profiles = DeveloperProfileManager.create_staff_profiles("alice")
```

## Testing Framework

### Automated Testing Script

```bash
# Test all functionality
./test-developer-profiles.sh alice

# Test specific areas
./test-developer-profiles.sh alice api      # API endpoints only
./test-developer-profiles.sh alice create   # Profile creation only
./test-developer-profiles.sh alice auth     # Authentication flow
./test-developer-profiles.sh alice ui       # Frontend integration
./test-developer-profiles.sh alice cleanup  # Delete all profiles
```

### Test Coverage

The system includes comprehensive tests for:

- **Service Layer Tests**: Profile creation, management, deletion
- **API Endpoint Tests**: All HTTP endpoints and error cases
- **Authentication Flow Tests**: Login and token validation
- **Frontend Integration Tests**: UI component functionality
- **Production Safety Tests**: Verification of security measures

### Example Test Run

```bash
./test-developer-profiles.sh alice full
```

Expected output:
```
======================================
Developer Profile System Test
======================================
Developer ID: alice
Test Type: full
API Base: http://localhost:8000/api/v1

======================================
Testing System Availability
======================================

➤ Checking backend availability...
✓ Backend is running

➤ Checking mock SSO availability...
✓ Mock SSO is enabled

➤ Checking frontend availability...
✓ Frontend is running

======================================
Testing Developer Profile Creation
======================================

➤ Testing quick setup for developer: alice
✓ Quick setup completed - 3 profiles created

Created profiles:
  - dev_alice_student (student): Alice Student
  - dev_alice_professor (professor): Prof. Alice
  - dev_alice_admin (admin): Alice Admin

... (continued)
```

## Configuration

### Environment Variables

```bash
# Enable mock SSO and developer profiles
ENABLE_MOCK_SSO=true

# Mock SSO domain for test users
MOCK_SSO_DOMAIN=dev.local

# Frontend environment for development
NODE_ENV=development
```

### Docker Configuration

Ensure these settings in `docker-compose.test.yml`:

```yaml
backend:
  environment:
    - ENABLE_MOCK_SSO=true
    - MOCK_SSO_DOMAIN=dev.local

frontend:
  environment:
    - NODE_ENV=development  # Not production
    - NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Best Practices

### Developer ID Convention
- Use your actual name or initials: `alice`, `bob`, `j_smith`
- Keep it short and consistent across projects
- Avoid special characters or spaces

### Profile Naming
- Descriptive names help identify test scenarios
- Include role context: "Alice Senior Student", "Bob Dept Professor"
- Use bilingual names for i18n testing

### Testing Workflows
1. **Feature Development**: Create specific profiles for your feature
2. **Role Testing**: Use staff suites to test different permission levels
3. **Data Scenarios**: Use custom attributes for edge cases
4. **Clean Workflows**: Delete profiles when switching contexts

### Team Coordination
- Each developer maintains their own profiles
- Share developer IDs for collaborative testing
- Document special test scenarios in team notes
- Use consistent naming conventions across the team

## Security Considerations

### Production Safety
- **Automatic Disabling**: System automatically disables in production
- **Environment Checks**: Multiple layers verify development environment
- **Clear Indicators**: UI clearly shows development-only features
- **No Production Data**: Uses separate test database and domains

### Development Security
- **Standard Password**: All profiles use `dev123456` for consistency
- **Local Domains**: Uses `.dev.local` and similar test domains
- **JWT Tokens**: Real authentication tokens for realistic testing
- **Role Verification**: Proper role-based access control testing

### Data Isolation
- **Developer Namespaces**: Each developer's profiles are isolated
- **Test Databases**: Uses development/test databases only
- **Cleanup Tools**: Easy deletion of test data
- **No Cross-Contamination**: Developers cannot access each other's profiles accidentally

## Troubleshooting

### Common Issues

#### Mock SSO Not Available
```bash
# Check if backend is running
curl http://localhost:8000/api/v1/health

# Check mock SSO setting
echo $ENABLE_MOCK_SSO

# Restart with correct settings
./test-docker.sh stop
./test-docker.sh start
```

#### Frontend Component Not Visible
- Verify `NODE_ENV=development` (not production)
- Check browser console for JavaScript errors
- Ensure Developer Profile Manager is imported correctly

#### Profile Creation Failed
- Verify database is running and accessible
- Check API logs for detailed error messages
- Ensure all required fields are provided

#### Authentication Issues
- Verify mock SSO endpoints are working
- Check JWT token generation and validation
- Test with curl commands first, then frontend

### Debug Commands

```bash
# Check service status
./test-docker.sh status

# View backend logs
./test-docker.sh logs backend

# Test API directly
curl -X POST http://localhost:8000/api/v1/auth/dev-profiles/debug/quick-setup

# Check database users
./test-docker.sh exec backend python -c "
from app.db.session import SessionLocal
from app.models.user import User
with SessionLocal() as db:
    users = db.query(User).filter(User.username.like('dev_%')).all()
    for user in users:
        print(f'{user.username} - {user.role} - {user.full_name}')
"
```

## Integration with Existing Systems

### Mock SSO Compatibility
The Developer Profile System builds on the existing Mock SSO infrastructure:
- Uses same JWT authentication
- Leverages existing user management
- Extends existing API patterns
- Maintains production safety measures

### Database Integration
- Uses existing User model and database
- Follows established naming conventions
- Maintains referential integrity
- Supports existing migration system

### Frontend Integration
- Integrates with existing auth hooks
- Uses established UI component patterns
- Follows existing styling guidelines
- Maintains responsive design principles

## Future Enhancements

### Planned Features
- **Profile Templates**: Pre-configured profile sets for common scenarios
- **Team Profiles**: Shared profiles for team collaboration
- **Export/Import**: Save and share profile configurations
- **Advanced Attributes**: More sophisticated custom attribute management
- **Audit Logging**: Track profile usage and modifications

### Extension Points
- **Custom Authenticators**: Support for different authentication methods
- **Profile Validators**: Custom validation rules for profiles
- **Integration Hooks**: Callbacks for profile lifecycle events
- **Bulk Operations**: Mass profile creation and management tools

---

## Summary

The Developer Profile System provides a comprehensive, safe, and efficient way for developers to create and manage personalized test user accounts. It enhances the development experience by providing:

✅ **Isolated Development**: Each developer gets their own test environment  
✅ **Quick Setup**: One-command profile creation for common scenarios  
✅ **Custom Scenarios**: Flexible profile creation for specific test cases  
✅ **Production Safety**: Multiple layers prevent production usage  
✅ **Team Friendly**: No interference between developers  
✅ **Comprehensive Testing**: Full test coverage and validation tools  

For questions or issues, please refer to the troubleshooting section or check the test scripts for usage examples. 

## Overview

The Developer Profile System extends the Mock SSO authentication to provide each developer with personalized test user accounts. This allows developers to create, manage, and test with their own isolated set of user profiles without interfering with other developers' work.

## Features

### 🔧 Personalized Development Environment
- Each developer gets their own namespace for test users
- Profile format: `dev_[developer-id]_[role]`
- Isolated testing environments per developer
- Persistent profiles across development sessions

### 🚀 Quick Profile Creation
- **Quick Setup**: Create basic profiles (Student, Professor, Admin)
- **Student Suite**: Comprehensive student profiles (Freshman, Graduate, PhD)
- **Staff Suite**: Complete staff profiles (Professor, College Admin, System Admin)
- **Custom Profiles**: Design specific test scenarios

### 🎭 Role-Based Testing
- All user roles supported: Student, Professor, College, Admin, Super Admin
- Bilingual names (Chinese/English) for realistic UI testing
- Custom attributes for specialized testing scenarios
- Automatic GPA and academic data generation

### 🔒 Production Safety
- Automatically disabled in production environments
- Multiple safety layers prevent accidental production use
- Clear development-only indicators in UI

## Quick Start

### 1. Start Development Environment

```bash
# Start all services with mock SSO enabled
./test-docker.sh start

# Verify developer profile system is available
./test-developer-profiles.sh --help
```

### 2. Create Your Test Profiles

```bash
# Quick setup with your developer ID
./test-developer-profiles.sh your-dev-id

# Or just the API endpoints
./test-developer-profiles.sh your-dev-id api

# Frontend UI testing
./test-developer-profiles.sh your-dev-id ui
```

### 3. Use Frontend Interface

1. Open http://localhost:3000
2. Look for "Developer Profile Manager" below the login form
3. Enter your developer ID
4. Use Quick Actions or create custom profiles
5. One-click login with created profiles

## API Reference

### Base URL
```
http://localhost:8000/api/v1/auth/dev-profiles
```

### Endpoints

#### Get All Developers
```http
GET /developers
```
Returns list of all developer IDs that have test profiles.

**Response:**
```json
{
  "success": true,
  "message": "Developer list retrieved successfully",
  "data": ["alice", "bob", "charlie"]
}
```

#### Get Developer Profiles
```http
GET /{developer_id}
```
Get all test profiles for a specific developer.

**Response:**
```json
{
  "success": true,
  "message": "Developer profiles for alice retrieved successfully",
  "data": {
    "developer_id": "alice",
    "profiles": [
      {
        "username": "dev_alice_student",
        "email": "dev_alice_student@dev.local",
        "full_name": "Alice Student",
        "chinese_name": "alice學生",
        "english_name": "Alice Student",
        "role": "student",
        "is_active": true,
        "created_at": "2024-01-01T12:00:00Z"
      }
    ],
    "count": 1
  }
}
```

#### Quick Setup
```http
POST /{developer_id}/quick-setup
```
Create basic test profiles (Student, Professor, Admin) for a developer.

**Response:**
```json
{
  "success": true,
  "message": "Quick setup completed for alice",
  "data": {
    "developer_id": "alice",
    "created_profiles": [
      {
        "username": "dev_alice_student",
        "full_name": "Alice Student",
        "role": "student"
      },
      {
        "username": "dev_alice_professor",
        "full_name": "Prof. Alice",
        "role": "professor"
      },
      {
        "username": "dev_alice_admin",
        "full_name": "Alice Admin",
        "role": "admin"
      }
    ],
    "count": 3
  }
}
```

#### Create Custom Profile
```http
POST /{developer_id}/create-custom
Content-Type: application/json

{
  "full_name": "Alice Custom Student",
  "chinese_name": "alice自定義學生",
  "english_name": "Alice Custom Student",
  "role": "student",
  "email_domain": "custom.dev",
  "custom_attributes": {
    "gpa": 3.9,
    "major": "Computer Science",
    "year": "senior"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "Custom profile created for alice",
  "data": {
    "username": "dev_alice_student",
    "email": "dev_alice_student@custom.dev",
    "full_name": "Alice Custom Student",
    "role": "student"
  }
}
```

#### Create Student Suite
```http
POST /{developer_id}/student-suite
```
Create comprehensive student profiles (Freshman, Graduate, PhD).

**Response:**
```json
{
  "success": true,
  "message": "Student suite created for alice",
  "data": {
    "developer_id": "alice",
    "created_profiles": [
      {
        "username": "dev_alice_student",
        "full_name": "Alice Freshman",
        "role": "student",
        "student_type": "undergraduate"
      },
      {
        "username": "dev_alice_student",
        "full_name": "Alice Graduate",
        "role": "student",
        "student_type": "graduate"
      },
      {
        "username": "dev_alice_student",
        "full_name": "Dr. Alice",
        "role": "student",
        "student_type": "phd"
      }
    ],
    "count": 3
  }
}
```

#### Create Staff Suite
```http
POST /{developer_id}/staff-suite
```
Create complete staff profiles (Professor, College Admin, System Admin).

#### Delete All Profiles
```http
DELETE /{developer_id}
```
Delete all test profiles for a developer.

**Response:**
```json
{
  "success": true,
  "message": "Deleted 5 profiles for developer alice",
  "data": {
    "developer_id": "alice",
    "deleted_count": 5
  }
}
```

#### Delete Specific Profile
```http
DELETE /{developer_id}/{role}
```
Delete a specific test profile for a developer.

## Frontend Integration

### Developer Profile Manager Component

The `DeveloperProfileManager` component provides a comprehensive UI for managing developer profiles:

```typescript
import { DeveloperProfileManager } from "@/components/developer-profile-manager";

// Usage in login page
<DeveloperProfileManager />
```

### Features:
- **Tabbed Interface**: Quick Actions, Custom Profile, Manage Profiles
- **Visual Profile Cards**: Role-based color coding and icons
- **One-Click Login**: Direct authentication with created profiles
- **Real-time Updates**: Automatically refreshes after profile operations
- **Responsive Design**: Works on desktop and mobile devices

### Tab Descriptions:

#### Quick Actions Tab
- **Quick Setup**: Create basic Student, Professor, Admin profiles
- **Student Suite**: Create Freshman, Graduate, PhD student profiles
- **Staff Suite**: Create Professor, College Admin, System Admin profiles
- **Cleanup**: Delete all profiles for the developer

#### Custom Profile Tab
- **Full Name**: Required field for the profile
- **Chinese Name**: Optional Chinese name for bilingual testing
- **English Name**: Optional English name
- **Role Selection**: Dropdown for all available roles
- **Email Domain**: Customizable email domain (default: dev.local)

#### Manage Profiles Tab
- **Profile Cards**: Visual representation of all created profiles
- **Role Badges**: Color-coded role indicators
- **Login Buttons**: One-click authentication
- **Profile Information**: Username, email, names, creation date

## Programming Interface

### Service Layer

```python
from app.services.developer_profile_service import DeveloperProfileService, DeveloperProfile

# Initialize service
service = DeveloperProfileService(db_session)

# Create a custom profile
profile = DeveloperProfile(
    developer_id="alice",
    full_name="Alice Test Student",
    chinese_name="alice測試學生",
    role=UserRole.STUDENT,
    custom_attributes={"gpa": 3.8}
)

user = await service.create_developer_user("alice", profile)

# Get all profiles for a developer
profiles = await service.get_developer_users("alice")

# Quick setup
users = await service.quick_setup_developer("alice")
```

### Profile Manager Helpers

```python
from app.services.developer_profile_service import DeveloperProfileManager

# Create custom profile
profile = DeveloperProfileManager.create_custom_profile(
    developer_id="alice",
    role=UserRole.STUDENT,
    full_name="Custom Student",
    gpa=3.9,
    major="Computer Science"
)

# Create student profiles
student_profiles = DeveloperProfileManager.create_student_profiles("alice")

# Create staff profiles
staff_profiles = DeveloperProfileManager.create_staff_profiles("alice")
```

## Testing Framework

### Automated Testing Script

```bash
# Test all functionality
./test-developer-profiles.sh alice

# Test specific areas
./test-developer-profiles.sh alice api      # API endpoints only
./test-developer-profiles.sh alice create   # Profile creation only
./test-developer-profiles.sh alice auth     # Authentication flow
./test-developer-profiles.sh alice ui       # Frontend integration
./test-developer-profiles.sh alice cleanup  # Delete all profiles
```

### Test Coverage

The system includes comprehensive tests for:

- **Service Layer Tests**: Profile creation, management, deletion
- **API Endpoint Tests**: All HTTP endpoints and error cases
- **Authentication Flow Tests**: Login and token validation
- **Frontend Integration Tests**: UI component functionality
- **Production Safety Tests**: Verification of security measures

### Example Test Run

```bash
./test-developer-profiles.sh alice full
```

Expected output:
```
======================================
Developer Profile System Test
======================================
Developer ID: alice
Test Type: full
API Base: http://localhost:8000/api/v1

======================================
Testing System Availability
======================================

➤ Checking backend availability...
✓ Backend is running

➤ Checking mock SSO availability...
✓ Mock SSO is enabled

➤ Checking frontend availability...
✓ Frontend is running

======================================
Testing Developer Profile Creation
======================================

➤ Testing quick setup for developer: alice
✓ Quick setup completed - 3 profiles created

Created profiles:
  - dev_alice_student (student): Alice Student
  - dev_alice_professor (professor): Prof. Alice
  - dev_alice_admin (admin): Alice Admin

... (continued)
```

## Configuration

### Environment Variables

```bash
# Enable mock SSO and developer profiles
ENABLE_MOCK_SSO=true

# Mock SSO domain for test users
MOCK_SSO_DOMAIN=dev.local

# Frontend environment for development
NODE_ENV=development
```

### Docker Configuration

Ensure these settings in `docker-compose.test.yml`:

```yaml
backend:
  environment:
    - ENABLE_MOCK_SSO=true
    - MOCK_SSO_DOMAIN=dev.local

frontend:
  environment:
    - NODE_ENV=development  # Not production
    - NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Best Practices

### Developer ID Convention
- Use your actual name or initials: `alice`, `bob`, `j_smith`
- Keep it short and consistent across projects
- Avoid special characters or spaces

### Profile Naming
- Descriptive names help identify test scenarios
- Include role context: "Alice Senior Student", "Bob Dept Professor"
- Use bilingual names for i18n testing

### Testing Workflows
1. **Feature Development**: Create specific profiles for your feature
2. **Role Testing**: Use staff suites to test different permission levels
3. **Data Scenarios**: Use custom attributes for edge cases
4. **Clean Workflows**: Delete profiles when switching contexts

### Team Coordination
- Each developer maintains their own profiles
- Share developer IDs for collaborative testing
- Document special test scenarios in team notes
- Use consistent naming conventions across the team

## Security Considerations

### Production Safety
- **Automatic Disabling**: System automatically disables in production
- **Environment Checks**: Multiple layers verify development environment
- **Clear Indicators**: UI clearly shows development-only features
- **No Production Data**: Uses separate test database and domains

### Development Security
- **Standard Password**: All profiles use `dev123456` for consistency
- **Local Domains**: Uses `.dev.local` and similar test domains
- **JWT Tokens**: Real authentication tokens for realistic testing
- **Role Verification**: Proper role-based access control testing

### Data Isolation
- **Developer Namespaces**: Each developer's profiles are isolated
- **Test Databases**: Uses development/test databases only
- **Cleanup Tools**: Easy deletion of test data
- **No Cross-Contamination**: Developers cannot access each other's profiles accidentally

## Troubleshooting

### Common Issues

#### Mock SSO Not Available
```bash
# Check if backend is running
curl http://localhost:8000/api/v1/health

# Check mock SSO setting
echo $ENABLE_MOCK_SSO

# Restart with correct settings
./test-docker.sh stop
./test-docker.sh start
```

#### Frontend Component Not Visible
- Verify `NODE_ENV=development` (not production)
- Check browser console for JavaScript errors
- Ensure Developer Profile Manager is imported correctly

#### Profile Creation Failed
- Verify database is running and accessible
- Check API logs for detailed error messages
- Ensure all required fields are provided

#### Authentication Issues
- Verify mock SSO endpoints are working
- Check JWT token generation and validation
- Test with curl commands first, then frontend

### Debug Commands

```bash
# Check service status
./test-docker.sh status

# View backend logs
./test-docker.sh logs backend

# Test API directly
curl -X POST http://localhost:8000/api/v1/auth/dev-profiles/debug/quick-setup

# Check database users
./test-docker.sh exec backend python -c "
from app.db.session import SessionLocal
from app.models.user import User
with SessionLocal() as db:
    users = db.query(User).filter(User.username.like('dev_%')).all()
    for user in users:
        print(f'{user.username} - {user.role} - {user.full_name}')
"
```

## Integration with Existing Systems

### Mock SSO Compatibility
The Developer Profile System builds on the existing Mock SSO infrastructure:
- Uses same JWT authentication
- Leverages existing user management
- Extends existing API patterns
- Maintains production safety measures

### Database Integration
- Uses existing User model and database
- Follows established naming conventions
- Maintains referential integrity
- Supports existing migration system

### Frontend Integration
- Integrates with existing auth hooks
- Uses established UI component patterns
- Follows existing styling guidelines
- Maintains responsive design principles

## Future Enhancements

### Planned Features
- **Profile Templates**: Pre-configured profile sets for common scenarios
- **Team Profiles**: Shared profiles for team collaboration
- **Export/Import**: Save and share profile configurations
- **Advanced Attributes**: More sophisticated custom attribute management
- **Audit Logging**: Track profile usage and modifications

### Extension Points
- **Custom Authenticators**: Support for different authentication methods
- **Profile Validators**: Custom validation rules for profiles
- **Integration Hooks**: Callbacks for profile lifecycle events
- **Bulk Operations**: Mass profile creation and management tools

---

## Summary

The Developer Profile System provides a comprehensive, safe, and efficient way for developers to create and manage personalized test user accounts. It enhances the development experience by providing:

✅ **Isolated Development**: Each developer gets their own test environment  
✅ **Quick Setup**: One-command profile creation for common scenarios  
✅ **Custom Scenarios**: Flexible profile creation for specific test cases  
✅ **Production Safety**: Multiple layers prevent production usage  
✅ **Team Friendly**: No interference between developers  
✅ **Comprehensive Testing**: Full test coverage and validation tools  

For questions or issues, please refer to the troubleshooting section or check the test scripts for usage examples. 