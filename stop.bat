@echo off
@REM Author: François Guillemette
@REM CrazyLogix CrazyVideoGenerator - Stop Script (Docker)

echo [*] Stopping CrazyVideoGenerator container...
docker compose down
if errorlevel 1 (
    echo [ERROR] Failed to stop container cleanly.
    pause
    exit /b 1
)
echo [OK] CrazyVideoGenerator container stopped.
