#!/bin/bash
# Price-Action: India long-only directional scan + publish.
# chmod +x run_scan_india.command  (once)
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== Price-Action scan - India (long-only) ==="
if ! python3 -m pa_scanner.cli --market in --web docs; then
    echo "Scan failed - see above."; read -n1 -r -p "Press any key..."; exit 1
fi
git add docs/data
git commit -m "scan India $(date +%F)" >/dev/null 2>&1
git pull --rebase -X theirs --no-edit
git push
open pa_report_in.html 2>/dev/null || true
