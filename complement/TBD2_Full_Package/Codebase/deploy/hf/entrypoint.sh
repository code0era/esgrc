#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# Single-container boot for the Hugging Face Spaces demo.
#
# Starts, in order, inside ONE container:
#   1. redis-server   (LLM cache, Co-Pilot history, rate-limit store)
#   2. alembic upgrade head   (build the SQLite schema)
#   3. seed_demo.py           (Vigilant Lens Demo Corp + completed pipeline runs)
#   4. uvicorn (FastAPI)      on 127.0.0.1:8000  — background
#   5. nginx                  on 0.0.0.0:7860    — foreground (serves SPA + /api)
#
# Everything lives on ephemeral storage (/tmp), so the demo RESEEDS clean on
# every boot. No external Postgres/Redis/R2 required. $0 Claude spend unless a
# user manually triggers a live pipeline run (ANTHROPIC_API_KEY optional).
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

echo "── TBD2 demo container booting ──────────────────────────────────────────"

# ── Environment (demo defaults; real secrets come from HF Space settings) ────
export PYTHONPATH=/app
export DATABASE_URL="${DATABASE_URL:-sqlite:////tmp/tbd2_demo.db}"
export DEMO_MODE="${DEMO_MODE:-true}"
export CELERY_TASK_ALWAYS_EAGER="${CELERY_TASK_ALWAYS_EAGER:-true}"
export REDIS_URL="${REDIS_URL:-redis://127.0.0.1:6379/0}"
export CELERY_BROKER_URL="${CELERY_BROKER_URL:-redis://127.0.0.1:6379/1}"
export CELERY_RESULT_BACKEND="${CELERY_RESULT_BACKEND:-redis://127.0.0.1:6379/2}"
# Disable the daily batch agent scheduler in the demo (no surprise Claude spend).
export AGENT_ENABLED="${AGENT_ENABLED:-false}"
# A real (non-placeholder) signing key so the SECRET_KEY startup gate passes.
# Regenerated each boot — fine, the demo reseeds and has no persistent sessions.
export SECRET_KEY="${SECRET_KEY:-$(python -c 'import secrets; print(secrets.token_hex(32))')}"

cd /app

# ── 1. Redis (ephemeral, no persistence, all scratch under /tmp) ─────────────
echo "→ starting redis-server"
redis-server --save '' --appendonly no --dir /tmp --port 6379 --bind 127.0.0.1 &
for i in $(seq 1 30); do
    if redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; then
        echo "  redis up"; break
    fi
    sleep 0.5
done

# ── 2. Schema + 3. Seed ──────────────────────────────────────────────────────
echo "→ applying migrations (alembic upgrade head)"
alembic upgrade head

echo "→ seeding demo data"
python pipeline/scripts/seed_demo.py || echo "  ⚠ seed reported an error (continuing)"

# ── 4. Backend (FastAPI) ─────────────────────────────────────────────────────
echo "→ starting uvicorn on 127.0.0.1:8000"
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1 &
API_PID=$!

# Wait for the API to answer /health before fronting it with nginx.
for i in $(seq 1 60); do
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "  api healthy"; break
    fi
    if ! kill -0 "$API_PID" 2>/dev/null; then
        echo "  ✗ uvicorn exited during startup"; exit 1
    fi
    sleep 1
done

# ── 5. nginx (foreground — keeps the container alive, serves SPA + /api) ─────
# Listen on the platform-provided port. Render (and most PaaS) inject $PORT and
# expect the app to bind it; HF Spaces / local default to 7860. We stamp the
# port into a copy of the nginx config at boot so the same image works anywhere.
LISTEN_PORT="${PORT:-7860}"
sed "s/listen 7860;/listen ${LISTEN_PORT};/" /app/deploy/hf/nginx.conf > /tmp/nginx.conf
echo "→ starting nginx on 0.0.0.0:${LISTEN_PORT}"
echo "── boot complete — open the app URL ─────────────────────────────────────"
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
