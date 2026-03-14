"""Minesweeper calibration tool.

Captures a single frame (live or from file), runs grid detection, and
produces a debug overlay image. Useful for verifying ROI coords and
cell colour values before a full run.

Usage::

    # Live capture from primary display
    python -m backend.tools.calibrate

    # From a saved screenshot
    python -m backend.tools.calibrate --image path/to/screenshot.png

    # Also dump every cell as a separate PNG into debug/
    python -m backend.tools.calibrate --save-cells
    python -m backend.tools.calibrate --image shot.png --save-cells
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import cv2
import numpy as np

# ---------------------------------------------------------------------------
# Ensure the repo root is on sys.path when the module is executed directly.
# When invoked via  python -m backend.tools.calibrate  this is not needed,
# but it keeps  python backend/tools/calibrate.py  working too.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.capture.screen import create_capture  # noqa: E402
from backend.config import MinesweeperConfig, ROI  # noqa: E402
from backend.processors.minesweeper import MinesweeperProcessor  # noqa: E402

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEBUG_PNG = _REPO_ROOT / "debug_grid.png"
DEBUG_CELLS_DIR = _REPO_ROOT / "debug"

# Visual styling for the annotated image
COLOR_GRID_RECT = (0, 255, 0)    # green  — outer grid bounding box
COLOR_CELL_GRID = (255, 255, 255)  # white  — individual cell borders
COLOR_LABEL_BG = (0, 0, 0)       # black  — label background
LABEL_FONT = cv2.FONT_HERSHEY_SIMPLEX
LABEL_SCALE = 0.3
LABEL_THICKNESS = 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _acquire_frame(image_path: str | None) -> np.ndarray | None:
    """Return a BGR frame from file or live capture.

    Args:
        image_path: Path to a PNG/JPG file, or None for live capture.

    Returns:
        BGR numpy array, or None if acquisition failed.
    """
    if image_path is not None:
        frame = cv2.imread(image_path)
        if frame is None:
            logger.error("Could not read image: %s", image_path)
        else:
            logger.info("Loaded frame from file: %s  (%dx%d)", image_path, frame.shape[1], frame.shape[0])
        return frame

    logger.info("Capturing live frame …")
    cap = create_capture()
    try:
        # dxcam may return None on the very first grab; retry a few times.
        for attempt in range(5):
            frame = cap.grab()
            if frame is not None:
                logger.info(
                    "Live frame captured (attempt %d): %dx%d",
                    attempt + 1,
                    frame.shape[1],
                    frame.shape[0],
                )
                return frame
            logger.debug("Grab returned None, retrying (%d/5)…", attempt + 1)
    finally:
        cap.release()

    logger.error("Live capture failed after 5 attempts")
    return None


def _refine_grid_origin(
    frame: np.ndarray,
    approx_roi: ROI,
    cell_size: int,
    search_px: int = 16,
) -> ROI:
    """Snap the ROI origin to the nearest actual cell boundary.

    Minesweeper cells have a 1-2px border (white for unrevealed, dark for
    revealed) that makes each border row/column deviate from the neutral
    interior gray (~192).  We scan ±search_px around the approximate origin
    and pick the row/column whose mean intensity deviates most from 192 —
    that row/column is a cell border, hence the true grid origin.

    Args:
        frame:       Full BGR screenshot.
        approx_roi:  Approximate grid ROI (may be off by a few pixels).
        cell_size:   Expected cell size in pixels.
        search_px:   How many pixels to scan in each direction.

    Returns:
        A new ROI with the refined (x, y) origin and the same w, h.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    fh, fw = gray.shape

    x0, y0 = approx_roi.x, approx_roi.y
    w, h = approx_roi.w, approx_roi.h

    # --- Refine Y ---
    y_lo = max(0, y0 - search_px)
    y_hi = min(fh, y0 + search_px + 1)
    x_lo = max(0, x0)
    x_hi = min(fw, x0 + w)

    row_means = np.mean(gray[y_lo:y_hi, x_lo:x_hi], axis=1)
    deviations = np.abs(row_means.astype(float) - 192.0)
    best_y = int(y_lo + int(np.argmax(deviations)))

    # --- Refine X ---
    x_lo2 = max(0, x0 - search_px)
    x_hi2 = min(fw, x0 + search_px + 1)
    y_lo2 = max(0, y0)
    y_hi2 = min(fh, y0 + h)

    col_means = np.mean(gray[y_lo2:y_hi2, x_lo2:x_hi2], axis=0)
    deviations_x = np.abs(col_means.astype(float) - 192.0)
    best_x = int(x_lo2 + int(np.argmax(deviations_x)))

    refined = ROI(x=best_x, y=best_y, w=w, h=h)
    logger.info(
        "Origin refined: (%d, %d) → (%d, %d)  [shift: dx=%+d dy=%+d]",
        x0, y0, best_x, best_y, best_x - x0, best_y - y0,
    )
    return refined


def _estimate_smiley_roi(grid_roi: ROI, config: MinesweeperConfig) -> ROI:
    """Estimate the smiley-face button region above the grid.

    Classic WinMine places the smiley roughly centred horizontally above the
    grid, at approximately one cell-height above the top of the grid.

    Args:
        grid_roi: Detected grid region of interest.
        config:   Minesweeper configuration (provides cell_size reference).

    Returns:
        Estimated ROI for the smiley face region.
    """
    cs = config.cell_size
    smiley_w = cs
    smiley_h = cs
    smiley_x = grid_roi.x + grid_roi.w // 2 - smiley_w // 2
    smiley_y = max(0, grid_roi.y - cs - 4)
    return ROI(x=smiley_x, y=smiley_y, w=smiley_w, h=smiley_h)


def _draw_debug_overlay(
    frame: np.ndarray,
    grid_roi: ROI,
    cells: list[list[str]],
    config: MinesweeperConfig,
    row_ys: list[int] | None = None,
    col_xs: list[int] | None = None,
) -> np.ndarray:
    """Draw annotated debug overlay on a copy of *frame*.

    Draws:
    - A green rectangle around the detected grid ROI.
    - A thin white grid separating individual cells.
    - Per-cell text labels ("?" for unrevealed, or the classification).

    Uses per-row/col pixel positions when available for exact alignment.
    Falls back to fixed-pitch stepping from grid_roi origin.

    Returns:
        Annotated BGR image.
    """
    out = frame.copy()
    cs = config.cell_size
    rows = len(cells)
    cols = len(cells[0]) if rows > 0 else 0

    # Outer grid bounding box
    gx, gy = grid_roi.x, grid_roi.y
    cv2.rectangle(out, (gx, gy), (gx + grid_roi.w, gy + grid_roi.h), COLOR_GRID_RECT, 2)

    for r in range(rows):
        for c in range(cols):
            cx = col_xs[c] if col_xs and c < len(col_xs) else gx + c * cs
            cy = row_ys[r] if row_ys and r < len(row_ys) else gy + r * cs
            # Cell border
            cv2.rectangle(out, (cx, cy), (cx + cs, cy + cs), COLOR_CELL_GRID, 1)

            label = cells[r][c]
            (tw, th), _ = cv2.getTextSize(label, LABEL_FONT, LABEL_SCALE, LABEL_THICKNESS)
            tx = cx + (cs - tw) // 2
            ty = cy + (cs + th) // 2
            cv2.rectangle(out, (tx - 1, ty - th - 1), (tx + tw + 1, ty + 1), COLOR_LABEL_BG, -1)
            cv2.putText(out, label, (tx, ty), LABEL_FONT, LABEL_SCALE, (255, 255, 255), LABEL_THICKNESS)

    return out


def _save_cell_images(
    frame: np.ndarray,
    grid_roi: ROI,
    cells: list[list[str]],
    config: MinesweeperConfig,
    output_dir: Path,
    row_ys: list[int] | None = None,
    col_xs: list[int] | None = None,
) -> None:
    """Save each cell as an individual PNG in *output_dir*.

    Filenames follow the pattern  cell_R_C_CLASS.png  (zero-padded to 2 digits).
    Uses per-row/col positions when available for exact alignment.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    cs = config.cell_size
    rows = len(cells)
    cols = len(cells[0]) if rows > 0 else 0

    for r in range(rows):
        for c in range(cols):
            y0 = row_ys[r] if row_ys and r < len(row_ys) else grid_roi.y + r * cs
            x0 = col_xs[c] if col_xs and c < len(col_xs) else grid_roi.x + c * cs
            cell_img = frame[y0:y0 + cs, x0:x0 + cs]
            label = cells[r][c].replace(" ", "empty")
            filename = output_dir / f"cell_{r:02d}_{c:02d}_{label}.png"
            cv2.imwrite(str(filename), cell_img)

    logger.info("Saved %d cell images to %s", rows * cols, output_dir)


# ---------------------------------------------------------------------------
# Core calibration logic
# ---------------------------------------------------------------------------


def calibrate(
    frame: np.ndarray,
    save_cells: bool = False,
    region: ROI | None = None,
) -> None:
    """Run grid detection on *frame* and print / save calibration artefacts.

    Args:
        frame:      BGR numpy array (full screenshot or loaded PNG).
        save_cells: If True, save every cell crop to  debug/cell_R_C.png.
        region:     Optional manual ROI override.  When provided, auto-detection
                    is skipped and this ROI is used directly.
    """
    config = MinesweeperConfig()
    processor = MinesweeperProcessor(config)

    print("\n=== Minesweeper Calibration ===\n")

    # --- Grid detection (or manual override) ---
    if region is not None:
        grid_roi = region
        print(f"INFO  Using manual --region override: x={region.x}, y={region.y}, "
              f"w={region.w}, h={region.h}")
    else:
        grid_roi = processor._detect_grid(frame)  # noqa: SLF001 (intentional — calibration tool)

    if grid_roi is None:
        print("FAIL  Grid not detected.  Tips:")
        print("       • Make sure Minesweeper is visible and not minimised.")
        print("       • Try running with --image path/to/screenshot.png")
        print("       • Use --region X,Y,W,H to specify the grid area manually.")
        print("       • The window must be in Borderless Windowed or Windowed mode.")
        return

    # Store grid ROI on the processor so classification uses per-row/col positions
    processor.set_grid_roi(grid_roi)

    print(f"OK    Grid ROI  : x={grid_roi.x}, y={grid_roi.y}, "
          f"w={grid_roi.w}, h={grid_roi.h}")

    cs = config.cell_size
    row_ys = processor._row_ys  # noqa: SLF001
    col_xs = processor._col_xs  # noqa: SLF001
    rows = len(row_ys) if row_ys else grid_roi.h // cs
    cols = len(col_xs) if col_xs else grid_roi.w // cs

    print(f"OK    Cell size  : {cs}×{cs} px")
    print(f"OK    Grid size  : {rows} rows × {cols} cols")
    print(f"OK    Origin     : ({grid_roi.x}, {grid_roi.y})")

    # --- Smiley face region ---
    smiley_roi = _estimate_smiley_roi(grid_roi, config)
    print(f"INFO  Smiley ROI : x={smiley_roi.x}, y={smiley_roi.y}, "
          f"w={smiley_roi.w}, h={smiley_roi.h}  (estimated)")

    # --- Per-cell classification via the processor ---
    cells = processor._classify_cells_from_frame(frame)  # noqa: SLF001
    if cells is None:
        print("FAIL  Cell classification returned None (no row/col positions).")
        return

    rows = len(cells)
    cols = len(cells[0]) if rows else 0

    # --- Per-cell detail report ---
    print(f"\n--- Cell detail ({rows}×{cols}) ---")
    print(f"{'Row':>4}  {'Col':>4}  {'Class':>8}  {'Center BGR'}")
    print("-" * 44)

    for r in range(rows):
        for c in range(cols):
            y0 = row_ys[r] if row_ys and r < len(row_ys) else grid_roi.y + r * cs
            x0 = col_xs[c] if col_xs and c < len(col_xs) else grid_roi.x + c * cs
            label = cells[r][c]

            if label == "?":
                bgr_str = "n/a"
            else:
                fh, fw = frame.shape[:2]
                if y0 + cs <= fh and x0 + cs <= fw:
                    cell_bgr = frame[y0:y0 + cs, x0:x0 + cs]
                    cy_px = cell_bgr.shape[0] // 2
                    cx_px = cell_bgr.shape[1] // 2
                    b, g, red = int(cell_bgr[cy_px, cx_px, 0]), int(cell_bgr[cy_px, cx_px, 1]), int(cell_bgr[cy_px, cx_px, 2])
                    bgr_str = f"({b:3d}, {g:3d}, {red:3d})"
                else:
                    bgr_str = "out-of-bounds"

            print(f"{r:>4}  {c:>4}  {label:>8}  {bgr_str}")

    # --- Debug PNG ---
    debug_img = _draw_debug_overlay(frame, grid_roi, cells, config, row_ys, col_xs)
    cv2.rectangle(
        debug_img,
        (smiley_roi.x, smiley_roi.y),
        (smiley_roi.x + smiley_roi.w, smiley_roi.y + smiley_roi.h),
        (255, 255, 0),  # cyan
        2,
    )
    cv2.imwrite(str(DEBUG_PNG), debug_img)
    print(f"\nOK    Debug image saved → {DEBUG_PNG}")

    # --- Optional per-cell images ---
    if save_cells:
        _save_cell_images(frame, grid_roi, cells, config, DEBUG_CELLS_DIR, row_ys, col_xs)
        print(f"OK    Cell images saved → {DEBUG_CELLS_DIR}/")

    # --- Summary ---
    from collections import Counter
    counts = Counter(cell for row in cells for cell in row)
    total = rows * cols
    unrevealed = counts.get("?", 0)
    print("\n=== Summary ===")
    print(f"  cell_size : {cs}")
    print(f"  grid      : {rows} rows × {cols} cols  ({total} cells total)")
    print(f"  origin    : ({grid_roi.x}, {grid_roi.y})")
    print(f"  unrevealed: {unrevealed}")
    print(f"  revealed  : {total - unrevealed}")
    if total - unrevealed > 0:
        print(f"  breakdown : {dict(counts)}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def bot_reveal(grid_roi: ROI, config: MinesweeperConfig, clicks: int = 20) -> None:
    """Randomly left-click *clicks* unrevealed cells to generate a mixed board.

    Uses Win32 SendMessage so the game window doesn't need focus.  Waits 80 ms
    between clicks to let the page re-render.

    Args:
        grid_roi: Calibrated grid ROI (screen coordinates).
        config:   MinesweeperConfig (provides cell_size).
        clicks:   Number of random cells to click.
    """
    import ctypes
    import ctypes.wintypes
    import random
    import time

    cs = config.cell_size
    rows = grid_roi.h // cs
    cols = grid_roi.w // cs
    if rows == 0 or cols == 0:
        logger.warning("bot_reveal: grid has no cells")
        return

    user32 = ctypes.windll.user32
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONUP   = 0x0202
    MK_LBUTTON     = 0x0001

    # Find the game window handle
    from backend.processors.minesweeper import _find_game_window  # noqa: PLC0415
    win_roi = _find_game_window()
    if win_roi is None:
        logger.warning("bot_reveal: game window not found, using SendInput fallback")
        # Fallback: move cursor and click
        import ctypes
        INPUT_MOUSE = 0
        MOUSEEVENTF_LEFTDOWN = 0x0002
        MOUSEEVENTF_LEFTUP   = 0x0004
        MOUSEEVENTF_ABSOLUTE = 0x8000
        MOUSEEVENTF_MOVE     = 0x0001

        class MOUSEINPUT(ctypes.Structure):
            _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long),
                        ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                        ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("mi", MOUSEINPUT)]

        screen_w = user32.GetSystemMetrics(0)
        screen_h = user32.GetSystemMetrics(1)
        candidates = [(r, c) for r in range(rows) for c in range(cols)]
        random.shuffle(candidates)
        for r, c in candidates[:clicks]:
            cx = grid_roi.x + c * cs + cs // 2
            cy = grid_roi.y + r * cs + cs // 2
            ax = int(cx * 65535 / screen_w)
            ay = int(cy * 65535 / screen_h)
            down = INPUT(INPUT_MOUSE, MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTDOWN, 0, None))
            up   = INPUT(INPUT_MOUSE, MOUSEINPUT(ax, ay, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_LEFTUP,   0, None))
            ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
            time.sleep(0.05)
            ctypes.windll.user32.SendInput(1, ctypes.byref(up),   ctypes.sizeof(INPUT))
            time.sleep(0.08)
        return

    # Find the HWND for the game window
    found_hwnd: list[int] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def _cb(hwnd: int, _: int) -> bool:
        if not user32.IsWindowVisible(hwnd):
            return True
        n = user32.GetWindowTextLengthW(hwnd)
        if n == 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        if "winmine" in buf.value.lower() or "minesweeper" in buf.value.lower():
            rect = ctypes.wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            if 100 < w < 1000 and 100 < h < 1000:
                found_hwnd.append(hwnd)
        return True

    cb = EnumWindowsProc(_cb)
    user32.EnumWindows(cb, 0)
    if not found_hwnd:
        logger.warning("bot_reveal: could not find HWND")
        return

    # Sort by window area (smallest = app window)
    found_hwnd.sort(key=lambda h: (lambda r: (r.right - r.left) * (r.bottom - r.top))(
        (lambda rect: (user32.GetWindowRect(h, ctypes.byref(rect)), rect)[1])(ctypes.wintypes.RECT())
    ))
    hwnd = found_hwnd[0]

    candidates = [(r, c) for r in range(rows) for c in range(cols)]
    random.shuffle(candidates)
    clicked = 0
    for r, c in candidates:
        if clicked >= clicks:
            break
        # Cell centre relative to the window client area
        cx = (grid_roi.x - win_roi.x) + c * cs + cs // 2
        cy = (grid_roi.y - win_roi.y) + r * cs + cs // 2
        lparam = (cy << 16) | (cx & 0xFFFF)
        user32.SendMessageW(hwnd, WM_LBUTTONDOWN, MK_LBUTTON, lparam)
        user32.SendMessageW(hwnd, WM_LBUTTONUP,   0,           lparam)
        time.sleep(0.08)
        clicked += 1

    print(f"OK    Bot clicked {clicked} cells.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.tools.calibrate",
        description="Minesweeper calibration: detect grid and inspect cell colours.",
    )
    parser.add_argument(
        "--image",
        metavar="PATH",
        default=None,
        help="Load frame from a PNG/JPG file instead of capturing the screen.",
    )
    parser.add_argument(
        "--save-cells",
        action="store_true",
        help="Save each cell crop as debug/cell_R_C.png for manual inspection.",
    )
    parser.add_argument(
        "--region",
        metavar="X,Y,W,H",
        default=None,
        help=(
            "Skip auto-detection and use this ROI directly.  "
            "Provide four comma-separated integers: X,Y,W,H  "
            "(e.g. --region 200,150,480,256)."
        ),
    )
    parser.add_argument(
        "--bot",
        metavar="N",
        type=int,
        default=0,
        help="Before calibrating, randomly click N cells to reveal a mixed board state.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main() -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-8s %(name)s — %(message)s",
    )

    # --bot: first detect grid, click N cells, then re-capture and calibrate
    if args.bot > 0 and args.image is None:
        frame = _acquire_frame(None)
        if frame is None:
            sys.exit(1)
        config = MinesweeperConfig()
        from backend.processors.minesweeper import MinesweeperProcessor  # noqa: PLC0415
        proc = MinesweeperProcessor(config)
        roi = proc._detect_grid(frame)  # noqa: SLF001
        if roi is None:
            print("FAIL  Cannot locate grid for bot clicks. Calibrating anyway.")
        else:
            print(f"INFO  Bot: clicking {args.bot} random cells …")
            bot_reveal(roi, config, clicks=args.bot)
            import time; time.sleep(0.5)  # let the page settle

    frame = _acquire_frame(args.image)
    if frame is None:
        sys.exit(1)

    region: ROI | None = None
    if args.region is not None:
        try:
            parts = [int(v.strip()) for v in args.region.split(",")]
            if len(parts) != 4:
                raise ValueError("Expected exactly 4 values")
            region = ROI(x=parts[0], y=parts[1], w=parts[2], h=parts[3])
        except ValueError as exc:
            logger.error("Invalid --region value %r: %s", args.region, exc)
            sys.exit(1)

    calibrate(frame, save_cells=args.save_cells, region=region)


if __name__ == "__main__":
    main()
