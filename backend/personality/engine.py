"""Personality engine — controls WHEN and HOW the character speaks.

Based on research:
- OCC emotion model: multi-axis emotional state with decay
- Dynamic response delays increase perceived humanness (ECIS 2018)
- PogChampNet-style excitement accumulation
- Neuro-sama timing patterns

Mimics human viewing behavior:
- Silent most of the time (~80%)
- Instant bursts for surprising events
- Delayed reactions for medium events
- Idle chatter when nothing happens
- Emotional momentum (doesn't reset instantly)
- Cooldowns (won't comment twice in 2s)
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from enum import Enum

log = logging.getLogger(__name__)


class ResponseMode(Enum):
    SILENT = "silent"
    BURST = "burst"     # Quick exclamation (max_tokens: 25)
    REACT = "react"     # Normal reaction (max_tokens: 80)
    CHAT = "chat"       # Idle chatter (max_tokens: 60)


@dataclass
class EmotionalState:
    """Multi-axis emotional state (OCC model simplified).

    All values 0.0 ~ 1.0, decay over time, boosted by events.
    """
    excitement: float = 0.0     # High-energy positive (big plays, clutch moments)
    tension: float = 0.0        # Anxiety/focus (low HP, boss fight, risky plays)
    amusement: float = 0.0      # Humor (weird deaths, funny moments, glitches)
    concern: float = 0.0        # Worry (repeated failures, bad decisions)

    def dominant(self) -> str:
        """Return the strongest emotion."""
        emotions = {
            "excitement": self.excitement,
            "tension": self.tension,
            "amusement": self.amusement,
            "concern": self.concern,
        }
        best = max(emotions, key=emotions.get)
        if emotions[best] < 0.15:
            return "calm"
        return best

    def intensity(self) -> float:
        """Overall emotional intensity (0~1)."""
        return min(1.0, max(self.excitement, self.tension, self.amusement, self.concern))

    def label_kr(self) -> str:
        """Korean label for the current emotional state."""
        d = self.dominant()
        labels = {
            "excitement": "흥분",
            "tension": "긴장",
            "amusement": "재미",
            "concern": "걱정",
            "calm": "평온",
        }
        return labels.get(d, "평온")

    def decay(self, dt: float = 1.0):
        """Apply time-based decay to all emotions."""
        rate = 0.08 * dt  # decay rate per second
        self.excitement = max(0, self.excitement - rate)
        self.tension = max(0, self.tension - rate * 0.5)  # tension decays slower
        self.amusement = max(0, self.amusement - rate * 1.2)  # amusement decays faster
        self.concern = max(0, self.concern - rate * 0.7)


@dataclass
class PersonalityState:
    """Tracks timing and utterance state."""
    last_speak_time: float = 0.0
    last_event_time: float = 0.0
    speak_count: int = 0
    consecutive_silences: int = 0
    emotions: EmotionalState = field(default_factory=EmotionalState)


class PersonalityEngine:
    """Decides when to speak, how urgently, and with what energy.

    Uses event scores from the CV detector + emotional state to route
    to different response modes with natural timing.
    """

    def __init__(self):
        self.state = PersonalityState()
        now = time.time()
        self.state.last_speak_time = 0  # Allow immediate first reaction
        self.state.last_event_time = now
        self._last_update = now

        # Tunable parameters
        self.cooldown_sec = 5.0          # default cooldown (exploration pace)
        self.combat_cooldown_sec = 1.5   # faster during combat
        self.burst_cooldown_sec = 1.0    # shortest for big events
        self.idle_chat_after = 10.0      # seconds of silence before idle chat
        self.burst_threshold = 0.7       # event score to trigger burst
        self.react_threshold = 0.5       # raised from 0.4 — less chatty during exploration
        self._in_combat = False          # track combat state for dynamic cooldown
        self._idle_chat_count = 0        # consecutive idle chats (max 3)

    def decide(self, event_score: float, event_label: str) -> tuple[ResponseMode, dict]:
        """Given an event score, decide what to do."""
        now = time.time()
        dt = now - self._last_update
        self._last_update = now

        since_speak = now - self.state.last_speak_time
        since_event = now - self.state.last_event_time

        # Decay emotions
        self.state.emotions.decay(dt)

        # Boost emotions based on event
        self._apply_event_boost(event_score, event_label)

        # Track event timing and combat state
        if event_score > 0.3:
            self.state.last_event_time = now
            self._idle_chat_count = 0  # Reset idle counter on real events

        # Detect combat state from event labels
        if event_label in ("major", "scene_change") and event_score >= 0.7:
            self._in_combat = True
        elif event_label == "idle" and self.state.consecutive_silences > 5:
            self._in_combat = False

        # Dynamic cooldown based on state
        active_cooldown = self.combat_cooldown_sec if self._in_combat else self.cooldown_sec

        # --- Decision logic ---

        # BIG EVENT — burst reaction (short cooldown)
        if event_score >= self.burst_threshold and since_speak >= self.burst_cooldown_sec:
            self.state.speak_count += 1
            self.state.consecutive_silences = 0
            mood = self.state.emotions.label_kr()
            return ResponseMode.BURST, {
                "max_tokens": 50,
                "temperature": 0.8,
                "delay_sec": random.uniform(0, 0.3),
                "prompt_hint": f"짧게! 1문장! (기분: {mood})",
            }

        # MEDIUM EVENT — normal reaction (dynamic cooldown)
        if event_score >= self.react_threshold and since_speak >= active_cooldown:
            delay = random.uniform(0.5, 2.0)
            self.state.speak_count += 1
            self.state.consecutive_silences = 0
            mood = self.state.emotions.label_kr()
            intensity = self.state.emotions.intensity()
            return ResponseMode.REACT, {
                "max_tokens": 120,
                "temperature": 0.6 + intensity * 0.3,
                "delay_sec": delay,
                "prompt_hint": f"화면 변화에 반응. 1-2문장. (기분: {mood})",
            }

        # Cooldown — stay quiet
        if since_speak < active_cooldown:
            self.state.consecutive_silences += 1
            return ResponseMode.SILENT, {}

        # IDLE — nothing for a while (max 3, then go silent)
        idle_chats_in_row = getattr(self, '_idle_chat_count', 0)
        if since_event > self.idle_chat_after and since_speak > self.idle_chat_after * 0.8:
            if idle_chats_in_row >= 3:
                # Already chatted 3 times idle — go quiet
                self.state.consecutive_silences += 1
                return ResponseMode.SILENT, {}
            idle_probability = min(0.25, 0.05 + (since_speak - self.idle_chat_after) * 0.02)
            if random.random() < idle_probability:
                self.state.speak_count += 1
                self.state.consecutive_silences = 0
                self._idle_chat_count += 1
                return ResponseMode.CHAT, {
                    "max_tokens": 100,
                    "temperature": 0.9,
                    "delay_sec": random.uniform(2.0, 6.0),
                    "prompt_hint": (
                        "화면에 특별한 건 없음. 게임 관련 잡담, 독백, 혼잣말. "
                        "캐릭터 성격에 맞는 자연스러운 한마디. "
                        "화면 묘사 금지. 이전에 했던 말과 다른 주제로."
                    ),
                }

        # Nothing to say
        self.state.consecutive_silences += 1
        return ResponseMode.SILENT, {}

    def _apply_event_boost(self, score: float, label: str):
        """Boost emotional state based on event type."""
        e = self.state.emotions

        if label == "scene_change":
            e.excitement = min(1.0, e.excitement + 0.4)
        elif label == "major":
            e.excitement = min(1.0, e.excitement + 0.5)
            e.tension = min(1.0, e.tension + 0.2)
        elif label == "event":
            e.excitement = min(1.0, e.excitement + 0.25)
        elif label == "ui_event":
            e.tension = min(1.0, e.tension + 0.15)
        elif label == "idle" and self.state.consecutive_silences > 10:
            # Long idle — build slight concern/boredom
            e.concern = min(0.3, e.concern + 0.02)

    def mark_spoken(self):
        """Call AFTER a successful API response to update the cooldown timer."""
        self.state.last_speak_time = time.time()

    def get_emotion_context(self) -> str:
        """Return natural-language emotional context for the prompt."""
        e = self.state.emotions
        parts = []
        if e.excitement > 0.6:
            parts.append("매우 흥분")
        elif e.excitement > 0.3:
            parts.append("흥분")
        if e.tension > 0.6:
            parts.append("매우 긴장")
        elif e.tension > 0.3:
            parts.append("긴장")
        if e.amusement > 0.3:
            parts.append("재밌어하는 중")
        if e.concern > 0.3:
            parts.append("걱정되는 중")
        if not parts:
            return "평온"
        return ", ".join(parts)
