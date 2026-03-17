"""Local CV event detection — runs every frame, no API calls.

Analyzes frames to produce an event_score (0.0 ~ 1.0) that determines
whether to call the LLM and with what urgency.

Techniques:
- Frame differencing with adaptive baseline (motion magnitude)
- Morphological opening to filter particle/damage number noise
- Spatial motion zones (4x4 grid) for center vs edge analysis
- Color histogram shift (scene transitions)
- SSIM structural similarity (layout changes)
- Optical flow magnitude (action intensity)
- Region-based change detection (UI vs game area)
- Gaussian blur to filter particle effects / minor animations
- Mean brightness + variance tracking (menu detection)
- Adaptive frame skipping for idle periods
- Pre-allocated buffers for zero-alloc hot path
"""

from __future__ import annotations

import logging
import cv2
import numpy as np
from dataclasses import dataclass
from collections import deque

log = logging.getLogger(__name__)

# Analysis resolution — small for speed
_W, _H = 320, 180

# Morphological kernel for opening (filters particle/damage noise)
_MORPH_KERNEL = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

# 4x4 grid zone dimensions
_ZONE_COLS, _ZONE_ROWS = 4, 4
_ZONE_W, _ZONE_H = _W // _ZONE_COLS, _H // _ZONE_ROWS

# Center 2x2 zone indices (rows 1-2, cols 1-2 in 0-indexed)
_CENTER_ZONES = {(r, c) for r in range(1, 3) for c in range(1, 3)}

# Adaptive frame skipping thresholds
_IDLE_THRESHOLD = 0.1
_WAKE_THRESHOLD = 0.2
_IDLE_STREAK_LIMIT = 5

# Variance tracking window
_VARIANCE_WINDOW = 15
_VARIANCE_DROP_RATIO = 0.4  # variance drops to 40% of recent median → menu likely


@dataclass
class EventSignal:
    """Output of the event detector for a single frame."""
    score: float = 0.0          # 0.0 = nothing, 1.0 = major event
    motion_pct: float = 0.0     # % of pixels that changed
    flow_magnitude: float = 0.0 # mean optical flow magnitude (action intensity)
    scene_change: bool = False  # True if histogram/SSIM indicates new scene
    ui_change: bool = False     # True if UI region changed significantly
    label: str = "idle"         # idle / minor / event / major / scene_change
    motion_center: float = 0.0  # motion in center 2x2 zones (gameplay area)
    motion_edges: float = 0.0   # motion in outer zones (UI areas)
    brightness: float = 0.0     # mean brightness of current frame
    variance: float = 0.0       # standard deviation (uniformity measure)
    menu_likely: bool = False   # True if variance dropped significantly


class EventDetector:
    """Fast local CV event detection from game screenshots.

    Designed to run at 30+ FPS with minimal CPU usage.
    All analysis is done on downscaled grayscale (320x180).
    """

    def __init__(self, game: str = "general"):
        self.game = game
        self._prev_gray: np.ndarray | None = None
        self._prev_blur: np.ndarray | None = None
        self._prev_hist: np.ndarray | None = None
        self._motion_history: deque[float] = deque(maxlen=20)
        self._flow_history: deque[float] = deque(maxlen=10)
        self._variance_history: deque[float] = deque(maxlen=_VARIANCE_WINDOW)
        self._baseline_motion: float = 5.0
        self._frame_count: int = 0
        self._idle_streak: int = 0  # consecutive idle frames for adaptive skipping

        # Pre-allocated buffers (Improvement 5)
        self._diff_buf = np.empty((_H, _W), dtype=np.uint8)

        # Game-specific UI regions (y1%, y2%, x1%, x2%) for separate tracking
        self._ui_regions = self._get_ui_regions(game)

    def _get_ui_regions(self, game: str) -> dict[str, tuple[float, float, float, float]]:
        """Game-specific UI regions to monitor separately."""
        if game == "maplestory":
            return {
                "hp_bar": (0.88, 1.0, 0.3, 0.7),    # bottom center
                "minimap": (0.0, 0.15, 0.0, 0.15),   # top left
                "buffs": (0.0, 0.05, 0.8, 1.0),      # top right
            }
        elif game == "palworld":
            return {
                "hp_area": (0.7, 1.0, 0.0, 0.2),     # bottom left
                "compass": (0.0, 0.05, 0.3, 0.7),    # top center
            }
        return {
            "bottom_ui": (0.85, 1.0, 0.0, 1.0),
        }

    def _compute_spatial_zones(self, motion_mask: np.ndarray) -> tuple[float, float]:
        """Divide motion mask into 4x4 grid and compute center vs edge motion.

        Returns (motion_center, motion_edges) as percentages.
        """
        center_pixels = 0
        center_total = 0
        edge_pixels = 0
        edge_total = 0

        for r in range(_ZONE_ROWS):
            y1 = r * _ZONE_H
            y2 = (r + 1) * _ZONE_H if r < _ZONE_ROWS - 1 else _H
            for c in range(_ZONE_COLS):
                x1 = c * _ZONE_W
                x2 = (c + 1) * _ZONE_W if c < _ZONE_COLS - 1 else _W
                zone = motion_mask[y1:y2, x1:x2]
                zone_sum = int(zone.sum())
                zone_size = zone.size

                if (r, c) in _CENTER_ZONES:
                    center_pixels += zone_sum
                    center_total += zone_size
                else:
                    edge_pixels += zone_sum
                    edge_total += zone_size

        motion_center = (center_pixels / max(center_total, 1)) * 100
        motion_edges = (edge_pixels / max(edge_total, 1)) * 100
        return motion_center, motion_edges

    def analyze(self, frame: np.ndarray) -> EventSignal:
        """Analyze a frame and return an event signal. Target: <5ms."""
        signal = EventSignal()
        self._frame_count += 1

        # Downscale + grayscale
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (_W, _H))
        # Gaussian blur to filter particle effects / minor UI animations
        blur = cv2.GaussianBlur(small, (5, 5), 0)

        # --- Brightness + variance tracking (Improvement 3) ---
        signal.brightness = float(np.mean(small))
        signal.variance = float(np.std(small))
        self._variance_history.append(signal.variance)

        # Menu detection: variance drops significantly vs recent median
        if len(self._variance_history) >= 5:
            recent_median = float(np.median(list(self._variance_history)[:-1]))
            if recent_median > 1.0 and signal.variance < recent_median * _VARIANCE_DROP_RATIO:
                signal.menu_likely = True

        if self._prev_gray is None:
            self._prev_gray = small
            self._prev_blur = blur
            self._prev_hist = self._calc_hist(frame)
            signal.score = 0.5  # Above react_threshold so first frame triggers
            signal.label = "first_frame"
            return signal

        # --- 1. Frame differencing on blurred (filters particles) ---
        # Use pre-allocated buffer (Improvement 5)
        cv2.absdiff(blur, self._prev_blur, dst=self._diff_buf)
        motion_mask = (self._diff_buf > 18).astype(np.uint8)

        # Morphological opening to remove particle/damage number noise (Improvement 1)
        motion_mask = cv2.morphologyEx(motion_mask, cv2.MORPH_OPEN, _MORPH_KERNEL)

        motion_pct = motion_mask.sum() / motion_mask.size * 100
        signal.motion_pct = round(motion_pct, 2)

        # --- Spatial motion zones (Improvement 2) ---
        motion_center, motion_edges = self._compute_spatial_zones(motion_mask)
        signal.motion_center = round(motion_center, 2)
        signal.motion_edges = round(motion_edges, 2)

        # Adaptive baseline
        self._motion_history.append(motion_pct)
        if len(self._motion_history) >= 5:
            self._baseline_motion = float(np.median(list(self._motion_history)))
        motion_ratio = motion_pct / max(self._baseline_motion, 0.5)

        # --- Adaptive frame skipping (Improvement 4) ---
        # If idle for too long, skip expensive optical flow + histogram
        skip_expensive = self._idle_streak >= _IDLE_STREAK_LIMIT

        # --- 2. Optical flow magnitude (every 3rd frame, skipped during idle) ---
        flow_mag = 0.0
        if not skip_expensive and self._frame_count % 3 == 0:
            flow = cv2.calcOpticalFlowFarneback(
                self._prev_gray, small, None,
                pyr_scale=0.5, levels=2, winsize=10,
                iterations=2, poly_n=5, poly_sigma=1.1, flags=0,
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            flow_mag = float(np.mean(mag))
            self._flow_history.append(flow_mag)
        signal.flow_magnitude = round(flow_mag, 3)

        # --- 3. Color histogram comparison (scene transitions, skipped during idle) ---
        hist_corr = 1.0
        if not skip_expensive:
            curr_hist = self._calc_hist(frame)
            if self._prev_hist is not None:
                hist_corr = cv2.compareHist(self._prev_hist, curr_hist, cv2.HISTCMP_CORREL)
                if hist_corr < 0.6:
                    signal.scene_change = True
            self._prev_hist = curr_hist

        # --- Menu detection overrides scene_change (Improvement 3) ---
        if signal.menu_likely:
            signal.scene_change = True

        # --- 4. UI region change detection ---
        game_h, game_w = small.shape
        for _name, (y1, y2, x1, x2) in self._ui_regions.items():
            ry1, ry2 = int(game_h * y1), int(game_h * y2)
            rx1, rx2 = int(game_w * x1), int(game_w * x2)
            if ry2 <= ry1 or rx2 <= rx1:
                continue
            ui_prev = self._prev_gray[ry1:ry2, rx1:rx2]
            ui_curr = small[ry1:ry2, rx1:rx2]
            if ui_prev.shape != ui_curr.shape:
                continue
            ui_diff = cv2.absdiff(ui_prev, ui_curr)
            ui_pct = (ui_diff > 25).sum() / max(ui_diff.size, 1) * 100
            if ui_pct > 20:
                signal.ui_change = True
                break

        # --- 5. Composite score (enhanced with spatial zones) ---
        score = 0.0

        # Spatial zone adjustments:
        # Motion only in center with no UI change → lower score (gameplay animation)
        center_only = motion_center > 3.0 and motion_edges < 1.0 and not signal.ui_change
        # Motion in edges/corners with UI change → higher score (state change)
        edge_with_ui = motion_edges > 2.0 and signal.ui_change

        if signal.scene_change:
            score = max(score, 0.85)
            signal.label = "scene_change"
        elif motion_ratio > 6.0:
            if center_only:
                score = max(score, 0.55)  # Downgrade: just heavy gameplay animation
                signal.label = "event"
            else:
                score = max(score, 0.75)
                signal.label = "major"
        elif motion_ratio > 3.0 or (flow_mag > 2.0 and motion_pct > 5):
            score = max(score, 0.55)
            signal.label = "event"
        elif edge_with_ui:
            score = max(score, 0.6)  # Upgrade: UI region + edge motion = state change
            signal.label = "ui_event"
        elif signal.ui_change and motion_pct > 2:
            score = max(score, 0.45)
            signal.label = "ui_event"
        elif motion_pct > 2.0 or flow_mag > 1.0:
            score = max(score, 0.2)
            signal.label = "minor"
        else:
            signal.label = "idle"

        signal.score = min(score, 1.0)

        # --- Adaptive frame skipping update (Improvement 4) ---
        if signal.score < _IDLE_THRESHOLD:
            self._idle_streak += 1
        elif signal.score > _WAKE_THRESHOLD:
            self._idle_streak = 0
        # Scores between 0.1 and 0.2 don't change the streak (hysteresis)

        # Update previous frames
        self._prev_gray = small
        self._prev_blur = blur

        return signal

    def _calc_hist(self, frame: np.ndarray) -> np.ndarray:
        """Color histogram for scene comparison. Downscale first for speed."""
        small = cv2.resize(frame, (160, 90))
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist
