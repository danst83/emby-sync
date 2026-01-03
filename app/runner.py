#!/usr/bin/env python3
import os, sys, json, traceback, yaml

# Import your modules
from notify import send_telegram
from emby_favorites_sync import main as sync_main

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config/emby-sync.yml")
#LOCKFILE    = os.environ.get("LOCKFILE", "/app/state/emby_sync.lock")

def esc(s: str) -> str:
    s = str(s)
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def load_yaml(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        raise RuntimeError(f"Failed to load YAML: {path} ({e})")

def normalize_config(raw: dict) -> dict:
    emby = raw.get("emby", {}) or {}
    sync = raw.get("sync", {}) or {}

    server = str(emby.get("server","")).strip()
    api    = str(emby.get("api_key","")).strip()
    user   = str(emby.get("user_id","")).strip()

    # Prefer new keys ('content' or 'mode') over legacy 'only'
    content_raw = sync.get("content", sync.get("mode", sync.get("only","both")))
    content     = str(content_raw).strip().lower()

    dest   = str(sync.get("dest_dir","/app/download")).strip()
    latest = bool(sync.get("latest_season_only", False))
    dryrun = bool(sync.get("dry_run", False))

    if content not in ("movies","tv","both"):
        raise ValueError(f"Invalid sync.content/mode/only: {content} (expected: movies|tv|both)")
    for key, val in (("emby.server", server), ("emby.api_key", api), ("emby.user_id", user)):
        if not val:
            raise ValueError(f"Missing required config key: {key}")

    return {
        "server": server,
        "api": api,
        "user": user,
        "dest": dest,
        "content": content,
        "latest": latest,
        "dryrun": dryrun,
    }

def notify_start(cfg: dict):
    send_telegram(
        f"🚀 <b>Emby sync started</b>\n"
        f"Server: <code>{esc(cfg['server'])}</code>\n"
        f"UserId: <code>{esc(cfg['user'])}</code>\n"
        f"Dest:   <code>{esc(cfg['dest'])}</code>\n"
        f"Content: <code>{cfg['content']}</code> "
        f"LatestSeasonOnly: <code>{cfg['latest']}</code> "
        f"DryRun: <code>{cfg['dryrun']}</code>",
        parse_mode="HTML",
    )

def notify_success():
    send_telegram("✅ <b>Emby sync finished successfully</b>")

def notify_failure(details: str):
    send_telegram(f"❌ <b>Emby sync failed</b>\n<pre>{esc(details)}</pre>", parse_mode="HTML")

def main() -> int:
    # # If entrypoint used a lock, runner can respect it too (optional check)
    # if os.path.exists(LOCKFILE):
    #     # entrypoint already exits on this; we keep runner simple and silent
    #     return 0

    # Load and normalize YAML config
    raw = load_yaml(CONFIG_PATH)
    cfg = normalize_config(raw)

    # Announce start
    notify_start(cfg)

    # Build argv for the sync script
    argv = [
        "emby_favorites_sync.py",
        "--server", cfg["server"],
        "--api-key", cfg["api"],
        "--user-id", cfg["user"],
        "--dest", cfg["dest"],
        "--content", cfg["content"],
    ]
    if cfg["latest"]: argv.append("--latest-season-only")
    if cfg["dryrun"]: argv.append("--dry-run")

    # Execute sync
    try:
        sys.argv = argv
        sync_main()
        notify_success()
        return 0
    except SystemExit as se:
        code = int(getattr(se, 'code', 0) or 0)
        if code == 0:
            notify_success()
            return 0
        else:
            notify_failure(f"SystemExit with code {code}")
            return code
    except Exception as e:
        tb = ''.join(traceback.format_exception(e))
        notify_failure(tb)
        return 1

if __name__ == "__main__":
    sys.exit(main())
