@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_live_dashboard_local.ps1"
if errorlevel 1 (
    echo.
    echo Price Action live dashboard failed. Review the error above.
    pause
    exit /b 1
)
