#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SERVICE_ROOT="$REPO_ROOT/rag/service"
PYTHON="$SERVICE_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  for candidate in python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PYTHON="$(command -v "$candidate")"
      break
    fi
  done
  [[ -x "$PYTHON" ]] || { echo "Python 3.11/3.12 was not found. Create rag/service/.venv or install Python 3.11/3.12." >&2; exit 1; }
fi
SCRIPT="$SERVICE_ROOT/scripts/sync_kol_platform.py"
[[ -f "$SCRIPT" ]] || { echo "Formal KOL synchronization script is missing: $SCRIPT" >&2; exit 1; }
exec "$PYTHON" "$SCRIPT" "$@"
