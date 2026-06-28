@echo off
REM ============================================================
REM  Price-Action: India long-only directional scan + publish
REM  Screens the curated India ~100 universe (no options/TWS),
REM  tags each hit BUY / HOLD / REDUCE / AVOID / WATCH / EXIT,
REM  pushes the snapshot to the India dashboard tab, opens report.
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

echo ============================================
echo   Price-Action scan - India (long-only)
echo ============================================
python -m pa_scanner.cli --market in --web docs
if errorlevel 1 (
    echo.
    echo Scan FAILED - see messages above.
    pause
    exit /b 1
)

git add docs/data
git commit -m "scan India %date%" >nul 2>&1
git pull --rebase -X theirs --no-edit
git push

echo.
echo Done. Opening local report; dashboard updates in ~1 min:
echo   https://bravo81-hash.github.io/Price-Action/
start "" "pa_report_in.html"
pause
