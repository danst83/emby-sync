#!/bin/bash
set -uo pipefail

LOCKFILE="${LOCKFILE:-/app/state/emby_sync.lock}"
LOGFILE="${LOGFILE:-/app/state/emby_sync.log}"
CONFIG_PATH="${CONFIG_PATH:-/app/config/emby-sync.yml}"

mkdir -p "$(dirname "$LOCKFILE")" "$(dirname "$LOGFILE")"

ts() { date "+%F %T"; }
log() { echo "$(ts) - $*" | tee -a "$LOGFILE"; }

# Try to acquire an exclusive lock (non-blocking)
exec 9>"$LOCKFILE"
if ! flock -n 9; then
  log "Another instance is running. Exiting."
  exit 0
fi

trap 'log "SIGINT";  exit 130' INT
trap 'log "SIGTERM"; exit 143' TERM

log "Using config: $CONFIG_PATH"
if [[ ! -f "$CONFIG_PATH" ]]; then
  log "Config not found: $CONFIG_PATH"
  exit 1
fi

# Execute the Python orchestrator and stream its output into the log
python /app/runner.py 2>&1 | while IFS= read -r line; do log "$line"; done
exit "${PIPESTATUS[0]}"