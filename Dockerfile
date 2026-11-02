# Production Dockerfile for Nexus AI Voice Assistant
# Multi-platform support (Linux amd64, arm64)

FROM python:3.11-slim

# Prevent Python from writing .pyc files & buffer stdout/stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    DB_PATH=/app/data/voice_assistant.db

WORKDIR /app

# Install system dependencies including curl for container health checks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first for optimal Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create non-root application user and data directory
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# Copy application source code
COPY --chown=appuser:appuser agent/ ./agent/
COPY --chown=appuser:appuser db/ ./db/
COPY --chown=appuser:appuser web/ ./web/
COPY --chown=appuser:appuser rag/ ./rag/
COPY --chown=appuser:appuser tests/ ./tests/
COPY --chown=appuser:appuser run_server.py ./
COPY --chown=appuser:appuser pytest.ini ./
COPY --chown=appuser:appuser .env.example ./

# Switch to non-root security user
USER appuser

EXPOSE 8000

# Health check verifies both HTTP server and SQLite database connection
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Production server start with dynamic port support
CMD ["sh", "-c", "python run_server.py"]
