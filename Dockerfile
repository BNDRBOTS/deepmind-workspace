# ============================================================================
# DeepMind Workspace — Production Docker Image
# Multi-stage build for minimal image size
# ============================================================================

# Stage 1: Builder
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ && \
    rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir --prefix=/install .

# Stage 2: Runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Security: non-root user
RUN groupadd -r deepmind && useradd -r -g deepmind deepmind

COPY --from=builder /install /usr/local
COPY . /app

# Create data directories
RUN mkdir -p /app/data && \
    chown -R deepmind:deepmind /app

USER deepmind

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8080/api/connectors/status')" || exit 1

ENTRYPOINT ["python", "-m", "deepmind.cli"]
