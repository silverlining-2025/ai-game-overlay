"""Extract frames from gameplay videos and deduplicate.

Usage:
    python -m backend.tools.extract_frames --input training_data/palworld/youtube --output training_data/palworld/frames

Requirements:
    pip install imagehash Pillow
    ffmpeg must be installed and on PATH
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import logging
from pathlib import Path

try:
    import imagehash
    from PIL import Image
except ImportError:
    print("ERROR: Required packages not installed. Run: pip install imagehash Pillow")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Extract 1 frame every N seconds
EXTRACT_INTERVAL_SEC = 2

# Output frame dimensions
FRAME_WIDTH = 640
FRAME_HEIGHT = 360

# Perceptual hash hamming distance threshold — below this = duplicate
HASH_DISTANCE_THRESHOLD = 8


def _check_ffmpeg() -> str:
    """Return path to ffmpeg or exit if not found."""
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        log.error("ffmpeg not found on PATH. Please install ffmpeg first.")
        log.error("  Windows: winget install ffmpeg  /  choco install ffmpeg")
        sys.exit(1)
    return ffmpeg


def _extract_frames_from_video(
    ffmpeg: str,
    video_path: Path,
    tmp_dir: Path,
    fps: float,
    width: int,
    height: int,
) -> list[Path]:
    """Run ffmpeg to extract frames from a single video into tmp_dir.

    Returns list of extracted frame paths.
    """
    # Output pattern: frame_00001.jpg, frame_00002.jpg, ...
    out_pattern = str(tmp_dir / "frame_%05d.jpg")

    cmd = [
        ffmpeg,
        "-i", str(video_path),
        "-vf", f"fps={fps},scale={width}:{height}",
        "-q:v", "2",  # JPEG quality (2 = high)
        "-y",  # overwrite
        out_pattern,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min max per video
        )
        if result.returncode != 0:
            log.warning("    ffmpeg error for %s: %s", video_path.name, result.stderr[-200:] if result.stderr else "unknown")
            return []
    except subprocess.TimeoutExpired:
        log.warning("    ffmpeg timed out for %s", video_path.name)
        return []
    except FileNotFoundError:
        log.error("ffmpeg not found at %s", ffmpeg)
        return []

    frames = sorted(tmp_dir.glob("frame_*.jpg"))
    return frames


def _compute_hash(frame_path: Path) -> imagehash.ImageHash | None:
    """Compute perceptual hash for a frame."""
    try:
        with Image.open(frame_path) as img:
            return imagehash.phash(img)
    except Exception as e:
        log.warning("    Could not hash %s: %s", frame_path.name, e)
        return None


def _deduplicate_frames(
    frame_paths: list[Path],
    threshold: int = HASH_DISTANCE_THRESHOLD,
) -> list[Path]:
    """Remove near-duplicate frames using perceptual hashing.

    Returns list of unique frame paths.
    """
    if not frame_paths:
        return []

    kept: list[tuple[Path, imagehash.ImageHash]] = []

    for fp in frame_paths:
        h = _compute_hash(fp)
        if h is None:
            continue

        is_dup = False
        for _, existing_hash in kept:
            if h - existing_hash < threshold:
                is_dup = True
                break

        if not is_dup:
            kept.append((fp, h))

    return [fp for fp, _ in kept]


def process_state(
    state: str,
    state_video_dir: Path,
    output_dir: Path,
    ffmpeg: str,
    fps: float,
    width: int,
    height: int,
    threshold: int,
) -> dict:
    """Process all videos for a single game state.

    Returns stats dict with total_extracted, after_dedup counts.
    """
    state_output = output_dir / state
    state_output.mkdir(parents=True, exist_ok=True)

    videos = sorted(
        [f for f in state_video_dir.iterdir() if f.suffix.lower() in (".mp4", ".mkv", ".webm", ".avi")]
    )

    if not videos:
        log.info("  No videos found in %s", state_video_dir)
        return {"total_extracted": 0, "after_dedup": 0}

    log.info("  Found %d video(s)", len(videos))

    all_extracted: list[Path] = []

    for vid in videos:
        log.info("    Extracting frames from: %s", vid.name)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            frames = _extract_frames_from_video(ffmpeg, vid, tmp_path, fps, width, height)
            log.info("      Extracted %d raw frames", len(frames))

            # Move extracted frames to a staging area so we can dedup across all videos
            for f in frames:
                # Use a globally unique name to avoid collisions
                dest = state_output / f"_tmp_{vid.stem}_{f.name}"
                shutil.copy2(str(f), str(dest))
                all_extracted.append(dest)

    total_extracted = len(all_extracted)
    log.info("  Total raw frames: %d — deduplicating (threshold=%d)...", total_extracted, threshold)

    unique = _deduplicate_frames(all_extracted, threshold)
    log.info("  Unique frames after dedup: %d (removed %d duplicates)", len(unique), total_extracted - len(unique))

    # Rename unique frames to clean sequential names, remove temp files
    unique_set = set(str(p) for p in unique)

    # First, rename uniques
    final_paths: list[Path] = []
    for idx, fp in enumerate(unique, 1):
        final_name = state_output / f"frame_{idx:05d}.jpg"
        shutil.move(str(fp), str(final_name))
        final_paths.append(final_name)

    # Remove non-unique temp files
    for fp in all_extracted:
        if str(fp) not in unique_set and fp.exists():
            fp.unlink()

    return {"total_extracted": total_extracted, "after_dedup": len(final_paths)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract frames from gameplay videos and deduplicate."
    )
    parser.add_argument(
        "--input",
        type=str,
        default="training_data/palworld/youtube",
        help="Input directory containing state subdirectories with videos (default: training_data/palworld/youtube)",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="training_data/palworld/frames",
        help="Output directory for extracted frames (default: training_data/palworld/frames)",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=1.0 / EXTRACT_INTERVAL_SEC,
        help=f"Frames per second to extract (default: {1.0 / EXTRACT_INTERVAL_SEC} = 1 frame every {EXTRACT_INTERVAL_SEC}s)",
    )
    parser.add_argument(
        "--width",
        type=int,
        default=FRAME_WIDTH,
        help=f"Output frame width (default: {FRAME_WIDTH})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=FRAME_HEIGHT,
        help=f"Output frame height (default: {FRAME_HEIGHT})",
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=HASH_DISTANCE_THRESHOLD,
        help=f"Perceptual hash hamming distance threshold for dedup (default: {HASH_DISTANCE_THRESHOLD})",
    )
    parser.add_argument(
        "--states",
        type=str,
        nargs="*",
        default=None,
        help="Only process specific states (default: all found subdirectories)",
    )
    args = parser.parse_args()

    ffmpeg = _check_ffmpeg()
    input_dir = Path(args.input)
    output_dir = Path(args.output)

    if not input_dir.exists():
        log.error("Input directory does not exist: %s", input_dir.resolve())
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    # Discover state subdirectories
    all_states = sorted([d.name for d in input_dir.iterdir() if d.is_dir() and not d.name.startswith("_")])

    if args.states:
        invalid = [s for s in args.states if s not in all_states]
        if invalid:
            log.error("States not found in input: %s", invalid)
            log.info("Available states: %s", all_states)
            sys.exit(1)
        states = args.states
    else:
        states = all_states

    if not states:
        log.error("No state subdirectories found in %s", input_dir.resolve())
        sys.exit(1)

    log.info("=== Frame Extraction Pipeline ===")
    log.info("Input:     %s", input_dir.resolve())
    log.info("Output:    %s", output_dir.resolve())
    log.info("FPS:       %.2f (1 frame every %.1fs)", args.fps, 1.0 / args.fps)
    log.info("Size:      %dx%d", args.width, args.height)
    log.info("Threshold: %d", args.threshold)
    log.info("States:    %d", len(states))
    print()

    grand_total = 0
    grand_dedup = 0

    for i, state in enumerate(states, 1):
        log.info("[%d/%d] Processing state: %s", i, len(states), state)
        stats = process_state(
            state=state,
            state_video_dir=input_dir / state,
            output_dir=output_dir,
            ffmpeg=ffmpeg,
            fps=args.fps,
            width=args.width,
            height=args.height,
            threshold=args.threshold,
        )
        grand_total += stats["total_extracted"]
        grand_dedup += stats["after_dedup"]
        print()

    log.info("=== Summary ===")
    log.info("Total raw frames extracted: %d", grand_total)
    log.info("After deduplication:        %d", grand_dedup)
    log.info("Duplicates removed:         %d (%.1f%%)",
             grand_total - grand_dedup,
             (100.0 * (grand_total - grand_dedup) / grand_total) if grand_total else 0)
    print()

    # Per-state breakdown
    log.info("Per-state breakdown:")
    for state in states:
        state_dir = output_dir / state
        if state_dir.exists():
            count = len(list(state_dir.glob("frame_*.jpg")))
            log.info("  %-25s %d frames", state, count)
        else:
            log.info("  %-25s 0 frames", state)


if __name__ == "__main__":
    main()
