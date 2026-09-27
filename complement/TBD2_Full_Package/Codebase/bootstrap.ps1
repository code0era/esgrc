# ─── TBD2 one-command setup ───────────────────────────────────────────────────
# Run once on a fresh machine:  .\bootstrap.ps1
# Creates .env (with generated secrets), a Python venv with both requirement sets,
# and installs frontend deps. Safe to re-run — it skips steps already done.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

Write-Host "== TBD2 bootstrap ==" -ForegroundColor Cyan
if (-not (Have python)) { throw "Python 3.10+ not found on PATH." }
if (-not (Have node))   { throw "Node 18+ not found on PATH." }

# 1. .env — generate from .env.example with real secrets
if (-not (Test-Path ".env")) {
    Write-Host "-> creating .env with generated SECRET_KEY + POSTGRES_PASSWORD" -ForegroundColor Green
    $secret = python -c "import secrets;print(secrets.token_hex(32))"
    $pgpass = python -c "import secrets;print(secrets.token_urlsafe(24))"
    (Get-Content ".env.example") `
        -replace "REPLACE_WITH_64_CHAR_HEX_STRING", $secret `
        -replace "REPLACE_WITH_STRONG_PASSWORD", $pgpass |
        Set-Content ".env" -Encoding utf8
    Write-Host "   .env created. Fill in ANTHROPIC_API_KEY + CLOUDFLARE_R2_* for LLM/pipeline." -ForegroundColor Yellow
} else {
    Write-Host "-> .env already exists, leaving it untouched" -ForegroundColor DarkGray
}

# 2. Python venv (.venv2 is the canonical one used by run-server.ps1)
$py = ".\ESGRC\.venv2\Scripts\python.exe"
if (-not (Test-Path $py)) {
    Write-Host "-> creating ESGRC\.venv2 virtual environment" -ForegroundColor Green
    python -m venv ESGRC\.venv2
}
Write-Host "-> installing backend + pipeline requirements" -ForegroundColor Green
& $py -m pip install --quiet --upgrade pip
& $py -m pip install --quiet -r ESGRC\requirements.txt
& $py -m pip install --quiet -r pipeline\requirements.txt

# 3. Frontend deps
if (-not (Test-Path "frontend\node_modules")) {
    Write-Host "-> npm install (frontend)" -ForegroundColor Green
    Push-Location frontend; npm install; Pop-Location
} else {
    Write-Host "-> frontend\node_modules present, skipping npm install" -ForegroundColor DarkGray
}

Write-Host "`n== Done ==" -ForegroundColor Cyan
Write-Host "Backend :  .\run-server.ps1          -> http://127.0.0.1:8000/docs"
Write-Host "Frontend:  cd frontend; npm run dev  -> http://localhost:3000  (mock data, no backend needed)"
Write-Host "Tests   :  .\run-tests.ps1"
