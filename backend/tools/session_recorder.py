"""Session recorder for demo mode.

Records CV events and AI responses during gameplay for later replay.
Output: .session.jsonl file with timestamped events.

Usage (recording):
    recorder = SessionRecorder(game="palworld", character="nozomi")
    recorder.start()
    # ... during gameplay loop ...
    recorder.record_event(signal, "major", 0.85)
    recorder.record_response("헐! 대박!", "excited", "(≧▽≦)", 1200)
    recorder.record_thinking()
    # ... at session end ...
    recorder.stop()  # saves to training_data/<game>/sessions/<timestamp>.session.jsonl

Usage (replay):
    player = SessionPlayer("path/to/session.jsonl")
    for event in player.play():
        # event is a dict with type, ts, and data
        broadcast(event)  # send to SSE clients
        time.sleep(event["delay"])  # wait for next event
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator

log = logging.getLogger(__name__)


class SessionRecorder:
    """Records CV events and AI responses as a JSONL session file.

    Each line is a JSON object with:
      - ts: float, seconds since session start
      - type: str, event type (matches SSE event types)
      - data: dict, event payload
    """

    def __init__(
        self,
        game: str = "general",
        character: str = "nozomi",
        locale: str = "ko",
        output_dir: Path | str | None = None,
    ):
        self.game = game
        self.character = character
        self.locale = locale
        self._start_time: float = 0.0
        self._events: list[dict] = []
        self._running = False

        if output_dir is None:
            # Default: training_data/<game>/sessions/
            repo_root = Path(__file__).resolve().parents[2]
            self._output_dir = repo_root / "training_data" / game / "sessions"
        else:
            self._output_dir = Path(output_dir)

    def start(self) -> None:
        """Begin recording. Call this before any record_* methods."""
        self._start_time = time.time()
        self._events = []
        self._running = True
        log.info("Session recording started (game=%s, char=%s)", self.game, self.character)

    def stop(self) -> Path:
        """Stop recording and save the session file. Returns the output path."""
        self._running = False
        duration = time.time() - self._start_time if self._start_time else 0.0

        # Write metadata as the first line
        metadata = {
            "ts": 0.0,
            "type": "session_metadata",
            "data": {
                "game": self.game,
                "character": self.character,
                "locale": self.locale,
                "duration_sec": round(duration, 2),
                "event_count": len(self._events),
                "recorded_at": datetime.now().isoformat(),
            },
        }

        # Build output path
        self._output_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{ts_str}.session.jsonl"
        output_path = self._output_dir / filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(metadata, ensure_ascii=False) + "\n")
            for event in self._events:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

        log.info(
            "Session saved: %s (%d events, %.1fs)",
            output_path, len(self._events), duration,
        )
        return output_path

    def _ts(self) -> float:
        """Seconds since session start."""
        if not self._start_time:
            return 0.0
        return round(time.time() - self._start_time, 3)

    def _append(self, event_type: str, data: dict) -> None:
        """Append a timestamped event."""
        if not self._running:
            return
        self._events.append({
            "ts": self._ts(),
            "type": event_type,
            "data": data,
        })

    # --- Recording methods (called from ai_loop) ---

    def record_event(self, label: str, score: float, motion_pct: float = 0.0,
                     scene_change: bool = False, menu_likely: bool = False) -> None:
        """Record a CV event detection result."""
        self._append("cv_event", {
            "label": label,
            "score": round(score, 3),
            "motion_pct": round(motion_pct, 2),
            "scene_change": scene_change,
            "menu_likely": menu_likely,
        })

    def record_thinking(self) -> None:
        """Record that the AI started thinking (maps to SSE 'thinking')."""
        self._append("thinking", {})

    def record_stream_start(self) -> None:
        """Record that streaming started."""
        self._append("stream_start", {})

    def record_stream_chunk(self, text: str) -> None:
        """Record a streaming text chunk."""
        self._append("stream_chunk", {"text": text})

    def record_response(self, text: str, mood: str, face: str,
                        elapsed_ms: int, cycle: int = 0,
                        event_label: str = "", event_score: float = 0.0,
                        mode: str = "", cost_estimate: str = "0.0000") -> None:
        """Record a complete AI response (maps to SSE 'stream_end')."""
        self._append("stream_end", {
            "text": text,
            "mood": mood,
            "face": face,
            "cycle": cycle,
            "elapsed_ms": elapsed_ms,
            "cost_estimate": cost_estimate,
            "debug": {
                "cycle": cycle,
                "ms": elapsed_ms,
                "cost": cost_estimate,
                "event": event_label,
                "score": round(event_score, 2),
                "mode": mode,
            },
        })

    def record_status(self, status_type: str, data: dict | None = None) -> None:
        """Record a status event (limit_reached, error, cost_warning, etc.)."""
        self._append(status_type, data or {})


class SessionPlayer:
    """Replays a recorded session file, yielding SSE-compatible events with timing.

    Each yielded dict has:
      - type: str (SSE event type like 'thinking', 'stream_end', etc.)
      - delay: float (seconds to wait before the *next* event)
      - plus all original event data fields
    """

    def __init__(self, session_path: str | Path):
        self.session_path = Path(session_path)
        self.metadata: dict = {}
        self._events: list[dict] = []
        self._load()

    def _load(self) -> None:
        """Load and parse the JSONL session file."""
        if not self.session_path.exists():
            raise FileNotFoundError(f"Session file not found: {self.session_path}")

        events = []
        with open(self.session_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    log.warning("Skipping malformed JSONL line: %s", line[:80])
                    continue

                if obj.get("type") == "session_metadata":
                    self.metadata = obj.get("data", {})
                else:
                    events.append(obj)

        self._events = events
        log.info(
            "Session loaded: %s (%d events, game=%s, duration=%.1fs)",
            self.session_path.name,
            len(self._events),
            self.metadata.get("game", "unknown"),
            self.metadata.get("duration_sec", 0),
        )

    def play(self) -> Generator[dict, None, None]:
        """Yield SSE-compatible events with timing delays.

        Each yielded dict contains:
          - type: the SSE event type
          - delay: seconds to wait before the next event
          - all fields from the original event's data dict
        """
        if not self._events:
            return

        for i, event in enumerate(self._events):
            ts = event.get("ts", 0.0)
            event_type = event.get("type", "unknown")
            data = event.get("data", {})

            # Calculate delay until next event
            if i + 1 < len(self._events):
                next_ts = self._events[i + 1].get("ts", ts)
                delay = max(0.0, next_ts - ts)
            else:
                delay = 0.5  # small delay after last event before loop restarts

            # Build SSE-compatible output: merge type + data + delay
            output = {"type": event_type, "delay": round(delay, 3)}
            output.update(data)

            yield output

    @property
    def duration(self) -> float:
        """Total session duration in seconds."""
        return self.metadata.get("duration_sec", 0.0)

    @property
    def event_count(self) -> int:
        """Number of playable events (excluding metadata)."""
        return len(self._events)
