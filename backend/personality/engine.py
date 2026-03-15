"""Personality engine — controls WHEN and HOW the character speaks.

Mimics human viewing behavior:
- Silent most of the time
- Instant reactions to big events
- Delayed reactions to medium events
- Idle chatter when nothing happens
- Excitement momentum (doesn't reset to neutral instantly)
- Cooldowns (won't comment twice in 2s)
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum


class ResponseMode(Enum):
    SILENT = "silent"         # Don't say anything
    BURST = "burst"           # Quick exclamation (max_tokens: 25)
    REACT = "react"           # Normal reaction (max_tokens: 80)
    CHAT = "chat"             # Idle chatter (max_tokens: 60)


@dataclass
class PersonalityState:
    """Tracks the character's emotional/timing state."""
    excitement: float = 0.0       # 0.0 ~ 1.0, decays over time
    last_speak_time: float = 0.0  # timestamp of last utterance
    last_event_time: float = 0.0  # timestamp of last detected event
    idle_since: float = 0.0       # how long since last significant event
    speak_count: int = 0          # total utterances this session
    consecutive_silences: int = 0 # how many cycles we've been quiet
    pending_thought: str = ""     # held thought to deliver later


class PersonalityEngine:
    """Decides when to speak, how urgently, and with what energy."""

    def __init__(self):
        self.state = PersonalityState()
        self.state.last_speak_time = time.time()
        self.state.last_event_time = time.time()
        self.state.idle_since = time.time()

        # Tunable parameters
        self.cooldown_sec = 2.0          # min seconds between utterances
        self.idle_chat_after = 12.0      # seconds of silence before idle chat
        self.excitement_decay = 0.15     # per-cycle decay
        self.burst_threshold = 0.7       # event score to trigger burst
        self.react_threshold = 0.4       # event score to trigger react

    def decide(self, event_score: float, event_label: str) -> tuple[ResponseMode, dict]:
        """Given an event score, decide what to do.

        Returns (mode, config) where config has:
          max_tokens, temperature, delay_sec, prompt_hint
        """
        now = time.time()
        since_last_speak = now - self.state.last_speak_time
        since_last_event = now - self.state.last_event_time

        # Update excitement (decay toward 0, boost on events)
        self.state.excitement = max(0, self.state.excitement - self.excitement_decay)
        if event_score > 0.4:
            self.state.excitement = min(1.0, self.state.excitement + event_score * 0.5)
            self.state.last_event_time = now
            self.state.idle_since = now

        # --- Decision logic ---

        # Cooldown check — don't spam
        if since_last_speak < self.cooldown_sec and event_score < self.burst_threshold:
            self.state.consecutive_silences += 1
            return ResponseMode.SILENT, {}

        # BIG EVENT — instant burst reaction
        if event_score >= self.burst_threshold:
            self.state.last_speak_time = now
            self.state.speak_count += 1
            self.state.consecutive_silences = 0
            return ResponseMode.BURST, {
                "max_tokens": 25,
                "temperature": 0.8,
                "delay_sec": 0,
                "prompt_hint": "짧게! 감탄사 위주! 1문장!",
            }

        # MEDIUM EVENT — normal reaction with slight delay
        if event_score >= self.react_threshold:
            delay = random.uniform(0.3, 1.5)
            self.state.last_speak_time = now
            self.state.speak_count += 1
            self.state.consecutive_silences = 0
            return ResponseMode.REACT, {
                "max_tokens": 80,
                "temperature": 0.7,
                "delay_sec": delay,
                "prompt_hint": "화면 변화에 반응. 캐릭터답게.",
            }

        # IDLE — nothing happening for a while
        if since_last_event > self.idle_chat_after and since_last_speak > self.idle_chat_after:
            # Don't idle chat too often
            if random.random() < 0.4:  # 40% chance to speak during idle
                self.state.last_speak_time = now
                self.state.speak_count += 1
                self.state.consecutive_silences = 0
                self.state.idle_since = now
                return ResponseMode.CHAT, {
                    "max_tokens": 60,
                    "temperature": 0.9,
                    "delay_sec": random.uniform(1, 3),
                    "prompt_hint": (
                        "화면에 특별한 건 없음. 게임 관련 잡담, 독백, 혼잣말. "
                        "캐릭터 성격에 맞는 자연스러운 한마디."
                    ),
                }

        # MINOR or nothing — stay quiet
        self.state.consecutive_silences += 1
        return ResponseMode.SILENT, {}

    def get_excitement_label(self) -> str:
        """Human-readable excitement level."""
        e = self.state.excitement
        if e > 0.8:
            return "극도로 흥분"
        elif e > 0.5:
            return "흥분"
        elif e > 0.3:
            return "관심"
        elif e > 0.1:
            return "약간 관심"
        return "평온"
