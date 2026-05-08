# Grafana → GitHub /dispatches webhook bridge.
# FastAPI + uvicorn, deps installed via uv.
FROM ghcr.io/astral-sh/uv:python3.12-alpine

# Install deps system-wide so we don't have to deal with venv ownership
# when we drop privileges below.
RUN uv pip install --system --no-cache \
    "fastapi>=0.115" \
    "uvicorn>=0.32" \
    "httpx>=0.27"

# Run as non-root.
RUN adduser -D -u 1100 bridge
WORKDIR /app
COPY bridge.py pyproject.toml ./

USER bridge
EXPOSE 8080
ENTRYPOINT ["python", "bridge.py"]
