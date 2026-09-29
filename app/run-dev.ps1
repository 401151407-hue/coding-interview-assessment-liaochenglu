# Optional convenience script: start the API and the frontend dev server together.
# Usage:  powershell -ExecutionPolicy Bypass -File app/run-dev.ps1
#
# Two windows are opened so each process keeps its own logs and can be stopped
# independently. Equivalent manual commands are listed in the root README.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"
$frontend = Join-Path $root "frontend"

if (-not (Test-Path (Join-Path $frontend "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    Push-Location $frontend
    npm install
    Pop-Location
}

Write-Host "Starting API on http://127.0.0.1:8000 ..."
Start-Process -FilePath "python" `
    -ArgumentList "-m", "uvicorn", "backend.main:app", "--reload", "--port", "8000" `
    -WorkingDirectory $backend

Write-Host "Starting frontend on http://127.0.0.1:5173 ..."
Start-Process -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory $frontend

Write-Host "Both services are starting. Open http://127.0.0.1:5173"
