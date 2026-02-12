#!/bin/bash
# Verify refactoring to Bun and uv

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}🔍 驗證 Bun & uv 重構...${NC}"
echo ""

# Check if required files exist
echo -e "${YELLOW}檢查必要檔案...${NC}"

files=(
    "backend/pyproject.toml"
    "backend/Dockerfile"
    "backend/.dockerignore"
    "frontend/Dockerfile"
    "frontend/.dockerignore"
    "mock-student-api/pyproject.toml"
    "mock-student-api/Dockerfile"
    "docker-compose.dev.yml"
    "DEV_SETUP.md"
    "REFACTOR_SUMMARY.md"
    "QUICKSTART.md"
    "dev.sh"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "${GREEN}✓${NC} $file"
    else
        echo -e "${RED}✗${NC} $file (缺少)"
        exit 1
    fi
done

echo ""
echo -e "${YELLOW}檢查 Docker Compose 配置...${NC}"

# Check docker-compose.dev.yml
if docker compose -f docker-compose.dev.yml config > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} docker-compose.dev.yml 配置有效"
else
    echo -e "${RED}✗${NC} docker-compose.dev.yml 配置無效"
    exit 1
fi

echo ""
echo -e "${YELLOW}檢查關鍵內容...${NC}"

# Check if frontend Dockerfile uses Bun
if grep -q "oven/bun" frontend/Dockerfile; then
    echo -e "${GREEN}✓${NC} Frontend Dockerfile 使用 Bun"
else
    echo -e "${RED}✗${NC} Frontend Dockerfile 未使用 Bun"
    exit 1
fi

# Check if backend Dockerfile uses uv
if grep -q "astral-sh/uv" backend/Dockerfile; then
    echo -e "${GREEN}✓${NC} Backend Dockerfile 使用 uv"
else
    echo -e "${RED}✗${NC} Backend Dockerfile 未使用 uv"
    exit 1
fi

# Check if mock-student-api Dockerfile uses uv
if grep -q "astral-sh/uv" mock-student-api/Dockerfile; then
    echo -e "${GREEN}✓${NC} Mock Student API Dockerfile 使用 uv"
else
    echo -e "${RED}✗${NC} Mock Student API Dockerfile 未使用 uv"
    exit 1
fi

# Check if docker-compose uses bun for frontend
if grep -q "bun run dev" docker-compose.dev.yml; then
    echo -e "${GREEN}✓${NC} docker-compose.dev.yml 使用 Bun 啟動前端"
else
    echo -e "${RED}✗${NC} docker-compose.dev.yml 未使用 Bun 啟動前端"
    exit 1
fi

# Check if Makefile uses bun
if grep -q "bun install" Makefile; then
    echo -e "${GREEN}✓${NC} Makefile 使用 Bun"
else
    echo -e "${RED}✗${NC} Makefile 未使用 Bun"
    exit 1
fi

# Check if Makefile uses uv
if grep -q "uv pip install" Makefile; then
    echo -e "${GREEN}✓${NC} Makefile 使用 uv"
else
    echo -e "${RED}✗${NC} Makefile 未使用 uv"
    exit 1
fi

# Check if backend/pyproject.toml has dependencies
if grep -q '\[project.dependencies\]' backend/pyproject.toml || grep -q 'dependencies = \[' backend/pyproject.toml; then
    echo -e "${GREEN}✓${NC} backend/pyproject.toml 包含依賴定義"
else
    echo -e "${RED}✗${NC} backend/pyproject.toml 缺少依賴定義"
    exit 1
fi

echo ""
echo -e "${GREEN}✅ 所有驗證通過！${NC}"
echo ""
echo -e "${YELLOW}下一步：${NC}"
echo "  1. 執行 './dev.sh up' 啟動開發環境"
echo "  2. 或參考 QUICKSTART.md 了解更多選項"
echo ""
