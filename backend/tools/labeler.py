"""Quick image labeling tool — click a button to label each screenshot.

Usage:
    python -m backend.tools.labeler training_data/palworld/20260316
"""

import json
import sys
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


LABELS = [
    # Combat & Action
    ("1", "combat_wild", "#ff4444"),
    ("2", "combat_boss", "#ff0088"),
    ("3", "capture_attempt", "#ff8800"),
    ("4", "capture_success", "#ffaa00"),
    # Movement & Exploration
    ("5", "exploration", "#44aa44"),
    ("6", "riding_mount", "#44aaaa"),
    ("7", "flying", "#22cccc"),
    # Base & Crafting
    ("8", "base_building", "#aaaa44"),
    ("9", "workbench_craft", "#cc8844"),
    ("0", "base_idle", "#888888"),
    # Menus & UI
    ("q", "pal_management", "#aa44aa"),
    ("w", "inventory_menu", "#6666cc"),
    ("e", "stat_levelup", "#44cccc"),
    ("r", "map_screen", "#4488cc"),
    ("t", "settings_option", "#999999"),
    # Game Flow
    ("a", "world_select", "#8888ff"),
    ("d", "char_creation", "#cc88cc"),
    ("f", "loading_screen", "#666666"),
    ("g", "patch_notes", "#555577"),
    ("h", "steam_launcher", "#334466"),
    # States
    ("z", "ammo_empty", "#cc6644"),
    ("x", "death_screen", "#cc0000"),
    ("c", "base_raid", "#ff2222"),
    ("v", "cutscene", "#4466cc"),
    # Skip
    ("s", "skip", "#333333"),
]


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m backend.tools.labeler <training_data_dir>")
        sys.exit(1)

    data_dir = Path(sys.argv[1])
    jsonl_path = data_dir / "responses.jsonl"

    if not jsonl_path.exists():
        print(f"No responses.jsonl in {data_dir}")
        sys.exit(1)

    # Load existing data
    entries = []
    for line in jsonl_path.read_text(encoding="utf-8").strip().split("\n"):
        entries.append(json.loads(line))

    # Find unlabeled entries
    unlabeled = [(i, e) for i, e in enumerate(entries) if "label" not in e]
    if not unlabeled:
        print("All entries already labeled!")
        sys.exit(0)

    print(f"{len(unlabeled)} unlabeled out of {len(entries)} total")

    # GUI
    root = tk.Tk()
    root.title(f"Labeler — {len(unlabeled)} remaining")
    root.configure(bg="#1a1a2e")

    current_idx = [0]

    # Image display
    img_label = tk.Label(root, bg="#1a1a2e")
    img_label.pack(padx=10, pady=10)

    # Info
    info_var = tk.StringVar()
    tk.Label(root, textvariable=info_var, font=("Consolas", 11),
             fg="#c0c0ff", bg="#1a1a2e", wraplength=800, justify="left").pack(padx=10)

    # Progress
    progress_var = tk.StringVar()
    tk.Label(root, textvariable=progress_var, font=("Consolas", 10),
             fg="#666688", bg="#1a1a2e").pack(pady=(5, 0))

    # Buttons
    btn_frame = tk.Frame(root, bg="#1a1a2e")
    btn_frame.pack(padx=10, pady=10)

    def show_current():
        if current_idx[0] >= len(unlabeled):
            info_var.set("All done! Saving...")
            save_and_quit()
            return

        idx, entry = unlabeled[current_idx[0]]
        img_path = data_dir / entry["image"]

        if img_path.exists():
            img = Image.open(img_path)
            img.thumbnail((800, 450))
            photo = ImageTk.PhotoImage(img)
            img_label.configure(image=photo)
            img_label.image = photo

        response = entry.get("response", "")[:100]
        info_var.set(f"[c{entry['cycle']}] {entry['image']}\nAI said: {response}")
        progress_var.set(f"{current_idx[0] + 1} / {len(unlabeled)}")
        root.title(f"Labeler — {len(unlabeled) - current_idx[0]} remaining")

    def apply_label(label_name):
        if current_idx[0] >= len(unlabeled):
            return
        idx, entry = unlabeled[current_idx[0]]
        if label_name != "skip":
            entries[idx]["label"] = label_name
        current_idx[0] += 1
        show_current()

    def save_and_quit():
        # Save back to JSONL
        with open(jsonl_path, "w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        labeled = sum(1 for e in entries if "label" in e)
        print(f"Saved! {labeled}/{len(entries)} labeled.")
        root.destroy()

    # Create buttons grid
    cols = 5
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
            idx, entry = unlabeled[current_idx[0]]
            entries[idx].pop("label", None)
            show_current()

    root.bind("<BackSpace>", undo)

    # Save on close
    root.protocol("WM_DELETE_WINDOW", save_and_quit)
    root.bind("<Escape>", lambda e: save_and_quit())

    show_current()
    root.mainloop()


if __name__ == "__main__":
    main()
