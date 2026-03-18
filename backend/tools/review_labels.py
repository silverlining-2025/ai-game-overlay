"""Review auto-labeled screenshots — confirm or correct labels.

Much faster than labeling from scratch: just press Enter to confirm
or a number+letter to correct.

Usage:
    python -m backend.tools.review_labels training_data/palworld/auto_labeled
"""

from __future__ import annotations

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk

from backend.cv.game_classifier import ZERO_SHOT_LABELS

# ---------------------------------------------------------------------------
# Two-level category hierarchy (matches labeler.py)
# ---------------------------------------------------------------------------

GROUPS = [
    {
        "key": "1",
        "name": "Combat",
        "color": "#cc3333",
        "labels": [
            ("q", "combat"),
            ("w", "capturing"),
            ("e", "boss_fight"),
        ],
    },
    {
        "key": "2",
        "name": "Exploration",
        "color": "#339933",
        "labels": [
            ("q", "exploring"),
            ("w", "mounted_ground"),
            ("e", "mounted_flying"),
            ("r", "gathering"),
            ("t", "dungeon"),
        ],
    },
    {
        "key": "3",
        "name": "Base",
        "color": "#aa8833",
        "labels": [
            ("q", "building"),
            ("w", "base_view"),
            ("e", "crafting_menu"),
        ],
    },
    {
        "key": "4",
        "name": "Menu/UI",
        "color": "#5555aa",
        "labels": [
            ("q", "inventory"),
            ("w", "pal_management"),
            ("e", "technology_tree"),
            ("r", "map_screen"),
            ("t", "merchant_shop"),
            ("y", "breeding_condenser"),
            ("u", "settings_menu"),
        ],
    },
    {
        "key": "5",
        "name": "Game Flow",
        "color": "#6655aa",
        "labels": [
            ("q", "loading_screen"),
            ("w", "death_respawn"),
            ("e", "cutscene_notification"),
            ("r", "dialogue_interaction"),
            ("t", "character_creation"),
            ("y", "world_select"),
            ("u", "title_screen"),
        ],
    },
    {
        "key": "6",
        "name": "Meta",
        "color": "#445566",
        "labels": [
            ("q", "external_app"),
        ],
    },
]

# Build label -> color mapping
_LABEL_COLORS: dict[str, str] = {}
for _g in GROUPS:
    for _, _lname in _g["labels"]:
        _LABEL_COLORS[_lname] = _g["color"]

# Style constants
BG_DARK = "#131320"
BG_PANEL = "#1a1a30"
BG_INFO = "#1e1e3a"
FG_DIM = "#555577"
FG_MID = "#8888aa"
FG_BRIGHT = "#c0c0e0"
FG_GREEN = "#44cc88"
FG_YELLOW = "#ccaa44"
FG_RED = "#cc4444"
FONT_MONO = ("Consolas", 9)
FONT_MONO_SM = ("Consolas", 8)
FONT_MONO_LG = ("Consolas", 12, "bold")
FONT_STATUS = ("Consolas", 14, "bold")
FONT_GROUP = ("Malgun Gothic", 11, "bold")
FONT_LABEL = ("Malgun Gothic", 10, "bold")


class ReviewApp:
    def __init__(self, auto_labeled_dir: Path, frames_dir: Path | None = None):
        self.auto_labeled_dir = auto_labeled_dir
        self.frames_dir = frames_dir
        self.results_path = auto_labeled_dir / "results.jsonl"

        if not self.results_path.exists():
            print(f"ERROR: results.jsonl not found in {auto_labeled_dir}")
            sys.exit(1)

        # Load all entries
        self.entries: list[dict] = []
        for line in self.results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                self.entries.append(json.loads(line))

        if not self.entries:
            print("No entries in results.jsonl")
            sys.exit(1)

        # Filter to unverified entries
        self.unverified = [
            (i, e) for i, e in enumerate(self.entries)
            if not e.get("verified")
        ]
        self.already_verified = len(self.entries) - len(self.unverified)

        if not self.unverified:
            print(f"All {len(self.entries)} entries already verified!")
            sys.exit(0)

        print(f"Found {len(self.unverified)} unverified / {len(self.entries)} total")
        print(f"Already verified: {self.already_verified}")

        # State
        self.current_idx = 0
        self.selected_group: int | None = None
        self.session_start = time.time()
        self.stats = {"accepted": 0, "corrected": 0, "skipped": 0}

        self._build_gui()

    def _resolve_image_path(self, entry: dict) -> Path | None:
        """Find the image file for an entry."""
        rel = entry.get("image", "")
        if not rel:
            return None

        # Try frames_dir first (original location)
        if self.frames_dir:
            p = self.frames_dir / rel
            if p.exists():
                return p

        # Try relative to auto_labeled_dir
        p = self.auto_labeled_dir / rel
        if p.exists():
            return p

        # Try in label subfolder
        label = entry.get("proposed_label", "")
        if label:
            p = self.auto_labeled_dir / label / Path(rel).name
            if p.exists():
                return p

        # Try parent of auto_labeled_dir (common layout: .../frames/<file>)
        p = self.auto_labeled_dir.parent / "frames" / rel
        if p.exists():
            return p

        return None

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title(f"Review Labels -- {len(self.unverified)} remaining")
        self.root.geometry("940x700")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(900, 660)

        # ---- Top: Image ----
        img_frame = tk.Frame(self.root, bg=BG_PANEL, highlightbackground="#333355",
                             highlightthickness=1)
        img_frame.pack(fill="both", expand=True, padx=8, pady=(6, 2))

        self.img_label = tk.Label(img_frame, bg=BG_PANEL)
        self.img_label.pack(padx=4, pady=4, fill="both", expand=True)

        # ---- Status line: agreement indicator ----
        self.status_frame = tk.Frame(self.root, bg=BG_DARK)
        self.status_frame.pack(fill="x", padx=8, pady=(4, 2))

        self.status_var = tk.StringVar()
        self.status_label = tk.Label(
            self.status_frame, textvariable=self.status_var,
            font=FONT_STATUS, fg=FG_GREEN, bg=BG_DARK, anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        self.confidence_var = tk.StringVar()
        tk.Label(
            self.status_frame, textvariable=self.confidence_var,
            font=FONT_MONO, fg=FG_MID, bg=BG_DARK, anchor="e",
        ).pack(side="right")

        # ---- Group buttons (for correction) ----
        correction_label = tk.Label(
            self.root, text="To correct: press group number (1-6), then sub-label key",
            font=FONT_MONO_SM, fg=FG_DIM, bg=BG_DARK, anchor="w",
        )
        correction_label.pack(fill="x", padx=12, pady=(2, 0))

        self.group_frame = tk.Frame(self.root, bg=BG_DARK)
        self.group_frame.pack(fill="x", padx=8, pady=(2, 2))

        self.group_buttons: list[tk.Button] = []
        for i, group in enumerate(GROUPS):
            btn = tk.Button(
                self.group_frame, text=f"[{group['key']}] {group['name']}",
                font=FONT_GROUP, fg="white", bg=group["color"],
                relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                command=lambda idx=i: self._select_group(idx),
            )
            btn.pack(side="left", padx=3, pady=3, fill="x", expand=True)
            self.group_buttons.append(btn)

        # ---- Sub-label buttons ----
        self.sub_frame = tk.Frame(self.root, bg=BG_DARK, height=50)
        self.sub_frame.pack(fill="x", padx=8, pady=(0, 2))
        self.sub_frame.pack_propagate(False)

        self.sub_prompt = tk.Label(
            self.sub_frame, text="Enter = accept  |  Space = skip  |  1-6 = correct",
            font=FONT_MONO, fg=FG_DIM, bg=BG_DARK,
        )
        self.sub_prompt.pack(pady=8)

        # ---- Progress ----
        progress_frame = tk.Frame(self.root, bg=BG_DARK)
        progress_frame.pack(fill="x", padx=8, pady=(2, 1))

        self.progress_canvas = tk.Canvas(
            progress_frame, height=12, bg="#222233",
            highlightthickness=0, bd=0,
        )
        self.progress_canvas.pack(fill="x")

        stats_frame = tk.Frame(self.root, bg=BG_DARK)
        stats_frame.pack(fill="x", padx=8, pady=(0, 6))

        self.progress_var = tk.StringVar()
        tk.Label(
            stats_frame, textvariable=self.progress_var, font=FONT_MONO,
            fg=FG_MID, bg=BG_DARK, anchor="w",
        ).pack(side="left")

        self.speed_var = tk.StringVar()
        tk.Label(
            stats_frame, textvariable=self.speed_var, font=FONT_MONO_SM,
            fg=FG_DIM, bg=BG_DARK, anchor="e",
        ).pack(side="right")

        # ---- Key bindings ----
        self.root.bind("<Return>", lambda e: self._accept())
        self.root.bind("<space>", lambda e: self._skip())
        self.root.bind("<Escape>", lambda e: self._save_and_quit())
        self.root.protocol("WM_DELETE_WINDOW", self._save_and_quit)

        for i, group in enumerate(GROUPS):
            self.root.bind(
                group["key"],
                lambda e, idx=i: self._select_group(idx),
            )

        # Show first
        self._show_current()

    def _select_group(self, group_idx: int):
        self.selected_group = group_idx
        group = GROUPS[group_idx]

        # Highlight selected group
        for i, btn in enumerate(self.group_buttons):
            g = GROUPS[i]
            if i == group_idx:
                btn.configure(relief="solid", bd=2, font=("Malgun Gothic", 11, "bold underline"))
            else:
                btn.configure(relief="flat", bd=0, font=FONT_GROUP)

        # Show sub-label buttons
        for widget in self.sub_frame.winfo_children():
            widget.destroy()

        for key, label_name in group["labels"]:
            btn = tk.Button(
                self.sub_frame,
                text=f"[{key.upper()}] {label_name}",
                font=FONT_LABEL, fg="white", bg=group["color"],
                relief="flat", bd=0, padx=10, pady=2, cursor="hand2",
                command=lambda n=label_name: self._correct(n),
            )
            btn.pack(side="left", padx=3, pady=4, fill="x", expand=True)

        # Bind sub-label keys
        self._unbind_sub_keys()
        for key, label_name in group["labels"]:
            self.root.bind(key, lambda e, n=label_name: self._correct(n))

    def _unbind_sub_keys(self):
        for key in ("q", "w", "e", "r", "t", "y", "u"):
            self.root.unbind(key)

    def _reset_group_selection(self):
        self.selected_group = None
        for i, btn in enumerate(self.group_buttons):
            btn.configure(relief="flat", bd=0, font=FONT_GROUP)
        self._unbind_sub_keys()

        for widget in self.sub_frame.winfo_children():
            widget.destroy()
        self.sub_prompt = tk.Label(
            self.sub_frame, text="Enter = accept  |  Space = skip  |  1-6 = correct",
            font=FONT_MONO, fg=FG_DIM, bg=BG_DARK,
        )
        self.sub_prompt.pack(pady=8)

    def _accept(self):
        """Accept the proposed label."""
        if self.current_idx >= len(self.unverified):
            return

        orig_idx, entry = self.unverified[self.current_idx]
        entry["verified"] = True
        entry["verified_label"] = entry.get("proposed_label", entry.get("clip_label", "unknown"))
        entry["verified_action"] = "accepted"
        self.stats["accepted"] += 1

        self._reset_group_selection()
        self.current_idx += 1
        self._show_current()

    def _correct(self, new_label: str):
        """Override with a different label."""
        if self.current_idx >= len(self.unverified):
            return

        orig_idx, entry = self.unverified[self.current_idx]
        entry["verified"] = True
        entry["verified_label"] = new_label
        entry["verified_action"] = "corrected"
        entry["original_proposed"] = entry.get("proposed_label", entry.get("clip_label", ""))
        self.stats["corrected"] += 1

        self._reset_group_selection()
        self.current_idx += 1
        self._show_current()

    def _skip(self):
        """Skip this entry (uncertain)."""
        if self.current_idx >= len(self.unverified):
            return

        orig_idx, entry = self.unverified[self.current_idx]
        entry["verified_action"] = "skipped"
        self.stats["skipped"] += 1

        self._reset_group_selection()
        self.current_idx += 1
        self._show_current()

    def _show_current(self):
        if self.current_idx >= len(self.unverified):
            self.status_var.set("ALL DONE! Saving...")
            self.status_label.configure(fg=FG_GREEN)
            self.root.after(500, self._save_and_quit)
            return

        orig_idx, entry = self.unverified[self.current_idx]

        # Show image
        img_path = self._resolve_image_path(entry)
        if img_path and img_path.exists():
            img = Image.open(img_path)
            img.thumbnail((800, 450))
            photo = ImageTk.PhotoImage(img)
            self.img_label.configure(image=photo)
            self.img_label.image = photo
        else:
            self.img_label.configure(
                image="",
                text=f"(image not found: {entry.get('image', '?')})",
                fg=FG_DIM,
            )

        # Agreement status
        agreement = entry.get("agreement")
        clip_label = entry.get("clip_label", "?")
        claude_label = entry.get("claude_label")
        proposed = entry.get("proposed_label", clip_label)
        confidence = entry.get("clip_confidence", 0)

        if agreement == "agreed":
            self.status_var.set(f"AGREED: {proposed}")
            self.status_label.configure(fg=FG_GREEN)
        elif agreement == "disagreed":
            self.status_var.set(f"CLIP: {clip_label}  vs  CLAUDE: {claude_label}")
            self.status_label.configure(fg=FG_YELLOW)
        else:
            # CLIP-only
            if confidence >= 0.7:
                self.status_var.set(f"CLIP (high): {proposed}")
                self.status_label.configure(fg=FG_GREEN)
            elif confidence >= 0.4:
                self.status_var.set(f"CLIP (medium): {proposed}")
                self.status_label.configure(fg=FG_YELLOW)
            else:
                self.status_var.set(f"CLIP (low): {proposed}")
                self.status_label.configure(fg=FG_RED)

        # Top-3 confidence
        top3 = entry.get("clip_top3", [])
        if top3:
            parts = [f"{t['label']}: {t['confidence']:.0%}" for t in top3[:3]]
            self.confidence_var.set("  |  ".join(parts))
        else:
            self.confidence_var.set(f"confidence: {confidence:.0%}")

        # Progress
        done = self.current_idx
        total = len(self.unverified)
        pct = done / total * 100 if total > 0 else 100

        elapsed = time.time() - self.session_start
        reviewed = self.stats["accepted"] + self.stats["corrected"] + self.stats["skipped"]
        if reviewed > 0:
            rate = 3600 / (elapsed / reviewed)
            self.speed_var.set(f"{elapsed/reviewed:.1f}s/img  |  {rate:.0f}/hr")
        else:
            self.speed_var.set("")

        self.progress_var.set(
            f"{done + 1} / {total} ({pct:.0f}%)  |  "
            f"Accepted: {self.stats['accepted']}  "
            f"Corrected: {self.stats['corrected']}  "
            f"Skipped: {self.stats['skipped']}"
        )

        self.root.title(f"Review Labels -- {total - done} remaining")

        # Progress bar
        self.progress_canvas.delete("all")
        self.root.update_idletasks()
        w = self.progress_canvas.winfo_width()
        if w > 1:
            fill_w = int(w * done / total) if total > 0 else w
            self.progress_canvas.create_rectangle(0, 0, fill_w, 12, fill="#4466aa", outline="")

    def _save_and_quit(self):
        """Save all entries back to results.jsonl."""
        with open(self.results_path, "w", encoding="utf-8") as f:
            for entry in self.entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        reviewed = self.stats["accepted"] + self.stats["corrected"] + self.stats["skipped"]
        total_verified = sum(1 for e in self.entries if e.get("verified"))
        elapsed = time.time() - self.session_start

        print("\n" + "=" * 60)
        print("REVIEW SESSION COMPLETE")
        print("=" * 60)
        print(f"Reviewed:    {reviewed} entries in {elapsed/60:.1f} min")
        print(f"Accepted:    {self.stats['accepted']} ({self.stats['accepted']/max(reviewed,1)*100:.1f}%)")
        print(f"Corrected:   {self.stats['corrected']} ({self.stats['corrected']/max(reviewed,1)*100:.1f}%)")
        print(f"Skipped:     {self.stats['skipped']} ({self.stats['skipped']/max(reviewed,1)*100:.1f}%)")
        print(f"Total verified: {total_verified}/{len(self.entries)}")
        if reviewed > 0:
            print(f"Speed:       {elapsed/reviewed:.1f}s/img ({3600/(elapsed/reviewed):.0f}/hr)")
        print(f"Saved:       {self.results_path}")

        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Review auto-labeled game screenshots — confirm or correct labels."
    )
    parser.add_argument(
        "auto_labeled_dir",
        type=str,
        help="Directory containing results.jsonl from auto_label.py",
    )
    parser.add_argument(
        "--frames-dir",
        type=str,
        default=None,
        help="Original frames directory (for resolving image paths)",
    )
    args = parser.parse_args()

    auto_dir = Path(args.auto_labeled_dir)
    if not auto_dir.exists():
        print(f"ERROR: Directory not found: {auto_dir}")
        sys.exit(1)

    frames_dir = Path(args.frames_dir) if args.frames_dir else None

    app = ReviewApp(auto_dir, frames_dir)
    app.run()


if __name__ == "__main__":
    main()
