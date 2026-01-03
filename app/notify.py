import os, json, time, requests, yaml

def _get_creds():
    cfg_path = os.getenv("CONFIG_PATH", "./config/emby-sync.yml")
    if os.path.exists(cfg_path):
        with open(cfg_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        tg = (raw.get("telegram") or {})
        return (tg.get("bot_token"), str(tg.get("chat_id")))
    # fallback to env vars
    return (os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID"))

def send_telegram(msg: str, parse_mode: str = "HTML") -> dict | None:
    bot_token, chat_id = _get_creds()
    if not bot_token or not chat_id:
        return None
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = {"chat_id": chat_id, "text": msg, "parse_mode": parse_mode, "disable_web_page_preview": True}
    r = requests.post(url, json=data, timeout=15)
    try:
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def edit_telegram(message_id: int, new_text: str, parse_mode: str = "HTML") -> None:
    bot_token, chat_id = _get_creds()
    if not bot_token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{bot_token}/editMessageText"
    data = {"chat_id": chat_id, "message_id": message_id, "text": new_text, "parse_mode": parse_mode, "disable_web_page_preview": True}
    try:
        r = requests.post(url, json=data, timeout=15)
        r.raise_for_status()
    except Exception:
        # Optionally log
        pass