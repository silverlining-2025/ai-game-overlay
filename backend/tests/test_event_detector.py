"""Tests for the CV event detector."""

import numpy as np
from backend.cv.event_detector import EventDetector, EventSignal


class TestEventDetector:
    def setup_method(self):
        self.detector = EventDetector(game="general")

    def test_first_frame(self, blank_frame):
        """First frame should return first_frame label."""
        signal = self.detector.analyze(blank_frame)
        assert signal.label == "first_frame"
        assert signal.score == 0.5

    def test_idle_on_unchanged(self, blank_frame):
        """Two identical frames should produce idle."""
        self.detector.analyze(blank_frame)
        signal = self.detector.analyze(blank_frame)
        assert signal.label == "idle"
        assert signal.score == 0.0

    def test_scene_change_detection(self, blank_frame, bright_frame):
        """Drastically different frames should detect scene change."""
        self.detector.analyze(blank_frame)
        signal = self.detector.analyze(bright_frame)
        assert signal.score > 0.5

    def test_event_signal_fields(self, blank_frame):
        """EventSignal should have all expected fields."""
        signal = self.detector.analyze(blank_frame)
        assert isinstance(signal, EventSignal)
        assert hasattr(signal, 'score')
        assert hasattr(signal, 'motion_pct')
        assert hasattr(signal, 'motion_center')
        assert hasattr(signal, 'motion_edges')
        assert hasattr(signal, 'brightness')
        assert hasattr(signal, 'variance')
        assert hasattr(signal, 'menu_likely')
        assert hasattr(signal, 'label')

    def test_motion_detection(self, blank_frame):
        """Adding motion to center should increase score."""
        self.detector.analyze(blank_frame)
        # Create frame with motion in center
        moving = blank_frame.copy()
        h, w = moving.shape[:2]
        moving[h//4:3*h//4, w//4:3*w//4] = 200  # bright center
        signal = self.detector.analyze(moving)
        assert signal.motion_pct > 0
