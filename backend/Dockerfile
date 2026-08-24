# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Builder: resolves and installs Python dependencies into a self-contained
# virtualenv at /opt/venv. Everything that is only needed to *build* wheels
# (uv itself, gcc, libpq-dev, the apt lists) stays in this stage and never
# reaches the runtime image.
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Build-only toolchain. Almost every dependency ships a manylinux wheel, but
# gcc/libpq-dev are kept here as a safety net for any sdist fallback — they
# cost nothing in the final image because this stage is discarded.
RUN echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends --allow-unauthenticated=false \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /tmp/pyproject.toml

# The venv is placed outside /app so the app bind-mount used by
# docker-compose.dev.yml cannot shadow the installed packages.
RUN uv venv --seed /opt/venv && \
    VIRTUAL_ENV=/opt/venv uv pip install -r /tmp/pyproject.toml

# ---------------------------------------------------------------------------
# Runtime: plain python-slim plus the shared libraries the app actually dlopen's
# at runtime (libmagic for python-magic, CJK fonts for reportlab, curl for the
# healthcheck). No compiler, no uv, no -dev packages.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    VIRTUAL_ENV=/opt/venv

WORKDIR /app

# Security: use trusted Debian repositories with package authentication.
RUN echo "deb http://deb.debian.org/debian bookworm main" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security bookworm-security main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends --allow-unauthenticated=false \
    curl \
    libmagic1 \
    # CJK fonts for Chinese PDF generation (reportlab)
    fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/* \
    && dpkg --get-selections > /installed-packages.list

COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Copy frontend email templates from the repo's frontend/emails dir.
# The build context is ./backend (see docker-compose.*.yml), which does
# not contain an emails/ subdir, so we depend on the named build context
# `frontend_emails` provided by compose (additional_contexts:) or by
# `docker buildx build --build-context frontend_emails=./frontend/emails ...`
# in CI. The image bakes templates at /frontend/emails so prod (which has
# no bind mount) finds them; dev compose still bind-mounts ./frontend/emails
# at /react-email-templates and points REACT_EMAIL_TEMPLATES_DIR there.
COPY --from=frontend_emails . /frontend/emails

# Create non-root user for security
RUN groupadd -r appuser -g 1000 && \
    useradd -r -u 1000 -g appuser -d /app -s /sbin/nologin appuser

# Create required directories with proper ownership
RUN mkdir -p uploads exports logs && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
