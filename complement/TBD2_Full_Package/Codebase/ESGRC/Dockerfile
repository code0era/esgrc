FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# The API mounts the pipeline + copilot routers (see main.py), so this image needs
# BOTH dependency sets. Built from the repo-root context (see docker-compose.yml).
COPY ESGRC/requirements.txt /app/esgrc-requirements.txt
COPY pipeline/requirements.txt /app/pipeline-requirements.txt
RUN pip install --no-cache-dir -r /app/esgrc-requirements.txt -r /app/pipeline-requirements.txt

# ESGRC app (main.py, app/, alembic/) at /app; pipeline package at /app/pipeline
COPY ESGRC/ /app/
COPY pipeline/ /app/pipeline/

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
