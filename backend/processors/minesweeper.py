"""Minesweeper grid detection and cell classification via CV."""

from __future__ import annotations

import logging

import cv2
import numpy as np

from backend.config import MinesweeperConfig, ROI
from .base import BaseProcessor

logger = logging.getLogger(__name__)


class MinesweeperProcessor(BaseProcessor):
    """Detects Minesweeper grid and classifies cells."""

    def __init__(self, config: MinesweeperConfig | None = None) -> None:
        self.config = config or MinesweeperConfig()
        self._grid_roi: ROI | None = self.config.grid_roi

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

        roi = self.crop_roi(frame, self._grid_roi)
        cells = self._classify_cells(roi)

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
        """Auto-detect the Minesweeper grid via contour analysis."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Look for the largest roughly rectangular contour
        best: ROI | None = None
        best_area = 0
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            area = w * h
            aspect = w / h if h > 0 else 0
            # Grid should be roughly square and reasonably large
            if area > best_area and 0.5 < aspect < 2.0 and area > 10000:
                best = ROI(x=x, y=y, w=w, h=h)
                best_area = area

        if best:
            logger.info("Auto-detected grid at (%d, %d) size %dx%d", best.x, best.y, best.w, best.h)
        else:
            logger.warning("Could not auto-detect Minesweeper grid")
        return best

    def _classify_cells(self, grid_roi: np.ndarray) -> list[list[str]] | None:
        """Classify each cell in the grid ROI."""
        h, w = grid_roi.shape[:2]
        cs = self.config.cell_size
        rows = h // cs
        cols = w // cs
        if rows == 0 or cols == 0:
            return None

        cells: list[list[str]] = []
        for r in range(rows):
            row: list[str] = []
            for c in range(cols):
                cell = grid_roi[r * cs:(r + 1) * cs, c * cs:(c + 1) * cs]
                row.append(self._classify_single_cell(cell))
            cells.append(row)
        return cells

    def _classify_single_cell(self, cell: np.ndarray) -> str:
        """Classify a single cell image.

        Returns: "?" (unrevealed), "1"-"8", " " (empty), "F" (flag), "M" (mine)
        """
        gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
        std_dev = float(np.std(gray))

        # Unrevealed cells have a 3D raised look → higher edge contrast
        if self._is_unrevealed(gray):
            return "?"

        # Revealed empty cell: very uniform color
        if std_dev < 5.0:
            return " "

        # Try color matching for numbers
        center = cell[cell.shape[0] // 4:3 * cell.shape[0] // 4,
                       cell.shape[1] // 4:3 * cell.shape[1] // 4]
        return self._match_number_color(center)

    def _is_unrevealed(self, gray_cell: np.ndarray) -> bool:
        """Check if cell has the 3D raised border typical of unrevealed cells."""
        h, w = gray_cell.shape
        top_strip = gray_cell[0:2, :]
        left_strip = gray_cell[:, 0:2]
        bottom_strip = gray_cell[h - 2:h, :]
        right_strip = gray_cell[:, w - 2:w]
        # Unrevealed: bright top/left, dark bottom/right
        top_mean = float(np.mean(top_strip))
        bottom_mean = float(np.mean(bottom_strip))
        return (top_mean - bottom_mean) > 30

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
