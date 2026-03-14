"""Minesweeper grid detection and cell classification via CV."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging

import cv2
import numpy as np

from backend.config import MinesweeperConfig, ROI
from .base import BaseProcessor

logger = logging.getLogger(__name__)

# Window title keywords used to locate the game window via Win32
_GAME_TITLE_KEYWORDS = ("minesweeper", "winmine")


def _find_game_window(keywords: tuple[str, ...] = _GAME_TITLE_KEYWORDS) -> ROI | None:
    """Return the client-area ROI of the first visible window whose title contains
    any of *keywords* (case-insensitive).  Uses Win32 EnumWindows via ctypes so
    no extra dependencies are required.  Returns None on non-Windows or if no
    matching window is found.
    """
    try:
        user32 = ctypes.windll.user32
    except AttributeError:
        return None  # Not on Windows

    results: list[tuple[int, int, int, int]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def _cb(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value.lower()
        if any(k in title for k in keywords):
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            pt = ctypes.wintypes.POINT(0, 0)
            user32.ClientToScreen(hwnd, ctypes.byref(pt))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if w > 100 and h > 100:
                results.append((int(pt.x), int(pt.y), w, h))
        return True

    # Keep a reference to the wrapped callback — ctypes will GC it otherwise,
    # causing EnumWindows to silently stop enumerating mid-way.
    callback = EnumWindowsProc(_cb)
    user32.EnumWindows(callback, 0)
    if not results:
        return None

    # Prefer the smallest matching window — a dedicated game app window
    # (Chrome --app mode, standalone exe, etc.) will be far smaller than a
    # full browser window that happens to have the game in a background tab.
    results.sort(key=lambda r: r[2] * r[3])
    x, y, w, h = results[0]
    logger.info("Win32: found game window at (%d, %d) %dx%d", x, y, w, h)
    return ROI(x=x, y=y, w=w, h=h)


class MinesweeperProcessor(BaseProcessor):
    """Detects Minesweeper grid and classifies cells."""

    def __init__(self, config: MinesweeperConfig | None = None) -> None:
        self.config = config or MinesweeperConfig()
        self._grid_roi: ROI | None = self.config.grid_roi
        self._unrevealed_tmpl: np.ndarray | None = None  # loaded lazily
        # Per-row/col pixel positions for exact cell cropping (set by _detect_grid)
        self._col_xs: list[int] = []  # global x-start of each column
        self._row_ys: list[int] = []  # global y-start of each row

    def process(self, frame: np.ndarray) -> dict:
        """Process a frame → extract grid state.

        Returns:
            {
                "grid": {"rows": int, "cols": int, "cells": list[list[str]],
                         "origin": [x, y], "cell_size": [w, h]},
                "status": "playing" | "won" | "lost" | "unknown"
            }
        """
        # Auto-detect grid if not set
        if self._grid_roi is None:
            self._grid_roi = self._detect_grid(frame)
            if self._grid_roi is None:
                return {"grid": None, "status": "unknown"}

        cells = self._classify_cells_from_frame(frame)

        if cells is None:
            return {"grid": None, "status": "unknown"}

        rows = len(cells)
        cols = len(cells[0]) if rows > 0 else 0

        return {
            "grid": {
                "rows": rows,
                "cols": cols,
                "cells": cells,
                "origin": [self._grid_roi.x, self._grid_roi.y],
                "cell_size": [self.config.cell_size, self.config.cell_size],
            },
            "status": self._detect_status(frame),
        }

    def set_grid_roi(self, roi: ROI) -> None:
        """Manually set the grid region."""
        self._grid_roi = roi

    def _detect_grid(self, frame: np.ndarray) -> ROI | None:
        """Auto-detect the Minesweeper grid position.

        Strategy:
        1. Load pre-saved unrevealed cell template from disk.
        2. matchTemplate → find the single best match (anchor).
        3. From the anchor, find cell boundaries via edge detection
           (128→255 transitions in the grayscale profile).
        4. Count rows/cols by stepping along those boundaries.
        5. Return ROI covering the full grid.
        """
        import pathlib

        cs = self.config.cell_size
        fh, fw = frame.shape[:2]

        # ── Step 0: Narrow search to the game window ─────────────────────────
        window_roi = _find_game_window()
        if window_roi is not None:
            sx = max(0, window_roi.x)
            sy = max(0, window_roi.y)
            ex = min(fw, window_roi.x + window_roi.w)
            ey = min(fh, window_roi.y + window_roi.h)
            search_frame = frame[sy:ey, sx:ex]
            x_off, y_off = sx, sy
        else:
            search_frame = frame
            x_off, y_off = 0, 0

        sh, sw = search_frame.shape[:2]
        gray = cv2.cvtColor(search_frame, cv2.COLOR_BGR2GRAY)

        # ── Step 1: Load template ────────────────────────────────────────────
        tmpl_path = (
            pathlib.Path(__file__).parent.parent
            / "templates" / "minesweeper" / "unrevealed.png"
        )
        if not tmpl_path.exists():
            logger.warning("_detect_grid: template not found at %s", tmpl_path)
            return None

        tmpl = cv2.imread(str(tmpl_path))
        if tmpl is None or tmpl.shape[:2] != (cs, cs):
            logger.warning("_detect_grid: invalid template at %s", tmpl_path)
            return None

        # ── Step 2: Find anchor via matchTemplate ────────────────────────────
        result = cv2.matchTemplate(search_frame, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < 0.80:
            logger.warning(
                "_detect_grid: best match score %.3f < 0.80 — "
                "template may not match current game state.",
                max_val,
            )
            return None

        anchor_x, anchor_y = max_loc  # top-left of best-matching cell
        logger.debug(
            "Anchor cell at (%d, %d) score=%.4f",
            anchor_x, anchor_y, max_val,
        )

        # ── Step 3: Find grid boundaries via edge detection ──────────────────
        # At a body-level row (anchor_y + cs//3), scan for 128→255 transitions
        # in the horizontal grayscale profile. These mark cell boundaries with
        # exact cs-pixel spacing.
        body_y = min(anchor_y + cs // 3, sh - 1)
        h_profile = gray[body_y, :].astype(np.float64)
        h_deriv = np.diff(h_profile)
        h_peaks = np.where(h_deriv > 80)[0]

        if len(h_peaks) < 2:
            logger.warning("_detect_grid: not enough horizontal transitions (%d)", len(h_peaks))
            return None

        # Filter to peaks with ~cs spacing (ignore spurious ones)
        h_regular: list[int] = [int(h_peaks[0])]
        for i in range(1, len(h_peaks)):
            spacing = h_peaks[i] - h_regular[-1]
            if cs - 2 <= spacing <= cs + 2:
                h_regular.append(int(h_peaks[i]))

        # Each peak marks a cell boundary (shadow→highlight). Cell N starts
        # at h_regular[N] + 1. The first visible cell starts at h_regular[0]+1,
        # and there is one cell before it (partially hidden by the game frame).
        # n_cols = len(h_regular)  (each peak starts a new cell, plus 1 before)
        # But the last peak might be the grid→right-border transition, not a
        # real cell start. Verify: the cell after the last peak must fit in frame.
        n_cols = len(h_regular)
        first_cell_x = int(h_regular[0]) + 1
        last_cell_end = first_cell_x + (n_cols - 1) * cs + cs
        if last_cell_end > sw:
            n_cols -= 1  # last peak was right-border, not a cell start

        # ── Step 4: Vertical boundaries ──────────────────────────────────────
        # Scan the FULL frame (not window-clipped search_frame) so we don't
        # miss rows that extend below the detected window boundary.
        full_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        # Column position in full-frame coordinates
        mid_col_x_full = min(first_cell_x + x_off + (n_cols // 2) * cs + cs // 2, fw - 1)
        anchor_y_full = anchor_y + y_off

        v_profile = full_gray[:, mid_col_x_full].astype(np.float64)
        v_deriv = np.diff(v_profile)
        v_peaks = np.where(v_deriv > 80)[0]

        # Filter to regularly-spaced peaks BELOW the header (skip header noise).
        v_near_anchor = [int(p) for p in v_peaks if p >= anchor_y_full - cs]
        v_near_anchor.sort()

        # Find the longest run of ~cs-spaced peaks
        best_run: list[int] = []
        current_run: list[int] = []
        for p in v_near_anchor:
            if not current_run or cs - 2 <= p - current_run[-1] <= cs + 2:
                current_run.append(p)
            else:
                if len(current_run) > len(best_run):
                    best_run = current_run
                current_run = [p]
        if len(current_run) > len(best_run):
            best_run = current_run

        if len(best_run) < 2:
            # Fallback: use anchor y and standard row count
            first_cell_y = anchor_y_full
            n_rows = 16  # default expert
            logger.debug("_detect_grid: vertical fallback — anchor y=%d, n_rows=%d", anchor_y_full, n_rows)
        else:
            first_cell_y = best_run[0] + 1
            # n_rows = peaks in run + 1 (one cell before first peak)
            n_rows = len(best_run) + 1

        # Sanity check against standard Minesweeper sizes
        _EXPECTED: dict[int, int] = {9: 9, 16: 16, 30: 16}
        expected_rows = _EXPECTED.get(n_cols)
        if expected_rows is not None and abs(n_rows - expected_rows) <= 2:
            n_rows = expected_rows

        if n_rows < 2 or n_cols < 2:
            logger.warning("_detect_grid: implausible grid %d×%d", n_rows, n_cols)
            return None

        origin_x = first_cell_x + x_off
        # first_cell_y and best_run are already in full-frame coordinates
        origin_y = first_cell_y

        # Build per-row y-positions from actual transition positions.
        # This handles sub-pixel rendering where some rows are 15px instead of 16.
        self._row_ys = [origin_y]  # first row
        for p in best_run:
            row_y = int(p) + 1  # already full-frame coords
            if row_y > self._row_ys[-1]:
                self._row_ys.append(row_y)
            if len(self._row_ys) >= n_rows:
                break
        # Pad with fixed-step if we didn't get enough transitions
        while len(self._row_ys) < n_rows:
            self._row_ys.append(self._row_ys[-1] + cs)

        # Build per-col x-positions from actual transitions.
        self._col_xs = [origin_x]
        for p in h_regular:
            col_x = int(p) + 1 + x_off
            if col_x > self._col_xs[-1]:
                self._col_xs.append(col_x)
            if len(self._col_xs) >= n_cols:
                break
        while len(self._col_xs) < n_cols:
            self._col_xs.append(self._col_xs[-1] + cs)

        roi = ROI(x=origin_x, y=origin_y, w=n_cols * cs, h=n_rows * cs)
        logger.info(
            "Grid detected at (%d, %d) %dx%d  [%d rows × %d cols]",
            origin_x, origin_y, roi.w, roi.h, n_rows, n_cols,
        )
        return roi

    def _classify_cells_from_frame(self, frame: np.ndarray) -> list[list[str]] | None:
        """Classify each cell using per-row/col positions for exact alignment."""
        cs = self.config.cell_size
        fh, fw = frame.shape[:2]

        if not self._row_ys or not self._col_xs:
            return None

        cells: list[list[str]] = []
        for r, y in enumerate(self._row_ys):
            row: list[str] = []
            for c, x in enumerate(self._col_xs):
                if y + cs <= fh and x + cs <= fw:
                    cell = frame[y:y + cs, x:x + cs]
                    row.append(self._classify_single_cell(cell))
                else:
                    row.append(" ")
            cells.append(row)
        return cells

    def _load_unrevealed_template(self) -> np.ndarray | None:
        """Load the unrevealed cell template (cached)."""
        if self._unrevealed_tmpl is not None:
            return self._unrevealed_tmpl
        import pathlib
        tmpl_path = (
            pathlib.Path(__file__).parent.parent
            / "templates" / "minesweeper" / "unrevealed.png"
        )
        if tmpl_path.exists():
            t = cv2.imread(str(tmpl_path))
            if t is not None:
                self._unrevealed_tmpl = t
        return self._unrevealed_tmpl

    def _classify_single_cell(self, cell: np.ndarray) -> str:
        """Classify a single cell image.

        Returns: "?" (unrevealed), "1"-"8", " " (empty), "F" (flag), "M" (mine)
        """
        # Template match for unrevealed (tolerant of 1-2px alignment errors)
        tmpl = self._load_unrevealed_template()
        if tmpl is not None and cell.shape == tmpl.shape:
            ncc = cv2.matchTemplate(
                cell, tmpl, cv2.TM_CCOEFF_NORMED
            )
            if float(ncc[0, 0]) >= 0.60:
                return "?"

        gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
        std_dev = float(np.std(gray))

        # Revealed empty cell: very uniform color
        if std_dev < 5.0:
            return " "

        # Try color matching for numbers
        center = cell[cell.shape[0] // 4:3 * cell.shape[0] // 4,
                       cell.shape[1] // 4:3 * cell.shape[1] // 4]
        return self._match_number_color(center)

    def _match_number_color(self, center: np.ndarray) -> str:
        """Match the dominant non-background color to a number."""
        # Get the most common non-gray color
        pixels = center.reshape(-1, 3)
        # Filter out background (gray-ish) pixels
        mask = np.std(pixels.astype(float), axis=1) > 15
        colored = pixels[mask]
        if len(colored) == 0:
            return " "

        dominant = np.median(colored, axis=0).astype(int)
        dominant_tuple = tuple(dominant.tolist())

        # Find closest match
        best_match = " "
        best_dist = float("inf")
        for color_bgr, number in self.config.cell_colors_bgr.items():
            dist = sum((a - b) ** 2 for a, b in zip(dominant_tuple, color_bgr)) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_match = number

        return best_match if best_dist < 80 else " "

    def _detect_status(self, frame: np.ndarray) -> str:
        """Detect game status (playing/won/lost). Placeholder for template matching."""
        return "playing"
