# Author: François Guillemette
# CrazyLogix CrazyVideoGenerator - Stop Script (PowerShell)

Write-Host "[*] Stopping CrazyVideoGenerator container..." -ForegroundColor Cyan
docker compose down
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] CrazyVideoGenerator container stopped." -ForegroundColor Green
} else {
    Write-Warning "Failed to stop container cleanly."
}
