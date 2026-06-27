#!/bin/bash
# Price-Action: LIVE last-hour scan (real-time TWS). LOCAL ONLY - no push.
# Use in the final hour: screens the universe, then refreshes hits with
# real-time TWS price + live trigger status. Re-run as often as needed.
# Requires TWS running and logged in (port 7496).
# Make executable once:  chmod +x run_scan_live.command
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "=== Price-Action LIVE (last-hour, real-time) ==="
if ! python3 -m pa_scanner.cli --tws --live; then
    echo "Live scan failed - is TWS running and logged in?"
    read -n1 -r -p "Press any key to close..."
    exit 1
fi

open pa_report.html 2>/dev/null || true
