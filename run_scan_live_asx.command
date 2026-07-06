#!/bin/bash
# Price-Action: LIVE last-hour ASX only (real-time TWS, local only).
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== LIVE ASX (last-hour) ==="
python3 -m pa_scanner.cli --market asx --live --no-ledger || { read -n1 -r -p "ASX live failed. Key..."; exit 1; }
open pa_report_asx.html 2>/dev/null || true
