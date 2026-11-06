# Author: François Guillemette
# CrazyLogix CrazyVideoGenerator - Local Bare-Metal Launch Script (PowerShell)

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  CrazyLogix CrazyVideoGenerator (Local Launch)" -ForegroundColor Green
Write-Host "========================================================"
Write-Host ""

python -m uvicorn app.main:app --host 0.0.0.0 --port 8202 --reload
