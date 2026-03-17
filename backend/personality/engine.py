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
        self.idle_chat_after = 45.0      # seconds before first idle chat (silence is closeness)
        self.burst_threshold = 0.7       # event score to trigger burst
        self.react_threshold = 0.5       # raised from 0.4 — less chatty during exploration
        self._in_combat = False          # track combat state for dynamic cooldown
        self._idle_chat_count = 0        # consecutive idle chats
        self._scene_comment_count = 0    # comments on same scene state
        self._last_scene_label = ""      # last scene state we commented on

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
            self._scene_comment_count = 0  # New scene, reset budget
            self._last_scene_label = event_label
        elif event_label == "idle" and self.state.consecutive_silences > 5:
            self._in_combat = False

        # Track same-scene comments — if scene hasn't changed, budget exhausts
        if event_label == self._last_scene_label and event_label not in ("scene_change", "major"):
            self._scene_comment_count += 0  # Don't increment on silent cycles
        elif event_label != self._last_scene_label:
            self._scene_comment_count = 0
            self._last_scene_label = event_label

        # Dynamic cooldown based on state + emotional intensity
        active_cooldown = self.combat_cooldown_sec if self._in_combat else self.cooldown_sec

        # Emotional silence amplifier — calm = quieter
        if self.state.emotions.intensity() < 0.15 and not self._in_combat:
            active_cooldown *= 2.0  # Double cooldown when calm

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
                "prompt_hint": f"지금 화면에서 변한 것에만 반응. 감탄사 위주! 1문장! 설명 금지! (기분: {mood})",
            }

        # Scene budget — max 2 comments on same unchanged scene
        if self._scene_comment_count >= 2 and event_score < self.burst_threshold:
            self.state.consecutive_silences += 1
            return ResponseMode.SILENT, {}

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
                "prompt_hint": f"이전 화면과 뭐가 달라졌는지 파악하고 그것에만 반응. 안 변한 건 무시. 1-2문장. (기분: {mood})",
            }

        # Cooldown — stay quiet
        if since_speak < active_cooldown:
            self.state.consecutive_silences += 1
            return ResponseMode.SILENT, {}

        # IDLE — exponential backoff (1st: 45s, 2nd: 120s, 3rd: 300s, then silent forever)
        idle_thresholds = [self.idle_chat_after, self.idle_chat_after * 2.5, self.idle_chat_after * 6]
        if self._idle_chat_count >= len(idle_thresholds):
            # Fully exhausted — go silent until real event
            self.state.consecutive_silences += 1
            return ResponseMode.SILENT, {}
        current_idle_threshold = idle_thresholds[self._idle_chat_count]
        if since_event > current_idle_threshold and since_speak > current_idle_threshold * 0.8:
            idle_probability = 0.15
            if random.random() < idle_probability:
                self.state.speak_count += 1
                self.state.consecutive_silences = 0
                self._idle_chat_count += 1

                # Pick a specific topic direction — never generic "잡담"
                topic_directions = [
                    "플레이어에게 질문해봐. 예: '이 게임 얼마나 했어?', '다른 캐릭터 해봤어?'",
                    "게임 자체에 대한 감상. 예: '이 게임 BGM 좋지 않아?', '그래픽 괜찮네'",
                    "다른 게임이나 추억 얘기. 예: '이거 예전에 했던 거랑 비슷한데', '옛날 생각난다'",
                    "캐릭터 자신의 상태. 예: '아 졸려', '배고프다', '심심해서 죽겠네'",
                    "유머/엉뚱한 관찰. 화면에 있는 뭔가를 웃기게 해석해봐.",
                    "가벼운 조언. 예: '저장 했어?', '인벤토리 정리 좀 해'",
                ]
                # Don't repeat the same direction
                direction = random.choice(topic_directions)

                return ResponseMode.CHAT, {
                    "max_tokens": 80,
                    "temperature": 0.9,
                    "delay_sec": random.uniform(2.0, 6.0),
                    "prompt_hint": (
                        f"화면 묘사 금지. 이 방향으로 한마디만: {direction}"
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
        self._scene_comment_count += 1

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
