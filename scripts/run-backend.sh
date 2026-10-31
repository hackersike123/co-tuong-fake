#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1 --loop uvloop --ws-ping-interval 20 --ws-ping-timeout 20
