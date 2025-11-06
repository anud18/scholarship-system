FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set work directory
WORKDIR /app

# Install system dependencies
# Security: Pin exact package versions to prevent dependency confusion attacks
# Configure trusted Debian repositories explicitly
RUN echo "deb http://deb.debian.org/debian trixie main" > /etc/apt/sources.list && \
    echo "deb http://deb.debian.org/debian-security trixie-security main" >> /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends --allow-unauthenticated=false \
    curl=8.14.1-2 \
    gcc=4:14.2.0-1 \
    postgresql-client=17+278 \
    tesseract-ocr=5.5.0-1+b1 \
    tesseract-ocr-eng=1:4.1.0-2 \
    libpq-dev=17.6-0+deb13u1 \
    libmagic-dev=1:5.46-5 \
    && rm -rf /var/lib/apt/lists/* \
    && dpkg --get-selections > /installed-packages.list

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Copy frontend email templates
COPY emails /frontend/emails

# Create uploads directory
RUN mkdir -p uploads

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
