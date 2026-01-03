import os, sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.notify import send_telegram

# # Set env vars for test (or use CONFIG_PATH pointing to a yaml)
# os.environ["TELEGRAM_BOT_TOKEN"] = "<your-bot-token>"
# os.environ["TELEGRAM_CHAT_ID"] = "<your-chat-id>"

send_telegram("Test message from notify_smoke.py")