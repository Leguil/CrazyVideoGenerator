@echo off
@REM Author: François Guillemette
@REM CrazyLogix CrazyVideoGenerator - Docker Image Build Script

setlocal enabledelayedexpansion
title CrazyLogix CrazyVideoGenerator - Docker Build

echo ========================================================
echo   CrazyLogix CrazyVideoGenerator - Docker Image Build
echo ========================================================
echo.

:: 1. Verify Docker CLI installation
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI not found. Please install Docker Desktop:
    echo         https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:: 2. Verify Docker daemon is running
echo [*] Checking Docker daemon status...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker daemon is not running. Please start Docker Desktop and retry.
    pause
    exit /b 1
)
echo [OK] Docker daemon is operational.

:: 3. Parse optional arguments
set BUILD_ARGS=
set CUDA_ARG=cu128
set TAG=crazylogix/crazy-video-generator:latest

:parse_loop
if "%~1"=="" goto end_parse
if /i "%~1"=="--no-cache" set BUILD_ARGS=!BUILD_ARGS! --no-cache
if /i "%~1"=="-nc" set BUILD_ARGS=!BUILD_ARGS! --no-cache
if /i "%~1"=="--pull" set BUILD_ARGS=!BUILD_ARGS! --pull
if /i "%~1"=="--cuda" (
    shift
    set CUDA_ARG=%~1
)
if /i "%~1"=="--tag" (
    shift
    set TAG=%~1
)
shift
goto parse_loop
:end_parse

echo.
echo [*] Build Configuration:
echo     Image Tag    : %TAG%
echo     CUDA Version : %CUDA_ARG%
echo     Options      : %BUILD_ARGS%
echo.

echo [*] Starting Docker build process...
docker compose build %BUILD_ARGS% --build-arg CUDA_WHL=%CUDA_ARG%

if errorlevel 1 (
    echo.
    echo ========================================================
    echo   [ERROR] Docker build failed.
    echo   Please inspect the build output above for details.
    echo ========================================================
    pause
    exit /b 1
)

if /i not "%TAG%"=="crazylogix/crazy-video-generator:latest" (
    docker tag crazylogix/crazy-video-generator:latest %TAG%
)

echo.
echo ========================================================
echo   [SUCCESS] Docker image built successfully!
echo ========================================================
docker images %TAG%
echo.
echo   You can launch the container using: start.bat
echo ========================================================
echo.
