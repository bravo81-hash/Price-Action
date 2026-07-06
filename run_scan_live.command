#!/bin/bash
# Price-Action: LIVE last-hour US + ASX (real-time TWS, local only).
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== LIVE US ==="
python3 -m pa_scanner.cli --tws --live || { read -n1 -r -p "US live failed. Key..."; exit 1; }
echo "=== LIVE ASX ==="
python3 -m pa_scanner.cli --market asx --live --no-ledger || { read -n1 -r -p "ASX live failed. Key..."; exit 1; }
open pa_report.html pa_report_asx.html 2>/dev/null || true
