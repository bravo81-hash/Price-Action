@echo off
REM ============================================================
REM  Price-Action: event-study backtest, all three markets.
REM  Replays the scanner over 2y of history, verifies replay
REM  parity vs the live scanner, and writes per-market reports
REM  to backtest\report_<mkt>.md + raw events CSV (local only).
REM ============================================================
cd /d "%~dp0"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"
python -m pa_scanner.backtest --market us  --verify 200
python -m pa_scanner.backtest --market asx --verify 100
python -m pa_scanner.backtest --market in  --verify 100
echo.
echo Reports in backtest\report_us.md / report_asx.md / report_in.md
pause
