"""Two-level hierarchical image labeling tool for game state classifier training data.

Scans ALL subdirectories under a training data directory, aggregates
unlabeled images, and presents them for labeling with a two-step
keyboard flow: group (1-6) then sub-label (Q/W/E/R/T/Y/U).

Labels match ZERO_SHOT_LABELS in backend/cv/game_classifier.py exactly,
so labeled data flows directly into the training pipeline.

Features:
- Two-level category system: 6 groups with 2-5 sub-labels each
- Side-by-side: screenshot + AI response text
- CLIP zero-shot prediction shown as confidence indicator
- Space = repeat last label (for runs of similar screenshots)
- ? = mark as uncertain (revisit later)
- Backspace = undo last label
- Recent history strip (last 5 labels as colored chips)
- Progress bar with speed tracking
- Auto-scans all session subdirectories

Usage:
    python -m backend.tools.labeler training_data/palworld
"""

import json
import sys
import time
import tkinter as tk
from pathlib import Path
from PIL import Image, ImageTk


# ---------------------------------------------------------------------------
# Two-level category hierarchy
# ---------------------------------------------------------------------------

GROUPS = [
    {
        "key": "1",
        "name": "Combat",
        "color": "#cc3333",
        "color_hover": "#ee4444",
        "labels": [
            ("q", "combat", "#ff4444", "일반 전투 (적 HP바 보임, 데미지 숫자)"),
            ("w", "capturing", "#ff8844", "포획 시도 (팰스피어 날아감/흔들림)"),
            ("e", "boss_fight", "#dd2222", "보스전 (상단 큰 HP바 + 타이머)"),
        ],
    },
    {
        "key": "2",
        "name": "Exploration",
        "color": "#339933",
        "color_hover": "#44bb44",
        "labels": [
            ("q", "exploring", "#44aa44", "탐험/이동 (3인칭, 전투 없음)"),
            ("w", "mounted_ground", "#66cc66", "지상 탈것 (팰 위에 탄 모습)"),
            ("e", "mounted_flying", "#22cccc", "비행 (높은 시점, 하늘)"),
            ("r", "gathering", "#88aa44", "채집 (나무/바위 치기, 아이템 드롭)"),
            ("t", "dungeon", "#668844", "던전 내부 (어두운 동굴/유적)"),
        ],
    },
    {
        "key": "3",
        "name": "Base",
        "color": "#aa8833",
        "color_hover": "#ccaa44",
        "labels": [
            ("q", "building", "#aaaa44", "건설 모드 (반투명 프리뷰)"),
            ("w", "base_view", "#888844", "거점 풍경 (팰들 일하는 모습)"),
            ("e", "crafting_menu", "#cc8844", "제작 UI (레시피 목록, Craft 버튼)"),
        ],
    },
    {
        "key": "4",
        "name": "Menu/UI",
        "color": "#5555aa",
        "color_hover": "#6666cc",
        "labels": [
            ("q", "inventory", "#6666cc", "인벤토리 (아이템 그리드, 장비)"),
            ("w", "pal_management", "#aa44aa", "팰 관리 (팰박스, 스탯, 파티)"),
            ("e", "technology_tree", "#4488cc", "기술 트리 (언락 노드 목록)"),
            ("r", "map_screen", "#44aacc", "맵 (탑다운 지도, 패스트트래블)"),
            ("t", "merchant_shop", "#cc8844", "상점 (구매/판매, 가격)"),
            ("y", "breeding_condenser", "#cc44aa", "교배/농축 (암수 슬롯, 별 등급)"),
            ("u", "settings_menu", "#999999", "설정 (옵션 탭, 슬라이더)"),
        ],
    },
    {
        "key": "5",
        "name": "Game Flow",
        "color": "#6655aa",
        "color_hover": "#8877cc",
        "labels": [
            ("q", "loading_screen", "#666666", "로딩 (진행바, 팁 텍스트)"),
            ("w", "death_respawn", "#aa2222", "사망 (어두운 화면, 리스폰)"),
            ("e", "cutscene_notification", "#4466cc", "알림 (레벨업, 습격경고, 업적)"),
            ("r", "dialogue_interaction", "#cc88cc", "대화 (NPC 대화창, 퀘스트)"),
            ("t", "character_creation", "#aa88cc", "캐릭터 생성 (외형 슬라이더)"),
            ("y", "world_select", "#8888ff", "월드 선택 (세이브 목록)"),
            ("u", "title_screen", "#6666aa", "타이틀 (메인 메뉴)"),
        ],
    },
    {
        "key": "6",
        "name": "Meta",
        "color": "#445566",
        "color_hover": "#556677",
        "labels": [
            ("q", "external_app", "#888888", "외부 앱 (스팀, 패치노트 등)"),
        ],
    },
]

# Build flat lookups: label_name -> group color, group name, description
_LABEL_COLOR_MAP: dict[str, str] = {}
_LABEL_GROUP_MAP: dict[str, str] = {}
_LABEL_DESC_MAP: dict[str, str] = {}
for _g in GROUPS:
    for _, _lname, _lcol, _ldesc in _g["labels"]:
        _LABEL_COLOR_MAP[_lname] = _lcol
        _LABEL_GROUP_MAP[_lname] = _g["name"]
        _LABEL_DESC_MAP[_lname] = _ldesc
_LABEL_COLOR_MAP["uncertain"] = "#aa6600"
_LABEL_GROUP_MAP["uncertain"] = "?"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _collect_unlabeled(base_dir: Path):
    """Scan all subdirectories for responses.jsonl and collect entries.

    Returns:
        all_entries: list of (jsonl_path, line_index, entry_dict, session_dir)
        unlabeled:   filtered subset where 'label' is not set
    """
    all_entries = []
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
    """Try to load the CLIP zero-shot classifier for confidence hints."""
    try:
        from backend.cv.game_classifier import GameClassifier
        import numpy as np

        clf = GameClassifier()
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


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------

# Style constants
BG_DARK = "#131320"
BG_PANEL = "#1a1a30"
BG_INFO = "#1e1e3a"
BG_BUTTON_ROW = "#16162a"
FG_DIM = "#555577"
FG_MID = "#8888aa"
FG_BRIGHT = "#c0c0e0"
FG_ACCENT = "#88aaff"
FG_CLIP = "#44cc88"
FONT_MONO = ("Consolas", 9)
FONT_MONO_SM = ("Consolas", 8)
FONT_MONO_LG = ("Consolas", 11, "bold")
FONT_LABEL = ("Malgun Gothic", 10, "bold")
FONT_LABEL_SM = ("Malgun Gothic", 9, "bold")
FONT_GROUP = ("Malgun Gothic", 11, "bold")


class LabelerApp:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.all_entries, self.unlabeled = _collect_unlabeled(base_dir)
        self.total = len(self.all_entries)
        self.already_labeled = self.total - len(self.unlabeled)

        if not self.unlabeled:
            print(f"All {self.total} entries already labeled!")
            sys.exit(0)

        print(f"Found {len(self.unlabeled)} unlabeled / {self.total} total in {base_dir}")
        print(f"Already labeled: {self.already_labeled}")

        self.clip_predict = _try_load_classifier()
        if self.clip_predict:
            print("CLIP classifier loaded.")

        # State
        self.current_idx = 0
        self.selected_group = None  # index into GROUPS
        self.last_label = None
        self.history: list[tuple[int, str]] = []  # (idx, label_name) for recent strip
        self.uncertain_count = sum(
            1 for _, _, e, _ in self.all_entries if e.get("label") == "uncertain"
        )
        self.session_start = time.time()
        self.labels_applied = 0

        self._build_gui()

    # ----- GUI construction -----

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title(f"Labeler -- {len(self.unlabeled)} remaining")
        self.root.geometry("940x740")
        self.root.configure(bg=BG_DARK)
        self.root.minsize(900, 700)

        # ---- Top section: image + info ----
        top_frame = tk.Frame(self.root, bg=BG_DARK)
        top_frame.pack(fill="both", expand=True, padx=8, pady=(6, 2))

        # Left: image
        img_container = tk.Frame(top_frame, bg=BG_PANEL, highlightbackground="#333355",
                                 highlightthickness=1)
        img_container.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self.img_label = tk.Label(img_container, bg=BG_PANEL)
        self.img_label.pack(padx=4, pady=4, fill="both", expand=True)

        # Right: info panel
        info_frame = tk.Frame(top_frame, bg=BG_INFO, width=280,
                              highlightbackground="#333355", highlightthickness=1)
        info_frame.pack(side="right", fill="y", padx=(4, 0))
        info_frame.pack_propagate(False)

        tk.Label(
            info_frame, text="AI Response", font=FONT_MONO_LG,
            fg=FG_ACCENT, bg=BG_INFO, anchor="w"
        ).pack(padx=8, pady=(8, 2), anchor="w")

        self.ai_text = tk.Text(
            info_frame, font=FONT_MONO, fg=FG_BRIGHT, bg=BG_INFO,
            wrap="word", relief="flat", height=10, state="disabled",
            borderwidth=0, highlightthickness=0, insertbackground=FG_BRIGHT,
        )
        self.ai_text.pack(padx=8, pady=(0, 4), fill="both", expand=True)

        # CLIP hint
        self.clip_hint_var = tk.StringVar(value="")
        tk.Label(
            info_frame, textvariable=self.clip_hint_var, font=FONT_MONO_SM,
            fg=FG_CLIP, bg=BG_INFO, anchor="w", justify="left", wraplength=260,
        ).pack(padx=8, pady=(0, 4), anchor="w")

        # Note
        tk.Label(
            info_frame,
            text="Note: label the PRIMARY activity.\nFrames can be multi-label\n(e.g. combat while flying).",
            font=FONT_MONO_SM, fg=FG_DIM, bg=BG_INFO,
            justify="left", wraplength=260,
        ).pack(padx=8, pady=(0, 8), anchor="w")

        # ---- Middle: group buttons (row 1) ----
        self.group_frame = tk.Frame(self.root, bg=BG_BUTTON_ROW)
        self.group_frame.pack(fill="x", padx=8, pady=(4, 2))

        self.group_buttons: list[tk.Button] = []
        for i, group in enumerate(GROUPS):
            btn = tk.Button(
                self.group_frame, text=f"[{group['key']}] {group['name']}",
                font=FONT_GROUP, fg="white", bg=group["color"],
                activebackground=group["color_hover"], activeforeground="white",
                relief="flat", bd=0, padx=12, pady=4, cursor="hand2",
                command=lambda idx=i: self._select_group(idx),
            )
            btn.pack(side="left", padx=3, pady=4, fill="x", expand=True)
            self.group_buttons.append(btn)

        # ---- Sub-label buttons (row 2) ----
        self.sub_frame = tk.Frame(self.root, bg=BG_BUTTON_ROW, height=62)
        self.sub_frame.pack(fill="x", padx=8, pady=(0, 2))
        self.sub_frame.pack_propagate(False)

        self.sub_buttons: list[tk.Button] = []
        self.sub_prompt_label = tk.Label(
            self.sub_frame, text="Select a group (1-6) to see sub-labels...",
            font=FONT_MONO, fg=FG_DIM, bg=BG_BUTTON_ROW,
        )
        self.sub_prompt_label.pack(pady=10)

        # ---- Quick actions row: Space / ? ----
        quick_frame = tk.Frame(self.root, bg=BG_DARK)
        quick_frame.pack(fill="x", padx=8, pady=(0, 2))

        self.space_label_var = tk.StringVar(value="[Space] Same as previous")
        self.space_btn = tk.Button(
            quick_frame, textvariable=self.space_label_var,
            font=FONT_LABEL_SM, fg="#cccccc", bg="#2a2a44",
            activebackground="#3a3a55", activeforeground="white",
            relief="flat", bd=0, padx=12, pady=3, cursor="hand2",
            command=self._apply_same_as_previous,
        )
        self.space_btn.pack(side="left", padx=(0, 6))

        tk.Button(
            quick_frame, text="[?] Uncertain (skip for now)",
            font=FONT_LABEL_SM, fg="#cccccc", bg="#443300",
            activebackground="#554400", activeforeground="white",
            relief="flat", bd=0, padx=12, pady=3, cursor="hand2",
            command=self._apply_uncertain,
        ).pack(side="left", padx=(0, 6))

        tk.Button(
            quick_frame, text="[Bksp] Undo",
            font=FONT_LABEL_SM, fg="#999999", bg="#2a2a2a",
            activebackground="#3a3a3a", activeforeground="white",
            relief="flat", bd=0, padx=12, pady=3, cursor="hand2",
            command=self._undo,
        ).pack(side="left", padx=(0, 6))

        self.uncertain_count_var = tk.StringVar(value="")
        tk.Label(
            quick_frame, textvariable=self.uncertain_count_var,
            font=FONT_MONO_SM, fg="#aa6600", bg=BG_DARK,
        ).pack(side="right")

        # ---- Progress bar ----
        progress_frame = tk.Frame(self.root, bg=BG_DARK)
        progress_frame.pack(fill="x", padx=8, pady=(2, 1))

        # Canvas progress bar
        self.progress_canvas = tk.Canvas(
            progress_frame, height=14, bg="#222233",
            highlightthickness=0, bd=0,
        )
        self.progress_canvas.pack(fill="x")

        # ---- Progress text + session info ----
        stats_frame = tk.Frame(self.root, bg=BG_DARK)
        stats_frame.pack(fill="x", padx=8, pady=(0, 1))

        self.progress_var = tk.StringVar()
        tk.Label(
            stats_frame, textvariable=self.progress_var, font=FONT_MONO,
            fg=FG_MID, bg=BG_DARK, anchor="w",
        ).pack(side="left")

        self.session_var = tk.StringVar()
        tk.Label(
            stats_frame, textvariable=self.session_var, font=FONT_MONO_SM,
            fg=FG_DIM, bg=BG_DARK, anchor="e",
        ).pack(side="right")

        # ---- Recent history strip ----
        history_frame = tk.Frame(self.root, bg=BG_DARK, height=28)
        history_frame.pack(fill="x", padx=8, pady=(0, 6))
        history_frame.pack_propagate(False)

        tk.Label(
            history_frame, text="Recent:", font=FONT_MONO_SM,
            fg=FG_DIM, bg=BG_DARK,
        ).pack(side="left", padx=(0, 4))

        self.history_chip_frame = tk.Frame(history_frame, bg=BG_DARK)
        self.history_chip_frame.pack(side="left", fill="x")

        # ---- Key bindings ----
        for i, group in enumerate(GROUPS):
            self.root.bind(
                group["key"],
                lambda e, idx=i: self._select_group(idx),
            )

        # Sub-label keys are bound dynamically when a group is selected
        self.root.bind("<space>", lambda e: self._apply_same_as_previous())
        self.root.bind("?", lambda e: self._apply_uncertain())
        self.root.bind("<BackSpace>", lambda e: self._undo())
        self.root.bind("<Escape>", lambda e: self._save_and_quit())
        self.root.protocol("WM_DELETE_WINDOW", self._save_and_quit)

        # Show first image
        self._show_current()

    # ----- Group / sub-label selection -----

    def _select_group(self, group_idx: int):
        self.selected_group = group_idx
        group = GROUPS[group_idx]

        # Highlight the selected group button
        for i, btn in enumerate(self.group_buttons):
            g = GROUPS[i]
            if i == group_idx:
                btn.configure(
                    relief="solid", bd=2,
                    bg=g["color_hover"],
                    font=("Malgun Gothic", 11, "bold underline"),
                )
            else:
                btn.configure(
                    relief="flat", bd=0,
                    bg=g["color"],
                    font=FONT_GROUP,
                )

        # Rebuild sub-label buttons
        for widget in self.sub_frame.winfo_children():
            widget.destroy()
        self.sub_buttons.clear()

        for key, label_name, color, desc in group["labels"]:
            btn_frame = tk.Frame(self.sub_frame, bg=color, cursor="hand2")
            btn_frame.pack(side="left", padx=4, pady=4, fill="x", expand=True)

            btn = tk.Button(
                btn_frame,
                text=f"[{key.upper()}] {label_name}",
                font=FONT_LABEL, fg="white", bg=color,
                activebackground=color, activeforeground="white",
                relief="flat", bd=0, padx=8, pady=1, cursor="hand2",
                command=lambda n=label_name: self._apply_label(n),
            )
            btn.pack(side="top", fill="x")

            tip = tk.Label(
                btn_frame, text=desc,
                font=("Malgun Gothic", 7), fg="#dddddd", bg=color,
                anchor="center",
            )
            tip.pack(side="top", fill="x")
            # Click on the tip label also applies the label
            tip.bind("<Button-1>", lambda e, n=label_name: self._apply_label(n))

            self.sub_buttons.append(btn)

        # Rebind sub-label keys
        self._unbind_sub_keys()
        for key, label_name, _, _ in group["labels"]:
            self.root.bind(
                key,
                lambda e, n=label_name: self._apply_label(n),
            )

    def _unbind_sub_keys(self):
        """Unbind all possible sub-label keys."""
        for key in ("q", "w", "e", "r", "t", "y", "u"):
            self.root.unbind(key)

    # ----- Label application -----

    def _apply_label(self, label_name: str):
        if self.current_idx >= len(self.unlabeled):
            return

        _, _, entry, _ = self.unlabeled[self.current_idx]
        entry["label"] = label_name
        self.last_label = label_name
        self.labels_applied += 1

        if label_name == "uncertain":
            self.uncertain_count += 1

        # Add to history
        self.history.append((self.current_idx, label_name))
        if len(self.history) > 5:
            self.history = self.history[-5:]

        # Deselect group and reset sub-labels for next image
        self.selected_group = None
        self._reset_group_highlight()
        self._show_sub_prompt()
        self._unbind_sub_keys()

        self.current_idx += 1
        self._show_current()

    def _apply_same_as_previous(self):
        if self.last_label is None:
            return
        self._apply_label(self.last_label)

    def _apply_uncertain(self):
        self._apply_label("uncertain")

    def _undo(self):
        if self.current_idx <= 0:
            return

        self.current_idx -= 1
        _, _, entry, _ = self.unlabeled[self.current_idx]
        old_label = entry.pop("label", None)
        self.labels_applied = max(0, self.labels_applied - 1)

        if old_label == "uncertain":
            self.uncertain_count = max(0, self.uncertain_count - 1)

        # Remove from history
        if self.history and self.history[-1][0] == self.current_idx:
            self.history.pop()

        # Reset group selection
        self.selected_group = None
        self._reset_group_highlight()
        self._show_sub_prompt()
        self._unbind_sub_keys()

        self._show_current()

    def _reset_group_highlight(self):
        for i, btn in enumerate(self.group_buttons):
            g = GROUPS[i]
            btn.configure(relief="flat", bd=0, bg=g["color"], font=FONT_GROUP)

    def _show_sub_prompt(self):
        for widget in self.sub_frame.winfo_children():
            widget.destroy()
        self.sub_buttons.clear()
        self.sub_prompt_label = tk.Label(
            self.sub_frame, text="Select a group (1-6) to see sub-labels...",
            font=FONT_MONO, fg=FG_DIM, bg=BG_BUTTON_ROW,
        )
        self.sub_prompt_label.pack(pady=10)

    # ----- Display -----

    def _show_current(self):
        if self.current_idx >= len(self.unlabeled):
            self.ai_text.config(state="normal")
            self.ai_text.delete("1.0", "end")
            self.ai_text.insert("1.0", "All done! Saving...")
            self.ai_text.config(state="disabled")
            self._save_and_quit()
            return

        jsonl_path, line_idx, entry, session_dir = self.unlabeled[self.current_idx]
        img_path = session_dir / entry.get("image", "")

        # Show image
        if img_path.exists():
            img = Image.open(img_path)
            img.thumbnail((600, 440))
            photo = ImageTk.PhotoImage(img)
            self.img_label.configure(image=photo)
            self.img_label.image = photo
        else:
            self.img_label.configure(image="", text="(image not found)")

        # Show AI response
        response = entry.get("response", "(no AI response)")
        self.ai_text.config(state="normal")
        self.ai_text.delete("1.0", "end")
        meta = f"Cycle: {entry.get('cycle', '?')}\n"
        meta += f"Image: {entry.get('image', '?')}\n"
        meta += f"Session: {session_dir.name}\n"
        meta += "-" * 30 + "\n\n"
        self.ai_text.insert("1.0", meta + response)
        self.ai_text.config(state="disabled")

        # CLIP prediction hint
        if self.clip_predict and img_path.exists():
            try:
                preds = self.clip_predict(str(img_path))
                hint_lines = ["CLIP prediction:"]
                for lbl, score in preds:
                    bar = "=" * int(score * 20)
                    hint_lines.append(f"  {lbl}: {score:.0%} {bar}")
                self.clip_hint_var.set("\n".join(hint_lines))
            except Exception:
                self.clip_hint_var.set("CLIP: (error)")
        else:
            self.clip_hint_var.set("")

        # Update space button hint
        if self.last_label:
            color = _LABEL_COLOR_MAP.get(self.last_label, "#888888")
            group_name = _LABEL_GROUP_MAP.get(self.last_label, "")
            self.space_label_var.set(f"[Space] {self.last_label}  ({group_name})")
            self.space_btn.configure(bg=color)
        else:
            self.space_label_var.set("[Space] Same as previous")
            self.space_btn.configure(bg="#2a2a44")

        # Uncertain count
        if self.uncertain_count > 0:
            self.uncertain_count_var.set(f"{self.uncertain_count} uncertain")
        else:
            self.uncertain_count_var.set("")

        # Progress
        done = self.current_idx
        remaining = len(self.unlabeled)
        pct = done / remaining * 100 if remaining > 0 else 100

        # Speed calculation
        elapsed = time.time() - self.session_start
        if self.labels_applied > 0 and elapsed > 0:
            sec_per_img = elapsed / self.labels_applied
            per_hour = 3600 / sec_per_img if sec_per_img > 0 else 0
            speed_str = f" | ~{sec_per_img:.1f} sec/img | {per_hour:.0f}/hr"
        else:
            speed_str = ""

        self.progress_var.set(
            f"{done + 1} / {remaining} ({pct:.0f}%){speed_str}  |  "
            f"Total: {self.already_labeled + done}/{self.total}"
        )

        try:
            rel = session_dir.relative_to(self.base_dir)
        except ValueError:
            rel = session_dir.name
        self.session_var.set(str(rel))

        self.root.title(
            f"Labeler -- {remaining - done} remaining ({pct:.0f}%)"
        )

        # Progress bar
        self.progress_canvas.delete("all")
        self.root.update_idletasks()
        canvas_w = self.progress_canvas.winfo_width()
        if canvas_w > 1:
            fill_w = int(canvas_w * (done / remaining)) if remaining > 0 else canvas_w
            self.progress_canvas.create_rectangle(
                0, 0, fill_w, 14, fill="#4466aa", outline=""
            )
            # Uncertain portion shown as orange ticks
            if self.uncertain_count > 0:
                unc_w = int(canvas_w * (self.uncertain_count / remaining))
                self.progress_canvas.create_rectangle(
                    fill_w, 0, fill_w + unc_w, 14, fill="#664400", outline=""
                )

        # History strip
        self._update_history_strip()

    def _update_history_strip(self):
        for widget in self.history_chip_frame.winfo_children():
            widget.destroy()

        for hist_idx, (img_idx, label_name) in enumerate(self.history):
            color = _LABEL_COLOR_MAP.get(label_name, "#555555")
            chip = tk.Label(
                self.history_chip_frame,
                text=f" {label_name} ",
                font=FONT_MONO_SM,
                fg="white", bg=color,
                padx=4, pady=1,
                cursor="hand2",
            )
            chip.pack(side="left", padx=2)
            chip.bind(
                "<Button-1>",
                lambda e, idx=img_idx: self._jump_to(idx),
            )

    def _jump_to(self, target_idx: int):
        """Jump back to a previously labeled image (for review)."""
        if 0 <= target_idx < len(self.unlabeled):
            # Undo the label so it appears as current
            _, _, entry, _ = self.unlabeled[target_idx]
            old_label = entry.pop("label", None)
            if old_label == "uncertain":
                self.uncertain_count = max(0, self.uncertain_count - 1)
            self.labels_applied = max(0, self.labels_applied - 1)

            self.current_idx = target_idx

            # Trim history to remove this and everything after
            self.history = [
                (i, l) for i, l in self.history if i < target_idx
            ]

            self.selected_group = None
            self._reset_group_highlight()
            self._show_sub_prompt()
            self._unbind_sub_keys()
            self._show_current()

    # ----- Save -----

    def _save_and_quit(self):
        """Save modified entries back to their respective JSONL files."""
        files_seen: set[Path] = set()
        for jsonl_path, _, _, _ in self.all_entries:
            files_seen.add(jsonl_path)

        for jsonl_path in files_seen:
            lines = jsonl_path.read_text(encoding="utf-8").strip().split("\n")
            entries_for_file = [
                (li, e)
                for jp, li, e, sd in self.all_entries
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
            1 for _, _, e, _ in self.all_entries if "label" in e
        )
        elapsed = time.time() - self.session_start
        minutes = elapsed / 60
        print(f"Saved! {labeled_total}/{self.total} labeled.")
        print(f"Session: {self.labels_applied} labels in {minutes:.1f} min")
        if self.labels_applied > 0:
            print(f"Speed: {elapsed / self.labels_applied:.1f} sec/img "
                  f"({3600 / (elapsed / self.labels_applied):.0f}/hr)")
        self.root.destroy()

    def run(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

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

    app = LabelerApp(base_dir)
    app.run()


if __name__ == "__main__":
    main()
