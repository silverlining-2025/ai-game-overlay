"""Tests for the Minesweeper CV processor."""

import numpy as np

from backend.config import MinesweeperConfig, ROI
from backend.processors.minesweeper import MinesweeperProcessor


class TestMinesweeperProcessor:
    def setup_method(self):
        self.config = MinesweeperConfig(cell_size=32)
        self.processor = MinesweeperProcessor(self.config)

    def test_process_blank_frame_no_grid(self, blank_frame):
        """Processing a blank frame with no grid ROI returns unknown status."""
        result = self.processor.process(blank_frame)
        assert result["status"] == "unknown"

    def test_process_with_manual_roi(self, blank_frame):
        """With a manually set ROI, process should attempt classification."""
        self.processor.set_grid_roi(ROI(x=0, y=0, w=160, h=160))
        result = self.processor.process(blank_frame)
        # Should detect a 5x5 grid of empty cells on a blank frame
        assert result["grid"] is not None
        assert result["grid"]["rows"] == 5
        assert result["grid"]["cols"] == 5

    def test_unrevealed_cell_detection(self, synthetic_cell_image):
        """Synthetic unrevealed cell should be detected."""
        assert self.processor._is_unrevealed(
            np.mean(synthetic_cell_image, axis=2).astype(np.uint8)
        )

    def test_number_color_matching(self, synthetic_number_cell):
        """Synthetic blue '1' cell should be classified correctly."""
        result = self.processor._classify_single_cell(synthetic_number_cell)
        assert result == "1"

    def test_classify_empty_cell(self):
        """A uniform gray cell should be classified as empty."""
        cell = np.full((32, 32, 3), 192, dtype=np.uint8)
        result = self.processor._classify_single_cell(cell)
        assert result == " "

    def test_grid_classification_shape(self):
        """Grid ROI should produce correct number of rows/cols."""
        # Create a 3x3 grid of 32x32 cells (96x96 image)
        grid = np.full((96, 96, 3), 192, dtype=np.uint8)
        self.processor.set_grid_roi(ROI(x=0, y=0, w=96, h=96))
        # Create a frame large enough
        frame = np.zeros((200, 200, 3), dtype=np.uint8)
        frame[0:96, 0:96] = grid
        result = self.processor.process(frame)
        assert result["grid"]["rows"] == 3
        assert result["grid"]["cols"] == 3
