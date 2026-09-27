FROM python:3.12-slim

WORKDIR /app

# System dependencies for analytics scripts (numpy, scipy, matplotlib)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Install pipeline dependencies
COPY pipeline/requirements.txt /app/pipeline/requirements.txt
RUN pip install --no-cache-dir -r /app/pipeline/requirements.txt

# torch (CPU-only) — the analytics scripts import it.
#  • x86_64: pull the ~200 MB CPU wheel from the pytorch CPU index (avoids the
#    ~2 GB CUDA build).
#  • aarch64 (e.g. Oracle Cloud Always-Free ARM): that index has no arm64 wheel,
#    so install from regular PyPI, which serves the aarch64 CPU build directly.
RUN if [ "$(uname -m)" = "aarch64" ] || [ "$(uname -m)" = "arm64" ]; then \
        pip install --no-cache-dir torch ; \
    else \
        pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu ; \
    fi

# Copy pipeline package
COPY pipeline/ /app/pipeline/

# Copy ESGRC's app/ package so it resolves as a top-level "app" import (matches
# WORKDIR /app + PYTHONPATH=/app below). Needed because pipeline.celery_app's
# imports list registers pipeline.routers.copilot_router, which imports
# app.dependencies.auth - so the worker crashes on boot (ModuleNotFoundError:
# No module named 'app') without this. Only app/ is copied, not all of ESGRC/
# (no main.py, alembic/, tests) - the worker never runs ESGRC's own API or
# migrations. Mirrors ESGRC/Dockerfile's `COPY ESGRC/ /app/` for the API image.
COPY ESGRC/app/ /app/app/

# Copy the Repo-01 analytics scripts into SCRIPTS_DIR so the worker can run them
# via subprocess. They live in per-module dirs, hence the repo-root build context
# (see docker-compose.yml). ScriptRunner resolves each by BASENAME from
# pipeline/scripts/scripts_registry.json, so SCRIPTS_DIR is deliberately flat -
# every module's scripts land side by side here. Filenames carry the module token
# (..._ESGRC_4_0.py, ..._Customer_3_0.py), so they cannot collide.
# Add one COPY line per module as it comes online.
COPY modules/esgrc/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/apex/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/customer/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/shared/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/bspt/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/enterprise/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/ictm/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/product/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/resource/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/service/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/brand/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/mkts/analytics_scripts/*.py /app/pipeline/scripts/
COPY modules/integration/analytics_scripts/*.py /app/pipeline/scripts/

# Set scripts directory
ENV SCRIPTS_DIR=/app/pipeline/scripts
ENV PYTHONPATH=/app

# Non-root user for security
RUN useradd -m -u 1000 celery
USER celery

CMD ["celery", "-A", "pipeline.celery_app", "worker", "--loglevel=info", "--concurrency=12"]
