# API Design Documentation

## API Architecture

The Scholarship Management System API follows RESTful principles with FastAPI, providing a modern, fast, and well-documented interface.

## Base URL Structure

```
Production: https://api.scholarship.edu
Development: http://localhost:8000
API Version: /api/v1
```

## Authentication

### JWT Token-based Authentication
```http
Authorization: Bearer <jwt-token>
```

### Token Endpoints
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - Student registration
- `POST /api/v1/auth/refresh` - Token refresh
- `POST /api/v1/auth/logout` - User logout

## API Endpoints

### User Management
```http
GET    /api/v1/users              # List users (admin only)
POST   /api/v1/users              # Create user (admin only)
GET    /api/v1/users/me           # Current user profile
PUT    /api/v1/users/me           # Update current user
GET    /api/v1/users/{id}         # Get user by ID (admin only)
PUT    /api/v1/users/{id}         # Update user (admin only)
DELETE /api/v1/users/{id}         # Delete user (super admin only)
GET    /api/v1/users/stats/overview # User statistics (admin only)
```

### Application Management
```http
GET    /api/v1/applications       # List applications (role-filtered)
POST   /api/v1/applications       # Create application
GET    /api/v1/applications/{id}  # Get application details
PUT    /api/v1/applications/{id}  # Update application
DELETE /api/v1/applications/{id}  # Delete application
POST   /api/v1/applications/{id}/submit # Submit for review
```

### Scholarship Management
```http
GET    /api/v1/scholarships       # List scholarships
POST   /api/v1/scholarships       # Create scholarship (admin only)
GET    /api/v1/scholarships/{id}  # Get scholarship details
PUT    /api/v1/scholarships/{id}  # Update scholarship (admin only)
DELETE /api/v1/scholarships/{id}  # Delete scholarship (admin only)
```

### File Management
```http
POST   /api/v1/files/upload       # Upload file
GET    /api/v1/files/{id}         # Download file
DELETE /api/v1/files/{id}         # Delete file
GET    /api/v1/files/{id}/preview # Preview file (images/PDFs)
```

## Response Format

All API responses follow a consistent structure:

### Success Response
```json
{
  "success": true,
  "message": "Operation successful",
  "data": {
    // Response data here
  },
  "trace_id": "req_abc123"
}
```

### Error Response
```json
{
  "success": false,
  "message": "Error description",
  "error": {
    "code": "ERROR_CODE",
    "details": "Detailed error information",
    "field_errors": {
      "field_name": ["Field-specific error messages"]
    }
  },
  "trace_id": "req_abc123"
}
```

### Pagination Response
```json
{
  "success": true,
  "message": "Data retrieved successfully",
  "data": {
    "items": [...],
    "page": 1,
    "size": 20,
    "total": 150,
    "pages": 8,
    "has_next": true,
    "has_prev": false
  },
  "trace_id": "req_abc123"
}
```

## HTTP Status Codes

- `200 OK` - Successful request
- `201 Created` - Resource created successfully
- `400 Bad Request` - Invalid request data
- `401 Unauthorized` - Authentication required
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found
- `422 Unprocessable Entity` - Validation errors
- `500 Internal Server Error` - Server error

## Query Parameters

### Pagination
```http
GET /api/v1/users?page=1&size=20
```

### Filtering
```http
GET /api/v1/users?role=student&is_active=true&search=john
```

### Sorting
```http
GET /api/v1/applications?sort=created_at&order=desc
```

## Request/Response Examples

### User Login
```http
POST /api/v1/auth/login
Content-Type: application/json

{
  "username": "student@university.edu",
  "password": "securepassword"
}
```

Response:
```json
{
  "success": true,
  "message": "Login successful",
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": "user123",
      "username": "student@university.edu",
      "full_name": "John Student",
      "role": "student",
      "is_active": true
    }
  }
}
```

### Create Application
```http
POST /api/v1/applications
Authorization: Bearer <token>
Content-Type: application/json

{
  "scholarship_type": "academic_excellence",
  "personal_statement": "I am applying for this scholarship...",
  "gpa": 3.8,
  "expected_graduation": "2025-06",
  "documents": ["doc_id_1", "doc_id_2"]
}
```

## Data Models

### User Model
```json
{
  "id": "string",
  "username": "string",
  "email": "string",
  "full_name": "string",
  "role": "student|professor|college|admin|super_admin",
  "is_active": "boolean",
  "created_at": "datetime",
  "updated_at": "datetime",
  "profile": {
    "student_id": "string",
    "department": "string",
    "year": "integer",
    "nationality": "string"
  }
}
```

### Application Model
```json
{
  "id": "integer",
  "student_id": "string",
  "scholarship_type": "string",
  "status": "draft|submitted|under_review|approved|rejected",
  "personal_statement": "string",
  "gpa": "number",
  "documents": ["string"],
  "submitted_at": "datetime",
  "reviewed_at": "datetime",
  "created_at": "datetime",
  "updated_at": "datetime"
}
```

## Rate Limiting

API endpoints are rate-limited to prevent abuse:

- **Authentication endpoints**: 5 requests per minute
- **General endpoints**: 100 requests per minute
- **File upload endpoints**: 10 requests per minute

Rate limit headers:
```http
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1609459200
```

## Error Codes

| Code | Description |
|------|-------------|
| `INVALID_CREDENTIALS` | Invalid username or password |
| `TOKEN_EXPIRED` | JWT token has expired |
| `INSUFFICIENT_PERMISSIONS` | User lacks required permissions |
| `VALIDATION_ERROR` | Request data validation failed |
| `RESOURCE_NOT_FOUND` | Requested resource doesn't exist |
| `DUPLICATE_RESOURCE` | Resource already exists |
| `FILE_TOO_LARGE` | Uploaded file exceeds size limit |
| `INVALID_FILE_TYPE` | File type not allowed |

## OpenAPI Documentation

Interactive API documentation is available at:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

## API Versioning

The API uses URL path versioning:
- Current version: `/api/v1/`
- Future versions: `/api/v2/`, `/api/v3/`, etc.

Backward compatibility is maintained for at least one major version.