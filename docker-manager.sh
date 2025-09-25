#!/bin/bash

# Docker Manager Script for Scholarship System
# Unified management for all environments: dev, staging, prod, prod-db

set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

show_usage() {
    echo "Usage: $0 <environment> <command> [options]"
    echo ""
    echo "Environments:"
    echo "  dev      - Development environment (hot reload, no nginx)"
    echo "  staging  - Staging environment (SSL, Portal SSO, full stack)"
    echo "  prod     - Production app server (external DB/MinIO)"
    echo "  prod-db  - Production database server (DB + MinIO only)"
    echo ""
    echo "Commands:"
    echo "  start       - Start services"
    echo "  stop        - Stop services and remove volumes"
    echo "  restart     - Restart services"
    echo "  status      - Show service status"
    echo "  logs        - Show service logs"
    echo "  init-db     - Initialize database (dev/staging only)"
    echo "  backup-db   - Backup database (prod-db only)"
    echo "  setup-ssl   - Setup self-signed SSL certificates (dev only)"
    echo "  health      - Check service health"
    echo ""
    echo "Examples:"
    echo "  $0 dev start              # Start development environment"
    echo "  $0 staging init-db           # Initialize staging database"
    echo "  $0 prod restart           # Restart production services"
    echo "  $0 prod-db backup-db      # Backup production database"
}

get_compose_file() {
    local env=$1
    case $env in
        "dev")
            echo "docker-compose.dev.yml"
            ;;
        "staging")
            echo "docker-compose.staging.yml"
            ;;
        "prod")
            echo "docker-compose.prod.yml"
            ;;
        "prod-db")
            echo "docker-compose.prod-db.yml"
            ;;
        *)
            log_error "Unknown environment: $env"
            exit 1
            ;;
    esac
}

check_env_file() {
    local env=$1
    local env_file=".env.${env}"
    
    if [ ! -f "$env_file" ]; then
        log_warning "Environment file $env_file not found"
        log_info "Creating $env_file from example..."
        
        if [ -f ".env.example.${env}" ]; then
            cp ".env.example.${env}" "$env_file"
            log_warning "Please edit $env_file with your actual configuration values"
        else
            log_error "Example file .env.example.${env} not found"
            return 1
        fi
    fi
}

setup_ssl_certificates() {
    local env=$1

    log_error "SSL certificate setup is no longer needed"
    log_info "For staging: Use real SSL certificates in /etc/nginx/ssl/"
    log_info "For production: Use real SSL certificates from a trusted CA"
    return 1
}

start_services() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    
    log_info "Starting $env environment..."
    
    # Check environment file
    check_env_file $env
    
    # Load environment variables
    if [ -f ".env.${env}" ]; then
        export $(cat ".env.${env}" | grep -v '^#' | xargs)
    fi
    
    # Special handling for different environments
    case $env in
        "prod-db")
            log_info "Creating required directories for production database..."
            sudo mkdir -p /opt/scholarship/postgres/{data,backups}
            sudo mkdir -p /opt/scholarship/minio/{data,config}
            sudo mkdir -p /opt/scholarship/redis/data
            sudo chown -R $(id -u):$(id -g) /opt/scholarship
            ;;
        "prod")
            log_info "Creating required directories for production app..."
            mkdir -p logs/{backend,nginx}
            ;;
    esac
    
    # Start services
    docker compose -f "$compose_file" up -d --build
    
    if [ $? -eq 0 ]; then
        log_success "$env environment started successfully"
        sleep 5
        show_service_info $env
    else
        log_error "Failed to start $env environment"
        exit 1
    fi
}

stop_services() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    
    log_info "Stopping $env environment..."
    docker compose -f "$compose_file" down -v
    
    if [ $? -eq 0 ]; then
        log_success "$env environment stopped successfully"
    else
        log_error "Failed to stop $env environment"
        exit 1
    fi
}

show_status() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    
    log_info "Status for $env environment:"
    docker compose -f "$compose_file" ps
}

show_logs() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    local service=${3:-""}
    
    if [ -n "$service" ]; then
        log_info "Showing logs for $service in $env environment:"
        docker compose -f "$compose_file" logs -f "$service"
    else
        log_info "Showing logs for $env environment:"
        docker compose -f "$compose_file" logs -f
    fi
}

init_database() {
    local env=$1
    
    case $env in
        "dev"|"staging")
            local compose_file=$(get_compose_file $env)
            local container_suffix=""

            if [ "$env" = "staging" ]; then
                container_suffix="_staging"
            elif [ "$env" = "dev" ]; then
                container_suffix="_dev"
            fi
            
            log_info "Initializing database for $env environment..."
            
            # Wait for services to be ready
            log_info "Waiting for services to start..."
            sleep 10
            
            # Check if database is ready
            for i in {1..30}; do
                if docker exec scholarship_postgres${container_suffix} pg_isready -U scholarship_user -d scholarship_db > /dev/null 2>&1; then
                    log_success "Database is ready"
                    break
                fi
                if [ $i -eq 30 ]; then
                    log_error "Database failed to start after 30 attempts"
                    exit 1
                fi
                echo "   Waiting for database... ($i/30)"
                sleep 2
            done
            
            # Run database migrations with Alembic
            log_info "Running database migrations..."
            docker exec scholarship_backend${container_suffix} alembic upgrade head

            if [ $? -eq 0 ]; then
                log_success "Database migrations completed!"
            else
                log_error "Database migrations failed"
                exit 1
            fi

            # Run seed script to populate initial data
            log_info "Seeding database with initial data..."
            docker exec scholarship_backend${container_suffix} python -m app.seed

            if [ $? -eq 0 ]; then
                log_success "Database seeding completed!"
            else
                log_warning "Database seeding completed with some warnings (core data is ready)"
                log_info "Core tables (users, scholarships, lookup data) are successfully initialized"
            fi

            # Verify database setup
            log_info "Verifying database setup..."
            user_count=$(docker exec scholarship_backend${container_suffix} python -c "
import asyncio
from app.db.session import AsyncSessionLocal
from sqlalchemy import func, select
from app.models.user import User

async def count_users():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(User))
        return result.scalar()

print(asyncio.run(count_users()))
" 2>/dev/null)

            if [ "$user_count" -gt 0 ]; then
                log_success "Database verification passed: $user_count users created"
            else
                log_error "Database verification failed: No users found"
                exit 1
            fi
            ;;
        *)
            log_error "Database initialization only available for dev and staging environments"
            exit 1
            ;;
    esac
}

backup_database() {
    local env=$1
    
    case $env in
        "prod-db")
            log_info "Creating database backup..."
            docker exec scholarship_postgres_backup /backup.sh
            if [ $? -eq 0 ]; then
                log_success "Database backup completed"
            else
                log_error "Database backup failed"
                exit 1
            fi
            ;;
        *)
            log_error "Database backup only available for prod-db environment"
            exit 1
            ;;
    esac
}

check_health() {
    local env=$1
    local compose_file=$(get_compose_file $env)
    
    log_info "Checking health for $env environment:"
    
    # Get list of services
    services=$(docker compose -f "$compose_file" ps --services)
    
    for service in $services; do
        container_name=$(docker compose -f "$compose_file" ps -q "$service" 2>/dev/null)
        if [ -n "$container_name" ]; then
            health=$(docker inspect --format='{{.State.Health.Status}}' "$container_name" 2>/dev/null || echo "no healthcheck")
            status=$(docker inspect --format='{{.State.Status}}' "$container_name" 2>/dev/null || echo "unknown")
            
            case $health in
                "healthy")
                    echo -e "  ${service}: ${GREEN}healthy${NC} (${status})"
                    ;;
                "unhealthy")
                    echo -e "  ${service}: ${RED}unhealthy${NC} (${status})"
                    ;;
                "starting")
                    echo -e "  ${service}: ${YELLOW}starting${NC} (${status})"
                    ;;
                "no healthcheck")
                    if [ "$status" = "running" ]; then
                        echo -e "  ${service}: ${BLUE}running${NC} (no healthcheck)"
                    else
                        echo -e "  ${service}: ${RED}${status}${NC}"
                    fi
                    ;;
                *)
                    echo -e "  ${service}: ${YELLOW}unknown${NC} (${status})"
                    ;;
            esac
        else
            echo -e "  ${service}: ${RED}not running${NC}"
        fi
    done
}

show_service_info() {
    local env=$1
    
    echo ""
    log_info "Service Information for $env environment:"
    
    case $env in
        "dev")
            echo "  🚀 Frontend: http://localhost:3000"
            echo "  🔧 Backend API: http://localhost:8000"
            echo "  📚 API Docs: http://localhost:8000/docs"
            echo "  🎭 Mock Student API: http://localhost:8080"
            echo "  🗄️  MinIO Console: http://localhost:9001"
            ;;
        "staging")
            echo "  🚀 Frontend: https://ss.test.nycu.edu.tw/"
            echo "  🔧 Backend API: https://ss.test.nycu.edu.tw/api/"
            echo "  📚 API Docs: https://ss.test.nycu.edu.tw/docs"
            echo "  🎭 Mock Student API: http://localhost:8080"
            echo "  🗄️  PgAdmin: http://localhost:8081"
            echo "  🗂️  MinIO Console: http://localhost:9001"
            ;;
        "prod")
            echo "  🚀 Frontend: https://${DOMAIN:-yourdomain.com}/"
            echo "  🔧 Backend API: https://${DOMAIN:-yourdomain.com}/api/"
            echo "  📚 API Docs: https://${DOMAIN:-yourdomain.com}/docs"
            ;;
        "prod-db")
            echo "  🗄️  PostgreSQL: ${DB_HOST:-localhost}:${DB_PORT:-5432}"
            echo "  🗂️  MinIO API: ${MINIO_HOST:-localhost}:${MINIO_PORT:-9000}"
            echo "  🗂️  MinIO Console: ${MINIO_HOST:-localhost}:${MINIO_CONSOLE_PORT:-9001}"
            echo "  💾 Redis: ${DB_HOST:-localhost}:${REDIS_PORT:-6379}"
            ;;
    esac
}

# Main script logic
if [ $# -lt 2 ]; then
    show_usage
    exit 1
fi

ENVIRONMENT=$1
COMMAND=$2

case $COMMAND in
    "start")
        start_services $ENVIRONMENT
        ;;
    "stop")
        stop_services $ENVIRONMENT
        ;;
    "restart")
        stop_services $ENVIRONMENT
        start_services $ENVIRONMENT
        ;;
    "status")
        show_status $ENVIRONMENT
        ;;
    "logs")
        show_logs $ENVIRONMENT $COMMAND $3
        ;;
    "init-db")
        init_database $ENVIRONMENT
        ;;
    "backup-db")
        backup_database $ENVIRONMENT
        ;;
    "setup-ssl")
        setup_ssl_certificates $ENVIRONMENT
        ;;
    "health")
        check_health $ENVIRONMENT
        ;;
    *)
        log_error "Unknown command: $COMMAND"
        show_usage
        exit 1
        ;;
esac