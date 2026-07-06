@echo off
REM ============================================================
REM  Price-Action: LIVE last-hour scan - US only (real-time TWS)
REM  Run in the final hour of the US session
REM  (~3-4pm ET = ~5-6am AEST next day).
REM  Real-time TWS price + live trigger status. LOCAL ONLY -
REM  no commit, no push. Re-run as often as you like.
REM  Requires TWS running and logged in (port 7496).
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   LIVE  US  (last-hour, real-time)
echo ============================================
python -m pa_scanner.cli --tws --live
if errorlevel 1 (
    echo US live scan FAILED - is TWS running and logged in?
    pause
    exit /b 1
)
start "" "pa_report.html"
