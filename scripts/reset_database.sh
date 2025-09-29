#!/bin/bash

# 資料庫完整重建腳本 - Database Complete Reset Script
# 這個腳本會完全重建資料庫，包括：
# 1. 停止所有容器
# 2. 移除資料庫 volume
# 3. 重新啟動資料庫
# 4. 執行 Alembic 遷移
# 5. 執行資料種子 (seed)
# 6. 重新建立所有容器

set -e  # Exit on any error

echo "🔄 開始資料庫完整重建流程..."

# Function to check if we're in the project root
check_project_root() {
    if [[ ! -f "docker-compose.dev.yml" ]]; then
        echo "❌ 錯誤: 請在專案根目錄執行此腳本"
        exit 1
    fi
}

# Function to stop and remove containers
cleanup_containers() {
    echo "🛑 停止所有容器..."
    docker compose -f docker-compose.dev.yml down || true

    echo "🗑️  移除 PostgreSQL volume..."
    docker volume rm scholarship-system_postgres_dev_data || true

    echo "✅ 容器清理完成"
}

# Function to start PostgreSQL and wait for it to be ready
start_postgres() {
    echo "🐘 啟動 PostgreSQL..."
    docker compose -f docker-compose.dev.yml up -d postgres

    # Wait for PostgreSQL to be healthy
    echo "⏳ 等待 PostgreSQL 準備就緒..."
    timeout=60
    counter=0

    while ! docker exec scholarship_postgres_dev pg_isready -U scholarship_user -d scholarship_db >/dev/null 2>&1; do
        if [ $counter -ge $timeout ]; then
            echo "❌ PostgreSQL 啟動超時"
            exit 1
        fi
        sleep 2
        counter=$((counter + 2))
        echo "   等待中... (${counter}s)"
    done

    echo "✅ PostgreSQL 已準備就緒"
}

# Function to start backend service for migrations
start_backend() {
    echo "🚀 啟動後端服務..."
    docker compose -f docker-compose.dev.yml up -d backend

    # Wait for backend to be ready
    echo "⏳ 等待後端服務準備就緒..."
    sleep 10

    echo "✅ 後端服務已啟動"
}

# Function to run migrations
run_migrations() {
    echo "📦 執行 Alembic 遷移..."

    # Run migrations with retry logic
    for i in {1..3}; do
        if docker exec scholarship_backend_dev alembic upgrade head; then
            echo "✅ Alembic 遷移成功完成"
            return 0
        else
            echo "⚠️  第 $i 次遷移失敗，重試中..."
            if [ $i -eq 3 ]; then
                echo "❌ Alembic 遷移失敗，手動檢查需要"
                return 1
            fi
            sleep 5
        fi
    done
}

# Function to run database seeding
run_seeding() {
    echo "🌱 執行資料庫種子..."

    if docker exec scholarship_backend_dev python -m app.seed; then
        echo "✅ 資料庫種子執行成功"
    else
        echo "⚠️  資料庫種子執行有問題，但繼續進行..."
        echo "   這可能是由於某些約束問題，但基本資料應該已建立"
    fi
}

# Function to start all services
start_all_services() {
    echo "🏗️  啟動所有服務..."

    # Rebuild backend container to ensure latest dependencies
    echo "🔨 重建後端容器..."
    docker compose -f docker-compose.dev.yml build backend

    # Start all services
    docker compose -f docker-compose.dev.yml up -d

    echo "✅ 所有服務已啟動"
}

# Function to verify the setup
verify_setup() {
    echo "🔍 驗證設置..."

    # Wait for backend to be fully ready
    sleep 15

    # Check database connection
    echo "   檢查資料庫連線..."
    if docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -c "SELECT COUNT(*) FROM alembic_version;" >/dev/null 2>&1; then
        echo "   ✅ 資料庫連線正常"
    else
        echo "   ❌ 資料庫連線失敗"
        return 1
    fi

    # Check tables
    echo "   檢查資料表..."
    table_count=$(docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -t -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public';" | xargs)
    echo "   📊 建立了 $table_count 個資料表"

    # Check basic data
    echo "   檢查基本資料..."
    user_count=$(docker exec scholarship_postgres_dev psql -U scholarship_user -d scholarship_db -t -c "SELECT COUNT(*) FROM users;" | xargs)
    echo "   👥 建立了 $user_count 個使用者"

    # Check current migration
    echo "   檢查遷移狀態..."
    current_migration=$(docker exec scholarship_backend_dev alembic current 2>/dev/null | head -1)
    echo "   📦 目前遷移: $current_migration"

    echo "✅ 設置驗證完成"
}

# Main execution
main() {
    echo "=========================================="
    echo "🎯 資料庫完整重建腳本"
    echo "=========================================="

    check_project_root
    cleanup_containers
    start_postgres
    start_backend

    if run_migrations; then
        run_seeding
        start_all_services
        verify_setup

        echo ""
        echo "=========================================="
        echo "🎉 資料庫重建完成！"
        echo ""
        echo "📊 服務狀態:"
        echo "   - PostgreSQL: http://localhost:5432"
        echo "   - Backend API: http://localhost:8000"
        echo "   - Frontend: http://localhost:3000"
        echo "   - MinIO: http://localhost:9000"
        echo ""
        echo "🔧 有用的指令:"
        echo "   - 檢查日誌: docker compose -f docker-compose.dev.yml logs -f"
        echo "   - 檢查資料庫: docker exec -it scholarship_postgres_dev psql -U scholarship_user -d scholarship_db"
        echo "   - 檢查遷移: docker exec scholarship_backend_dev alembic current"
        echo "=========================================="
    else
        echo ""
        echo "=========================================="
        echo "❌ 資料庫重建失敗"
        echo ""
        echo "🔧 除錯建議:"
        echo "   1. 檢查 Alembic 遷移檔案是否有衝突"
        echo "   2. 檢查 Docker 日誌: docker compose -f docker-compose.dev.yml logs backend"
        echo "   3. 手動執行遷移: docker exec scholarship_backend_dev alembic upgrade head"
        echo "=========================================="
        exit 1
    fi
}

# Parse command line arguments
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        --help|-h)
            echo "資料庫完整重建腳本"
            echo ""
            echo "用法: $0 [選項]"
            echo ""
            echo "選項:"
            echo "  --help, -h    顯示此幫助訊息"
            echo "  --dry-run     預覽將要執行的步驟（不實際執行）"
            echo ""
            echo "此腳本將會："
            echo "  1. 停止所有 Docker 容器"
            echo "  2. 移除 PostgreSQL 資料 volume"
            echo "  3. 重新建立資料庫並執行遷移"
            echo "  4. 執行資料種子"
            echo "  5. 啟動所有服務"
            exit 0
            ;;
        --dry-run)
            echo "🔍 預覽模式 - 以下是將要執行的步驟："
            echo "1. 停止 Docker Compose 服務"
            echo "2. 移除 scholarship-system_postgres_dev_data volume"
            echo "3. 啟動 PostgreSQL 容器"
            echo "4. 啟動後端容器"
            echo "5. 執行 'alembic upgrade head'"
            echo "6. 執行 'python -m app.seed'"
            echo "7. 重建並啟動所有服務"
            echo "8. 驗證設置"
            exit 0
            ;;
        "")
            main
            ;;
        *)
            echo "❌ 未知選項: $1"
            echo "使用 --help 查看可用選項"
            exit 1
            ;;
    esac
fi