# ==============================================================================
# Multi-stage Production Dockerfile for Project SentinelForge
# Stage 1: Build React Frontend (Vite)
# Stage 2: Minimal, Hardened Python 3.11 Runtime with Dual Python/Node.js Sandbox
# ==============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-slim AS frontend-builder
WORKDIR /build

COPY src/web/package.json src/web/package-lock.json ./
RUN npm ci

COPY src/web/ ./
RUN npm run build

# --- Stage 2: Runtime Environment ---
FROM python:3.11-slim-bookworm AS runtime

LABEL maintainer="SentinelForge Engineering Team"
LABEL description="Production container for SentinelForge AI Developer Platform"

# System dependencies:
# - curl: Required for container health checks
# - git: Required for sandboxed version-control operations
# - nodejs & npm: Required for dual runtime sandbox execution (JS/TS support)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

# Hardened environment configurations
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    SENTENCE_TRANSFORMERS_HOME=/app/models \
    HF_HOME=/app/models \
    PORT=8000 \
    HOST=0.0.0.0

WORKDIR /app

# Install Python production and sandbox execution dependencies
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt pytest

# Pre-download local embedding weights into /app/models
# Guarantees instantaneous, zero-network container boot and full OFFLINE_MODE compatibility
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2', cache_folder='/app/models')"

# Create restricted non-root user `sentinel` (UID 1000)
RUN groupadd -g 1000 sentinel && \
    useradd -u 1000 -g sentinel -m -s /bin/bash sentinel && \
    mkdir -p /app/data/workspace /app/data/chroma /app/data/scratch /app/models && \
    chown -R sentinel:sentinel /app

# Copy application sources and artifacts
COPY --chown=sentinel:sentinel src/ /app/src/
COPY --chown=sentinel:sentinel data/ /app/data/
COPY --chown=sentinel:sentinel scripts/ /app/scripts/
COPY --chown=sentinel:sentinel pyproject.toml README.md /app/

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder --chown=sentinel:sentinel /build/dist /app/src/web/dist

# Ensure permissions are strictly preserved for sentinel user
RUN chown -R sentinel:sentinel /app/data

# Non-root execution policy
USER sentinel

EXPOSE 8000

# Container liveness & readiness healthcheck
HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/api/v1/health || exit 1

# Production server entrypoint
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
