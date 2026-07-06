@echo off
REM ============================================================
REM  Price-Action: LIVE last-hour scan (US + ASX, real-time TWS)
REM  Use in the final hour. Refreshes US and ASX hits with
REM  real-time TWS price + live trigger status. LOCAL ONLY -
REM  no commit, no push. Re-run as often as you like.
REM  Requires TWS running and logged in (port 7496).
REM  (India is not included - traded via a separate broker.)
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   LIVE  US (last-hour, real-time)
echo ============================================
python -m pa_scanner.cli --tws --live
if errorlevel 1 (
    echo US live scan FAILED - is TWS running and logged in?
    pause
    exit /b 1
)

echo ============================================
echo   LIVE  ASX (last-hour, real-time)
echo ============================================
python -m pa_scanner.cli --market asx --live --no-ledger
if errorlevel 1 (
    echo ASX live scan FAILED - is TWS running and logged in?
    pause
    exit /b 1
)

start "" "pa_report.html"
start "" "pa_report_asx.html"
