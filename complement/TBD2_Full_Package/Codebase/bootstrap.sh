#!/usr/bin/env bash
# ─── TBD2 one-command setup (macOS / Linux) ───────────────────────────────────
# Run once on a fresh machine:  ./bootstrap.sh
# Creates .env (generated secrets), a Python venv with both requirement sets,
# and installs frontend deps. Safe to re-run — skips steps already done.
# NOTE: use Python 3.10–3.12 (numpy/pandas have no 3.13 wheels).
set -euo pipefail
cd "$(dirname "$0")"

echo "== TBD2 bootstrap =="
command -v python3 >/dev/null || { echo "ERROR: Python 3.10-3.12 not found"; exit 1; }
command -v node    >/dev/null || { echo "ERROR: Node 18+ not found"; exit 1; }

# 1. .env — generate from .env.example with real secrets
if [ ! -f .env ]; then
  echo "-> creating .env with generated SECRET_KEY + POSTGRES_PASSWORD"
  SECRET=$(python3 -c "import secrets;print(secrets.token_hex(32))")
  PGPASS=$(python3 -c "import secrets;print(secrets.token_urlsafe(24))")
  sed -e "s#REPLACE_WITH_64_CHAR_HEX_STRING#${SECRET}#" \
      -e "s#REPLACE_WITH_STRONG_PASSWORD#${PGPASS}#" .env.example > .env
  echo "   .env created. Fill in ANTHROPIC_API_KEY + CLOUDFLARE_R2_* for LLM/pipeline."
else
  echo "-> .env already exists, leaving it untouched"
fi

# 2. Python venv (ESGRC/.venv2 is the canonical one the run scripts use)
PY="ESGRC/.venv2/bin/python"
if [ ! -x "$PY" ]; then
  echo "-> creating ESGRC/.venv2 virtual environment"
  python3 -m venv ESGRC/.venv2
fi
echo "-> installing backend + pipeline requirements"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r ESGRC/requirements.txt
"$PY" -m pip install --quiet -r pipeline/requirements.txt

# 3. Frontend deps
if [ ! -d frontend/node_modules ]; then
  echo "-> npm install (frontend)"
  ( cd frontend && npm install )
else
  echo "-> frontend/node_modules present, skipping npm install"
fi

echo ""
echo "== Done =="
echo "Backend :  ./run-server.sh              -> http://127.0.0.1:8000/docs"
echo "Frontend:  cd frontend && npm run dev   -> http://localhost:3000  (mock data)"
echo "Tests   :  ./run-tests.sh"
