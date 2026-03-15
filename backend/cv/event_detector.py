"""Local CV event detection — runs every frame, no API calls.

Analyzes frames to produce an event_score (0.0 ~ 1.0) that determines
whether to call the LLM and with what urgency.

Techniques:
- Frame differencing (motion magnitude)
- Color histogram shift (scene transitions)
- Structural similarity (SSIM) for major layout changes
- Region-based change detection (UI areas vs game area)
"""

from __future__ import annotations

import cv2
import numpy as np
from dataclasses import dataclass, field
from collections import deque


@dataclass
class EventSignal:
    """Output of the event detector for a single frame."""
    score: float = 0.0          # 0.0 = nothing, 1.0 = major event
    motion_pct: float = 0.0     # % of pixels that changed
    scene_change: bool = False  # True if histogram shift indicates new scene
    ui_change: bool = False     # True if UI region changed significantly
    label: str = "idle"         # idle / minor / event / major / scene_change


class EventDetector:
    """Fast local CV event detection from game screenshots."""

    def __init__(self, game: str = "general"):
        self.game = game
        self._prev_gray: np.ndarray | None = None
        self._prev_hist: np.ndarray | None = None
        self._motion_history: deque[float] = deque(maxlen=10)
        self._baseline_motion: float = 5.0  # adaptive baseline

    def analyze(self, frame: np.ndarray) -> EventSignal:
        """Analyze a frame and return an event signal. ~2-5ms."""
        signal = EventSignal()

        # Convert to grayscale, downscale for speed
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (320, 180))

        if self._prev_gray is None:
            self._prev_gray = small
            self._prev_hist = self._calc_hist(frame)
            signal.score = 0.3  # First frame — trigger initial reaction
            signal.label = "first_frame"
            return signal

        # --- 1. Frame differencing (motion magnitude) ---
        diff = cv2.absdiff(small, self._prev_gray)
        motion_mask = (diff > 20).astype(np.uint8)  # threshold: 20/255
        motion_pct = motion_mask.sum() / motion_mask.size * 100
        signal.motion_pct = motion_pct

        # Update adaptive baseline (what "normal" motion looks like)
        self._motion_history.append(motion_pct)
        if len(self._motion_history) >= 5:
            self._baseline_motion = np.median(list(self._motion_history))

        # Motion relative to baseline
        motion_ratio = motion_pct / max(self._baseline_motion, 0.5)

        # --- 2. Color histogram comparison (scene transitions) ---
        curr_hist = self._calc_hist(frame)
        if self._prev_hist is not None:
            hist_corr = cv2.compareHist(self._prev_hist, curr_hist, cv2.HISTCMP_CORREL)
            if hist_corr < 0.7:
                signal.scene_change = True
        self._prev_hist = curr_hist

        # --- 3. UI region change detection ---
        h, w = small.shape
        # Bottom strip (UI area) — check separately
        ui_prev = self._prev_gray[int(h * 0.85):, :]
        ui_curr = small[int(h * 0.85):, :]
        ui_diff = cv2.absdiff(ui_prev, ui_curr)
        ui_change_pct = (ui_diff > 30).sum() / ui_diff.size * 100
        if ui_change_pct > 15:
            signal.ui_change = True

        # --- 4. Compute composite score ---
        score = 0.0

        if signal.scene_change:
            score = max(score, 0.8)
            signal.label = "scene_change"
        elif motion_ratio > 5.0:
            # Way more motion than normal — something big happened
            score = max(score, 0.7)
            signal.label = "major"
        elif motion_ratio > 2.0:
            score = max(score, 0.5)
            signal.label = "event"
        elif signal.ui_change and motion_pct > 3:
            # UI changed + some game motion
            score = max(score, 0.4)
            signal.label = "ui_event"
        elif motion_pct > 1.5:
            score = max(score, 0.2)
            signal.label = "minor"
        else:
            signal.label = "idle"

        signal.score = min(score, 1.0)
        self._prev_gray = small

        return signal

    def _calc_hist(self, frame: np.ndarray) -> np.ndarray:
        """Calculate color histogram for scene comparison."""
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        return hist
