#!/usr/bin/env bash
# Fail if legacy lint debt grows. Lower backend/.ruff-baseline whenever you pay some down.
set -euo pipefail
cd "$(dirname "$0")/../backend"
current=$( (ruff check . --output-format concise -q 2>/dev/null || true) | wc -l | tr -d ' ')
baseline=$(cat .ruff-baseline)
echo "ruff legacy issues: current=$current baseline=$baseline"
if [ "$current" -gt "$baseline" ]; then echo "Lint debt increased; fix new issues." >&2; exit 1; fi
