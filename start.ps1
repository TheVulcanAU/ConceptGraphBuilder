# Start the Concept Graph server
# Usage: .\start.ps1
# Requires: ANTHROPIC_API_KEY set in environment

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Error "ANTHROPIC_API_KEY is not set. Set it before running."
    exit 1
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

# Install deps if needed
if (-not (Get-Command uvicorn -ErrorAction SilentlyContinue)) {
    Write-Host "Installing dependencies..."
    pip install -r requirements.txt
}

Write-Host "Starting server at http://localhost:8000"
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
