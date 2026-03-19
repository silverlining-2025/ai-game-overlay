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
import random
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

    @property
    def data(self) -> dict[str, Any]:
        """Public access to the memory data dict."""
        return self._data

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

    def add_moment(
        self,
        text: str,
        moment_type: str = "notable",
        emotional_weight: float = 1.0,
    ) -> None:
        """Record a notable moment (max 20, oldest evicted first).

        Args:
            text: Description of what happened (Korean OK).
            moment_type: Category — e.g. "funny", "achievement", "fail",
                         "epic", "notable".
            emotional_weight: How emotionally significant this moment is
                              (0.0 = trivial, 1.0 = normal, 2.0+ = very impactful).
        """
        moment = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "text": text,
            "type": moment_type,
            "emotional_weight": emotional_weight,
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
    # Fuzzy recall — imperfect human-like memory callbacks
    # ------------------------------------------------------------------

    def get_fuzzy_callback(
        self, current_context: str, locale: str = "ko"
    ) -> str | None:
        """Find a relevant past moment and return it as fuzzy recall.

        Searches stored moments for keyword overlap with the current context.
        If a match is found, returns a "fuzzified" recall string that sounds
        like imperfect human memory — hedged, partial, or vague.

        Args:
            current_context: Current situation text (location, activity, event).
            locale: Language for the recall string ("ko" or "en").

        Returns:
            A prompt injection string, or None if no relevant match.
        """
        if not self.moments:
            return None

        # Simple keyword matching
        context_words = set(current_context.lower().split())
        best_match = None
        best_score = 0

        for moment in self.moments:
            moment_words = set(moment["text"].lower().split())
            overlap = len(context_words & moment_words)
            if overlap > best_score:
                best_score = overlap
                best_match = moment

        if best_match and best_score >= 1:
            if locale == "ko":
                return self._fuzzify(best_match)
            return self._fuzzify_en(best_match)

        # 10% chance to reference a random moment even without context match
        if random.random() < 0.1 and self.moments:
            chosen = random.choice(self.moments)
            if locale == "ko":
                return self._fuzzify(chosen)
            return self._fuzzify_en(chosen)

        return None

    def _fuzzify(self, moment: dict) -> str:
        """Make a memory reference feel fuzzy and human, not database-accurate."""
        text = moment["text"]
        roll = random.random()

        if roll < 0.7:
            # Accurate but hedged
            templates = [
                f"전에 {text}... 맞지?",
                f"이거 전에도... {text} 비슷한 거 있었는데",
                f"어디서 봤는데... {text}... 맞나?",
            ]
        elif roll < 0.9:
            # Partial recall
            templates = [
                "전에 뭔가... 이 비슷한 게 있었는데, 기억이 가물가물",
                f"이거 어제였나... 그제였나... 하여튼 전에 {text[:15]}...",
                "확실하진 않은데, 예전에 이 비슷한 데서...",
            ]
        else:
            # Vague connection
            templates = [
                "전에도 이런 적 있었는데... 뭐였더라",
                "어디서 본 것 같은데, 기억이 안 나네",
            ]

        return random.choice(templates)

    def _fuzzify_en(self, moment: dict) -> str:
        """English version of fuzzy recall."""
        text = moment["text"]
        roll = random.random()

        if roll < 0.7:
            templates = [
                f"Didn't something like {text}... happen before?",
                f"This reminds me of... {text}... I think?",
                f"Wait, wasn't there a time when {text}...?",
            ]
        elif roll < 0.9:
            templates = [
                "Something like this happened before... can't quite remember",
                f"Was it yesterday or... anyway, {text[:15]}...",
            ]
        else:
            templates = [
                "This feels familiar... what was it",
                "I've seen something like this before... or have I?",
            ]

        return random.choice(templates)

    # ------------------------------------------------------------------
    # Prompt injection
    # ------------------------------------------------------------------

    def get_context_for_prompt(self, locale: str = "ko") -> str:
        """Return a narrative string suitable for injection into the system prompt.

        Produces natural, conversational text rather than structured lists.
        """
        sessions = self._data["relationship"]["sessions_together"]
        prev_summary = self._data["last_session"].get("summary", "")
        moments = self._data["moments"]

        parts: list[str] = []

        if locale == "en":
            session_line = f"This is session #{sessions} with this player."
            if prev_summary:
                session_line += f" Last time: {prev_summary}"
            parts.append(session_line)

            player = self._data["player"]
            player_bits: list[str] = []
            if player.get("name"):
                player_bits.append(f"Name: {player['name']}")
            if player.get("level_range"):
                player_bits.append(f"Level: {player['level_range']}")
            if player.get("play_style"):
                player_bits.append(f"Style: {player['play_style']}")
            if player_bits:
                parts.append("Player: " + ", ".join(player_bits) + ".")

            if moments:
                recent = moments[-5:]
                narrative_pieces: list[str] = []
                for m in recent:
                    weight = m.get("emotional_weight", 1.0)
                    mtype = m.get("type", "notable")
                    text = m["text"]
                    if mtype in ("fail", "funny"):
                        narrative_pieces.append(f"remember when {text}? That was rough" if weight >= 1.5 else f"remember {text}")
                    elif mtype in ("achievement", "epic"):
                        narrative_pieces.append(f"{text} was amazing" if weight >= 1.5 else f"remember pulling off {text}")
                    else:
                        narrative_pieces.append(f"there was that time with {text}")
                if narrative_pieces:
                    joined = ". Also, ".join(narrative_pieces)
                    parts.append(f"From before: {joined}.")
        else:
            session_line = f"이 플레이어와 {sessions}번째 세션이야."
            if prev_summary:
                session_line += f" 저번에 {prev_summary}"
            parts.append(session_line)

            player = self._data["player"]
            player_bits: list[str] = []
            if player.get("name"):
                player_bits.append(f"이름은 {player['name']}")
            if player.get("level_range"):
                player_bits.append(f"레벨대는 {player['level_range']}")
            if player.get("play_style"):
                player_bits.append(f"{player['play_style']} 스타일")
            if player_bits:
                parts.append("플레이어 정보: " + ", ".join(player_bits) + ".")

            if moments:
                recent = moments[-5:]
                narrative_pieces: list[str] = []
                for m in recent:
                    weight = m.get("emotional_weight", 1.0)
                    mtype = m.get("type", "notable")
                    text = m["text"]
                    if mtype in ("fail", "funny"):
                        narrative_pieces.append(f"{text} 때 진짜 힘들었잖아" if weight >= 1.5 else f"{text} 했던 거 기억나")
                    elif mtype in ("achievement", "epic"):
                        narrative_pieces.append(f"{text} 성공했을 때 진짜 좋아했잖아" if weight >= 1.5 else f"{text} 해냈던 거 기억나")
                    else:
                        narrative_pieces.append(f"{text} 있었잖아")
                if narrative_pieces:
                    if len(narrative_pieces) == 1:
                        parts.append(f"예전에 {narrative_pieces[0]}.")
                    else:
                        joined = ". 그리고 ".join(narrative_pieces)
                        parts.append(f"예전에 {joined}.")

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
