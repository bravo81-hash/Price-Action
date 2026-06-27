#!/bin/bash
# Price-Action: one-click scan + publish (macOS / Linux)
# Make executable once:  chmod +x run_scan.command
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate

echo "=== Price-Action scan ==="
if ! python3 -m pa_scanner.cli --web docs --tws; then
    echo "Scan failed."
    read -n1 -r -p "Press any key to close..."
    exit 1
fi

git add docs/data
git commit -m "scan $(date +%F)" >/dev/null 2>&1
git push

echo "Done. Dashboard: https://bravo81-hash.github.io/Price-Action/"
open pa_report.html 2>/dev/null || true
