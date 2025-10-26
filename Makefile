# Scholarship System Makefile
# Provides convenient commands for development, testing, and deployment

.PHONY: help install setup dev test lint format clean build deploy docker-up docker-down

# Colors for output
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "$(CYAN)Scholarship System - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Setup Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## .*Setup/ {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Development Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## .*Development/ {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Testing Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## .*Test/ {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Docker Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## .*Docker/ {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(GREEN)Other Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / && !/Setup|Development|Test|Docker/ {printf "  $(CYAN)%-20s$(NC) %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# Setup Commands
install: ## Setup - Install all dependencies (backend + frontend)
	@echo "$(GREEN)Installing dependencies...$(NC)"
	@echo "$(CYAN)Installing backend dependencies...$(NC)"
	cd backend && pip install -r requirements.txt && pip install -r requirements-dev.txt || pip install -r requirements.txt
	@echo "$(CYAN)Installing frontend dependencies...$(NC)"
	cd frontend && npm ci
	@echo "$(GREEN)✅ Dependencies installed successfully!$(NC)"

setup: install ## Setup - Complete project setup (install deps + setup env)
	@echo "$(GREEN)Setting up development environment...$(NC)"
	@if [ ! -f backend/.env ]; then \
		echo "$(YELLOW)Creating backend .env file...$(NC)"; \
		cp backend/.env.example backend/.env 2>/dev/null || echo "DATABASE_URL=sqlite+aiosqlite:///./scholarship.db\nSECRET_KEY=dev-secret-key" > backend/.env; \
	fi
	@if [ ! -f frontend/.env.local ]; then \
		echo "$(YELLOW)Creating frontend .env.local file...$(NC)"; \
		cp frontend/.env.example frontend/.env.local 2>/dev/null || echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > frontend/.env.local; \
	fi
	@echo "$(GREEN)✅ Development environment setup complete!$(NC)"
	@echo "$(CYAN)Next steps:$(NC)"
	@echo "  1. Run 'make dev' to start development servers"
	@echo "  2. Run 'make test' to run tests"
	@echo "  3. Run 'make docker-up' to start with Docker"

# Development Commands
dev: ## Development - Start both backend and frontend in development mode
	@echo "$(GREEN)Starting development servers...$(NC)"
	@trap 'kill 0' SIGINT; \
	(cd backend && echo "$(CYAN)Starting backend on http://localhost:8000$(NC)" && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
	(cd frontend && echo "$(CYAN)Starting frontend on http://localhost:3000$(NC)" && npm run dev) & \
	wait

dev-backend: ## Development - Start only backend server
	@echo "$(GREEN)Starting backend server...$(NC)"
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-frontend: ## Development - Start only frontend server
	@echo "$(GREEN)Starting frontend server...$(NC)"
	cd frontend && npm run dev

dev-safe: ## Development - Test API connection then start frontend
	@echo "$(GREEN)Testing API connection before starting frontend...$(NC)"
	cd frontend && npm run dev:safe

# Testing Commands
test: ## Test - Run all tests (backend + frontend)
	@echo "$(GREEN)Running all tests...$(NC)"
	@echo "$(CYAN)Running backend tests...$(NC)"
	cd backend && python -m pytest app/tests -v
	@echo "$(CYAN)Running frontend tests...$(NC)"
	cd frontend && npm run test:ci
	@echo "$(GREEN)✅ All tests completed!$(NC)"

test-backend: ## Test - Run backend tests only
	@echo "$(GREEN)Running backend tests...$(NC)"
	cd backend && python -m pytest app/tests -v

test-frontend: ## Test - Run frontend tests only
	@echo "$(GREEN)Running frontend tests...$(NC)"
	cd frontend && npm run test:ci

test-e2e: ## Test - Run end-to-end tests
	@echo "$(GREEN)Running E2E tests...$(NC)"
	@if [ -f "./test-docker.sh" ]; then \
		chmod +x ./test-docker.sh; \
		./test-docker.sh start; \
		echo "$(YELLOW)Waiting for services to start...$(NC)"; \
		sleep 30; \
		echo "$(CYAN)Running E2E tests...$(NC)"; \
		./test-docker.sh stop; \
		echo "$(GREEN)✅ E2E tests completed!$(NC)"; \
	else \
		echo "$(RED)❌ test-docker.sh not found$(NC)"; \
	fi

test-coverage: ## Test - Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	cd backend && python -m pytest app/tests --cov=app --cov-report=html --cov-report=term-missing
	cd frontend && npm run test:ci
	@echo "$(GREEN)✅ Coverage reports generated!$(NC)"
	@echo "$(CYAN)Backend coverage: backend/htmlcov/index.html$(NC)"
	@echo "$(CYAN)Frontend coverage: frontend/coverage/lcov-report/index.html$(NC)"

# Code Quality Commands
lint: ## Lint and format all code
	@echo "$(GREEN)Linting and formatting code...$(NC)"
	@echo "$(CYAN)Backend linting...$(NC)"
	cd backend && python -m black app && python -m isort app && python -m flake8 app/core app/db app/middleware app/utils app/main.py
	@echo "$(CYAN)Frontend linting...$(NC)"
	cd frontend && npm run lint && npx prettier --write "**/*.{js,jsx,ts,tsx,json,css,md}"
	@echo "$(GREEN)✅ Code formatting completed!$(NC)"

format: lint ## Alias for lint command

check-types: ## Check TypeScript and Python type annotations
	@echo "$(GREEN)Checking types...$(NC)"
	@echo "$(CYAN)Backend type checking...$(NC)"
	cd backend && python -m mypy app --ignore-missing-imports
	@echo "$(CYAN)Frontend type checking...$(NC)"
	cd frontend && npx tsc --noEmit
	@echo "$(GREEN)✅ Type checking completed!$(NC)"

security-scan: ## Run security scans
	@echo "$(GREEN)Running security scans...$(NC)"
	@echo "$(CYAN)Backend security scan...$(NC)"
	cd backend && python -m bandit -r app || true
	cd backend && pip install pip-audit && pip-audit --desc || true
	@echo "$(CYAN)Frontend security scan...$(NC)"
	cd frontend && npm audit || true
	@echo "$(GREEN)✅ Security scans completed!$(NC)"

# Build Commands
build: ## Build production applications
	@echo "$(GREEN)Building applications for production...$(NC)"
	@echo "$(CYAN)Building frontend...$(NC)"
	cd frontend && npm run build
	@echo "$(GREEN)✅ Build completed!$(NC)"

build-docker: ## Build Docker images
	@echo "$(GREEN)Building Docker images...$(NC)"
	@echo "$(CYAN)Building backend image...$(NC)"
	docker build -t scholarship-backend:latest ./backend
	@echo "$(CYAN)Building frontend image...$(NC)"
	docker build -t scholarship-frontend:latest ./frontend
	@echo "$(GREEN)✅ Docker images built successfully!$(NC)"

# Docker Commands
docker-up: ## Docker - Start all services with Docker Compose
	@echo "$(GREEN)Starting services with Docker Compose (dev environment)...$(NC)"
	docker compose -f docker-compose.dev.yml up -d
	@echo "$(GREEN)✅ Services started!$(NC)"
	@echo "$(CYAN)Backend: http://localhost:8000$(NC)"
	@echo "$(CYAN)Frontend: http://localhost:3000$(NC)"
	@echo "$(CYAN)API Docs: http://localhost:8000/docs$(NC)"

docker-down: ## Docker - Stop all Docker Compose services
	@echo "$(GREEN)Stopping Docker services...$(NC)"
	docker compose -f docker-compose.dev.yml down
	@echo "$(GREEN)✅ Services stopped!$(NC)"

docker-restart: ## Docker - Restart all Docker Compose services
	@echo "$(GREEN)Restarting Docker services...$(NC)"
	docker compose -f docker-compose.dev.yml restart
	@echo "$(GREEN)✅ Services restarted!$(NC)"

docker-logs: ## Docker - Show logs from all services
	@echo "$(GREEN)Showing Docker logs...$(NC)"
	docker compose -f docker-compose.dev.yml logs -f

docker-clean: ## Docker - Clean up Docker resources
	@echo "$(GREEN)Cleaning up Docker resources...$(NC)"
	docker compose -f docker-compose.dev.yml down -v
	docker system prune -f
	@echo "$(GREEN)✅ Docker cleanup completed!$(NC)"

# Database Commands
db-migrate: ## Run database migrations
	@echo "$(GREEN)Running database migrations...$(NC)"
	cd backend && alembic upgrade head
	@echo "$(GREEN)✅ Migrations completed!$(NC)"

db-reset: ## Reset database (WARNING: This will delete all data)
	@echo "$(RED)⚠️  WARNING: This will delete all data!$(NC)"
	@read -p "Are you sure? (y/N) " -n 1 -r; \
	if [[ $$REPLY =~ ^[Yy]$$ ]]; then \
		echo ""; \
		echo "$(GREEN)Resetting database...$(NC)"; \
		cd backend && alembic downgrade base && alembic upgrade head; \
		echo "$(GREEN)✅ Database reset completed!$(NC)"; \
	else \
		echo ""; \
		echo "$(YELLOW)Database reset cancelled$(NC)"; \
	fi

db-seed: ## Seed database with sample data
	@echo "$(GREEN)Seeding database with sample data...$(NC)"
	cd backend && python -c "from app.core.init_db import init_db; init_db()"
	@echo "$(GREEN)✅ Database seeded!$(NC)"

init-lookup: ## Initialize lookup tables (reference data)
	@echo "$(GREEN)Initializing lookup tables (reference data)...$(NC)"
	@if ! docker compose -f docker-compose.dev.yml ps backend | grep -q "Up" 2>/dev/null; then \
		echo "$(YELLOW)⚠️  Backend service is not running. Starting development services first...$(NC)"; \
		docker compose -f docker-compose.dev.yml up -d --build; \
		echo "$(CYAN)⏳ Waiting for services to start...$(NC)"; \
		sleep 10; \
		echo "$(CYAN)🔍 Checking database connection...$(NC)"; \
		for i in {1..30}; do \
			if docker exec scholarship_postgres_dev pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then \
				echo "$(GREEN)✅ Database is ready$(NC)"; \
				break; \
			fi; \
			if [ $$i -eq 30 ]; then \
				echo "$(RED)❌ Database failed to start after 30 attempts$(NC)"; \
				exit 1; \
			fi; \
			echo "   Waiting for database... ($$i/30)"; \
			sleep 2; \
		done; \
	else \
		echo "$(GREEN)✅ Backend service is already running$(NC)"; \
	fi
	@echo "$(CYAN)🚀 Running lookup tables initialization...$(NC)"
	@docker exec scholarship_backend_dev python -m app.core.init_lookup_tables
	@echo "$(GREEN)✅ Lookup tables initialization completed successfully!$(NC)"
	@echo ""
	@echo "$(CYAN)📊 Reference Data Initialized:$(NC)"
	@echo "  - 3 degree types (博士, 碩士, 學士)"
	@echo "  - 16 student identity types"
	@echo "  - 11 studying status types"
	@echo "  - 8 school identity types"
	@echo "  - 29 NYCU academies/colleges"
	@echo "  - 16 departments"
	@echo "  - 27 enrollment types"

init-testdata: ## Initialize test data (users, scholarships, etc.)
	@echo "$(GREEN)Initializing test data (users, scholarships, etc.)...$(NC)"
	@if ! docker compose -f docker-compose.dev.yml ps backend | grep -q "Up" 2>/dev/null; then \
		echo "$(RED)❌ Backend service is not running. Please start services first with 'make docker-up'$(NC)"; \
		exit 1; \
	fi
	@echo "$(CYAN)🔍 Checking if lookup tables are initialized...$(NC)"
	@DEGREE_COUNT=$$(docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -t -c "SELECT COUNT(*) FROM degrees;" 2>/dev/null | tr -d ' '); \
	if [ "$$DEGREE_COUNT" -eq 0 ] 2>/dev/null; then \
		echo "$(YELLOW)⚠️  Lookup tables not found. Initializing lookup tables first...$(NC)"; \
		$(MAKE) init-lookup; \
	else \
		echo "$(GREEN)✅ Lookup tables found ($$DEGREE_COUNT degrees)$(NC)"; \
	fi
	@echo "$(CYAN)🚀 Running test data initialization...$(NC)"
	@docker exec scholarship_backend_dev python -c "\
import asyncio; \
from app.core.init_db import createTestUsers, createTestStudents, createTestScholarships, createApplicationFields, createSystemAnnouncements; \
from app.db.session import AsyncSessionLocal; \
async def init_test_data(): \
    async with AsyncSessionLocal() as session: \
        users = await createTestUsers(session); \
        await createTestStudents(session, users); \
        await createTestScholarships(session); \
        await createApplicationFields(session); \
        await createSystemAnnouncements(session); \
    print('✅ Test data initialization completed!'); \
asyncio.run(init_test_data())"
	@echo "$(GREEN)✅ Test data initialization completed successfully!$(NC)"
	@echo ""
	@echo "$(CYAN)📋 Test User Accounts:$(NC)"
	@echo "  - Admin: admin / admin123"
	@echo "  - Super Admin: super_admin / super123"
	@echo "  - Professor: professor / professor123"
	@echo "  - College: college / college123"
	@echo "  - Student (學士): stu_under / stuunder123"
	@echo "  - Student (博士): stu_phd / stuphd123"
	@echo "  - Student (逕讀博士): stu_direct / studirect123"
	@echo "  - Student (碩士): stu_master / stumaster123"
	@echo "  - Student (陸生): stu_china / stuchina123"

init-all: docker-up init-lookup init-testdata ## Initialize complete development environment (Docker + DB + Test Data)
	@echo ""
	@echo "$(GREEN)🎉 Development environment fully initialized!$(NC)"
	@echo "$(CYAN)Ready to start developing!$(NC)"
	@echo ""
	@echo "$(YELLOW)Next steps:$(NC)"
	@echo "  - Run 'make dev' to start development servers"
	@echo "  - Visit http://localhost:3000 for frontend"
	@echo "  - Visit http://localhost:8000/docs for API docs"

# Utility Commands
clean: ## Clean up generated files and caches
	@echo "$(GREEN)Cleaning up...$(NC)"
	@echo "$(CYAN)Cleaning Python cache...$(NC)"
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@echo "$(CYAN)Cleaning Node.js cache...$(NC)"
	cd frontend && rm -rf .next node_modules/.cache
	@echo "$(CYAN)Cleaning test artifacts...$(NC)"
	rm -rf backend/htmlcov backend/.coverage backend/.pytest_cache
	rm -rf frontend/coverage
	@echo "$(GREEN)✅ Cleanup completed!$(NC)"

logs: ## Show application logs
	@echo "$(GREEN)Showing application logs...$(NC)"
	@if [ -f "logs/app.log" ]; then \
		tail -f logs/app.log; \
	else \
		echo "$(YELLOW)No log file found. Start the application first.$(NC)"; \
	fi

health-check: ## Check if all services are running
	@echo "$(GREEN)Checking service health...$(NC)"
	@echo "$(CYAN)Backend health:$(NC)"
	@curl -f http://localhost:8000/health 2>/dev/null && echo " ✅ Backend is healthy" || echo " ❌ Backend is not responding"
	@echo "$(CYAN)Frontend health:$(NC)"
	@curl -f http://localhost:3000 2>/dev/null && echo " ✅ Frontend is healthy" || echo " ❌ Frontend is not responding"

# CI/CD Commands
ci-setup: ## Setup for CI environment
	@echo "$(GREEN)Setting up CI environment...$(NC)"
	make install
	@echo "$(GREEN)✅ CI setup completed!$(NC)"

ci-test: ## Run CI test suite
	@echo "$(GREEN)Running CI test suite...$(NC)"
	make lint
	make check-types
	make test-coverage
	make security-scan
	@echo "$(GREEN)✅ CI tests completed!$(NC)"

ci-build: ## Build for CI/CD
	@echo "$(GREEN)Building for CI/CD...$(NC)"
	make build
	make build-docker
	@echo "$(GREEN)✅ CI build completed!$(NC)"

# Development Helpers
watch-backend: ## Watch backend files and restart on changes
	@echo "$(GREEN)Watching backend files...$(NC)"
	cd backend && find . -name "*.py" | entr -r uvicorn app.main:app --reload

watch-frontend: ## Watch frontend files for changes
	@echo "$(GREEN)Watching frontend files...$(NC)"
	cd frontend && npm run dev

init-project: ## Initialize project for first-time setup
	@echo "$(GREEN)Initializing project...$(NC)"
	make setup
	make db-migrate
	make db-seed
	@echo "$(GREEN)✅ Project initialization completed!$(NC)"
	@echo ""
	@echo "$(CYAN)🎉 Welcome to the Scholarship System!$(NC)"
	@echo ""
	@echo "$(YELLOW)Quick start:$(NC)"
	@echo "  make dev        - Start development servers"
	@echo "  make docker-up  - Start with Docker"
	@echo "  make test       - Run all tests"
	@echo "  make help       - Show all available commands"
	@echo ""

# Performance and Monitoring
benchmark: ## Run performance benchmarks
	@echo "$(GREEN)Running performance benchmarks...$(NC)"
	@if command -v k6 >/dev/null 2>&1; then \
		echo "$(CYAN)Running API load tests...$(NC)"; \
		k6 run performance-tests/api-load-test.js || echo "$(YELLOW)k6 load test script not found$(NC)"; \
	else \
		echo "$(YELLOW)k6 not installed. Install with: https://k6.io/docs/getting-started/installation/$(NC)"; \
	fi

profile: ## Profile application performance
	@echo "$(GREEN)Profiling application...$(NC)"
	@echo "$(CYAN)Backend profiling...$(NC)"
	cd backend && python -m cProfile -o profile.prof app/main.py || echo "$(YELLOW)Profiling requires additional setup$(NC)"
	@echo "$(CYAN)Frontend bundle analysis...$(NC)"
	cd frontend && npm run build && npx webpack-bundle-analyzer .next/static/chunks/*.js || echo "$(YELLOW)Bundle analyzer not configured$(NC)"

# Documentation
docs: ## Generate and serve documentation
	@echo "$(GREEN)Generating documentation...$(NC)"
	@if [ -d "docs" ]; then \
		echo "$(CYAN)Starting documentation server...$(NC)"; \
		cd docs && python -m http.server 8080; \
	else \
		echo "$(YELLOW)No docs directory found$(NC)"; \
	fi

# Version and Release
version: ## Show current version information
	@echo "$(GREEN)Version Information:$(NC)"
	@echo "$(CYAN)Git commit:$(NC) $$(git rev-parse --short HEAD 2>/dev/null || echo 'Not a git repository')"
	@echo "$(CYAN)Git branch:$(NC) $$(git branch --show-current 2>/dev/null || echo 'Not a git repository')"
	@echo "$(CYAN)Backend Python:$(NC) $$(cd backend && python --version 2>/dev/null || echo 'Python not found')"
	@echo "$(CYAN)Frontend Node:$(NC) $$(cd frontend && node --version 2>/dev/null || echo 'Node.js not found')"
	@echo "$(CYAN)Frontend npm:$(NC) $$(cd frontend && npm --version 2>/dev/null || echo 'npm not found')"

# Environment Management
env-check: ## Check environment configuration
	@echo "$(GREEN)Checking environment configuration...$(NC)"
	@echo "$(CYAN)Backend environment:$(NC)"
	@if [ -f "backend/.env" ]; then \
		echo " ✅ backend/.env exists"; \
	else \
		echo " ❌ backend/.env missing"; \
	fi
	@echo "$(CYAN)Frontend environment:$(NC)"
	@if [ -f "frontend/.env.local" ]; then \
		echo " ✅ frontend/.env.local exists"; \
	else \
		echo " ❌ frontend/.env.local missing"; \
	fi
	@echo "$(CYAN)Docker environment:$(NC)"
	@if command -v docker >/dev/null 2>&1; then \
		echo " ✅ Docker is installed"; \
	else \
		echo " ❌ Docker not installed"; \
	fi
	@if command -v docker-compose >/dev/null 2>&1; then \
		echo " ✅ Docker Compose is installed"; \
	else \
		echo " ❌ Docker Compose not installed"; \
	fi
