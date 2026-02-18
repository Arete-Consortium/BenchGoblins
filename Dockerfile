# Stage 1: Builder — install pip deps with build tools available
FROM python:3.12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY src/api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime — slim image with no build tools
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy all source code
COPY src/ ./src/

# Set Python path so imports work (core module is in /app/src)
ENV PYTHONPATH="/app/src:/app/src/api"

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application from the api directory
WORKDIR /app/src/api

# Use PORT env variable (Fly.io sets this), default to 8000
ENV PORT=8000
CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port $PORT"]
