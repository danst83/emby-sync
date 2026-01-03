


## Overview

Tools to sync Emby favorites and optionally notify via Telegram. Run locally (Windows) or on a Synology NAS.

## Build the Docker image (Windows PowerShell)

```powershell
docker build -t emby-sync:latest -f app\Dockerfile app
```

Optionally export the image to a tar (for upload to Synology):

```powershell
docker save -o emby-sync.tar emby-sync:latest
```

## Run with Docker Compose (Windows)

```powershell
# If compose file is at repo root
docker compose up -d --build

# Or specify a file
docker compose -f .\docker-compose.windows.yml run --rm emby-sync
```

## Run locally without Docker (quick test)

```powershell
cd app
python emby_favorites_sync.py --config ..\config\emby-sync.yml
```

## Synology NAS

- Upload `emby-sync.tar` via Container Manager → Image → Upload.
- Or create a Project and import `docker-compose.synology.yml` to deploy.
- To run on a schedule (every 5 min), use Control Panel → Task Scheduler → User-defined script:

It can also run it through a command line 
```bash
docker run --rm --name emby-sync \
  -v /volume1/docker/emby-sync/config:/app/config:ro \
  -v /volume1/docker/emby-sync/state:/app/state \
  -v /volume2/emby-sync/:/downloads \
  emby-sync:latest
```

## Telegram setup

1. In Telegram, message `@BotFather` → `/newbot` → get the API token.
2. Get your chat id in PowerShell:

```powershell
$token = "YOUR_TOKEN"
$u = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates"
$u.result | ForEach-Object { $_.message.chat.id }
```

## Config file (`config/emby-sync.yml`)

```yml
telegram:
  bot_token: "3245:adfad"
  chat_id: "23452"

emby:
  server: "http://yourserver:42402/"
  api_key: ""
  user_id: ""

sync:
  dest_dir: "./downloads"          # inside container; mapped to NAS volume
  content: "tv"                    # movies | tv | both
  latest_season_only: true
  dry_run: true
```

## Notes

- Ensure the compose service uses `image: emby-sync:latest` or a `build:` block.
- On Synology via SSH, you may need `sudo` for Docker commands.
- For Windows paths in volumes, prefer Compose files tailored to Windows (see `docker-compose.windows.yml`).

