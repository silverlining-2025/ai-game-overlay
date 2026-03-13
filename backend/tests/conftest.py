"""Shared test fixtures."""

import numpy as np
import pytest


@pytest.fixture
def blank_frame() -> np.ndarray:
    """A blank 800x600 BGR frame."""
    return np.zeros((600, 800, 3), dtype=np.uint8)


@pytest.fixture
def sample_minesweeper_grid() -> list[list[str]]:
    """A simple 5x5 Minesweeper grid for solver tests."""
    return [
        ["1", "1", " ", " ", " "],
        ["?", "2", "1", " ", " "],
        ["?", "?", "1", " ", " "],
        ["?", "2", "1", " ", " "],
        ["?", "1", " ", " ", " "],
    ]


@pytest.fixture
def synthetic_cell_image() -> np.ndarray:
    """A synthetic 32x32 cell image resembling an unrevealed Minesweeper cell."""
    cell = np.full((32, 32, 3), 192, dtype=np.uint8)  # gray background
    # Bright top/left border
    cell[0:2, :] = [240, 240, 240]
    cell[:, 0:2] = [240, 240, 240]
    # Dark bottom/right border
    cell[30:32, :] = [128, 128, 128]
    cell[:, 30:32] = [128, 128, 128]
    return cell


@pytest.fixture
def synthetic_number_cell() -> np.ndarray:
    """A synthetic 32x32 cell with a blue '1' (BGR: 255, 0, 0)."""
    cell = np.full((32, 32, 3), 192, dtype=np.uint8)  # gray background
    # Draw a blue region in center
    cell[8:24, 12:20] = [255, 0, 0]  # blue in BGR
    return cell
