# Author: François Guillemette
# CrazyLogix CrazyVideoGenerator - Start Script (PowerShell)

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  CrazyLogix CrazyVideoGenerator (Docker Launch)" -ForegroundColor Green
Write-Host "========================================================"
Write-Host ""

# Verify Docker is installed
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found. Please install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

# Verify Docker daemon is running
Write-Host "[*] Checking Docker daemon status..." -ForegroundColor Cyan
try {
    docker info 2>&1 | Out-Null
    Write-Host "[OK] Docker daemon is running." -ForegroundColor Green
} catch {
    Write-Error "Docker Desktop is not running. Please launch Docker Desktop and retry."
    exit 1
}

# Check if image needs building
$imageExists = $false
try {
    docker image inspect crazylogix/crazy-video-generator:latest 2>&1 | Out-Null
    $imageExists = $true
} catch {
    $imageExists = $false
}

if ($Build -or (-not $imageExists)) {
    Write-Host "[*] Building CrazyVideoGenerator container image..." -ForegroundColor Cyan
    docker compose build
    if ($LASTEXITCODE -ne 0) {
        Write-Error "Failed to build container image."
        exit 1
    }
}

Write-Host "[*] Launching container in detached mode..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "Failed to start container."
    exit 1
}

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  CrazyLogix CrazyVideoGenerator is running!" -ForegroundColor Green
Write-Host "========================================================"
Write-Host "  Web Studio URL : http://localhost:8202" -ForegroundColor Yellow
Write-Host "  View Logs      : docker compose logs -f"
Write-Host "  Stop Studio    : .\stop.ps1"
Write-Host "========================================================"
Write-Host ""

if (-not $NoBrowser) {
    Start-Process "http://localhost:8202"
}
