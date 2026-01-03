
# notify.py
import os, requests, yaml

def _get_creds():
    # Prefer YAML; fallback to env for flexibility
    cfg_path = os.getenv("CONFIG_PATH", "./config/emby-sync.yml")
    print(os.getcwd())
    if os.path.exists(cfg_path):
        raw = yaml.safe_load(open(cfg_path, "r", encoding="utf-8")) or {}
        tel = (raw.get("telegram") or {})
        bot = str(tel.get("bot_token", "")).strip()
        cid = str(tel.get("chat_id", "")).strip()
        if bot and cid:
            return bot, cid
    # fallback to env vars
    return os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", "")

def send_telegram(msg: str, parse_mode: str = "HTML") -> None:
    print("Sending Telegram notification...")
    bot_token, chat_id = _get_creds()
    print(bot_token, chat_id)
    if not bot_token or not chat_id:
        return
    requests.post(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        json={"chat_id": chat_id, "text": msg, "parse_mode": parse_mode, "disable_web_page_preview": True},
        timeout=30
    )
