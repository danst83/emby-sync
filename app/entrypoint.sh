#!/bin/bash
set -euo pipefail

LOCKFILE="${LOCKFILE:-/app/state/emby_sync.lock}"
LOGFILE="${LOGFILE:-/app/state/emby_sync.log}"
CONFIG_PATH="${CONFIG_PATH:-/app/config/emby-sync.yml}"

mkdir -p "$(dirname "$LOCKFILE")" "$(dirname "$LOGFILE")"

ts() { date "+%F %T"; }
log() { echo "$(ts) - $*" | tee -a "$LOGFILE"; }

cleanup() {
  [[ -f "$LOCKFILE" ]] && rm -f "$LOCKFILE" || true
}
trap 'log "SIGINT";  cleanup; exit 130' INT
trap 'log "SIGTERM"; cleanup; exit 143' TERM

if [[ -e "$LOCKFILE" ]]; then
  log "Lock exists; another run active. Exiting."
  # runner.py will send Telegram; entrypoint stays simple
  exit 0
fi
echo $$ > "$LOCKFILE"

log "Using config: $CONFIG_PATH"
if [[ ! -f "$CONFIG_PATH" ]]; then
  log "Config not found: $CONFIG_PATH"
  cleanup
  exit 1
fi

# Execute the Python orchestrator and stream its output into the log
python /app/runner.py 2>&1 | while IFS= read -r line; do log "$line"; done
EXIT=$?

cleanup
exit $EXIT
