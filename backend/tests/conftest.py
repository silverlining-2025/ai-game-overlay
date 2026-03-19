"""Shared test fixtures for the AI companion overlay."""

import numpy as np
import pytest


@pytest.fixture
def blank_frame() -> np.ndarray:
    """A blank 1920x1080 BGR frame."""
    return np.zeros((1080, 1920, 3), dtype=np.uint8)


@pytest.fixture
def noisy_frame() -> np.ndarray:
    """A 1920x1080 frame with random noise (simulates active gameplay)."""
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, (1080, 1920, 3), dtype=np.uint8)


@pytest.fixture
def bright_frame() -> np.ndarray:
    """A bright 1920x1080 frame (simulates outdoor/menu)."""
    return np.full((1080, 1920, 3), 200, dtype=np.uint8)
