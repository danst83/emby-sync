import sys, traceback, os
from notify import send_telegram, edit_telegram
from emby_favorites_sync import main as sync_main
from emby_favorites_sync import NullReporter
import argparse

class TelegramReporter(NullReporter):
    def __init__(self):
        self.message_ids: dict[str, int] = {}

    def _key(self, item: dict) -> str:
        return item.get("Id") or item.get("Name") or "unknown"

    def _display_name(self, item: dict) -> str:
        t = (item.get("Type") or "").lower()
        if t == "episode":
            series = item.get("SeriesName") or item.get("Series") or ""
            # Season/Episode numbers if available
            ss = item.get("ParentIndexNumber")
            ee = item.get("IndexNumber")
            season_str = f"Season {ss}" if ss is not None else (item.get("SeasonName") or "")
            ep_name = item.get("Name") or ""
            ep_num = f"E{ee:02d}" if isinstance(ee, int) else ""
            sea_num = f"S{ss:02d}" if isinstance(ss, int) else ""
            # Prefer SxxExx format when numbers exist
            if sea_num or ep_num:
                return esc(f"{series} {sea_num}{ep_num} - {ep_name}")
            # Fallback to season name
            if season_str:
                return esc(f"{series} - {season_str} - {ep_name}")
            return esc(f"{series} - {ep_name}")
        # Movie or other
        return esc(item.get("Name") or "Unknown")

    def on_start_item(self, item, out_path):
        name = self._display_name(item)
        resp = send_telegram(f"Starting: {name}")
        if resp and resp.get("ok") and resp.get("result"):
            mid = resp["result"]["message_id"]
            self.message_ids[self._key(item)] = mid

    def on_progress(self, item, out_path, bytes_written, total_bytes):
        mid = self.message_ids.get(self._key(item))
        if not mid or not total_bytes:
            return
        pct = int(100 * bytes_written / total_bytes)
        text = f"Downloading: {self._display_name(item)}\n{pct}% ({bytes_written/1024/1024:.1f} MB / {total_bytes/1024/1024:.1f} MB)"
        edit_telegram(mid, text)

    def on_done(self, item, out_path):
        mid = self.message_ids.get(self._key(item))
        text = f"Completed: {self._display_name(item)}"
        if mid:
            edit_telegram(mid, text)
        else:
            send_telegram(text)

    def on_skip(self, item, reason):
        mid = self.message_ids.get(self._key(item))
        text = f"Skipped: {self._display_name(item)}"
        if mid:
            edit_telegram(mid, text)
        else:
            send_telegram(text)

    def on_error(self, item, error):
        send_telegram(f"Error: {self._display_name(item)}\n{esc(error)}")

def esc(s: str) -> str:
    s = str(s)
    return s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')

def notify_start():
    send_telegram("🚀 <b>Emby sync started</b>\n")

def notify_success():
    send_telegram("✅ <b>Emby sync finished successfully</b>")

def notify_failure(details: str):
    send_telegram(f"❌ <b>Emby sync failed</b>\n<pre>{esc(details)}</pre>", parse_mode="HTML")

def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--config", dest="config_path", help="Path to YAML config file")
    return p.parse_args()

def main() -> int:    
    try:
        args = parse_args()
        if args.config_path:
            os.environ["CONFIG_PATH"] = args.config_path  # notify.py and sync read this
        
        #notify_start()
        reporter = TelegramReporter()
        sync_main(reporter=reporter)
        #notify_success()
        return 0
    except SystemExit as se:
        code = int(getattr(se, 'code', 0) or 0)
        if code == 0:
            #notify_success()
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
