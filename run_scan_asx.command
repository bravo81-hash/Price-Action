#!/bin/bash
# Price-Action: ASX long-only directional scan + publish.
# chmod +x run_scan_asx.command  (once)
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== Price-Action scan - ASX (long-only) ==="
if ! python3 -m pa_scanner.cli --market asx --web docs; then
    echo "Scan failed - see above."; read -n1 -r -p "Press any key..."; exit 1
fi
git add docs/data
git commit -m "scan ASX $(date +%F)" >/dev/null 2>&1
git pull --rebase -X theirs --no-edit
git push
open pa_report_asx.html 2>/dev/null || true
