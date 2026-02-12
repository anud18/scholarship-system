# 🚀 Quick Start - Bun & uv 開發環境

本專案已遷移至現代化的快速工具鏈：
- **前端**: Bun (取代 npm)
- **後端**: uv (取代 pip)

## 最快速開始 (使用 Docker)

```bash
# 啟動所有服務
./dev.sh up

# 查看日誌
./dev.sh logs

# 停止服務
./dev.sh down
```

服務網址：
- 前端: http://localhost:3000
- 後端 API: http://localhost:8000/docs
- MinIO: http://localhost:9001

## 本地開發設置

### 1. 安裝工具

```bash
# 安裝 uv (Backend)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 安裝 Bun (Frontend)  
curl -fsSL https://bun.sh/install | bash
```

### 2. 安裝依賴

```bash
# Backend
cd backend
uv pip install -r pyproject.toml --extra dev

# Frontend
cd frontend
bun install
```

### 3. 啟動開發

```bash
# 方式 1: 使用 Makefile
make dev

# 方式 2: 分別啟動
# Terminal 1 - Backend
cd backend && uvicorn app.main:app --reload

# Terminal 2 - Frontend  
cd frontend && bun run dev
```

## 常用命令

### Docker 開發

```bash
./dev.sh up          # 啟動所有服務
./dev.sh down        # 停止所有服務
./dev.sh build       # 重建容器
./dev.sh logs        # 查看所有日誌
./dev.sh logs backend # 查看後端日誌
./dev.sh ps          # 顯示運行狀態
./dev.sh clean       # 清理所有容器和資料卷
```

### 本地開發

```bash
# Backend
cd backend
uv pip install <package>              # 安裝套件
python -m pytest                      # 運行測試
alembic upgrade head                  # 資料庫遷移

# Frontend
cd frontend
bun add <package>                     # 安裝套件
bun add -d <package>                  # 安裝開發依賴
bun run dev                          # 開發伺服器
bun test                             # 運行測試
bun run build                        # 生產構建
```

## 添加新依賴

### Backend (Python)

編輯 `backend/pyproject.toml`:

```toml
[project]
dependencies = [
    "fastapi==0.129.0",
    "your-new-package==1.0.0",  # 添加在這裡
]
```

然後安裝:
```bash
cd backend
uv pip install -r pyproject.toml
```

### Frontend (JavaScript)

```bash
cd frontend
bun add <package>        # 生產依賴
bun add -d <package>     # 開發依賴
```

## 疑難排解

### 前端問題

```bash
# 重新安裝依賴
cd frontend
rm -rf node_modules bun.lockb
bun install

# 清除 Next.js 快取
rm -rf .next
bun run dev
```

### 後端問題

```bash
# 重新建立虛擬環境
cd backend
rm -rf .venv
uv venv
uv pip install -r pyproject.toml --extra dev
```

### Docker 問題

```bash
# 完全重建
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml build --no-cache
docker compose -f docker-compose.dev.yml up
```

## 效能提升

- **Backend 依賴安裝**: pip (~45s) → uv (~4s) = **11倍速** ⚡
- **Frontend 依賴安裝**: npm (~30s) → bun (~3s) = **10倍速** ⚡

## 更多資訊

- 詳細設置: [DEV_SETUP.md](DEV_SETUP.md)
- 重構摘要: [REFACTOR_SUMMARY.md](REFACTOR_SUMMARY.md)
- 專案文檔: [README.md](README.md)
