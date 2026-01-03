#!/bin/bash
# Extra safety: if a previous container exists and is still running, skip
if docker ps --filter "name=emby-sync" --format '{{.Names}}' | grep -q '^emby-sync$'; then
  exit 0
fi

docker run --rm \
  --name emby-sync \
  -e TELEGRAM_BOT_TOKEN="$(cat /volume1/emby-sync/secrets/telegram_token.txt)" \
  -e TELEGRAM_CHAT_ID="$(cat /volume1/emby-sync/secrets/telegram_chat_id.txt)" \
  -e EMBY_SERVER="http://YOUR_EMBY:8096/emby" \
  -e EMBY_API_KEY="$(cat /volume1/emby-sync/secrets/emby_api_key.txt)" \
  -e EMBY_USER_ID="$(cat /volume1/emby-sync/secrets/user_id.txt)" \
  -e DEST_DIR="/app/download" \
  -e ONLY="tv" \
  -e LATEST_SEASON_ONLY="true" \
  -v /volume1/emby-sync/download:/app/download \
  -v /volume1/emby-sync/state:/app/state \
  emby-sync:latest
