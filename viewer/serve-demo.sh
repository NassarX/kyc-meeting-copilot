#!/usr/bin/env bash
# Serve the demo viewer on a fixed public link (Tailscale Funnel) from this Mac.
#   viewer/serve-demo.sh            # public link, password and budget required
#   viewer/serve-demo.sh --local    # this Mac only, http://127.0.0.1:8000
# Settings come from .env at the repo root (git-ignored; see .env.example): ANTHROPIC_API_KEY, VIEWER_PASSWORD,
# VIEWER_BUDGET_USD.
# Ctrl-C stops the viewer, closes the link and lets the Mac sleep again.
set -euo pipefail
cd "$(dirname "$0")/.."                       # repo root
PORT=8000
[ -f .env ] && { set -a; . ./.env; set +a; }

if [ "${1:-}" != "--local" ]; then
  [ -n "${VIEWER_PASSWORD:-}" ] || { echo "Refusing to go public: set VIEWER_PASSWORD in .env"; exit 1; }
  [ -n "${VIEWER_BUDGET_USD:-}" ] || { echo "Refusing to go public: set VIEWER_BUDGET_USD in .env (e.g. 5)"; exit 1; }
  TS=$(command -v tailscale || true)
  [ -z "$TS" ] && [ -x /Applications/Tailscale.app/Contents/MacOS/Tailscale ] && TS=/Applications/Tailscale.app/Contents/MacOS/Tailscale
  [ -n "$TS" ] || { echo "Tailscale not found: install it from tailscale.com/download and sign in"; exit 1; }
fi

uv run kyc-viewer --port "$PORT" &
VIEWER=$!
caffeinate -dims -w "$VIEWER" &               # keep the Mac awake while the viewer runs
trap 'kill "$VIEWER" 2>/dev/null; [ -n "${TS:-}" ] && "$TS" funnel --https=443 "$PORT" off >/dev/null 2>&1; true' EXIT
for _ in $(seq 1 40); do curl -s -o /dev/null "http://127.0.0.1:$PORT/" -u ":${VIEWER_PASSWORD:-}" && break; sleep 0.5; done  # gitleaks:allow (a variable, not a secret)

if [ "${1:-}" = "--local" ]; then
  echo "Local only: http://127.0.0.1:$PORT  (Ctrl-C to stop)"; wait "$VIEWER"
else
  echo "Opening the public link. If Tailscale prints a link to enable Funnel, open it once, then run this again."
  "$TS" funnel --https=443 "$PORT"            # prints https://<this-mac>.<tailnet>.ts.net; Ctrl-C closes it
fi
