"""Tests for the personality engine."""

from backend.personality.engine import PersonalityEngine, ResponseMode, EmotionalState


class TestEmotionalState:
    def test_dominant_calm(self):
        """Low emotions should return calm."""
        e = EmotionalState()
        assert e.dominant() == "calm"

    def test_dominant_excitement(self):
        """High excitement should be dominant."""
        e = EmotionalState(excitement=0.8)
        assert e.dominant() == "excitement"

    def test_decay(self):
        """Emotions should decay over time."""
        e = EmotionalState(excitement=1.0, tension=1.0)
        e.decay(dt=5.0)
        assert e.excitement < 1.0
        assert e.tension < 1.0
        assert e.excitement >= 0.0

    def test_intensity(self):
        """Intensity should reflect the strongest emotion."""
        e = EmotionalState(excitement=0.8, tension=0.3)
        assert e.intensity() == 0.8


class TestPersonalityEngine:
    def setup_method(self):
        self.engine = PersonalityEngine()

    def test_first_reaction_allowed(self):
        """First event should not be blocked by cooldown."""
        mode, config = self.engine.decide(0.8, "major")
        assert mode == ResponseMode.BURST

    def test_low_score_silent(self):
        """Low score should result in silence."""
        mode, _ = self.engine.decide(0.05, "idle")
        assert mode == ResponseMode.SILENT

    def test_mark_spoken_updates_time(self):
        """mark_spoken should update last_speak_time."""
        import time
        before = self.engine.state.last_speak_time
        time.sleep(0.01)
        self.engine.mark_spoken()
        assert self.engine.state.last_speak_time > before

    def test_mood_coloring_ko(self):
        """Korean mood coloring should return Korean text."""
        text = self.engine.get_mood_coloring(locale="ko")
        assert isinstance(text, str)
        assert len(text) > 0

    def test_mood_coloring_en(self):
        """English mood coloring should return English text."""
        text = self.engine.get_mood_coloring(locale="en")
        assert isinstance(text, str)
        # Should contain English words, not Korean
        assert "tone" in text.lower() or "energy" in text.lower() or "relaxed" in text.lower()

    def test_burst_config(self):
        """BURST mode should have low max_tokens and quick delay."""
        mode, config = self.engine.decide(0.9, "major")
        assert mode == ResponseMode.BURST
        assert config["max_tokens"] <= 50
        assert config["delay_sec"] < 1.0

    def test_should_disagree_returns_none_normally(self):
        """Without death patterns, disagreement should be None."""
        result = self.engine.should_disagree({})
        assert result is None
