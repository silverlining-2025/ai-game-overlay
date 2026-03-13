"""Rolling game state accumulator."""

from __future__ import annotations

import time
from copy import deepcopy


class GameState:
    """Tracks current and previous game state for change detection."""

    def __init__(self, game: str) -> None:
        self.game = game
        self.current: dict = {}
        self.previous: dict = {}
        self.last_updated: float = 0.0

    def update(self, new_data: dict) -> bool:
        """Update state with new data. Returns True if state changed."""
        if new_data == self.current:
            return False
        self.previous = deepcopy(self.current)
        self.current = deepcopy(new_data)
        self.last_updated = time.time()
        return True

    def to_message(self) -> dict:
        """Format current state as a WebSocket message."""
        return {
            "type": "state_update",
            "ts": int(self.last_updated * 1000),
            "game": self.game,
            "data": self.current,
        }

    def get_diff(self) -> dict:
        """Return fields that changed between previous and current state."""
        diff: dict = {}
        for key, value in self.current.items():
            if key not in self.previous or self.previous[key] != value:
                diff[key] = value
        return diff
