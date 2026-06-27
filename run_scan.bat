@echo off
REM ============================================================
REM  Price-Action: one-click scan + publish
REM  Double-click this (or a desktop shortcut to it) to run a
REM  full scan, push the snapshot, and open the local report.
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   Price-Action scan
echo ============================================
python -m pa_scanner.cli --web docs
if errorlevel 1 (
    echo.
    echo Scan FAILED - see messages above.
    pause
    exit /b 1
)

git add docs/data
git commit -m "scan %date%" >nul 2>&1
git push

echo.
echo Done. Opening local report; dashboard updates in ~1 min:
echo   https://bravo81-hash.github.io/Price-Action/
start "" "pa_report.html"
pause
