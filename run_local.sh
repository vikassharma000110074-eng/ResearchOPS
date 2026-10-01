#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
export PYTHONPATH="$PWD/backend"
.venv/bin/python -m researchops_backend.worker &
researchops_worker_pid=$!
trap 'kill "$researchops_worker_pid" 2>/dev/null || true' EXIT INT TERM
.venv/bin/python -m uvicorn app:app --host 0.0.0.0 --port 3000
