@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m pa_scanner.pattern_cli --live %*
) else (
  python -m pa_scanner.pattern_cli --live %*
)
pause
