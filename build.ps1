# Author: François Guillemette
# CrazyLogix CrazyVideoGenerator - Docker Image Build Script (PowerShell)

[CmdletBinding()]
param(
    [switch]$NoCache,
    [switch]$Pull,
    [string]$Cuda = "cu128",
    [string]$Tag = "crazylogix/crazy-video-generator:latest"
)

$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Green
Write-Host "  CrazyLogix CrazyVideoGenerator - Docker Image Build" -ForegroundColor Green
Write-Host "========================================================"
Write-Host ""

# 1. Verify Docker CLI is available
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Error "Docker CLI not found. Please install Docker Desktop: https://www.docker.com/products/docker-desktop/"
    exit 1
}

# 2. Verify Docker daemon is active
Write-Host "[*] Checking Docker daemon status..." -ForegroundColor Cyan
try {
    docker info 2>&1 | Out-Null
    Write-Host "[OK] Docker daemon is operational." -ForegroundColor Green
} catch {
    Write-Error "Docker Desktop is not running. Please start Docker Desktop and retry."
    exit 1
}

# 3. Assemble build arguments
$buildCmd = @("compose", "build")
if ($NoCache) {
    Write-Host "[*] Building without cache (--no-cache)..." -ForegroundColor Yellow
    $buildCmd += "--no-cache"
}
if ($Pull) {
    Write-Host "[*] Pulling newest base images (--pull)..." -ForegroundColor Cyan
    $buildCmd += "--pull"
}
$buildCmd += @("--build-arg", "CUDA_WHL=$Cuda")

Write-Host ""
Write-Host "[*] Build Configuration:" -ForegroundColor Cyan
Write-Host "    Target Image : $Tag"
Write-Host "    CUDA Version : $Cuda"
Write-Host "    No-Cache     : $($NoCache.IsPresent)"
Write-Host ""

$sw = [System.Diagnostics.Stopwatch]::StartNew()

Write-Host "[*] Starting build execution..." -ForegroundColor Cyan
& docker @buildCmd

if ($LASTEXITCODE -ne 0) {
    $sw.Stop()
    Write-Error "Docker build failed with exit code $LASTEXITCODE."
    exit $LASTEXITCODE
}

if ($Tag -ne "crazylogix/crazy-video-generator:latest") {
    docker tag "crazylogix/crazy-video-generator:latest" $Tag
}

$sw.Stop()
$elapsed = [Math]::Round($sw.Elapsed.TotalSeconds, 1)

Write-Host ""
Write-Host "========================================================" -ForegroundColor Green
Write-Host "  [SUCCESS] Docker image built successfully in ${elapsed}s!" -ForegroundColor Green
Write-Host "========================================================"
docker images $Tag
Write-Host ""
Write-Host "  You can launch the container using: .\start.ps1" -ForegroundColor Yellow
Write-Host "========================================================"
Write-Host ""
