#!/bin/bash
cd "$(dirname "$0")"
PY=python3
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"
"$PY" -m pa_scanner.pattern_cli --live "$@"
