"""
emby_favorites_sync.py

Downloads Movies and TV Episodes marked as Favorite in Emby,
checking a local folder first and only downloading missing items.

Features
- Fetch favorites for a user: Movies, Series, Episodes
- For favorited Series, fetch all episodes for that series or just the latest season
- Resolve original file via PlaybackInfo (MediaSources/Path)
- Direct-stream download (no transcoding) with /Videos/{Id}/stream?static=true
- Emby-friendly local naming: 
    Movies:  {Title} ({Year}).{ext}
    TV:      {Series} ({Year})/Season {SS}/{Series} S{SS}E{EE} - {Episode}.{ext}
- Dry-run mode to preview actions

Auth
- Emby API key in 'X-Emby-Token' header (or ?api_key=)
"""

import argparse
import json
import os
import re
import random
import string
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml 
import requests
from typing import Protocol, Any
from contextlib import suppress

# Try to use tqdm if available, otherwise fall back to a simple text progress
try:
    from tqdm import tqdm
    HAS_TQDM = True
except Exception:
    HAS_TQDM = False

class Reporter(Protocol):
    def on_start_item(self, item: Dict, out_path: Path) -> None: ...
    def on_progress(self, item: Dict, out_path: Path, bytes_written: int, total_bytes: Optional[int]) -> None: ...
    def on_done(self, item: Dict, out_path: Path) -> None: ...
    def on_skip(self, item: Dict, reason: str) -> None: ...
    def on_error(self, item: Dict, error: Exception) -> None: ...

# Provide a no-op default reporter
class NullReporter:
    def on_start_item(self, item: Dict, out_path: Path) -> None: pass
    def on_progress(self, item: Dict, out_path: Path, bytes_written: int, total_bytes: Optional[int]) -> None: pass
    def on_done(self, item: Dict, out_path: Path) -> None: pass
    def on_skip(self, item: Dict, reason: str) -> None: pass
    def on_error(self, item: Dict, error: Exception) -> None: pass


# --------- Helpers ---------
def slugify_filename(name: str) -> str:
    # Remove filesystem-unfriendly chars but keep readable names
    return re.sub(r'[\\/:*?"<>|]+', '', name).strip()

def play_session_id() -> str:
    return ''.join(random.choices(string.ascii_letters + string.digits, k=16))

def ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def choose_best_media_source(sources: List[Dict]) -> Optional[Dict]:
    """
    Heuristic: prefer highest resolution, then bitrate, then size.
    """
    if not sources:
        return None
    def key(s):
        return (s.get("Width", 0), s.get("Bitrate", 0), s.get("Size", 0))
    return sorted(sources, key=key, reverse=True)[0]

def guess_extension_from_source(source: Dict, fallback: str = "mkv") -> str:
    # Prefer file extension from Path, else Container
    path = source.get("Path") or ""
    ext = Path(path).suffix.lstrip(".")
    if ext:
        return ext
    cont = source.get("Container")
    return (cont or fallback).lower()

# --------- Emby API Client ---------
class EmbyClient:
    def __init__(self, base_url: str, api_key: str, user_id: str, timeout: int = 30):
        # Accept both forms: with/without trailing '/emby'
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.user_id = user_id
        self.timeout = timeout
        self.sess = requests.Session()
        self.sess.headers.update({"X-Emby-Token": api_key})
    
    def _url(self, path: str) -> str:
        # If base_url already includes '/emby', use direct; otherwise append.
        if self.base_url.endswith("/emby"):
            return f"{self.base_url}{path}"
        return f"{self.base_url}/emby{path}"

    def get(self, path: str, params: Optional[Dict] = None) -> requests.Response:
        params = dict(params or {})
        # Add api_key also as a query for compatibility with some setups
        params.setdefault("api_key", self.api_key)
        r = self.sess.get(self._url(path), params=params, timeout=self.timeout)
        r.raise_for_status()
        return r

    def stream_get(self, path: str, params: Optional[Dict] = None) -> requests.Response:
        params = dict(params or {})
        params.setdefault("api_key", self.api_key)
        r = self.sess.get(self._url(path), params=params, stream=True, timeout=self.timeout)
        r.raise_for_status()
        return r

    # Favorites for Movies/Series/Episodes
    def get_favorites(self, include_types: List[str]) -> List[Dict]:
        params = {
            "Recursive": True,
            #"IncludeItemTypes": ",".join(include_types),
            "IsFavorite": True,
            "UserId": self.user_id,
            # Extra fields to help naming
            "Fields": "Path,ProductionYear,ParentId,IndexNumber,ParentIndexNumber,SeriesName,MediaSources"
        }

        # Add filter only if non-empty
        if include_types:
            params["IncludeItemTypes"] = ",".join(include_types)

        resp = self.get(f"/Users/{self.user_id}/Items", params=params)
        return resp.json().get("Items", [])

    # Episodes for a given Series
    def get_series_episodes(self, series_id: str) -> List[Dict]:
        # Prefer Shows/{Id}/Episodes for clarity; add fields for naming
        params = {
            "UserId": self.user_id,
            "Fields": "Path,IndexNumber,ParentIndexNumber,SeriesName,ProductionYear"
        }
        resp = self.get(f"/Shows/{series_id}/Episodes", params=params)
        return resp.json().get("Items", [])

    # PlaybackInfo to retrieve MediaSources (and the file Path)
    def get_playback_info(self, item_id: str) -> Dict:
        params = {
            "UserId": self.user_id
        }
        resp = self.get(f"/Items/{item_id}/PlaybackInfo", params=params)
        return resp.json()
    
    # Direct stream download (static=true)
    def direct_stream(self, item_id: str, media_source_id: str, session_id: str) -> requests.Response:
        params = {
            "static": "true",
            "MediaSourceId": media_source_id,
            "PlaySessionId": session_id
        }
        # Use /Videos/{Id}/stream; Emby also supports /Video/{Id}/stream
        return self.stream_get(f"/Videos/{item_id}/stream", params=params)
    
    def get_series_seasons(self, series_id: str) -> list[dict]:
        """
        Returns a list of season items for a series.
        Each item typically has: Type='Season', IndexNumber=<int>, Id=<guid>, Name, etc.
        """
        params = {
            "UserId": self.user_id,
            # We may include fields if we need more detail later
            "Fields": "IndexNumber,ProductionYear"
        }
        resp = self.get(f"/Shows/{series_id}/Seasons", params=params)
        return resp.json().get("Items", [])

# --------- Naming & Destination ---------
def movie_dest(item: Dict, dest_root: Path, ext: str) -> Path:
    title = slugify_filename(item.get("Name", "Unknown"))
    year = item.get("ProductionYear")
    folder = f"{title} ({year})" if year else title
    folder_path = dest_root / "Movies" / folder
    ensure_dir(folder_path)
    return folder_path / f"{folder}.{ext}"

def episode_dest(item: Dict, dest_root: Path, ext: str) -> Path:
    series = slugify_filename(item.get("SeriesName") or item.get("Name") or "Unknown Series")
    year = item.get("ProductionYear")
    series_folder = f"{series} ({year})" if year else series
    season_num = item.get("ParentIndexNumber") or 0
    ep_num = item.get("IndexNumber") or 0
    season_folder = dest_root / "TV" / series_folder / f"Season {season_num:02d}"
    ensure_dir(season_folder)
    ep_title = slugify_filename(item.get("Name", "Episode"))
    filename = f"{series} S{season_num:02d}E{ep_num:02d} - {ep_title}.{ext}"
    return season_folder / filename

def resolve_best_source_and_ext(client: EmbyClient, item: Dict) -> Tuple[Optional[Dict], str]:
    # Try fields from list call first; if not enough, query PlaybackInfo
    sources_from_list = item.get("MediaSources") or []
    if sources_from_list:
        src = choose_best_media_source(sources_from_list)
        return src, guess_extension_from_source(src)
    pb = client.get_playback_info(item["Id"])
    src = choose_best_media_source(pb.get("MediaSources", []))
    ext = guess_extension_from_source(src or {}, "mkv")
    return src, ext

# --------- Core workflow ---------
def collect_items_to_download(
    client: EmbyClient,
    include_movies: bool,
    include_tv: bool,
    latest_season_only: bool = False
) -> List[Dict]:
    include_types = []
    if include_movies:
        include_types.append("Movie")
    if include_tv:
        include_types.extend(["Series", "Episode"])

    favorites = client.get_favorites(include_types=include_types)

    items: List[Dict] = []
    for it in favorites:
        t = it.get("Type")

        if t == "Series":
            if not include_tv:
                continue

            if latest_season_only:
                # 1) Get all seasons
                seasons = client.get_series_seasons(series_id=it["Id"])
                if not seasons:
                    # fallback: no seasons found, try all episodes (or skip)
                    eps = client.get_series_episodes(series_id=it["Id"])
                    items.extend(eps)
                    continue

                # 2) Choose latest season
                #    - Prefer max IndexNumber
                #    - Skip season 0 (Specials) unless it’s the only season
                def season_sort_key(s):
                    # If IndexNumber is None, treat as -1 so it won't win
                    idx = s.get("IndexNumber", -1)
                    return idx

                # Filter out "Specials" (season 0) when there are other seasons
                non_specials = [s for s in seasons if (s.get("IndexNumber") or 0) > 0]
                candidate_pool = non_specials if non_specials else seasons
                latest = sorted(candidate_pool, key=season_sort_key, reverse=True)[0]

                # 3) Fetch episodes only for that season
                eps = client.get_series_episodes(series_id=it["Id"])
                # If the endpoint is heavy, prefer SeasonId param:
                # eps = client.get(f"/Shows/{it['Id']}/Episodes", 
                #                  params={"UserId": client.user_id, "SeasonId": latest["Id"]}).json().get("Items", [])
                # The method overloading above would require a new client helper; for now filter:
                season_id = latest.get("Id")
                # Efficient path: call the endpoint with SeasonId. Since we did not add a dedicated method,
                # let’s do it inline:
                resp = client.get(f"/Shows/{it['Id']}/Episodes", params={
                    "UserId": client.user_id,
                    "SeasonId": season_id,
                    "Fields": "Path,IndexNumber,ParentIndexNumber,SeriesName,ProductionYear"
                })
                eps = resp.json().get("Items", [])

                items.extend(eps)

            else:
                # Original behavior: all episodes from the series
                eps = client.get_series_episodes(series_id=it["Id"])
                items.extend(eps)

        else:
            # Movie or Episode already favorited directly
            items.append(it)

    # Deduplicate by Id
    dedup = {}
    for it in items:
        dedup[it["Id"]] = it
    return list(dedup.values())


def download_missing(
    client: EmbyClient,
    items: List[Dict],
    dest_root: Path,
    dry_run: bool = False,
    reporter: Optional[Reporter] = None
) -> Dict[str, Any]:
    reporter = reporter or NullReporter()
    skipped, downloaded = 0, 0
    results_downloaded: list[str] = []
    results_skipped: list[str] = []

    for it in items:
        item_type = it.get("Type")
        src, ext = resolve_best_source_and_ext(client, it)
        if not src:
            msg = f"No media source for {it.get('Name')} ({item_type})"
            print(f"[WARN] {msg}. Skipping.")
            results_skipped.append(msg)
            skipped += 1
            #reporter.on_skip(it, msg)
            continue

        # Choose destination
        if item_type == "Movie":
            out_path = movie_dest(it, dest_root, ext)
        else:
            out_path = episode_dest(it, dest_root, ext)

        if out_path.exists():
            msg = f"Exists: {out_path}"
            print(f"[SKIP] {msg}")
            results_skipped.append(msg)
            skipped += 1
            #reporter.on_skip(it, msg)
            continue

        if dry_run:
            print(f"[DRY] Would download: {it.get('Name')} -> {out_path}")
            downloaded += 1
            results_downloaded.append(str(out_path))
            #reporter.on_skip(it, "dry-run")
            continue

        # Stream download
        sess_id = play_session_id()
        tmp_path = out_path.with_suffix(out_path.suffix + ".part")
        try:
            resp = client.direct_stream(item_id=it["Id"], media_source_id=src.get("Id", ""), session_id=sess_id)

            # Try to get total size for progress
            total_bytes = None
            with suppress(Exception):
                cl = resp.headers.get("Content-Length")
                if cl is not None:
                    total_bytes = int(cl)

            reporter.on_start_item(it, out_path)

            chunk_size = 64 * 1024 * 1024  # 64 MiB
            written = 0

            if HAS_TQDM and total_bytes:
                # tqdm progress bar
                from tqdm import tqdm
                with open(tmp_path, "wb") as f, tqdm(
                    total=total_bytes,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=f"{out_path.name}",
                    miniters=1,
                    leave=True,
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            pbar.update(len(chunk))
                            reporter.on_progress(it, out_path, written, total_bytes)
            else:
                # Simple loop with periodic reporting
                next_report = 0
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            written += len(chunk)
                            if total_bytes:
                                percent = int(100 * written / total_bytes)
                                if percent >= next_report:
                                    print(f"  ... {percent}% ({written/1024/1024:.1f} MB / { (total_bytes or 1)/1024/1024:.1f} MB)")
                                    reporter.on_progress(it, out_path, written, total_bytes)
                                    next_report = min(percent + 5, 100)  # every ~5%
                            else:
                                # Unknown total: report every 100 MB
                                if (written // (100 * 1024 * 1024)) > next_report:
                                    next_report = written // (100 * 1024 * 1024)
                                    print(f"  ... {written/1024/1024:.1f} MB downloaded")
                                    reporter.on_progress(it, out_path, written, total_bytes)

                            #reporter.on_progress(it, out_path, written, total_bytes)

            os.replace(tmp_path, out_path)
            print(f"[OK] Downloaded: {out_path}")
            downloaded += 1
            results_downloaded.append(str(out_path))
            reporter.on_done(it, out_path)

        except Exception as e:
            print(f"[ERR] Failed downloading {it.get('Name')}: {e}")
            results_skipped.append(f"Fail {it.get('Name')}: {e}")
            skipped += 1
            reporter.on_error(it, e)
            with suppress(Exception):
                if tmp_path.exists():
                    tmp_path.unlink()

    summary = {"downloaded": downloaded, "skipped": skipped, "total": len(items),
               "downloaded_paths": results_downloaded, "skipped_details": results_skipped}
    print(f"\nSummary: downloaded={downloaded}, skipped={skipped}, total={len(items)}")
    return summary


# ---------- YAML config loader ----------
def load_config(config_path: Optional[str]) -> Dict:
    """
    Load config from YAML file:
    Returns normalized dict:
        {
          "emby_server": str,
          "emby_api_key": str,
          "emby_user_id": str,
          "dest_dir": str,
          "content": str,                  # "movies" | "tv" | "both"
          "latest_season_only": bool,
          "dry_run": bool
        }
    """

    # Resolve config path:
    cp = config_path or os.environ.get("CONFIG_PATH") or "./config/emby-sync.yml"
    cfg_file = Path(cp)
    if not cfg_file.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_file}")

    with cfg_file.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    emby = raw.get("emby", {}) or {}
    sync = raw.get("sync", {}) or {}

    # normalize & defaults
    emby_server = str(emby.get("server", "")).strip()
    emby_api_key = str(emby.get("api_key", "")).strip()
    emby_user_id = str(emby.get("user_id", "")).strip()

    dest_dir = str(sync.get("dest_dir", "./downloads")).strip()
    content = str(sync.get("content", "tv")).strip().lower()
    latest_season_only = bool(sync.get("latest_season_only", False))
    dry_run = bool(sync.get("dry_run", False))

    if content not in ("movies", "tv", "both"):
        raise ValueError(f"Invalid value for sync.content: {content} (expected: movies|tv|both)")

    for key, val in (("emby.server", emby_server), ("emby.api_key", emby_api_key), ("emby.user_id", emby_user_id)):
        if not val:
            raise ValueError(f"Missing required config key: {key}")

    return {
        "emby_server": emby_server,
        "emby_api_key": emby_api_key,
        "emby_user_id": emby_user_id,
        "dest_dir": dest_dir,
        "content": content,
        "latest_season_only": latest_season_only,
        "dry_run": dry_run,
    }

def main(reporter: Optional[Reporter] = None):
    ap = argparse.ArgumentParser(description="Download Emby favorites to local storage (YAML-configured).")
    ap.add_argument("--config", help="Path to YAML config (overrides CONFIG_PATH/env).")
    # Optional CLI overrides (helpful for quick tests):
    ap.add_argument("--server", help="Override emby.server")
    ap.add_argument("--api-key", help="Override emby.api_key")
    ap.add_argument("--user-id", help="Override emby.user_id")
    ap.add_argument("--dest", help="Override sync.dest_dir")
    ap.add_argument("--content", choices=["movies", "tv", "both"], help="Override sync.content")
    ap.add_argument("--latest-season-only", action="store_true", help="Override sync.latest_season_only=True")
    ap.add_argument("--dry-run", action="store_true", help="Override sync.dry_run=True")
    args = ap.parse_args()

    cfg = load_config(args.config)  

    # Apply CLI overrides (if provided)
    if args.server: cfg["emby_server"] = args.server
    if args.api_key: cfg["emby_api_key"] = args.api_key
    if args.user_id: cfg["emby_user_id"] = args.user_id
    if args.dest: cfg["dest_dir"] = args.dest
    if args.content: cfg["content"] = args.content
    if args.latest_season_only: cfg["latest_season_only"] = True
    if args.dry_run: cfg["dry_run"] = True

    # Decide what to include based on 'content'
    include_movies = cfg["content"] in ("movies", "both")
    include_tv     = cfg["content"] in ("tv", "both")

    dest_root = Path(cfg["dest_dir"]).resolve()
    ensure_dir(dest_root)

    client = EmbyClient(
        base_url=cfg["emby_server"],
        api_key=cfg["emby_api_key"],
        user_id=cfg["emby_user_id"]
    )

    items = collect_items_to_download(
        client,
        include_movies=include_movies,
        include_tv=include_tv,
        latest_season_only=cfg["latest_season_only"]
    )

    print(f"Found {len(items)} items to consider.")
    summary = download_missing(client, items, dest_root, dry_run=cfg["dry_run"], reporter=reporter)
    # Optional: write JSON summary to a state file for runner/entrypoint logging
    with suppress(Exception):
        state_dir = Path(os.environ.get("STATE_DIR", "/app/state"))
        ensure_dir(state_dir)
        (state_dir / "last_result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
