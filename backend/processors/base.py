"""Base processor and shared CV utilities."""

from __future__ import annotations

from abc import ABC, abstractmethod

import cv2
import numpy as np

from backend.config import ROI


class BaseProcessor(ABC):
    """Abstract processor for a specific game."""

    @abstractmethod
    def process(self, frame: np.ndarray) -> dict:
        """Process a frame and return structured game state data."""

    # --- Shared utilities ---

    @staticmethod
    def crop_roi(frame: np.ndarray, roi: ROI) -> np.ndarray:
        """Crop frame to a region of interest."""
        return frame[roi.slice]

    @staticmethod
    def color_threshold(
        roi: np.ndarray,
        hsv_lower: tuple[int, int, int],
        hsv_upper: tuple[int, int, int],
    ) -> float:
        """Return fill percentage (0-1) of pixels within HSV color range."""
        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(
            hsv,
            np.array(hsv_lower, dtype=np.uint8),
            np.array(hsv_upper, dtype=np.uint8),
        )
        total = mask.size
        if total == 0:
            return 0.0
        return float(cv2.countNonZero(mask)) / total

    @staticmethod
    def template_match(
        image: np.ndarray,
        template: np.ndarray,
        threshold: float = 0.85,
    ) -> list[tuple[int, int, float]]:
        """Find template matches. Returns list of (x, y, confidence)."""
        if len(image.shape) == 3:
            image_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            image_gray = image
        if len(template.shape) == 3:
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            template_gray = template

        result = cv2.matchTemplate(image_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)
        matches = []
        for pt in zip(*locations[::-1]):
            matches.append((int(pt[0]), int(pt[1]), float(result[pt[1], pt[0]])))
        return matches
