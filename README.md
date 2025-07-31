# Scholarship Management System

A comprehensive scholarship application and approval management system built with FastAPI, PostgreSQL, Next.js 15, and TypeScript.

## 🚀 Features

- **Multi-role Support**: Students, Faculty, Admin, Super Admin roles
- **Application Workflow**: Complete scholarship application lifecycle
- **Document Management**: File upload with OCR processing and virus scanning
- **Multi-language Support**: English/Chinese switching for student interfaces
- **GPA Validation**: Automatic validation based on scholarship requirements
- **Email Notifications**: Status updates and workflow notifications
- **Responsive Design**: Modern UI with Tailwind CSS and shadcn/ui

## 🛠️ Quick Start

Get started in 5 minutes with Docker:

```bash
# Start all services
./test-docker.sh start

# Access the application
# Frontend: http://localhost:3000
# API Docs: http://localhost:8000/docs
```

👉 **[Complete Quick Start Guide](docs/getting-started/quick-start.md)**

## 📚 Documentation

### Getting Started
- 🚀 [Quick Start Guide](docs/getting-started/quick-start.md)
- 📦 [Installation Guide](docs/getting-started/installation.md)
- 🔧 [Development Setup](docs/getting-started/development-setup.md)

### Architecture
- 🏗️ [System Overview](docs/architecture/system-overview.md)
- 🗄️ [Database Schema](docs/architecture/database-schema.md)
- 🔌 [API Design](docs/architecture/api-design.md)

### Features
- 👥 [User Management](docs/features/user-management.md)
- 🔐 [Authentication System](docs/features/authentication.md)
- 🧑‍💻 [Developer Profiles](docs/features/developer-profiles.md)

### Development
- 🧪 [Testing Guide](docs/development/testing.md)
- 🚀 [CI/CD Pipeline](docs/development/ci-cd.md)
- 📝 [Migration Guides](docs/development/migration-guides.md)

### Deployment
- 🐳 [Docker Setup](docs/deployment/docker-setup.md)
- 🌐 [Production Deployment](docs/deployment/production-deployment.md)

### Specifications
- 📋 [System Requirements (SRS)](docs/specifications/srs-v1.0.md)
- 📊 [Business Requirements](docs/specifications/requirements.md)

## 🔧 Development

### Environment Setup
```bash
# Copy environment template
cp .env.example .env

# Edit configuration
nano .env
```

### Database Management
```bash
# Run migrations
./test-docker.sh migrate

# Seed test data
./test-docker.sh seed

# Reset database
./test-docker.sh reset-db
```

### Testing
```bash
# Run all tests
./test-docker.sh test

# Backend tests only
./test-docker.sh test-backend

# Frontend tests only
./test-docker.sh test-frontend

# E2E tests
./test-docker.sh test-e2e
```

## 📋 API Endpoints

### Authentication
- `POST /api/v1/auth/login` - User login
- `POST /api/v1/auth/register` - Student registration
- `POST /api/v1/auth/refresh` - Token refresh

### Applications
- `GET /api/v1/applications` - List applications (role-filtered)
- `POST /api/v1/applications` - Create application
- `GET /api/v1/applications/{id}` - Get application details
- `PUT /api/v1/applications/{id}` - Update application
- `POST /api/v1/applications/{id}/submit` - Submit for review

### Users
- `GET /api/v1/users/me` - Current user profile
- `PUT /api/v1/users/me` - Update profile
- `GET /api/v1/users` - List users (admin only)

## 🔒 Security Features

- **JWT Authentication** with role-based access control
- **Input Validation** with Pydantic and Zod
- **File Upload Security** with type/size restrictions and virus scanning
- **SQL Injection Protection** with parameterized queries
- **Rate Limiting** on API endpoints

## 🌐 Multi-language Support

Student-facing interfaces support English/Chinese switching:
- Dashboard and navigation
- Form labels and validation messages
- Email notifications

## 📊 Business Rules

### User Roles
- **Student**: Submit and manage applications
- **Faculty**: Review applications in their department
- **Admin**: Full system access
- **Super Admin**: System configuration and user management

### GPA Requirements
- Academic Excellence: 3.8+
- Merit-based: 3.5+
- Need-based: 2.5+
- Athletic: 2.0+
- International Student: 3.0+

### Application Status Flow
`Draft → Submitted → Under Review → Approved/Rejected`

## 🧪 Testing Strategy

- **Unit Tests**: 90% coverage target
- **Integration Tests**: All API endpoints
- **E2E Tests**: Critical user workflows
- **Performance Tests**: p95 < 600ms response time

## 📈 Performance Targets

- **API Response Time**: p95 < 600ms
- **Page Load Time**: < 3 seconds
- **File Upload**: 10MB max per file
- **Concurrent Users**: 100+ simultaneous

## 🚀 Deployment

### Production Environment
```bash
# Build production images
docker-compose -f docker-compose.prod.yml build

# Deploy with secrets
docker-compose -f docker-compose.prod.yml up -d
```

### Health Checks
All services include health checks for monitoring and auto-recovery.

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

### Code Standards
- **Backend**: camelCase for variables/functions, PascalCase for classes
- **Frontend**: PascalCase for components, camelCase for variables
- **API Endpoints**: camelCase (e.g., `/getApplications`)
- **Database**: snake_case for tables and fields

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 📞 Support

For issues and questions:
- Create an issue on GitHub
- Check the [Documentation](docs/)
- Review the [API Documentation](http://localhost:8000/docs) when running

---

**Target Launch**: July 3, 2025

Built with ❤️ for education accessibility 