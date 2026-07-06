#!/bin/bash
# Price-Action: US + ASX one-click scan + publish (macOS).
cd "$(dirname "$0")" || exit 1
[ -f .venv/bin/activate ] && source .venv/bin/activate
echo "=== US (options) ==="
python3 -m pa_scanner.cli --web docs --tws || { read -n1 -r -p "US failed. Key..."; exit 1; }
echo "=== ASX (long-only, TWS) ==="
python3 -m pa_scanner.cli --market asx --web docs --tws || { read -n1 -r -p "ASX failed. Key..."; exit 1; }
git add docs/data
git commit -m "scan US+ASX $(date +%F)" >/dev/null 2>&1
git pull --rebase -X theirs --no-edit
git push
open pa_report.html pa_report_asx.html 2>/dev/null || true
