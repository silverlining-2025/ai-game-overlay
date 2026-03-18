"""Persistent cross-session memory for the AI companion.

Survives across sessions so the AI remembers the player — their name,
play style, notable moments, running jokes, and relationship history.

Save location: training_data/<game>/companion_memory.json

Integration (handled by the overlay agent, not here):
    - At session start:  memory = CompanionMemory(game); memory.increment_session()
    - In system prompt:  append memory.get_context_for_prompt()
    - At session end:    memory.update_session(summary); memory.save()
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if getattr(sys, "frozen", False):
    _REPO_ROOT = Path(sys.executable).parent
else:
    _REPO_ROOT = Path(__file__).resolve().parents[2]

_TRAINING_DATA_DIR = _REPO_ROOT / "training_data"

# Maximum number of stored moments (FIFO eviction)
_MAX_MOMENTS = 20


def _empty_memory() -> dict[str, Any]:
    """Return a blank companion memory structure."""
    return {
        "player": {
            "name": "",
            "level_range": "",
            "play_style": "",
            "notable_pals": [],
        },
        "moments": [],
        "relationship": {
            "sessions_together": 0,
            "total_reactions": 0,
            "favorite_topics": [],
        },
        "last_session": {
            "date": "",
            "summary": "",
        },
    }


class CompanionMemory:
    """Persistent memory for the AI companion -- survives across sessions.

    Stores:
    - Player profile (name, level, play style observations)
    - Notable moments (funny deaths, clutch captures, boss kills)
    - Running jokes / callbacks
    - Companion's relationship with the player
    """

    def __init__(self, game: str) -> None:
        self.game = game
        self._path = _TRAINING_DATA_DIR / game / "companion_memory.json"
        self._data: dict[str, Any] = self.load()

    # ------------------------------------------------------------------
    # Properties for convenient access
    # ------------------------------------------------------------------

    @property
    def player(self) -> dict[str, Any]:
        return self._data["player"]

    @property
    def moments(self) -> list[dict[str, str]]:
        return self._data["moments"]

    @property
    def relationship(self) -> dict[str, Any]:
        return self._data["relationship"]

    @property
    def last_session(self) -> dict[str, str]:
        return self._data["last_session"]

    # ------------------------------------------------------------------
    # Core persistence
    # ------------------------------------------------------------------

    def load(self) -> dict[str, Any]:
        """Read memory from disk.  Returns empty structure if file missing."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # Merge with empty template so new keys are always present
                template = _empty_memory()
                for section in template:
                    if section not in data:
                        data[section] = template[section]
                return data
            except (json.JSONDecodeError, OSError):
                pass
        return _empty_memory()

    def save(self) -> None:
        """Write current memory to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------
    # Moment tracking
    # ------------------------------------------------------------------

    def add_moment(self, text: str, moment_type: str = "notable") -> None:
        """Record a notable moment (max 20, oldest evicted first).

        Args:
            text: Description of what happened (Korean OK).
            moment_type: Category — e.g. "funny", "achievement", "fail",
                         "epic", "notable".
        """
        moment = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "type": moment_type,
        }
        self._data["moments"].append(moment)
        # FIFO eviction: keep only the most recent entries
        if len(self._data["moments"]) > _MAX_MOMENTS:
            self._data["moments"] = self._data["moments"][-_MAX_MOMENTS:]

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def increment_session(self) -> None:
        """Call at the start of every new session."""
        self._data["relationship"]["sessions_together"] += 1

    def update_session(self, summary: str) -> None:
        """Record the end-of-session summary and date."""
        self._data["last_session"]["date"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%d"
        )
        self._data["last_session"]["summary"] = summary

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def get_context_for_prompt(self) -> str:
        """Return a compact string suitable for injection into the system prompt.

        Example output (Korean):
            이 플레이어와 5번째 세션. 이전에: 사막 보스 클리어.
            기억할 것: 보스전에서 3번 죽음 (funny), 첫 레전더리 포획 (achievement)
        """
        sessions = self._data["relationship"]["sessions_together"]
        prev_summary = self._data["last_session"].get("summary", "")
        moments = self._data["moments"]

        parts: list[str] = []

        # Session count + previous summary
        session_line = f"이 플레이어와 {sessions}번째 세션."
        if prev_summary:
            session_line += f" 이전에: {prev_summary}"
        parts.append(session_line)

        # Player info (if known)
        player = self._data["player"]
        player_bits: list[str] = []
        if player.get("name"):
            player_bits.append(f"이름: {player['name']}")
        if player.get("level_range"):
            player_bits.append(f"레벨대: {player['level_range']}")
        if player.get("play_style"):
            player_bits.append(f"플레이 스타일: {player['play_style']}")
        if player_bits:
            parts.append("플레이어 정보: " + ", ".join(player_bits))

        # Notable moments (most recent 5 for prompt brevity)
        if moments:
            recent = moments[-5:]
            moment_strs = [f"{m['text']} ({m['type']})" for m in recent]
            parts.append("기억할 것: " + ", ".join(moment_strs))

        return "\n".join(parts)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def increment_reactions(self, count: int = 1) -> None:
        """Track total number of reactions across all sessions."""
        self._data["relationship"]["total_reactions"] += count

    def update_player(self, **kwargs: str) -> None:
        """Update player profile fields.

        Example: memory.update_player(name="하나시코", level_range="280-285")
        """
        for key, value in kwargs.items():
            if key in self._data["player"]:
                self._data["player"][key] = value

    def add_favorite_topic(self, topic: str) -> None:
        """Add a topic the player enjoys discussing (deduped, max 10)."""
        topics = self._data["relationship"]["favorite_topics"]
        if topic not in topics:
            topics.append(topic)
        if len(topics) > 10:
            self._data["relationship"]["favorite_topics"] = topics[-10:]
