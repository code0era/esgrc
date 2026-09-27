#!/usr/bin/env bash
# Starts the ESGRC + Pipeline FastAPI backend for local dev (SQLite, no external
# services). Dev-safe defaults are only set if not already provided.
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD"

: "${SECRET_KEY:=dev-only-$(python3 -c 'import secrets;print(secrets.token_hex(32))')}"
: "${DATABASE_URL:=sqlite:///./esgrc.db}"
: "${DEBUG:=true}"
: "${AGENT_ENABLED:=false}"
: "${LLM_AGENT_ENABLED:=false}"
: "${ANTHROPIC_API_KEY:=sk-ant-dev-placeholder}"
export SECRET_KEY DATABASE_URL DEBUG AGENT_ENABLED LLM_AGENT_ENABLED ANTHROPIC_API_KEY

cd ESGRC
exec .venv2/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000
