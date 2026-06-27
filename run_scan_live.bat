@echo off
REM ============================================================
REM  Price-Action: LIVE last-hour scan (real-time TWS)
REM  Use this in the final hour of the session. Screens the
REM  universe, then refreshes the hits with real-time TWS price
REM  + live trigger status. LOCAL ONLY - no commit, no push.
REM  Re-run as often as you like; opens the local report.
REM  Requires TWS running and logged in (port 7496).
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   Price-Action LIVE  (last-hour, real-time)
echo ============================================
python -m pa_scanner.cli --tws --live
if errorlevel 1 (
    echo.
    echo Live scan FAILED - is TWS running and logged in?
    pause
    exit /b 1
)

start "" "pa_report.html"
