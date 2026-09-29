#!/usr/bin/env bash
set -euo pipefail

OPEN_BROWSER=0
if [[ "${1:-}" == "--open-browser" ]]; then
  OPEN_BROWSER=1
  shift
fi
if [[ $# -gt 0 ]]; then
  echo "Usage: $0 [--open-browser]" >&2
  exit 2
fi

read_port() {
  local name="$1" default="$2" value="${!name:-$default}"
  if [[ ! "$value" =~ ^[1-9][0-9]{0,4}$ ]] || (( value < 1 || value > 65535 )); then
    echo "$name must be an integer between 1 and 65535; received '$value'." >&2
    exit 2
  fi
  printf '%s' "$value"
}

RAG_HUB_PORT="$(read_port RAG_HUB_PORT 8001)"
RAG_FRONTEND_PORT="$(read_port RAG_FRONTEND_PORT 8010)"
C_VOC_PORT="$(read_port C_VOC_PORT 8765)"
B_END_PORT="$(read_port B_END_PORT 8000)"
KOL_PLATFORM_PORT="$(read_port KOL_PLATFORM_PORT 8766)"
RAG_HUB_URL="http://127.0.0.1:${RAG_HUB_PORT}"
RAG_FRONTEND_URL="http://127.0.0.1:${RAG_FRONTEND_PORT}"
C_VOC_URL="http://127.0.0.1:${C_VOC_PORT}"
B_END_URL="http://127.0.0.1:${B_END_PORT}"
KOL_URL="http://127.0.0.1:${KOL_PLATFORM_PORT}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RAG_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$RAG_ROOT/.." && pwd)"
SERVICE_ROOT="$RAG_ROOT/service"
FRONTEND_ROOT="$RAG_ROOT/frontend-v2"
C_ROOT="$REPO_ROOT/customer-voc/sentiment-analysis/voc-sentiment-analysis"
B_ROOT="$REPO_ROOT/b2b-public-sector/week7/compliance-sales-support"
KOL_ROOT="$REPO_ROOT/creator-intelligence/global-creator-assessment-platform"

require_file() {
  [[ -f "$1" ]] || { echo "Required local file is missing: $1" >&2; exit 1; }
}

for required in \
  "$SERVICE_ROOT/app/main.py" "$SERVICE_ROOT/.env" \
  "$C_ROOT/app_server.py" "$C_ROOT/.env" \
  "$FRONTEND_ROOT/server.py" "$FRONTEND_ROOT/dist/index.html" \
  "$B_ROOT/api/main.py" "$B_ROOT/requirements.txt" \
  "$KOL_ROOT/app/main.py" "$KOL_ROOT/requirements.txt"; do
  require_file "$required"
done

find_python() {
  local candidate version
  for candidate in "${1:-}" "$SERVICE_ROOT/.venv/bin/python" "python3.12" "python3" "python"; do
    [[ -n "$candidate" ]] || continue
    if [[ -x "$candidate" ]] || command -v "$candidate" >/dev/null 2>&1; then
      version="$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
      if [[ "$version" == "3.11" || "$version" == "3.12" ]]; then
        command -v "$candidate" 2>/dev/null || printf '%s' "$candidate"
        return 0
      fi
    fi
  done
  echo "Python 3.11 or 3.12 was not found. Create rag/service/.venv or install Python 3.11/3.12." >&2
  exit 1
}

SERVICE_PYTHON="$(find_python "$SERVICE_ROOT/.venv/bin/python")"
if [[ -x "$C_ROOT/venv312/bin/python" ]]; then C_PYTHON="$C_ROOT/venv312/bin/python"; else C_PYTHON="$SERVICE_PYTHON"; fi
if [[ -x "$B_ROOT/.venv/bin/python" ]]; then B_PYTHON="$B_ROOT/.venv/bin/python"; else B_PYTHON="$SERVICE_PYTHON"; fi
if [[ -x "$KOL_ROOT/.venv/bin/python" ]]; then KOL_PYTHON="$KOL_ROOT/.venv/bin/python"; else KOL_PYTHON="$SERVICE_PYTHON"; fi

port_open() {
  local port="$1"
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" >/dev/null 2>&1
    return
  fi
  "$SERVICE_PYTHON" - "$port" <<'PY'
import socket
import sys

with socket.socket() as sock:
    sock.settimeout(0.5)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}
wait_port() {
  local name="$1" port="$2" attempt
  for attempt in {1..20}; do
    port_open "$port" && return 0
    sleep 0.5
  done
  echo "$name did not accept connections on port $port after 10 seconds." >&2
  return 1
}

env_value() {
  local file="$1" key="$2" line
  [[ -f "$file" ]] || return 0
  line="$(grep -E "^${key}=" "$file" | head -n 1 || true)"
  line="${line#*=}"
  line="${line#\"}"; line="${line%\"}"
  line="${line#\'}"; line="${line%\'}"
  printf '%s' "$(printf '%s' "$line" | sed 's/[[:space:]]*$//')"
}

set_env_value() {
  local file="$1" key="$2" value="$3" tmp
  tmp="$(mktemp)"
  if grep -qE "^${key}=" "$file" 2>/dev/null; then
    sed "s|^${key}=.*|${key}=${value}|" "$file" > "$tmp"
  else
    cat "$file" > "$tmp"
    printf '\n%s=%s\n' "$key" "$value" >> "$tmp"
  fi
  mv "$tmp" "$file"
}

is_placeholder_secret() {
  case "$(printf '%s' "${1:-}" | tr '[:upper:]' '[:lower:]')" in
    ""|replace-me|replace_with_rag_hub_api_key|replace-with-shared-secret) return 0 ;;
    *) return 1 ;;
  esac
}

check_c_instance() {
  local response db expected
  port_open "$C_VOC_PORT" || return 1
  response="$(curl -fsS --max-time 2 "$C_VOC_URL/api/health" 2>/dev/null || true)"
  db="$(printf '%s' "$response" | sed -n 's/.*"db"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p')"
  [[ -n "$db" ]] || return 1
  expected="$(cd "$C_ROOT" && pwd)"
  case "$db" in "$expected"/*) return 0 ;; *) return 1 ;; esac
}

check_kol_instance() {
  local response
  port_open "$KOL_PLATFORM_PORT" || return 1
  response="$(curl -fsS --max-time 2 "$KOL_URL/health" 2>/dev/null || true)"
  printf '%s' "$response" | grep -q '"status"[[:space:]]*:[[:space:]]*"ok"'
}

start_service() {
  local name="$1" port="$2" python="$3" workdir="$4" logfile="$5"; shift 5
  if port_open "$port"; then
    echo "[OK] $name is already running on port $port."
    return 0
  fi
  (cd "$workdir" && nohup "$python" "$@" >> "$logfile" 2>&1 &)
  echo "[..] Starting $name on port $port..."
}

if port_open "$C_VOC_PORT" && ! check_c_instance; then
  echo "C_VOC_PORT $C_VOC_PORT is occupied by another service, not the current C VOC app." >&2
  exit 1
fi
if port_open "$KOL_PLATFORM_PORT" && ! check_kol_instance; then
  echo "KOL_PLATFORM_PORT $KOL_PLATFORM_PORT is occupied by another service, not the KOL platform." >&2
  exit 1
fi

SERVICE_ENV="$SERVICE_ROOT/.env"
C_ENV="$C_ROOT/.env"
SERVICE_KEY="$(env_value "$SERVICE_ENV" RAG_HUB_API_KEY)"
C_KEY="$(env_value "$C_ENV" RAG_HUB_API_KEY)"
if ! is_placeholder_secret "$SERVICE_KEY" && is_placeholder_secret "$C_KEY"; then
  set_env_value "$C_ENV" RAG_HUB_API_KEY "$SERVICE_KEY"
elif is_placeholder_secret "$SERVICE_KEY" && ! is_placeholder_secret "$C_KEY"; then
  set_env_value "$SERVICE_ENV" RAG_HUB_API_KEY "$C_KEY"
elif ! is_placeholder_secret "$SERVICE_KEY" && ! is_placeholder_secret "$C_KEY" && [[ "$SERVICE_KEY" != "$C_KEY" ]]; then
  echo "RAG_HUB_API_KEY differs between rag/service/.env and the C-side .env." >&2
  exit 1
fi
SERVICE_KEY="$(env_value "$SERVICE_ENV" RAG_HUB_API_KEY)"
set_env_value "$C_ENV" RAG_HUB_URL "$RAG_HUB_URL"
set_env_value "$C_ENV" C_RAG_PUSH_ENABLED true
set_env_value "$C_ENV" C_RAG_SNAPSHOT_MODE historical

if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  for container in maxkb ollama; do
    if docker ps -a --format '{{.Names}}' | grep -qx "$container"; then
      docker start "$container" >/dev/null 2>&1 || echo "[WARN] Docker container '$container' could not be started." >&2
    fi
  done
else
  echo "[WARN] Docker is unavailable; MaxKB/Ollama containers were not started." >&2
fi
if ! port_open 11434 && command -v ollama >/dev/null 2>&1; then
  nohup ollama serve >> "$SERVICE_ROOT/ollama.log" 2>&1 &
  echo "[..] Starting native Ollama on port 11434..."
fi

start_service "RAG Hub API" "$RAG_HUB_PORT" "$SERVICE_PYTHON" "$SERVICE_ROOT" "$SERVICE_ROOT/rag-service.log" \
  -m uvicorn app.main:app --host 127.0.0.1 --port "$RAG_HUB_PORT" --env-file .env
start_service "C-side VOC" "$C_VOC_PORT" "$C_PYTHON" "$C_ROOT" "$C_ROOT/voc.log" \
  app_server.py --host 127.0.0.1 --port "$C_VOC_PORT"
start_service "KOL platform" "$KOL_PLATFORM_PORT" "$KOL_PYTHON" "$KOL_ROOT" "$KOL_ROOT/kol.log" \
  -m uvicorn app.main:app --host 127.0.0.1 --port "$KOL_PLATFORM_PORT"

export RAG_HUB_SERVICE_ENV="$SERVICE_ENV"
export RAG_HUB_INTERNAL_URL="$RAG_HUB_URL"
export RAG_FRONTEND_PORT="$RAG_FRONTEND_PORT"
start_service "RAG frontend" "$RAG_FRONTEND_PORT" "$SERVICE_PYTHON" "$FRONTEND_ROOT" "$FRONTEND_ROOT/frontend.log" server.py

B_PUSH_ENABLED=false
if ! is_placeholder_secret "$SERVICE_KEY"; then B_PUSH_ENABLED=true; else echo "[WARN] RAG_HUB_API_KEY is not configured; B-side push is disabled." >&2; fi
if port_open "$B_END_PORT"; then
  echo "[OK] B-side business platform is already running on port $B_END_PORT."
else
  export RAG_PUSH_ENABLED="$B_PUSH_ENABLED"
  export RAG_HUB_BASE_URL="$RAG_HUB_URL"
  export RAG_HUB_API_KEY="$SERVICE_KEY"
  export B_END_PUBLIC_URL="$B_END_URL"
  B_ARGS=(-m uvicorn api.main:app --host 127.0.0.1 --port "$B_END_PORT")
  [[ -f "$B_ROOT/.env" ]] && B_ARGS+=(--env-file .env)
  start_service "B-side business platform" "$B_END_PORT" "$B_PYTHON" "$B_ROOT" "$B_ROOT/b-side.log" "${B_ARGS[@]}"
fi

wait_port "RAG Hub API" "$RAG_HUB_PORT"
wait_port "C-side VOC" "$C_VOC_PORT"
wait_port "KOL platform" "$KOL_PLATFORM_PORT"
wait_port "RAG frontend" "$RAG_FRONTEND_PORT"
wait_port "B-side business platform" "$B_END_PORT"

echo "C-side VOC : $C_VOC_URL/"
echo "B-side app  : $B_END_URL/"
echo "KOL platform: $KOL_URL/"
echo "RAG frontend: $RAG_FRONTEND_URL/"
echo "RAG API     : $RAG_HUB_URL/health"
echo "MaxKB       : http://127.0.0.1:8080/"
echo "KOL sync    : ./sync-kol-to-rag.sh --dry-run"

if (( OPEN_BROWSER )); then
  command -v open >/dev/null 2>&1 || { echo "macOS 'open' command is unavailable; skip browser launch." >&2; exit 0; }
  open "$C_VOC_URL/"; open "$B_END_URL/"; open "$KOL_URL/"; open "$RAG_FRONTEND_URL/"
fi
