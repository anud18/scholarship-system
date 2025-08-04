#!/bin/bash

# Simple test Docker script for CI/CD
set -e

case "$1" in
    "start")
        echo "Starting test services..."
        if [ -f "docker-compose.test.yml" ]; then
            docker compose -f docker-compose.test.yml up -d --build
        elif [ -f "docker-compose.yml" ]; then
            docker compose up -d --build
        else
            echo "No docker-compose file found, skipping Docker start"
        fi
        echo "Services started successfully"
        ;;
    "stop")
        echo "Stopping test services..."
        if [ -f "docker-compose.test.yml" ]; then
            docker compose -f docker-compose.test.yml down -v
        elif [ -f "docker-compose.yml" ]; then
            docker compose down -v
        else
            echo "No docker-compose file found, skipping Docker stop"
        fi
        echo "Services stopped successfully"
        ;;
    "status")
        echo "Checking service status..."
        docker compose ps || true
        ;;
    "init-lookup")
        echo "Initializing lookup tables (reference data)..."
        
        # Check if backend service is running
        if ! docker compose ps backend | grep -q "Up"; then
            echo "⚠️  Backend service is not running. Starting services first..."
            echo "Starting test services..."
            if [ -f "docker-compose.test.yml" ]; then
                docker compose -f docker-compose.test.yml up -d --build
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
                if docker exec scholarship_postgres_test pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then
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
        docker exec scholarship_backend_test python -m app.core.init_lookup_tables
        
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
        if ! docker compose ps backend | grep -q "Up"; then
            echo "❌ Backend service is not running. Please start services first with 'start' command"
            exit 1
        fi
        
        # Check if lookup tables exist
        echo "🔍 Checking if lookup tables are initialized..."
        DEGREE_COUNT=$(docker exec scholarship_postgres_test psql -U scholarship_user -d scholarship_db -t -c "SELECT COUNT(*) FROM degrees;" 2>/dev/null | tr -d ' ')
        
        if [ "$DEGREE_COUNT" -eq 0 ] 2>/dev/null; then
            echo "⚠️  Lookup tables not found. Initializing lookup tables first..."
            $0 init-lookup
        else
            echo "✅ Lookup tables found ($DEGREE_COUNT degrees)"
        fi
        
        # Run test data initialization (without lookup tables)
        echo "🚀 Running test data initialization..."
        docker exec scholarship_backend_test python -c "
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
        if ! docker compose ps backend | grep -q "Up"; then
            echo "⚠️  Backend service is not running. Starting services first..."
            echo "Starting test services..."
            if [ -f "docker-compose.test.yml" ]; then
                docker compose -f docker-compose.test.yml up -d --build
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
                if docker exec scholarship_postgres_test pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then
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
        docker exec scholarship_backend_test python -m app.core.init_db
        
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
            echo "🌐 Access the application:"
            echo "- Frontend: http://localhost:3000"
            echo "- Backend API: http://localhost:8000"
            echo "- API Docs: http://localhost:8000/docs"
        else
            echo "❌ Database initialization failed"
            exit 1
        fi
        ;;
    "restart")
        echo "Restarting services..."
        $0 stop
        $0 start
        ;;
    *)
        echo "Usage: $0 {start|stop|status|init-lookup|init-testdata|init-db|restart}"
        echo ""
        echo "Commands:"
        echo "  start        - Start Docker services"
        echo "  stop         - Stop Docker services and remove volumes"
        echo "  status       - Check service status"
        echo "  init-lookup  - Initialize lookup tables (reference data only)"
        echo "  init-testdata- Initialize test data (users, scholarships, etc.)"
        echo "  init-db      - Initialize complete database (lookup + test data)"
        echo "  restart      - Restart all services"
        echo ""
        echo "Data Initialization Options:"
        echo "  init-lookup   : Only reference data (degrees, academies, etc.)"
        echo "  init-testdata : Only test users and scholarships (requires lookup data)"
        echo "  init-db       : Complete initialization (recommended for fresh setup)"
        exit 1
        ;;
esac