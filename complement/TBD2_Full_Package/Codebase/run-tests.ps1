# Runs both test suites (ESGRC backend + pipeline) with CI-equivalent env. LLM/R2 fully mocked.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = ".\ESGRC\.venv2\Scripts\python.exe"

$env:PYTHONPATH            = $PSScriptRoot
$env:SECRET_KEY            = "ci-test-secret-key-not-for-production-use"
$env:ANTHROPIC_API_KEY     = "sk-ant-ci-mock-key"
$env:LLM_AGENT_ENABLED     = "false"

Write-Host "== ESGRC backend tests ==" -ForegroundColor Cyan
$testDbDir = Join-Path $PSScriptRoot ".local\test_databases"
New-Item -ItemType Directory -Force -Path $testDbDir | Out-Null
$env:DATABASE_URL = "sqlite:///./.local/test_databases/test_esgrc.db"
& $py -m pytest ESGRC\tests\ -q
if ($LASTEXITCODE -ne 0) { throw "ESGRC tests failed" }

Write-Host "`n== Pipeline tests ==" -ForegroundColor Cyan
$env:DATABASE_URL             = "sqlite:///./.local/test_databases/test_pipeline.db"
$env:REDIS_URL                = "redis://localhost:6379/0"
$env:CLOUDFLARE_R2_BUCKET     = "ci-test-bucket"
$env:CLOUDFLARE_R2_ENDPOINT   = "https://ci-test.r2.example.com"
$env:CLOUDFLARE_R2_ACCESS_KEY = "ci-test-access-key"
$env:CLOUDFLARE_R2_SECRET_KEY = "ci-test-secret-key"
$env:CELERY_TASK_ALWAYS_EAGER = "true"
$env:DEMO_MODE                = "false"
& $py -m pytest pipeline\tests\ -q --override-ini="asyncio_mode=auto"
if ($LASTEXITCODE -ne 0) { throw "Pipeline tests failed" }

Write-Host "`n== All tests passed ==" -ForegroundColor Green
