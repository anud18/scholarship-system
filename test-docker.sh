#!/bin/bash

# Development Docker script for hot reload development
set -e

case "$1" in
    "start")
        echo "Starting development services..."
        if [ -f "docker-compose.dev.yml" ]; then
            docker compose -f docker-compose.dev.yml up -d --build
        elif [ -f "docker-compose.yml" ]; then
            docker compose up -d --build
        else
            echo "No docker-compose file found, skipping Docker start"
        fi
        echo "Development services started successfully with hot reload"
        ;;
    "stop")
        echo "Stopping development services..."
        if [ -f "docker-compose.dev.yml" ]; then
            docker compose -f docker-compose.dev.yml down -v
        elif [ -f "docker-compose.yml" ]; then
            docker compose down -v
        else
            echo "No docker-compose file found, skipping Docker stop"
        fi
        echo "Development services stopped successfully"
        ;;
    "status")
        echo "Checking development service status..."
        if [ -f "docker-compose.dev.yml" ]; then
            docker compose -f docker-compose.dev.yml ps
        else
            docker compose ps || true
        fi
        echo ""
        echo "🚀 Development Service URLs:"
        echo "- Frontend (Hot Reload): http://localhost:3000"
        echo "- Backend API (Hot Reload): http://localhost:8000"
        echo "- API Docs: http://localhost:8000/docs"
        echo "- Mock Student API: http://localhost:8080"
        echo "- MinIO Console: http://localhost:9001"
        echo "- PostgreSQL: localhost:5432"
        echo "- Redis: localhost:6379"
        echo ""
        echo "🔧 Development Features:"
        echo "- Hot reload enabled for both frontend and backend"
        echo "- Mock SSO enabled (no real Portal login required)"
        echo "- All services accessible directly (no nginx)"
        echo "- Source code mounted for live editing"
        echo ""
        echo "📊 Service Health Check:"
        curl -s http://localhost:8000/health | jq . || echo "Backend not responding"
        echo ""
        curl -s http://localhost:8080/health | jq . || echo "Mock Student API not responding"
        ;;
    "init-lookup")
        echo "Initializing lookup tables (reference data)..."

        # Check if backend service is running
        if ! docker compose -f docker-compose.dev.yml ps backend | grep -q "Up" 2>/dev/null; then
            echo "⚠️  Backend service is not running. Starting development services first..."
            echo "Starting development services..."
            if [ -f "docker-compose.dev.yml" ]; then
                docker compose -f docker-compose.dev.yml up -d --build
            elif [ -f "docker-compose.yml" ]; then
                docker compose up -d --build
            else
                echo "❌ No docker-compose file found"
                exit 1
            fi

            # Wait for services to be ready
            echo "⏳ Waiting for services to start..."
            sleep 10

            # Check if database is ready
            echo "🔍 Checking database connection..."
            for i in {1..30}; do
                if docker exec scholarship_postgres_dev pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then
                    echo "✅ Database is ready"
                    break
                fi
                if [ $i -eq 30 ]; then
                    echo "❌ Database failed to start after 30 attempts"
                    exit 1
                fi
                echo "   Waiting for database... ($i/30)"
                sleep 2
            done
        else
            echo "✅ Backend service is already running"
        fi

        # Run lookup tables initialization
        echo "🚀 Running lookup tables initialization..."
        docker exec scholarship_backend_dev python -m app.core.init_lookup_tables

        if [ $? -eq 0 ]; then
            echo "✅ Lookup tables initialization completed successfully!"
            echo ""
            echo "📊 Reference Data Initialized:"
            echo "- 3 degree types (博士, 碩士, 學士)"
            echo "- 16 student identity types"
            echo "- 11 studying status types"
            echo "- 8 school identity types"
            echo "- 29 NYCU academies/colleges"
            echo "- 16 departments"
            echo "- 27 enrollment types"
        else
            echo "❌ Lookup tables initialization failed"
            exit 1
        fi
        ;;
    "init-testdata")
        echo "Initializing test data (users, scholarships, etc.)..."

        # Check if backend service is running
        if ! docker compose -f docker-compose.dev.yml ps backend | grep -q "Up" 2>/dev/null; then
            echo "❌ Backend service is not running. Please start services first with 'start' command"
            exit 1
        fi

        # Check if lookup tables exist
        echo "🔍 Checking if lookup tables are initialized..."
        DEGREE_COUNT=$(docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -t -c "SELECT COUNT(*) FROM degrees;" 2>/dev/null | tr -d ' ')

        if [ "$DEGREE_COUNT" -eq 0 ] 2>/dev/null; then
            echo "⚠️  Lookup tables not found. Initializing lookup tables first..."
            $0 init-lookup
        else
            echo "✅ Lookup tables found ($DEGREE_COUNT degrees)"
        fi

        # Run test data initialization (without lookup tables)
        echo "🚀 Running test data initialization..."
        docker exec scholarship_backend_dev python -c "
import asyncio
from app.core.init_db import createTestUsers, createTestStudents, createTestScholarships, createApplicationFields, createSystemAnnouncements
from app.db.session import AsyncSessionLocal

async def init_test_data():
    async with AsyncSessionLocal() as session:
        users = await createTestUsers(session)
        await createTestStudents(session, users)
        await createTestScholarships(session)
        await createApplicationFields(session)
        await createSystemAnnouncements(session)
    print('✅ Test data initialization completed!')

asyncio.run(init_test_data())
"

        if [ $? -eq 0 ]; then
            echo "✅ Test data initialization completed successfully!"
            echo ""
            echo "📋 Test User Accounts:"
            echo "- Admin: admin / admin123"
            echo "- Super Admin: super_admin / super123"
            echo "- Professor: professor / professor123"
            echo "- College: college / college123"
            echo "- Student (學士): stu_under / stuunder123"
            echo "- Student (博士): stu_phd / stuphd123"
            echo "- Student (逕讀博士): stu_direct / studirect123"
            echo "- Student (碩士): stu_master / stumaster123"
            echo "- Student (陸生): stu_china / stuchina123"
        else
            echo "❌ Test data initialization failed"
            exit 1
        fi
        ;;
    "init-db")
        echo "Initializing complete database (lookup tables + test data)..."

        # Check if backend service is running
        if ! docker compose -f docker-compose.dev.yml ps backend | grep -q "Up" 2>/dev/null; then
            echo "⚠️  Backend service is not running. Starting development services first..."
            echo "Starting development services..."
            if [ -f "docker-compose.dev.yml" ]; then
                docker compose -f docker-compose.dev.yml up -d --build
            elif [ -f "docker-compose.yml" ]; then
                docker compose up -d --build
            else
                echo "❌ No docker-compose file found"
                exit 1
            fi

            # Wait for services to be ready
            echo "⏳ Waiting for services to start..."
            sleep 10

            # Check if database is ready
            echo "🔍 Checking database connection..."
            for i in {1..30}; do
                if docker exec scholarship_postgres_dev pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then
                    echo "✅ Database is ready"
                    break
                fi
                if [ $i -eq 30 ]; then
                    echo "❌ Database failed to start after 30 attempts"
                    exit 1
                fi
                echo "   Waiting for database... ($i/30)"
                sleep 2
            done
        else
            echo "✅ Backend service is already running"
        fi

        # Run complete database initialization
        echo "🚀 Running complete database initialization..."
        docker exec scholarship_backend_dev python -m app.core.init_db

        if [ $? -eq 0 ]; then
            echo "✅ Database initialization completed successfully!"
            echo ""
            echo "📋 Test User Accounts:"
            echo "- Admin: admin / admin123"
            echo "- Super Admin: super_admin / super123"
            echo "- Professor: professor / professor123"
            echo "- College: college / college123"
            echo "- Student (學士): stu_under / stuunder123"
            echo "- Student (博士): stu_phd / stuphd123"
            echo "- Student (逕讀博士): stu_direct / studirect123"
            echo "- Student (碩士): stu_master / stumaster123"
            echo "- Student (陸生): stu_china / stuchina123"
            echo ""
            echo "🌐 Access the development application:"
            echo "- Frontend: http://localhost:3000"
            echo "- Backend API: http://localhost:8000"
            echo "- API Docs: http://localhost:8000/docs"
        else
            echo "❌ Database initialization failed"
            exit 1
        fi
        ;;
    "restart")
        echo "Restarting development services..."
        $0 stop
        $0 start
        ;;
    "logs")
        echo "Showing development service logs..."
        if [ -n "$2" ]; then
            echo "Logs for service: $2"
            docker compose -f docker-compose.dev.yml logs -f "$2"
        else
            echo "Logs for all services:"
            docker compose -f docker-compose.dev.yml logs -f
        fi
        ;;
    "dev")
        echo "🚀 Development Environment Information"
        echo ""
        echo "📁 File Structure:"
        echo "- Backend code: ./backend/ (auto-reload enabled)"
        echo "- Frontend code: ./frontend/ (auto-reload enabled)"
        echo "- Mock API: ./mock-student-api/ (auto-reload enabled)"
        echo ""
        echo "🔧 Development Tips:"
        echo "- Edit backend files in ./backend/ - changes reload automatically"
        echo "- Edit frontend files in ./frontend/ - Next.js hot reload active"
        echo "- Mock SSO is enabled - no real Portal login needed"
        echo "- Use mock student data for testing"
        echo "- Database persists between restarts (use 'stop' to reset)"
        echo ""
        echo "🐛 Debugging:"
        echo "- Backend logs: ./test-docker.sh logs backend"
        echo "- Frontend logs: ./test-docker.sh logs frontend"
        echo "- Database logs: ./test-docker.sh logs postgres"
        echo "- All logs: ./test-docker.sh logs"
        echo ""
        echo "📚 Useful Commands:"
        echo "- ./test-docker.sh status    # Check all services"
        echo "- ./test-docker.sh init-db   # Reset & initialize database"
        echo "- ./test-docker.sh restart   # Restart all services"
        ;;
    *)
        echo "🚀 Development Docker Script - Hot Reload Environment"
        echo "Usage: $0 {start|stop|status|init-lookup|init-testdata|init-db|restart|logs|dev}"
        echo ""
        echo "Commands:"
        echo "  start        - Start development services with hot reload"
        echo "  stop         - Stop development services and remove volumes"
        echo "  status       - Check service status and show URLs"
        echo "  restart      - Restart all development services"
        echo "  logs [service] - Show logs (optional: specify service name)"
        echo "  dev          - Show development info and tips"
        echo ""
        echo "Database Commands:"
        echo "  init-lookup  - Initialize lookup tables (reference data only)"
        echo "  init-testdata- Initialize test data (users, scholarships, etc.)"
        echo "  init-db      - Initialize complete database (recommended for fresh setup)"
        echo ""
        echo "Data Initialization Options:"
        echo "  init-lookup   : Only reference data (degrees, academies, etc.)"
        echo "  init-testdata : Only test users and scholarships (requires lookup data)"
        echo "  init-db       : Complete initialization (recommended for fresh setup)"
        echo ""
        echo "🔧 Development Features:"
        echo "  - Hot reload for backend and frontend"
        echo "  - Mock SSO enabled (no Portal login required)"
        echo "  - All services accessible directly"
        echo "  - Source code mounted for live editing"
        echo "  - PostgreSQL, Redis, MinIO included locally"
        echo ""
        echo "For production/staging environments, use: ./docker-manager.sh"
        exit 1
        ;;
esac
