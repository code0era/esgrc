# Starts the ESGRC + Pipeline FastAPI backend for local development (SQLite, no external services).
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "$PSScriptRoot;$env:PYTHONPATH"

# Dev-safe defaults — only set if not already provided by the environment or ESGRC/.env
if (-not $env:SECRET_KEY)          { $env:SECRET_KEY          = "dev-only-$(python -c 'import secrets;print(secrets.token_hex(32))')" }
if (-not $env:DATABASE_URL)        { $env:DATABASE_URL        = "sqlite:///./esgrc.db" }
if (-not $env:DEBUG)               { $env:DEBUG               = "true" }
if (-not $env:AGENT_ENABLED)       { $env:AGENT_ENABLED       = "false" }   # no nightly scheduler in dev
if (-not $env:LLM_AGENT_ENABLED)   { $env:LLM_AGENT_ENABLED   = "false" }   # no Anthropic calls without a key
if (-not $env:ANTHROPIC_API_KEY)   { $env:ANTHROPIC_API_KEY   = "sk-ant-dev-placeholder" }

Set-Location "$PSScriptRoot\ESGRC"
& .\.venv2\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
