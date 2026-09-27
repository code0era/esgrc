#!/usr/bin/env bash
# Runs both test suites (ESGRC backend + pipeline) with CI-equivalent env.
# LLM, R2, and Redis are all mocked (pipeline uses an in-memory FakeRedis) —
# no external services required. Expected: 258 ESGRC passed + 570 pipeline passed
# (1 pipeline test skipped). Test counts move most days - if this drifts again,
# re-verify rather than trust it.
set -euo pipefail
cd "$(dirname "$0")"
PY="ESGRC/.venv2/bin/python"

export PYTHONPATH="$PWD"
export SECRET_KEY="ci-test-secret-key-not-for-production-use"
export ANTHROPIC_API_KEY="sk-ant-ci-mock-key"
export LLM_AGENT_ENABLED=false

echo "== ESGRC backend tests =="
mkdir -p .local/test_databases
DATABASE_URL="sqlite:///./.local/test_databases/test_esgrc.db" "$PY" -m pytest ESGRC/tests/ -q

echo ""
echo "== Pipeline tests =="
DATABASE_URL="sqlite:///./.local/test_databases/test_pipeline.db" \
REDIS_URL="redis://localhost:6379/0" \
CLOUDFLARE_R2_BUCKET="ci-test-bucket" \
CLOUDFLARE_R2_ENDPOINT="https://ci-test.r2.example.com" \
CLOUDFLARE_R2_ACCESS_KEY="ci-test-access-key" \
CLOUDFLARE_R2_SECRET_KEY="ci-test-secret-key" \
CELERY_TASK_ALWAYS_EAGER=true \
DEMO_MODE=false \
"$PY" -m pytest pipeline/tests/ -q --override-ini="asyncio_mode=auto"

echo ""
echo "== All tests passed =="
