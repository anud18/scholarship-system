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
    *)
        echo "Usage: $0 {start|stop|status}"
        exit 1
        ;;
esac