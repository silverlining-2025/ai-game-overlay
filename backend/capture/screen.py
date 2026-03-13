"""Screen capture with dxcam (primary) and mss (fallback)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class ScreenCapture(ABC):
    """Abstract screen capture interface."""

    def __init__(self) -> None:
        self._prev_frame: np.ndarray | None = None

    @abstractmethod
    def grab(self) -> np.ndarray | None:
        """Capture full screen. Returns BGR numpy array or None on failure."""

    @abstractmethod
    def grab_region(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        """Capture a specific region. Returns BGR numpy array or None."""

    def has_changed(self, frame: np.ndarray, threshold: float = 5.0) -> bool:
        """Check if frame differs enough from previous to warrant processing."""
        if self._prev_frame is None:
            self._prev_frame = frame
            return True
        diff = cv2.absdiff(frame, self._prev_frame)
        mean_diff = float(np.mean(diff))
        self._prev_frame = frame
        return mean_diff > threshold

    @abstractmethod
    def release(self) -> None:
        """Release capture resources."""


class DXCamCapture(ScreenCapture):
    """Windows DXGI Desktop Duplication via dxcam (~240 FPS)."""

    def __init__(self) -> None:
        super().__init__()
        import dxcam  # Windows-only
        self._camera = dxcam.create(output_color="BGR")
        logger.info("DXCam capture initialized")

    def grab(self) -> np.ndarray | None:
        frame = self._camera.grab()
        return frame

    def grab_region(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        frame = self._camera.grab(region=(x, y, x + w, y + h))
        return frame

    def release(self) -> None:
        self._camera.release()
        logger.info("DXCam capture released")


class MSSCapture(ScreenCapture):
    """Cross-platform fallback via python-mss (~50 FPS)."""

    def __init__(self) -> None:
        super().__init__()
        import mss
        self._sct = mss.mss()
        self._monitor = self._sct.monitors[1]  # primary monitor
        logger.info("MSS capture initialized (fallback mode)")

    def grab(self) -> np.ndarray | None:
        img = self._sct.grab(self._monitor)
        frame = np.array(img)[:, :, :3]  # BGRA → BGR
        return frame

    def grab_region(self, x: int, y: int, w: int, h: int) -> np.ndarray | None:
        region = {"left": x, "top": y, "width": w, "height": h}
        img = self._sct.grab(region)
        frame = np.array(img)[:, :, :3]
        return frame

    def release(self) -> None:
        self._sct.close()
        logger.info("MSS capture released")


def create_capture() -> ScreenCapture:
    """Create the best available screen capture. dxcam first, mss fallback."""
    try:
        return DXCamCapture()
    except Exception as e:
        logger.warning("dxcam unavailable (%s), falling back to mss", e)
        return MSSCapture()
