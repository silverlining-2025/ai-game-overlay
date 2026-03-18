"""Download YouTube gameplay videos for training data collection.

Usage:
    python -m backend.tools.download_videos --game palworld --output training_data/palworld/youtube

Requirements:
    pip install yt-dlp
"""

import argparse
import os
import sys
import json
import logging
from pathlib import Path

try:
    import yt_dlp
except ImportError:
    print("ERROR: yt-dlp is not installed. Run: pip install yt-dlp")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Per-game search queries keyed by game state
# ---------------------------------------------------------------------------

GAME_QUERIES = {
    "palworld": {
        "combat": ["palworld combat gameplay", "palworld fighting wild pals"],
        "boss_fight": ["palworld boss fight gameplay", "palworld tower boss fight", "palworld alpha boss"],
        "capturing": ["palworld pal capture sphere", "palworld catching pals"],
        "exploring": ["palworld exploration walkthrough"],
        "mounted_flying": ["palworld flying mount gameplay"],
        "mounted_ground": ["palworld riding mount"],
        "gathering": ["palworld mining logging resources"],
        "dungeon": ["palworld dungeon run"],
        "building": ["palworld base building tutorial"],
        "base_view": ["palworld base tour"],
        "crafting_menu": ["palworld crafting guide workbench"],
        "inventory": ["palworld inventory management"],
        "pal_management": ["palworld palbox management"],
        "technology_tree": ["palworld technology tree guide"],
        "map_screen": ["palworld map fast travel"],
        "merchant_shop": ["palworld merchant shop"],
        "breeding_condenser": ["palworld breeding farm guide", "palworld condenser"],
        "death_respawn": ["palworld death game over"],
        "loading_screen": ["palworld loading screen"],
        "character_creation": ["palworld character creation"],
        "title_screen": ["palworld title screen main menu"],
        "cutscene_notification": ["palworld level up notification"],
        "dialogue_interaction": ["palworld npc dialogue quest"],
        "world_select": ["palworld world select save"],
        "settings_menu": ["palworld settings options menu"],
    },
}

# How many videos to download per search query
MAX_RESULTS_PER_QUERY = 3

# Maximum video duration in seconds (10 minutes)
MAX_DURATION_SEC = 600

# Target resolution height
TARGET_HEIGHT = 720


def _progress_hook(d: dict) -> None:
    """yt-dlp progress callback."""
    if d["status"] == "downloading":
        pct = d.get("_percent_str", "??%").strip()
        speed = d.get("_speed_str", "??").strip()
        print(f"\r  Downloading: {pct}  {speed}   ", end="", flush=True)
    elif d["status"] == "finished":
        print("\r  Download complete, post-processing...         ")


def _build_ydl_opts(output_template: str) -> dict:
    """Return yt-dlp option dict for search + download."""
    return {
        "format": f"bestvideo[height<={TARGET_HEIGHT}]+bestaudio/best[height<={TARGET_HEIGHT}]/best",
        "merge_output_format": "mp4",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress_hook],
        "match_filter": yt_dlp.utils.match_filter_func(f"duration < {MAX_DURATION_SEC}"),
        "ignoreerrors": True,
        "noplaylist": True,
    }


def _manifest_path(output_dir: Path) -> Path:
    return output_dir / "_downloaded.json"


def _load_manifest(output_dir: Path) -> dict:
    """Load the manifest that tracks which video IDs have been downloaded."""
    p = _manifest_path(output_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_manifest(output_dir: Path, manifest: dict) -> None:
    p = _manifest_path(output_dir)
    p.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _next_video_index(state_dir: Path) -> int:
    """Find the next available video index in a state directory."""
    existing = list(state_dir.glob("video_*.mp4"))
    if not existing:
        return 1
    indices = []
    for f in existing:
        try:
            indices.append(int(f.stem.split("_")[1]))
        except (IndexError, ValueError):
            continue
    return max(indices, default=0) + 1


def download_for_state(
    state: str,
    queries: list[str],
    output_dir: Path,
    manifest: dict,
    max_per_query: int = MAX_RESULTS_PER_QUERY,
) -> int:
    """Download videos for a single game state. Returns count of new downloads."""
    state_dir = output_dir / state
    state_dir.mkdir(parents=True, exist_ok=True)

    downloaded_ids = set(manifest.get(state, []))
    new_count = 0
    vid_index = _next_video_index(state_dir)

    for query in queries:
        log.info("  Searching: %s", query)
        search_query = f"ytsearch{max_per_query}:{query}"

        # First pass: extract info to get video IDs
        extract_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "ignoreerrors": True,
            "noplaylist": True,
        }
        try:
            with yt_dlp.YoutubeDL(extract_opts) as ydl:
                result = ydl.extract_info(search_query, download=False)
        except Exception as e:
            log.warning("    Search failed for '%s': %s", query, e)
            continue

        if not result or "entries" not in result:
            log.warning("    No results for '%s'", query)
            continue

        entries = [e for e in result["entries"] if e is not None]
        log.info("    Found %d candidate videos", len(entries))

        for entry in entries:
            video_id = entry.get("id", "")
            title = entry.get("title", "unknown")

            if video_id in downloaded_ids:
                log.info("    Skipping (already downloaded): %s", title)
                continue

            out_path = str(state_dir / f"video_{vid_index:03d}.mp4")
            dl_opts = _build_ydl_opts(out_path)

            video_url = entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"
            log.info("    Downloading [%s]: %s", video_id, title)

            try:
                with yt_dlp.YoutubeDL(dl_opts) as ydl:
                    ydl.download([video_url])
            except Exception as e:
                log.warning("    Failed to download '%s': %s", title, e)
                continue

            # Verify file was actually created (match_filter may have skipped it)
            if os.path.exists(out_path):
                downloaded_ids.add(video_id)
                manifest.setdefault(state, []).append(video_id)
                vid_index += 1
                new_count += 1
                log.info("    Saved: %s", out_path)
            else:
                log.info("    Skipped (too long or unavailable): %s", title)

    return new_count


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download YouTube gameplay videos for training data collection."
    )
    parser.add_argument(
        "--game",
        type=str,
        default="palworld",
        choices=list(GAME_QUERIES.keys()),
        help="Game to download videos for (default: palworld)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="training_data/palworld/youtube",
        help="Output directory for downloaded videos (default: training_data/palworld/youtube)",
    )
    parser.add_argument(
        "--states",
        type=str,
        nargs="*",
        default=None,
        help="Only download for specific states (default: all)",
    )
    parser.add_argument(
        "--max-per-query",
        type=int,
        default=MAX_RESULTS_PER_QUERY,
        help=f"Max videos to download per search query (default: {MAX_RESULTS_PER_QUERY})",
    )
    args = parser.parse_args()

    queries = GAME_QUERIES[args.game]
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    states = args.states if args.states else list(queries.keys())
    invalid = [s for s in states if s not in queries]
    if invalid:
        log.error("Unknown states for %s: %s", args.game, invalid)
        log.info("Available states: %s", list(queries.keys()))
        sys.exit(1)

    manifest = _load_manifest(output_dir)
    total_new = 0

    log.info("=== Downloading %s videos ===", args.game)
    log.info("Output directory: %s", output_dir.resolve())
    log.info("States to process: %d", len(states))
    print()

    for i, state in enumerate(states, 1):
        log.info("[%d/%d] State: %s (%d queries)", i, len(states), state, len(queries[state]))
        count = download_for_state(
            state, queries[state], output_dir, manifest, args.max_per_query
        )
        total_new += count
        _save_manifest(output_dir, manifest)
        log.info("  -> %d new videos for '%s'", count, state)
        print()

    log.info("=== Done! %d new videos downloaded ===", total_new)


if __name__ == "__main__":
    main()
