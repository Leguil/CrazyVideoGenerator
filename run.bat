@echo off
@REM Author: François Guillemette
@REM CrazyLogix CrazyVideoGenerator - Local Bare-Metal Launch Script

title CrazyLogix CrazyVideoGenerator - Local Server
echo ========================================================
echo   CrazyLogix CrazyVideoGenerator (Local Server)
echo ========================================================
echo.

python -m uvicorn app.main:app --host 0.0.0.0 --port 8202 --reload
if errorlevel 1 (
    echo.
    echo [ERROR] Application crashed or failed to start.
    pause
)
