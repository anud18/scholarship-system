#!/bin/bash

# 在 dev 環境前面加上 production nginx（nginx/nginx.prod.conf，原封不動）
# Put the production nginx in front of the dev stack — see
# docker-compose.dev-nginx.yml for what this does and does not simulate.
#
#   ./scripts/dev-nginx.sh up     # 產生自簽憑證（首次）並啟動 → https://localhost:8443
#   ./scripts/dev-nginx.sh down   # 移除 nginx 容器，backend/frontend 回到一般 dev 設定
#   RELEASE_TAG=v1.2.0 ./scripts/dev-nginx.sh up   # 改跑該 release 的 image（見 docker-compose.dev-release.yml）
#
# DEV_NGINX_HTTPS_PORT overrides the published HTTPS port (default 8443).
# DEV_NGINX_EXTRA_SAN adds cert SANs for access from other hosts, e.g.
#   DEV_NGINX_EXTRA_SAN=IP:203.0.113.10 (delete nginx/ssl/dev to regenerate).

set -euo pipefail

PROJECT_NAME="scholarship-system"
DEV_COMPOSE="docker-compose.dev.yml"
NGINX_COMPOSE="docker-compose.dev-nginx.yml"
RELEASE_COMPOSE="docker-compose.dev-release.yml"
SSL_DIR="nginx/ssl/dev"
CERT_DAYS=825

check_project_root() {
    if [[ ! -f "$DEV_COMPOSE" || ! -f "$NGINX_COMPOSE" ]]; then
        echo "❌ 錯誤: 請在專案根目錄執行此腳本"
        exit 1
    fi
}

# nginx.prod.conf expects fullchain.pem / privkey.pem, plus chain.pem for
# ssl_trusted_certificate. A self-signed cert is its own chain.
generate_cert() {
    if [[ -f "$SSL_DIR/fullchain.pem" && -f "$SSL_DIR/privkey.pem" && -f "$SSL_DIR/chain.pem" ]]; then
        return
    fi
    echo "🔐 產生自簽憑證 → $SSL_DIR"
    mkdir -p "$SSL_DIR"
    # serverAuth EKU + SAN + <=825 days: what Safari/macOS demand before it
    # will accept even an explicitly trusted self-signed cert.
    openssl req -x509 -nodes -newkey rsa:2048 -days "$CERT_DAYS" \
        -keyout "$SSL_DIR/privkey.pem" -out "$SSL_DIR/fullchain.pem" \
        -subj "/CN=localhost" \
        -addext "subjectAltName=DNS:localhost,IP:127.0.0.1${DEV_NGINX_EXTRA_SAN:+,$DEV_NGINX_EXTRA_SAN}" \
        -addext "extendedKeyUsage=serverAuth"
    cp "$SSL_DIR/fullchain.pem" "$SSL_DIR/chain.pem"
    # The nginx master reads the key as root; world-readable is fine for a
    # throwaway localhost cert and avoids host/container uid mismatches.
    chmod 644 "$SSL_DIR"/*.pem
}

compose() {
    docker compose -p "$PROJECT_NAME" "$@"
}

# RELEASE_TAG=v1.2.0 swaps backend/frontend to that release's images.
overlay_files() {
    local files=(-f "$DEV_COMPOSE" -f "$NGINX_COMPOSE")
    if [[ -n "${RELEASE_TAG:-}" ]]; then
        files+=(-f "$RELEASE_COMPOSE")
    fi
    echo "${files[@]}"
}

cmd_up() {
    generate_cert
    # Add-on to an already running dev stack: touch only the app tier and
    # nginx, never postgres/redis/rustfs/mock SIS.
    # shellcheck disable=SC2046  # word-splitting the -f list is intended
    compose $(overlay_files) up -d --no-deps backend frontend nginx
    compose $(overlay_files) exec nginx nginx -t
    echo "✅ https://localhost:${DEV_NGINX_HTTPS_PORT:-8443}（自簽憑證，瀏覽器需手動信任）"
    if [[ -n "${RELEASE_TAG:-}" ]]; then
        echo "   release $RELEASE_TAG — 登入請用 /dev-login"
    fi
}

cmd_down() {
    compose -f "$DEV_COMPOSE" -f "$NGINX_COMPOSE" rm -sf nginx
    # Recreate the app tier without any overlay: FRONTEND_URL back to :3000
    # and, if a release was running, back to hot-reload source mounts.
    compose -f "$DEV_COMPOSE" up -d --no-deps backend frontend
    echo "✅ nginx 已移除，backend/frontend 回到一般 dev 設定"
}

check_project_root
case "${1:-}" in
    up) cmd_up ;;
    down) cmd_down ;;
    *)
        echo "用法: $0 {up|down}"
        exit 1
        ;;
esac
