#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] == (3,12) else 1)' || { echo 'Use Python 3.12.'; exit 1; }
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
if [ ! -f .env ]; then cp .env.example .env; fi
printf '%s\n' 'Add your rotated Gemini and Tavily keys to .env, then run ./run_local.sh.'
