# ============================================================================
# DeepMind Workspace — Render-Optimized Production Dockerfile
# ============================================================================

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_DEFAULT_TIMEOUT=300

WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        git \
        curl && \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and source
COPY pyproject.toml ./
COPY src/ src/
COPY config/ config/
COPY scripts/ scripts/

# Install Python dependencies with extended timeout
RUN pip install --timeout=300 -e .

# Pre-download embedding model during build (not runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')" && \
    rm -rf /root/.cache

# Copy remaining application files
COPY . .

# Make scripts executable
RUN chmod +x scripts/*.sh || true

# Create data directory (will be mounted by Render Disk)
RUN mkdir -p /data && chmod 777 /data

EXPOSE 8080

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8080}/api/health || exit 1

# For Render: use uvicorn with proper port binding
# For local: python -m deepmind.cli still works
CMD uvicorn deepmind.app:app --host 0.0.0.0 --port ${PORT:-8080} --workers 1 --log-level info
