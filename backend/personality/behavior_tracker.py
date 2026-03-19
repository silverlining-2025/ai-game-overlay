"""Tracks player behavior patterns for unprompted observations.

Detects patterns like:
- Death frequency and locations
- Playstyle (aggressive/cautious/explorer/builder)
- Session duration and activity distribution
- Repeated failures at same spot
- Risk tolerance (fighting at low HP)
"""

import time
from dataclasses import dataclass, field
from collections import deque


@dataclass
class BehaviorTracker:
    session_start: float = field(default_factory=time.time)
    death_count: int = 0
    death_locations: list = field(default_factory=list)
    activity_time: dict = field(default_factory=lambda: {})  # activity -> seconds
    last_activity: str = ""
    last_activity_start: float = field(default_factory=time.time)
    combat_count: int = 0
    capture_count: int = 0
    menu_opens: int = 0
    observation_cooldown: float = 0  # timestamp of last observation

    def update(self, session_state: dict, event_label: str, emotions_tension: float):
        """Call every cycle to update tracking."""
        now = time.time()
        activity = session_state.get("activity", "idle")

        # Track activity duration
        if activity != self.last_activity:
            if self.last_activity and self.last_activity in self.activity_time:
                self.activity_time[self.last_activity] += now - self.last_activity_start
            elif self.last_activity:
                self.activity_time[self.last_activity] = now - self.last_activity_start
            self.last_activity = activity
            self.last_activity_start = now

        # Track events
        if event_label == "scene_change" and emotions_tension > 0.5:
            self.death_count += 1
            location = session_state.get("location", "unknown")
            self.death_locations.append(location)

        if activity == "combat":
            self.combat_count += 1

        if activity == "menu":
            self.menu_opens += 1

    def get_session_minutes(self) -> float:
        return (time.time() - self.session_start) / 60

    def get_playstyle(self) -> str:
        if not self.activity_time:
            return "unknown"
        top = max(self.activity_time, key=self.activity_time.get)
        if top == "combat": return "aggressive"
        if top == "explore": return "explorer"
        if top == "build": return "builder"
        if top == "gather": return "gatherer"
        return "balanced"

    def get_observation_prompt(self, locale: str = "ko") -> str | None:
        """Generate an unprompted observation about player behavior. Returns prompt or None."""
        now = time.time()

        # Cooldown: max one observation every 3 minutes
        if now - self.observation_cooldown < 180:
            return None

        session_min = self.get_session_minutes()
        observations = []

        if locale == "ko":
            if session_min > 30:
                observations.append(f"플레이어가 {session_min:.0f}분째 게임 중")
            if self.death_count >= 3:
                observations.append(f"이번 세션에서 {self.death_count}번 죽음")
            if self.death_count >= 2 and self.death_locations:
                from collections import Counter
                common = Counter(self.death_locations).most_common(1)[0]
                if common[1] >= 2:
                    observations.append(f"'{common[0]}'에서 {common[1]}번 죽음")
            style = self.get_playstyle()
            if style != "unknown" and session_min > 10:
                style_kr = {"aggressive": "공격적", "explorer": "탐험 위주", "builder": "건설 위주", "gatherer": "채집 위주", "balanced": "균형잡힌"}.get(style, style)
                observations.append(f"플레이 스타일: {style_kr}")
        else:
            if session_min > 30:
                observations.append(f"Player has been going for {session_min:.0f} minutes")
            if self.death_count >= 3:
                observations.append(f"Died {self.death_count} times this session")
            if self.death_count >= 2 and self.death_locations:
                from collections import Counter
                common = Counter(self.death_locations).most_common(1)[0]
                if common[1] >= 2:
                    observations.append(f"Died {common[1]} times at '{common[0]}'")
            style = self.get_playstyle()
            if style != "unknown" and session_min > 10:
                observations.append(f"Playstyle: {style}")

        if not observations:
            return None

        self.observation_cooldown = now

        import random
        obs = random.choice(observations)
        if locale == "ko":
            return f"[행동 관찰] {obs}\n위 관찰을 바탕으로 플레이어의 행동에 대해 자연스럽게 한마디 해. 화면 묘사 금지. 패턴이나 습관에 대한 감상."
        else:
            return f"[Behavior observation] {obs}\nComment naturally on this player pattern. Don't describe the screen. React to the habit or pattern."
