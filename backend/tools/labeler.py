"""Image labeling tool for game state classifier training data.

Scans ALL subdirectories under a training data directory, aggregates
unlabeled images, and presents them for labeling with keyboard shortcuts.

Labels match ZERO_SHOT_LABELS in backend/cv/game_classifier.py exactly,
so labeled data flows directly into the training pipeline.

Features:
- Side-by-side: screenshot + AI response text
- CLIP zero-shot prediction shown as confidence indicator
- Multi-label note for ambiguous frames
- Progress percentage
- Undo with Backspace
- Auto-scans all session subdirectories

Usage:
    python -m backend.tools.labeler training_data/palworld
"""

import json
import sys
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


# ---------------------------------------------------------------------------
# Labels — MUST match ZERO_SHOT_LABELS in backend/cv/game_classifier.py
# ---------------------------------------------------------------------------

LABELS = [
    # Combat & Exploration
    ("1", "combat_wild", "#ff4444"),
    ("2", "exploration", "#44aa44"),
    ("3", "flying", "#22cccc"),
    # Base & Crafting
    ("4", "base_building", "#aaaa44"),
    ("5", "workbench_craft", "#cc8844"),
    ("6", "base_idle", "#888888"),
    # Creatures / Companions
    ("7", "pal_management", "#aa44aa"),
    ("8", "cutscene", "#4466cc"),
    # Menus & UI
    ("9", "inventory_menu", "#6666cc"),
    ("0", "map_screen", "#4488cc"),
    ("q", "settings_option", "#999999"),
    # Game Flow
    ("w", "world_select", "#8888ff"),
    ("e", "char_creation", "#cc88cc"),
    ("r", "loading_screen", "#666666"),
    ("t", "patch_notes", "#555577"),
    ("a", "steam_launcher", "#334466"),
    # Skip
    ("s", "skip", "#333333"),
]


def _collect_unlabeled(base_dir: Path):
    """Scan all subdirectories for responses.jsonl and collect entries.

    Returns:
        all_entries: list of (jsonl_path, line_index, entry_dict, session_dir)
        unlabeled:   filtered subset where 'label' is not set
    """
    all_entries = []

    # Walk all subdirectories looking for responses.jsonl
    jsonl_files = sorted(base_dir.rglob("responses.jsonl"))

    if not jsonl_files:
        print(f"No responses.jsonl found under {base_dir}")
        sys.exit(1)

    for jsonl_path in jsonl_files:
        session_dir = jsonl_path.parent
        lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
        for line_idx, line in enumerate(lines):
            if not line.strip():
                continue
            entry = json.loads(line)
            all_entries.append((jsonl_path, line_idx, entry, session_dir))

    unlabeled = [
        (jp, li, e, sd)
        for jp, li, e, sd in all_entries
        if "label" not in e
    ]
    return all_entries, unlabeled


def _try_load_classifier():
    """Try to load the CLIP zero-shot classifier for confidence hints.

    Returns a callable classify_top_k(image_path) -> list[(label, score)]
    or None if unavailable.
    """
    try:
        from backend.cv.game_classifier import GameClassifier
        import numpy as np

        clf = GameClassifier()
        # Force load to check availability
        clf._load()
        if clf.mode == "none":
            return None

        def predict(img_path: str):
            img = Image.open(img_path).convert("RGB")
            frame = np.array(img)
            return clf.classify_top_k(frame, k=3)

        return predict
    except Exception as e:
        print(f"CLIP classifier not available (optional): {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m backend.tools.labeler <training_data_dir>")
        print("  e.g. python -m backend.tools.labeler training_data/palworld")
        print("\nScans ALL subdirectories for responses.jsonl files.")
        sys.exit(1)

    base_dir = Path(sys.argv[1])
    if not base_dir.exists():
        print(f"Directory not found: {base_dir}")
        sys.exit(1)

    all_entries, unlabeled = _collect_unlabeled(base_dir)
    total = len(all_entries)
    already_labeled = total - len(unlabeled)

    if not unlabeled:
        print(f"All {total} entries already labeled!")
        sys.exit(0)

    print(f"Found {len(unlabeled)} unlabeled out of {total} total across {base_dir}")
    print(f"Already labeled: {already_labeled}")

    # Try loading CLIP classifier for confidence hints
    clip_predict = _try_load_classifier()
    if clip_predict:
        print("CLIP classifier loaded — predictions will be shown as hints.")
    else:
        print("CLIP classifier not available — labeling without predictions.")

    # --- GUI ---
    root = tk.Tk()
    root.title(f"Labeler -- {len(unlabeled)} remaining")
    root.geometry("900x700")
    root.configure(bg="#1a1a2e")
    root.minsize(900, 700)

    current_idx = [0]

    # Top section: image + AI response side by side
    top_frame = tk.Frame(root, bg="#1a1a2e")
    top_frame.pack(fill="both", expand=True, padx=10, pady=5)

    # Left: image
    img_frame = tk.Frame(top_frame, bg="#1a1a2e")
    img_frame.pack(side="left", fill="both", expand=True)

    img_label = tk.Label(img_frame, bg="#1a1a2e")
    img_label.pack(padx=5, pady=5, fill="both", expand=True)

    # Right: AI response + metadata
    info_frame = tk.Frame(top_frame, bg="#1e1e3a", width=280)
    info_frame.pack(side="right", fill="y", padx=(5, 0), pady=5)
    info_frame.pack_propagate(False)

    tk.Label(
        info_frame, text="AI Response", font=("Consolas", 10, "bold"),
        fg="#8888cc", bg="#1e1e3a", anchor="w"
    ).pack(padx=8, pady=(8, 2), anchor="w")

    ai_text = tk.Text(
        info_frame, font=("Consolas", 9), fg="#c0c0ff", bg="#1e1e3a",
        wrap="word", relief="flat", height=10, state="disabled",
        borderwidth=0, highlightthickness=0,
    )
    ai_text.pack(padx=8, pady=(0, 5), fill="both", expand=True)

    # CLIP prediction hint
    clip_hint_var = tk.StringVar(value="")
    clip_hint_label = tk.Label(
        info_frame, textvariable=clip_hint_var, font=("Consolas", 9),
        fg="#44cc88", bg="#1e1e3a", anchor="w", justify="left",
        wraplength=260,
    )
    clip_hint_label.pack(padx=8, pady=(0, 5), anchor="w")

    # Multi-label note
    tk.Label(
        info_frame,
        text="Note: frames can be multi-label\n(e.g. combat while flying).\nLabel the PRIMARY activity.",
        font=("Consolas", 8), fg="#666688", bg="#1e1e3a",
        justify="left", wraplength=260,
    ).pack(padx=8, pady=(0, 8), anchor="w")

    # Progress bar area
    progress_frame = tk.Frame(root, bg="#1a1a2e")
    progress_frame.pack(fill="x", padx=10, pady=(0, 5))

    progress_var = tk.StringVar()
    tk.Label(
        progress_frame, textvariable=progress_var, font=("Consolas", 10),
        fg="#8888aa", bg="#1a1a2e",
    ).pack(side="left")

    session_var = tk.StringVar()
    tk.Label(
        progress_frame, textvariable=session_var, font=("Consolas", 9),
        fg="#555577", bg="#1a1a2e",
    ).pack(side="right")

    # Buttons
    btn_frame = tk.Frame(root, bg="#1a1a2e")
    btn_frame.pack(padx=10, pady=(0, 10))

    def show_current():
        if current_idx[0] >= len(unlabeled):
            ai_text.config(state="normal")
            ai_text.delete("1.0", "end")
            ai_text.insert("1.0", "All done! Saving...")
            ai_text.config(state="disabled")
            save_and_quit()
            return

        jsonl_path, line_idx, entry, session_dir = unlabeled[current_idx[0]]
        img_path = session_dir / entry.get("image", "")

        # Show image
        if img_path.exists():
            img = Image.open(img_path)
            # Scale to fit available space while keeping aspect ratio
            img.thumbnail((580, 480))
            photo = ImageTk.PhotoImage(img)
            img_label.configure(image=photo)
            img_label.image = photo

        # Show AI response
        response = entry.get("response", "(no AI response)")
        ai_text.config(state="normal")
        ai_text.delete("1.0", "end")
        meta = f"Cycle: {entry.get('cycle', '?')}\n"
        meta += f"Image: {entry.get('image', '?')}\n"
        meta += f"Session: {session_dir.name}\n"
        meta += "-" * 30 + "\n\n"
        ai_text.insert("1.0", meta + response)
        ai_text.config(state="disabled")

        # CLIP prediction hint
        if clip_predict and img_path.exists():
            try:
                preds = clip_predict(str(img_path))
                hint_lines = ["CLIP prediction:"]
                for lbl, score in preds:
                    bar = "#" * int(score * 20)
                    hint_lines.append(f"  {lbl}: {score:.0%} {bar}")
                clip_hint_var.set("\n".join(hint_lines))
            except Exception:
                clip_hint_var.set("CLIP: (error)")
        else:
            clip_hint_var.set("")

        # Progress
        done = current_idx[0]
        pct = done / len(unlabeled) * 100
        progress_var.set(
            f"{done + 1} / {len(unlabeled)}  ({pct:.0f}% done)  |  "
            f"Total labeled: {already_labeled + done}/{total}"
        )
        session_var.set(f"{session_dir.relative_to(base_dir)}")
        root.title(f"Labeler -- {len(unlabeled) - done} remaining ({pct:.0f}%)")

    def apply_label(label_name):
        if current_idx[0] >= len(unlabeled):
            return
        jsonl_path, line_idx, entry, session_dir = unlabeled[current_idx[0]]
        if label_name != "skip":
            entry["label"] = label_name
        current_idx[0] += 1
        show_current()

    def save_and_quit():
        """Save modified entries back to their respective JSONL files."""
        # Group entries by jsonl_path and rebuild each file
        files_to_save: dict[Path, list] = {}
        for jsonl_path, line_idx, entry, session_dir in all_entries:
            if jsonl_path not in files_to_save:
                files_to_save[jsonl_path] = []

        # Re-read and update each file
        for jsonl_path in files_to_save:
            lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
            entries_for_file = [
                (li, e)
                for jp, li, e, sd in all_entries
                if jp == jsonl_path
            ]
            updated_lines = list(lines)
            for li, e in entries_for_file:
                if li < len(updated_lines):
                    updated_lines[li] = json.dumps(e, ensure_ascii=False)
            with open(jsonl_path, "w", encoding="utf-8") as f:
                for line in updated_lines:
                    f.write(line + "\n")

        labeled_total = sum(
            1 for _, _, e, _ in all_entries if "label" in e
        )
        print(f"Saved! {labeled_total}/{total} labeled across all sessions.")
        root.destroy()

    # Create buttons grid
    cols = 6
    for i, (key, name, color) in enumerate(LABELS):
        row = i // cols
        col = i % cols
        btn = tk.Button(
            btn_frame, text=f"[{key}] {name}",
            font=("Malgun Gothic", 9, "bold"),
            fg="white", bg=color, activebackground=color,
            width=16, height=1,
            command=lambda n=name: apply_label(n),
        )
        btn.grid(row=row, column=col, padx=2, pady=2)

    # Keyboard shortcuts
    for key, name, _ in LABELS:
        root.bind(key, lambda e, n=name: apply_label(n))

    # Undo with backspace
    def undo(event=None):
        if current_idx[0] > 0:
            current_idx[0] -= 1
            _, _, entry, _ = unlabeled[current_idx[0]]
            entry.pop("label", None)
            show_current()

    root.bind("<BackSpace>", undo)

    # Save on close
    root.protocol("WM_DELETE_WINDOW", save_and_quit)
    root.bind("<Escape>", lambda e: save_and_quit())

    show_current()
    root.mainloop()


if __name__ == "__main__":
    main()
