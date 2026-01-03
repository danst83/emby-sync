


## Emby Sync — Setup and Usage

This project builds a Docker image that syncs Emby favorites and can notify via Telegram. Use the Windows commands below (PowerShell) or adapt for Synology.

### 1) Build the Docker image (Windows)

```powershell
docker build -t emby-sync:latest -f app/Dockerfile app
```

Optionally export the image to a tar file (useful for Synology import):

```powershell
docker save -o images/emby-sync.tar emby-sync:latest
```

### 2) Run with Docker Compose (Windows)

Use the Windows compose file in this repo:

```powershell
docker compose -f .\docker-compose.windows.yml up -d
```

To test/run the container once:

```powershell
docker compose -f .\docker-compose.windows.yml run --rm emby-sync
```

### 3) Test Python locally (without Docker)

From the `app` folder:

```powershell
python .\emby_favorites_sync.py --config ..\config\emby-sync.yml
```

### 4) Telegram setup

- Create a bot via Telegram: message `@BotFather`, send `/newbot`, and obtain the API token.
- Get your chat ID using PowerShell:

```powershell
$token = "YOUR_TOKEN"
$u = Invoke-RestMethod -Uri "https://api.telegram.org/bot$token/getUpdates"
$u.result | ForEach-Object { $_.message.chat.id }
```

### 5) Configuration file

Create `config/emby-sync.yml` with your details:

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

1. Import the Docker image tar:
   - Build and `docker save` the image on Windows (see step 1).
   - Upload `images/emby-sync.tar` into Synology Container Manager and import.

2. Use a Compose project:
   - In Container Manager, create a project and upload your compose file (e.g., `docker-compose.synology.yml`).

Schedule periodic runs via Task Scheduler:

- Task Scheduler → Create → Scheduled Task → User-defined script
- User: `root`
- Schedule: Every 5 minutes
- Script:

```bash
docker start --attach emby-sync
```

Note: Adjust container name and volume mappings to match your environment.


