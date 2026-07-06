#!/bin/bash
# Price-Action: LIVE last-hour US only (real-time TWS, local only).
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== LIVE US (last-hour) ==="
python3 -m pa_scanner.cli --tws --live || { read -n1 -r -p "US live failed. Key..."; exit 1; }
open pa_report.html 2>/dev/null || true
