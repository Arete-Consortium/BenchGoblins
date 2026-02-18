FROM python:3.12-slim

# API runs from /app/api; core module at /app/core (sibling).
# main.py's sys.path.insert adds /app so "from core.scoring import ..."
# resolves to /app/core/scoring.py.

WORKDIR /app/api

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy core module (sibling — found via sys.path parent hack in main.py)
COPY core/ /app/core/

# Copy API application code
COPY api/ /app/api/

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
