@echo off
REM ============================================================
REM  Price-Action: US + ASX one-click scan + publish
REM  New default. Runs the US options scan and the ASX long-only
REM  scan (both via TWS), pushes both snapshots to the dashboard,
REM  and opens both local reports. Requires TWS running (7496).
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   Price-Action scan - US (options)
echo ============================================
python -m pa_scanner.cli --web docs --tws
if errorlevel 1 (
    echo US scan FAILED - see messages above.
    pause
    exit /b 1
)

echo ============================================
echo   Price-Action scan - ASX (long-only, TWS)
echo ============================================
python -m pa_scanner.cli --market asx --web docs --tws
if errorlevel 1 (
    echo ASX scan FAILED - see messages above.
    pause
    exit /b 1
)

git add docs/data
git commit -m "scan US+ASX %date%" >nul 2>&1
git pull --rebase -X theirs --no-edit
if errorlevel 1 (
    echo.
    echo WARNING: git pull/rebase FAILED - dashboard NOT published. Resolve manually.
    pause
    exit /b 1
)
git push
if errorlevel 1 (
    echo.
    echo WARNING: git push FAILED - dashboard NOT published. Check network/credentials.
    pause
    exit /b 1
)

echo.
echo Done. Dashboard updates in ~1 min:
echo   https://bravo81-hash.github.io/Price-Action/
start "" "pa_report.html"
start "" "pa_report_asx.html"
pause
