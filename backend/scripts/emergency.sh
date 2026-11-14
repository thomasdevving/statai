#!/usr/bin/env bash
# Emergency laptop mode (BE-04.4): run the server on this laptop for phones on the same network
# (typically a phone hotspot) when the venue Wi-Fi or Railway fails.
#
#   backend/scripts/emergency.sh            # real Gemini, memory store, port 8000
#   backend/scripts/emergency.sh --fake     # fake AI (rehearsal without a Gemini key)
#   PORT=8001 backend/scripts/emergency.sh
#
# Storage is always memory (the fixture recipe is seeded at startup). GEMINI_API_KEY and any
# GHOSTCHEF_MODEL_* values come from the environment, else from backend/.env. The demo key comes
# from DEMO_API_KEY / backend/.env as usual. No key is ever printed.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BACKEND_DIR"

FAKE=0
for arg in "$@"; do
  case "$arg" in
    --fake) FAKE=1 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

PORT="${PORT:-8000}"

# Read one KEY=value from backend/.env (last occurrence wins; surrounding quotes and CR stripped).
dotenv_get() {
  [[ -f .env ]] || return 0
  local line
  line="$(grep -E "^[[:space:]]*(export[[:space:]]+)?$1=" .env | tail -n 1 || true)"
  [[ -n "$line" ]] || return 0
  line="${line#*=}"
  line="${line%$'\r'}"
  # trim surrounding whitespace
  line="${line#"${line%%[![:space:]]*}"}"
  line="${line%"${line##*[![:space:]]}"}"
  if [[ "$line" =~ ^\"([^\"]*)\" || "$line" =~ ^\'([^\']*)\' ]]; then
    line="${BASH_REMATCH[1]}"                       # quoted: take what is inside the quotes
  else
    line="${line%%[[:space:]]#*}"                   # unquoted: drop an inline " # comment"
    line="${line%"${line##*[![:space:]]}"}"
  fi
  printf '%s' "$line"
}

# ghostchef_ai reads these from the process environment, not from backend/.env.
for var in GEMINI_API_KEY GHOSTCHEF_MODEL_VIDEO GHOSTCHEF_MODEL_CHECK GHOSTCHEF_MODEL_WATCH \
           GHOSTCHEF_MODEL_LIVE; do
  if [[ -z "${!var:-}" ]]; then
    val="$(dotenv_get "$var")"
    if [[ -n "$val" ]]; then export "$var=$val"; fi
  fi
done

export STORAGE=memory
export PUBLIC_BASE_URL=          # derive URLs from the request, i.e. the LAN address phones use
if [[ "$FAKE" == 1 ]]; then
  export GHOSTCHEF_AI_FAKE=1
else
  export GHOSTCHEF_AI_FAKE=0
  if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    echo "GEMINI_API_KEY is not set (environment or backend/.env). Use --fake to rehearse without it." >&2
    exit 1
  fi
  # Real Gemini on a shared network: refuse the public default demo key.
  demo_key="${DEMO_API_KEY:-$(dotenv_get DEMO_API_KEY)}"
  if [[ -z "$demo_key" || "$demo_key" == "dev-key" ]]; then
    echo "DEMO_API_KEY is unset or the public default 'dev-key'. Set a private key in backend/.env" >&2
    echo "(the same one the apps use), or use --fake." >&2
    exit 1
  fi
  unset demo_key
fi

if [[ -x .venv/bin/python ]]; then PY=.venv/bin/python; else PY="$(command -v python3 || command -v python)"; fi

lan_addresses() {
  if command -v ip >/dev/null 2>&1; then
    # Skip container / VM bridges (docker0, br-*, veth*, virbr*): phones cannot reach them.
    ip -4 -o addr show scope global 2>/dev/null \
      | awk '$2 !~ /^(docker|br-|veth|virbr|cni|flannel)/ {split($4, a, "/"); print a[1]}'
  elif command -v ipconfig >/dev/null 2>&1 && [[ "$(uname)" == Darwin ]]; then
    for ifc in en0 en1 en2 bridge100; do ipconfig getifaddr "$ifc" 2>/dev/null || true; done
  elif command -v hostname >/dev/null 2>&1; then
    hostname -I 2>/dev/null | tr ' ' '\n'
  fi
}

echo "Ghost Chef emergency mode: STORAGE=memory, AI=$([[ "$FAKE" == 1 ]] && echo fake || echo gemini), port $PORT"
echo "Type one of these into the app's settings as the server URL (same Wi-Fi / hotspot as this laptop):"
found=0
while read -r addr; do
  [[ -n "$addr" ]] || continue
  echo "    http://$addr:$PORT"
  found=1
done < <(lan_addresses | sort -u)
[[ "$found" == 1 ]] || echo "    (no LAN address found: is this laptop connected to the hotspot?)"
echo "Demo key: the DEMO_API_KEY in backend/.env (not printed). Check: curl http://<address>:$PORT/health"
echo "Plain HTTP: the web simulator's camera works only on this laptop (http://localhost:$PORT/app/)."
echo

exec "$PY" -m uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --workers 1
