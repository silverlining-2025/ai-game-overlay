"""OCR engine wrapping EasyOCR with lazy initialization."""

from __future__ import annotations

import logging

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class OCREngine:
    """Lazy-loaded EasyOCR wrapper for Korean + English text extraction."""

    def __init__(self, languages: list[str] | None = None, gpu: bool = True) -> None:
        self._languages = languages or ["ko", "en"]
        self._gpu = gpu
        self._reader = None  # lazy init

    def _ensure_reader(self) -> None:
        if self._reader is None:
            import easyocr
            logger.info("Loading EasyOCR (%s, gpu=%s)...", self._languages, self._gpu)
            self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
            logger.info("EasyOCR loaded")

    def read_text(
        self,
        image: np.ndarray,
        preprocess: bool = True,
    ) -> list[str]:
        """Extract text from an image region.

        Args:
            image: BGR numpy array (cropped to text region for best results)
            preprocess: Apply grayscale + threshold + denoise before OCR

        Returns:
            List of detected text strings
        """
        self._ensure_reader()

        if preprocess:
            image = self._preprocess(image)

        results = self._reader.readtext(image, detail=0)
        return [text.strip() for text in results if text.strip()]

    def read_text_with_boxes(
        self,
        image: np.ndarray,
        preprocess: bool = True,
    ) -> list[tuple[list, str, float]]:
        """Extract text with bounding boxes and confidence.

        Returns:
            List of (bbox, text, confidence)
        """
        self._ensure_reader()

        if preprocess:
            image = self._preprocess(image)

        return self._reader.readtext(image)

    @staticmethod
    def _preprocess(image: np.ndarray) -> np.ndarray:
        """Preprocess image for better OCR accuracy."""
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        # Adaptive threshold for varying backgrounds
        binary = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        # Light denoise
        denoised = cv2.fastNlMeansDenoising(binary, h=10)
        return denoised
