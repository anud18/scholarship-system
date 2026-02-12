#!/bin/bash
# Development environment management script
# Simplifies docker compose commands for development

set -e

COMPOSE_FILE="docker-compose.dev.yml"
PROJECT_NAME="scholarship-system"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

show_help() {
    echo -e "${GREEN}Development Environment Management${NC}"
    echo ""
    echo "Usage: ./dev.sh [command]"
    echo ""
    echo "Commands:"
    echo "  up          - Start all services"
    echo "  down        - Stop all services"
    echo "  restart     - Restart all services"
    echo "  build       - Rebuild all containers"
    echo "  logs        - View logs from all services"
    echo "  logs <svc>  - View logs from specific service"
    echo "  ps          - Show running services"
    echo "  clean       - Stop and remove all containers, networks, and volumes"
    echo "  backend     - Start only backend service"
    echo "  frontend    - Start only frontend service"
    echo "  db          - Start database services only (postgres, redis, minio)"
    echo "  shell-be    - Open shell in backend container"
    echo "  shell-fe    - Open shell in frontend container"
    echo "  help        - Show this help message"
    echo ""
    echo "Examples:"
    echo "  ./dev.sh up            # Start all services in background"
    echo "  ./dev.sh logs backend  # View backend logs"
    echo "  ./dev.sh restart       # Restart all services"
}

case "$1" in
    up)
        echo -e "${GREEN}Starting development environment...${NC}"
        docker compose -f $COMPOSE_FILE up -d
        echo -e "${GREEN}✅ Services started!${NC}"
        echo ""
        echo -e "${YELLOW}Service URLs:${NC}"
        echo "  Frontend:  http://localhost:3000"
        echo "  Backend:   http://localhost:8000"
        echo "  API Docs:  http://localhost:8000/docs"
        echo "  MinIO:     http://localhost:9001"
        echo "  Mock API:  http://localhost:8080"
        echo ""
        echo "Run './dev.sh logs' to view logs"
        ;;
    down)
        echo -e "${YELLOW}Stopping development environment...${NC}"
        docker compose -f $COMPOSE_FILE down
        echo -e "${GREEN}✅ Services stopped${NC}"
        ;;
    restart)
        echo -e "${YELLOW}Restarting development environment...${NC}"
        docker compose -f $COMPOSE_FILE restart
        echo -e "${GREEN}✅ Services restarted${NC}"
        ;;
    build)
        echo -e "${GREEN}Rebuilding containers...${NC}"
        docker compose -f $COMPOSE_FILE build --no-cache
        echo -e "${GREEN}✅ Build complete${NC}"
        ;;
    logs)
        if [ -z "$2" ]; then
            docker compose -f $COMPOSE_FILE logs -f
        else
            docker compose -f $COMPOSE_FILE logs -f "$2"
        fi
        ;;
    ps)
        docker compose -f $COMPOSE_FILE ps
        ;;
    clean)
        echo -e "${RED}⚠️  This will remove all containers, networks, and volumes!${NC}"
        read -p "Are you sure? (y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker compose -f $COMPOSE_FILE down -v
            echo -e "${GREEN}✅ Cleaned up${NC}"
        fi
        ;;
    backend)
        echo -e "${GREEN}Starting backend service...${NC}"
        docker compose -f $COMPOSE_FILE up -d backend
        docker compose -f $COMPOSE_FILE logs -f backend
        ;;
    frontend)
        echo -e "${GREEN}Starting frontend service...${NC}"
        docker compose -f $COMPOSE_FILE up -d frontend
        docker compose -f $COMPOSE_FILE logs -f frontend
        ;;
    db)
        echo -e "${GREEN}Starting database services...${NC}"
        docker compose -f $COMPOSE_FILE up -d postgres redis minio
        docker compose -f $COMPOSE_FILE ps
        ;;
    shell-be)
        docker compose -f $COMPOSE_FILE exec backend /bin/bash
        ;;
    shell-fe)
        docker compose -f $COMPOSE_FILE exec frontend /bin/sh
        ;;
    help|"")
        show_help
        ;;
    *)
        echo -e "${RED}Unknown command: $1${NC}"
        echo ""
        show_help
        exit 1
        ;;
esac
