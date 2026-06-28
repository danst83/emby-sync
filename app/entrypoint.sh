#!/bin/bash
set -uo pipefail

LOCKFILE="${LOCKFILE:-/app/state/emby_sync.lock}"
LOGFILE="${LOGFILE:-/app/state/emby_sync.log}"
CONFIG_PATH="${CONFIG_PATH:-/app/config/emby-sync.yml}"

mkdir -p "$(dirname "$LOCKFILE")" "$(dirname "$LOGFILE")"

ts() { date "+%F %T"; }
log() { echo "$(ts) - $*" | tee -a "$LOGFILE"; }

cleanup() {
  rm -f "$LOCKFILE" 2>/dev/null || true
}

# Always clean up on exit (normal, error, or signal)
trap cleanup EXIT
trap 'log "SIGINT";  exit 130' INT
trap 'log "SIGTERM"; exit 143' TERM

# Stale lock detection
if [[ -e "$LOCKFILE" ]]; then
  OLD_PID=$(cat "$LOCKFILE" 2>/dev/null || echo "")
  if [[ -n "$OLD_PID" ]] && [[ "$OLD_PID" != "$$" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    log "Lock exists; another run active (PID $OLD_PID). Exiting."
    # Don't remove an active lock on exit
    trap - EXIT
    exit 0
  else
    log "Stale lock found (PID ${OLD_PID:-unknown} not running). Removing."
    rm -f "$LOCKFILE"
  fi
fi
echo $$ > "$LOCKFILE"

log "Using config: $CONFIG_PATH"
if [[ ! -f "$CONFIG_PATH" ]]; then
  log "Config not found: $CONFIG_PATH"
  exit 1
fi

# Execute the Python orchestrator and stream its output into the log
python /app/runner.py 2>&1 | while IFS= read -r line; do log "$line"; done
exit "${PIPESTATUS[0]}"