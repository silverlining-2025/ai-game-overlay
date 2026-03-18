"""Auto-label game screenshots using CLIP zero-shot and optional Claude Vision.

Usage:
    python -m backend.tools.auto_label --input training_data/palworld/frames --output training_data/palworld/auto_labeled
    python -m backend.tools.auto_label --input training_data/palworld/frames --use-claude  # uses Claude Vision API too
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Claude Vision prompt — asks for a single label from the 26-label taxonomy
CLAUDE_PROMPT = (
    "이 게임 스크린샷의 상태를 분류해: "
    "combat, capturing, boss_fight, exploring, mounted_ground, mounted_flying, "
    "gathering, dungeon, building, base_view, crafting_menu, inventory, "
    "pal_management, technology_tree, map_screen, merchant_shop, "
    "breeding_condenser, settings_menu, loading_screen, death_respawn, "
    "cutscene_notification, dialogue_interaction, character_creation, "
    "world_select, title_screen, external_app. 라벨만 출력해."
)


def _collect_frames(input_dir: Path) -> list[Path]:
    """Recursively collect all .jpg frames from input directory."""
    extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    frames = []
    for ext in extensions:
        frames.extend(input_dir.rglob(f"*{ext}"))
    frames.sort()
    return frames


def _load_classifier():
    """Load CLIP zero-shot classifier."""
    try:
        from backend.cv.game_classifier import GameClassifier

        clf = GameClassifier()
        clf._load()
        if clf.mode == "none":
            print("WARNING: CLIP classifier failed to load (mode=none).")
            return None
        print(f"CLIP classifier loaded (mode={clf.mode}, {len(clf.class_names)} classes).")
        return clf
    except Exception as e:
        print(f"ERROR: Could not load CLIP classifier: {e}")
        return None


def _classify_frame(clf, img_path: Path) -> dict:
    """Run CLIP zero-shot classification on a single frame.

    Returns dict with clip_label, clip_confidence, clip_top3.
    """
    import numpy as np
    from PIL import Image

    img = Image.open(img_path).convert("RGB")
    frame = np.array(img)

    top3 = clf.classify_top_k(frame, k=3)
    label, confidence = top3[0]

    return {
        "clip_label": label,
        "clip_confidence": round(confidence, 4),
        "clip_top3": [
            {"label": lbl, "confidence": round(conf, 4)} for lbl, conf in top3
        ],
    }


def _load_api_key() -> str | None:
    """Load Anthropic API key from backend/.env or environment."""
    # Check environment first
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key:
        return key

    # Try loading from backend/.env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("ANTHROPIC_API_KEY="):
                return line.split("=", 1)[1].strip()

    return None


def _classify_with_claude(img_path: Path, api_key: str, max_retries: int = 5) -> str | None:
    """Send a frame to Claude Haiku Vision for classification.

    Returns the label string or None on failure.
    Handles rate limits with exponential backoff.
    """
    import httpx

    # Read and encode image
    img_bytes = img_path.read_bytes()
    b64_img = base64.b64encode(img_bytes).decode("utf-8")

    # Determine media type
    suffix = img_path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    media_type = media_types.get(suffix, "image/jpeg")

    payload = {
        "model": "claude-3-5-haiku-20241022",
        "max_tokens": 50,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_img,
                        },
                    },
                    {
                        "type": "text",
                        "text": CLAUDE_PROMPT,
                    },
                ],
            }
        ],
    }

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }

    from backend.cv.game_classifier import ZERO_SHOT_LABELS

    valid_labels = set(ZERO_SHOT_LABELS.keys())

    for attempt in range(max_retries):
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
                timeout=30.0,
            )

            if resp.status_code == 429:
                # Rate limited — exponential backoff
                wait = min(2 ** attempt * 2, 60)
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
                continue

            if resp.status_code != 200:
                log.warning("Claude API error %d: %s", resp.status_code, resp.text[:200])
                return None

            data = resp.json()
            text = data.get("content", [{}])[0].get("text", "").strip().lower()

            # Extract just the label — Claude might return extra text
            for label in valid_labels:
                if label in text:
                    return label

            log.warning("Claude returned unrecognized label: %s", text)
            return text if text else None

        except httpx.TimeoutException:
            wait = min(2 ** attempt * 2, 60)
            print(f"  Timeout, retrying in {wait}s...")
            time.sleep(wait)
            continue
        except Exception as e:
            log.warning("Claude API call failed: %s", e)
            return None

    return None


def _format_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{seconds / 60:.1f}m"
    else:
        return f"{seconds / 3600:.1f}h"


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    parser = argparse.ArgumentParser(
        description="Auto-label game screenshots using CLIP zero-shot + optional Claude Vision."
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        required=True,
        help="Input directory containing game frames (.jpg, .png, etc.)",
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output directory for auto-labeled results (default: <input>/../auto_labeled)",
    )
    parser.add_argument(
        "--use-claude",
        action="store_true",
        help="Also classify with Claude Haiku Vision API for consensus checking",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from existing results.jsonl (skip already-processed frames)",
    )
    args = parser.parse_args()

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"ERROR: Input directory not found: {input_dir}")
        sys.exit(1)

    output_dir = Path(args.output) if args.output else input_dir.parent / "auto_labeled"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect frames
    frames = _collect_frames(input_dir)
    if not frames:
        print(f"No image files found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(frames)} frames in {input_dir}")

    # Load existing results for resume
    results_path = output_dir / "results.jsonl"
    already_processed: set[str] = set()
    if args.resume and results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                already_processed.add(entry.get("image", ""))
        print(f"Resuming: {len(already_processed)} frames already processed")

    # Load CLIP classifier
    clf = _load_classifier()
    if clf is None:
        print("FATAL: CLIP classifier is required. Install torch + transformers.")
        sys.exit(1)

    # Load Claude API if requested
    api_key = None
    if args.use_claude:
        api_key = _load_api_key()
        if api_key is None:
            print("ERROR: --use-claude requires ANTHROPIC_API_KEY in backend/.env or environment")
            sys.exit(1)
        print("Claude Vision enabled (claude-3-5-haiku)")

    # Process frames
    results: list[dict] = []
    stats = {"total": 0, "agreed": 0, "disagreed": 0, "clip_only": 0, "errors": 0}
    start_time = time.time()

    # Open results file in append mode for resume support
    mode = "a" if args.resume else "w"
    results_file = open(results_path, mode, encoding="utf-8")

    try:
        for i, frame_path in enumerate(frames):
            # Make path relative for storage
            try:
                rel_path = str(frame_path.relative_to(input_dir))
            except ValueError:
                rel_path = frame_path.name

            # Skip if already processed
            if rel_path in already_processed:
                continue

            stats["total"] += 1
            elapsed = time.time() - start_time
            remaining_count = len(frames) - i - 1

            # ETA calculation
            if stats["total"] > 1:
                avg_time = elapsed / (stats["total"] - 1)
                eta = _format_time(avg_time * remaining_count)
            else:
                eta = "..."

            # Progress bar
            pct = (i + 1) / len(frames) * 100
            bar_len = 30
            filled = int(bar_len * (i + 1) / len(frames))
            bar = "=" * filled + "-" * (bar_len - filled)
            print(f"\r[{bar}] {pct:5.1f}% ({i+1}/{len(frames)}) ETA: {eta}  ", end="", flush=True)

            # CLIP classification
            try:
                clip_result = _classify_frame(clf, frame_path)
            except Exception as e:
                log.warning("CLIP failed on %s: %s", frame_path.name, e)
                stats["errors"] += 1
                continue

            entry = {
                "image": rel_path,
                "clip_label": clip_result["clip_label"],
                "clip_confidence": clip_result["clip_confidence"],
                "clip_top3": clip_result["clip_top3"],
            }

            # Claude classification (if enabled)
            if args.use_claude and api_key:
                claude_label = _classify_with_claude(frame_path, api_key)
                if claude_label:
                    entry["claude_label"] = claude_label
                    if claude_label == clip_result["clip_label"]:
                        entry["agreement"] = "agreed"
                        entry["proposed_label"] = clip_result["clip_label"]
                        entry["confidence_level"] = "high"
                        stats["agreed"] += 1
                    else:
                        entry["agreement"] = "disagreed"
                        entry["proposed_label"] = clip_result["clip_label"]
                        entry["confidence_level"] = "low"
                        stats["disagreed"] += 1
                else:
                    entry["claude_label"] = None
                    entry["proposed_label"] = clip_result["clip_label"]
                    entry["confidence_level"] = "medium"
                    stats["clip_only"] += 1
            else:
                entry["proposed_label"] = clip_result["clip_label"]
                if clip_result["clip_confidence"] >= 0.7:
                    entry["confidence_level"] = "high"
                elif clip_result["clip_confidence"] >= 0.4:
                    entry["confidence_level"] = "medium"
                else:
                    entry["confidence_level"] = "low"
                stats["clip_only"] += 1

            results.append(entry)

            # Write to JSONL immediately (crash-safe)
            results_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
            results_file.flush()

            # Copy image to label subfolder for browsing
            label = entry["proposed_label"]
            label_dir = output_dir / label
            label_dir.mkdir(parents=True, exist_ok=True)
            dest = label_dir / f"{frame_path.parent.name}_{frame_path.name}"
            if not dest.exists():
                shutil.copy2(frame_path, dest)

    except KeyboardInterrupt:
        print("\n\nInterrupted! Saving progress...")
    finally:
        results_file.close()

    # Print summary
    print("\n")
    print("=" * 60)
    print("AUTO-LABELING COMPLETE")
    print("=" * 60)
    elapsed = time.time() - start_time
    print(f"Processed:  {stats['total']} frames in {_format_time(elapsed)}")
    if stats["total"] > 0:
        print(f"Speed:      {elapsed / stats['total']:.2f}s per frame")

    if args.use_claude:
        print(f"Agreed:     {stats['agreed']} ({stats['agreed']/max(stats['total'],1)*100:.1f}%)")
        print(f"Disagreed:  {stats['disagreed']} ({stats['disagreed']/max(stats['total'],1)*100:.1f}%)")

    print(f"CLIP-only:  {stats['clip_only']}")
    print(f"Errors:     {stats['errors']}")
    print(f"Results:    {results_path}")
    print(f"Folders:    {output_dir}/")

    # Print label distribution
    if results:
        label_counts: dict[str, int] = {}
        for r in results:
            lbl = r["proposed_label"]
            label_counts[lbl] = label_counts.get(lbl, 0) + 1

        print("\nLabel distribution:")
        for lbl, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            bar = "#" * min(count, 50)
            print(f"  {lbl:30s} {count:5d}  {bar}")


if __name__ == "__main__":
    main()
