


## Emby Sync — Setup and Usage

A Docker-based tool that syncs your Emby favorites to local storage and sends notifications via Telegram. The instructions below use PowerShell on Windows; adapt paths as needed for Synology.

### 1) Build the Docker image (Windows)

```powershell
docker build -t emby-sync:latest -f app/Dockerfile app
```

Optionally, export the image as a tar file for transfer to a Synology NAS:

```powershell
docker save -o images/emby-sync.tar emby-sync:latest
```

### 2) Run with Docker Compose (Windows)

Start the container in the background:

```powershell
docker compose -f .\docker-compose.windows.yml up -d
```

Or run it once for testing (container is removed after exit):

```powershell
docker compose -f .\docker-compose.windows.yml run --rm emby-sync
```

### 3) Run locally without Docker

Run the sync script directly from the `app` folder:

```powershell
python .\emby_favorites_sync.py --config ..\config\emby-sync.yml
```

### 4) Telegram setup

1. Create a bot: message `@BotFather` on Telegram, send `/newbot`, and copy the API token.
2. Retrieve your chat ID with PowerShell:

```powershell
$token = "YOUR_TOKEN"
$u = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates"
$u.result | ForEach-Object { $_.message.chat.id }
```

### 5) Configuration file

Create `config/emby-sync.yml` with your Emby server and Telegram credentials:

```yaml
telegram:
  bot_token: "3245:adfad"
  chat_id: "23452"

emby:
  server: "http://yourserver:8096/"  # Example Emby server URL
  api_key: ""
  user_id: ""

sync:
  dest_dir: "./downloads"          # inside container; map this to your NAS volume
  content: "tv"                    # movies | tv | both
  latest_season_only: true
  dry_run: true
```

### 6) Synology: import and schedule

#### Method 1 — Compose project

1. **Import the Docker image:**
   - Build and export with `docker save` on Windows (see step 1).
   - In Synology Container Manager, go to Action → Import → Add From File → From This DSM and select `emby-sync.tar`.

2. **Create a Compose project:**
   - In Container Manager, create a new project and upload `docker-compose.synology.yml`.

3. **Schedule periodic runs** via Task Scheduler:
   - Task Scheduler → Create → Scheduled Task → User-defined script
   - User: `root`
   - Schedule: e.g., every 5 minutes
   - Script:

```bash
docker start --attach emby-sync
```

#### Method 2 — Standalone container

Import the image as in Method 1, but skip creating a Compose project. Instead, schedule the container to run directly.

Schedule periodic runs via Task Scheduler:

- Task Scheduler → Create → Scheduled Task → User-defined script
- User: `root`
- Script:

```bash
docker run --rm \
  --name emby-sync \
  -e CONFIG_PATH=/app/config/emby-sync.yml \
  -e TZ=America/New_York \
  -v /volume2/emby-sync/:/app/downloads \
  -v /volume1/docker/emby-sync/state:/app/state \
  -v /volume1/docker/emby-sync/config:/app/config:ro \
  emby-sync:latest
```

> **Note:** Adjust volume mappings and timezone to match your environment.


