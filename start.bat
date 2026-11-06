@echo off
@REM Author: François Guillemette
@REM CrazyLogix CrazyVideoGenerator - Start Script (Docker)

setlocal enabledelayedexpansion
title CrazyLogix CrazyVideoGenerator - Starting...

echo ========================================================
echo   CrazyLogix CrazyVideoGenerator (Docker Launch)
echo ========================================================
echo.

:: Check Docker installation
where docker >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker CLI not found. Please install Docker Desktop:
    echo         https://www.docker.com/products/docker-desktop/
    pause
    exit /b 1
)

:: Check Docker Daemon status
echo [*] Checking Docker daemon status...
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker Desktop does not seem to be running.
    echo         Please start Docker Desktop and try running start.bat again.
    pause
    exit /b 1
)
echo [OK] Docker daemon is running.

:: Check if rebuild is requested
set DO_BUILD=0
if "%1"=="--build" set DO_BUILD=1
if "%1"=="-b" set DO_BUILD=1

docker image inspect crazylogix/crazy-video-generator:latest >nul 2>&1
if errorlevel 1 set DO_BUILD=1

if !DO_BUILD! EQU 1 (
    echo [*] Building CrazyVideoGenerator container image...
    docker compose build
    if errorlevel 1 (
        echo.
        echo [ERROR] Failed to build CrazyVideoGenerator container image.
        pause
        exit /b 1
    )
)

:: Start container in detached mode
echo [*] Launching CrazyVideoGenerator container...
docker compose up -d
if errorlevel 1 (
    echo.
    echo [ERROR] Failed to start CrazyVideoGenerator container.
    pause
    exit /b 1
)

echo.
echo ========================================================
echo   CrazyLogix CrazyVideoGenerator is running!
echo ========================================================
echo   Web Studio URL : http://localhost:8202
echo   View Logs      : docker compose logs -f
echo   Stop Studio    : stop.bat
echo ========================================================
echo.

:: Optionally open in default web browser
set /p OPEN_BROWSER="Open Web Studio in browser? [Y/n]: "
if /i not "%OPEN_BROWSER%"=="n" (
    start http://localhost:8202
)
