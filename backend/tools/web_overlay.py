"""Web-based AI companion overlay — event-driven architecture.

5-layer pipeline:
  L1: Local CV event detection (~3ms, free)
  L2: Personality engine (timing, emotions, routing)
  L3: Claude Haiku API (on-demand, variable tokens)
  L4: Natural timing (delays, cooldowns)
  L5: Edge TTS voice output (optional)

Usage:
    python -m backend.tools.web_overlay --game palworld
    python -m backend.tools.web_overlay --game palworld --tts
"""

from __future__ import annotations

import argparse
import asyncio
import atexit
import base64
import io
import json
import logging
import os
import re
import signal
import sys
import threading
import time
import warnings
from collections import deque
from datetime import date, datetime
from pathlib import Path

warnings.filterwarnings("ignore")

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("overlay")

# --- Global kill switch: ensures API calls stop immediately on exit ---
_SHUTDOWN = threading.Event()


def _force_exit(*_args):
    """Graceful shutdown — stops all API calls, then exits."""
    _SHUTDOWN.set()
    # Give threads 1s to clean up, then force exit
    threading.Timer(1.0, lambda: os._exit(0)).start()


signal.signal(signal.SIGINT, _force_exit)
signal.signal(signal.SIGTERM, _force_exit)
atexit.register(lambda: _SHUTDOWN.set())

if getattr(sys, 'frozen', False):
    _REPO_ROOT = Path(sys.executable).parent
else:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env — environment variable takes priority over .env file
_env_path = _REPO_ROOT / "backend" / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

if not os.environ.get("ANTHROPIC_API_KEY"):
    log.warning("ANTHROPIC_API_KEY not found in env or .env file")


# ---------- Daily Usage Tracker ----------

class UsageTracker:
    """Tracks daily API reaction counts and cost in a persistent JSON file."""

    def __init__(self, max_reactions: int = 20):
        self._path = _REPO_ROOT / "training_data" / ".usage.json"
        self._max_reactions = max_reactions  # 0 = unlimited (premium)
        self._lock = threading.Lock()
        self._data = self._load()

    def _empty(self) -> dict:
        return {
            "date": date.today().isoformat(),
            "reactions": 0,
            "api_calls": 0,
            "cost_usd": 0.0,
        }

    def _load(self) -> dict:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if data.get("date") == date.today().isoformat():
                    return data
                # Date changed — reset for new day
                log.info("New day detected, resetting usage counter")
        except (json.JSONDecodeError, KeyError, TypeError):
            pass
        return self._empty()

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _maybe_reset(self) -> None:
        """Reset if the stored date is not today (midnight rollover)."""
        today = date.today().isoformat()
        if self._data.get("date") != today:
            log.info("Midnight rollover — resetting daily usage counter")
            self._data = self._empty()

    def check_limit(self) -> bool:
        """Return True if under limit (or unlimited). False if limit reached."""
        with self._lock:
            self._maybe_reset()
            if self._max_reactions == 0:
                return True  # premium / unlimited
            return self._data["reactions"] < self._max_reactions

    def record_reaction(self, input_tokens: int, output_tokens: int) -> None:
        """Increment reaction count and accumulate cost after a successful API response."""
        with self._lock:
            self._maybe_reset()
            self._data["reactions"] += 1
            self._data["api_calls"] += 1
            cost = (input_tokens * 1.0 + output_tokens * 5.0) / 1_000_000
            self._data["cost_usd"] = round(self._data["cost_usd"] + cost, 6)
            self._save()

    def record_api_call(self) -> None:
        """Increment api_calls only (for SKIP/SUPPRESSED responses that still cost tokens)."""
        with self._lock:
            self._maybe_reset()
            self._data["api_calls"] += 1
            self._save()

    def get_usage(self) -> dict:
        """Return current usage stats for the /usage endpoint."""
        with self._lock:
            self._maybe_reset()
            return {
                "date": self._data["date"],
                "reactions": self._data["reactions"],
                "api_calls": self._data["api_calls"],
                "limit": self._max_reactions,
                "cost_usd": self._data["cost_usd"],
            }


# Import prompts from live_overlay
from backend.tools.live_overlay import (
    get_system_prompt,
    detect_mood,
    pick_face,
    frame_to_base64,
    crop_ui_region,
)

# ---------- HTML page (loaded from file) ----------
_STATIC_DIR = _REPO_ROOT / "backend" / "static"


def _load_html_page() -> str:
    html_path = _STATIC_DIR / "overlay.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<html><body><h1>overlay.html not found</h1></body></html>"



# ---------- Structured Temporal Memory ----------

def _make_session_state() -> dict:
    """Create a fresh session state dict."""
    return {
        "location": "",
        "activity": "",
        "recent_events": [],   # list of {"text": str, "ts": float}
        "active_quest": "",
        "mood_trend": "",
    }


_STATE_RE = re.compile(
    r'\[STATE:\s*'
    r'location\s*=\s*(?P<location>[^,\]]*?)\s*,\s*'
    r'activity\s*=\s*(?P<activity>[^,\]]*?)\s*'
    r'(?:,\s*event\s*=\s*(?P<event>[^,\]]*?)\s*)?'
    r'(?:,\s*quest\s*=\s*(?P<quest>[^,\]]*?)\s*)?'
    r'(?:,\s*mood\s*=\s*(?P<mood>[^,\]]*?)\s*)?'
    r'\]',
    re.IGNORECASE,
)

_STATE_WINDOW_SEC = 60.0  # clear events older than this


def _parse_and_strip_state(text: str, session_state: dict) -> str:
    """Extract [STATE: ...] from Claude's response, update session_state, return cleaned text."""
    match = _STATE_RE.search(text)
    if not match:
        return text

    now = time.time()

    loc = (match.group("location") or "").strip()
    act = (match.group("activity") or "").strip()
    evt = (match.group("event") or "").strip()
    quest = (match.group("quest") or "").strip()
    mood = (match.group("mood") or "").strip()

    if loc and loc.lower() != "unknown":
        session_state["location"] = loc
    if act and act.lower() != "unknown":
        session_state["activity"] = act
    if quest:
        session_state["active_quest"] = quest
    if mood:
        session_state["mood_trend"] = mood

    # Add event to recent_events (keep last 3, within time window)
    if evt and evt.lower() != "none":
        session_state["recent_events"].append({"text": evt, "ts": now})

    # Prune old events (older than 60s) and keep max 3
    session_state["recent_events"] = [
        e for e in session_state["recent_events"]
        if now - e["ts"] < _STATE_WINDOW_SEC
    ][-3:]

    # Strip the [STATE: ...] line from displayed text
    cleaned = text[:match.start()] + text[match.end():]
    # Clean up trailing/leading whitespace and empty lines left behind
    cleaned = cleaned.strip()
    return cleaned


def _build_state_context(session_state: dict, locale: str = "ko") -> str:
    """Format session_state as a compact context string for the next prompt."""
    parts = []
    if locale == "en":
        if session_state["location"]:
            parts.append(f"Location: {session_state['location']}")
        if session_state["activity"]:
            parts.append(f"Activity: {session_state['activity']}")
        if session_state["recent_events"]:
            event_texts = [e["text"] for e in session_state["recent_events"]]
            parts.append(f"Recent: {' → '.join(event_texts)}")
        if session_state["active_quest"]:
            parts.append(f"Quest: {session_state['active_quest']}")
        if session_state["mood_trend"]:
            parts.append(f"Mood: {session_state['mood_trend']}")
        header = "[Session State] "
    else:
        if session_state["location"]:
            parts.append(f"위치: {session_state['location']}")
        if session_state["activity"]:
            parts.append(f"활동: {session_state['activity']}")
        if session_state["recent_events"]:
            event_texts = [e["text"] for e in session_state["recent_events"]]
            parts.append(f"최근: {' → '.join(event_texts)}")
        if session_state["active_quest"]:
            parts.append(f"퀘스트: {session_state['active_quest']}")
        if session_state["mood_trend"]:
            parts.append(f"분위기: {session_state['mood_trend']}")
        header = "[세션 상태] "

    if not parts:
        return ""
    return header + ", ".join(parts)


def _check_state_contradictions(session_state: dict, cv_context: dict) -> None:
    """Anti-fixation: reset state fields that contradict CV signals."""
    activity = session_state.get("activity", "").lower()

    # If state says combat but CV shows no motion in center, reset
    if activity == "combat":
        motion_center = cv_context.get("motion_center", 0)
        motion_edges = cv_context.get("motion_edges", 0)
        if motion_center < 5 and motion_edges < 5:
            session_state["activity"] = "unknown"

    # If state says menu but CV says no menu likely, reset
    if activity == "menu":
        if not cv_context.get("menu_likely", False):
            session_state["activity"] = "unknown"

    # If state says explore/travel but motion is zero, could be idle
    if activity in ("explore", "travel"):
        motion_center = cv_context.get("motion_center", 0)
        motion_edges = cv_context.get("motion_edges", 0)
        if motion_center < 2 and motion_edges < 2:
            session_state["activity"] = "unknown"


def _trigram_similarity(a: str, b: str) -> float:
    """Fast trigram Jaccard similarity — no ML needed."""
    if len(a) < 3 or len(b) < 3:
        return 0.0
    tri_a = set(a[i:i+3] for i in range(len(a) - 2))
    tri_b = set(b[i:i+3] for i in range(len(b) - 2))
    if not tri_a or not tri_b:
        return 0.0
    return len(tri_a & tri_b) / len(tri_a | tri_b)


TEMPLATES = {
    "scene_change": {
        "ko": ["어?", "오?", "뭐야?", "잠깐", "헐"],
        "en": ["Huh?", "Oh?", "Wait—", "Whoa", "Hold on"],
    },
    "major": {
        "ko": ["헐!", "와!", "오오!", "야!", "대박"],
        "en": ["Whoa!", "Oh!", "Wow!", "Hey!", "No way"],
    },
}


def _get_template_response(event_label: str, mode, character: str, locale: str = "ko") -> str | None:
    """Pre-written instant responses for common events. Returns None to use API instead."""
    import random
    from backend.personality.engine import ResponseMode

    if mode != ResponseMode.BURST:
        return None

    templates = TEMPLATES.get(event_label, {}).get(locale, [])
    if not templates:
        return None

    # Only use templates 30% of the time — rest go to Claude for richer responses
    if random.random() > 0.3:
        return None

    return random.choice(templates)


def _save_training_pair(frame, text: str, cycle: int, game: str) -> None:
    """Save screenshot + AI response as a training pair."""
    import cv2

    train_dir = _REPO_ROOT / "training_data" / game / datetime.now().strftime("%Y%m%d")
    train_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%H%M%S")
    prefix = f"{ts}_c{cycle:04d}"

    # Save screenshot
    cv2.imwrite(str(train_dir / f"{prefix}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 90])

    # Append to JSONL log (one line per pair)
    log_path = train_dir / "responses.jsonl"
    import json
    entry = {
        "cycle": cycle,
        "timestamp": datetime.now().isoformat(),
        "image": f"{prefix}.jpg",
        "response": text,
        "game": game,
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Web AI Companion Overlay")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--history", type=int, default=5)
    parser.add_argument("--game", type=str, default="general")
    parser.add_argument("--character", type=str, default="nozomi")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--popup", action="store_true", help="Open as compact popup overlay (Chrome app mode)")
    parser.add_argument("--headless", action="store_true", help="Don't open a browser (for Tauri frontend)")
    parser.add_argument("--chattiness", type=float, default=0.5,
                        help="How talkative (0.0=quiet, 0.5=normal, 1.0=chatty)")
    parser.add_argument("--save-training", action="store_true", dest="save_training",
                        help="Save screenshots + AI responses as training data")
    parser.add_argument("--tts", action="store_true", help="Enable voice output (Edge TTS)")
    parser.add_argument("--locale", type=str, default="ko", choices=["ko", "en"],
                        help="UI/prompt language (ko=Korean, en=English)")
    parser.add_argument("--max-reactions", type=int, default=20, dest="max_reactions",
                        help="Daily reaction limit (0=unlimited/premium, default=20)")
    args = parser.parse_args()

    import anthropic
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from sse_starlette.sse import EventSourceResponse

    from backend.capture.screen import create_capture

    # Initialize usage tracker
    usage_tracker = UsageTracker(max_reactions=args.max_reactions)
    log.info("Usage tracker: max_reactions=%d (%s)",
             args.max_reactions, "unlimited" if args.max_reactions == 0 else "free tier")

    app = FastAPI()
    # CORS: allow all origins — server only binds to 127.0.0.1 so this is safe
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    clients: list[asyncio.Queue] = []

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return _load_html_page()

    @app.post("/shutdown")
    async def shutdown():
        _SHUTDOWN.set()
        return {"status": "shutting down"}

    @app.post("/feedback")
    async def feedback(request: Request):
        try:
            body = await request.json()
            game = body.get("game", args.game)
            entry = {
                "timestamp": datetime.now().isoformat(),
                "cycle": body.get("cycle", 0),
                "text": body.get("text", ""),
                "rating": body.get("rating", ""),
                "game": game,
                "character": body.get("character", args.character),
            }
            feedback_dir = _REPO_ROOT / "training_data" / game
            feedback_dir.mkdir(parents=True, exist_ok=True)
            feedback_path = feedback_dir / "feedback.jsonl"
            with open(feedback_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            log.info("Feedback saved: cycle=%d rating=%s", entry["cycle"], entry["rating"])
            return JSONResponse({"status": "ok"})
        except Exception as e:
            log.error("Feedback save error: %s", e)
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    @app.post("/text-feedback")
    async def text_feedback(request: Request):
        try:
            body = await request.json()
            game = body.get("game", args.game)
            entry = {
                "timestamp": body.get("timestamp", datetime.now().isoformat()),
                "type": "text",
                "text": body.get("text", ""),
                "game": game,
                "character": body.get("character", args.character),
            }
            feedback_dir = _REPO_ROOT / "training_data" / game
            feedback_dir.mkdir(parents=True, exist_ok=True)
            feedback_path = feedback_dir / "feedback.jsonl"
            with open(feedback_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            log.info("Text feedback saved: %s", entry["text"][:60])
            return JSONResponse({"status": "ok"})
        except Exception as e:
            log.error("Text feedback save error: %s", e)
            return JSONResponse({"status": "error", "message": str(e)}, status_code=500)

    @app.get("/usage")
    async def usage():
        return JSONResponse(usage_tracker.get_usage())

    @app.get("/stream")
    async def stream():
        q: asyncio.Queue = asyncio.Queue(maxsize=10)
        clients.append(q)

        async def event_gen():
            try:
                while True:
                    try:
                        data = await asyncio.wait_for(q.get(), timeout=30.0)
                        yield {"data": json.dumps(data, ensure_ascii=False)}
                    except asyncio.TimeoutError:
                        yield {"data": json.dumps({"type": "heartbeat"})}
            except asyncio.CancelledError:
                raise
            finally:
                if q in clients:
                    clients.remove(q)
                log.info("SSE client disconnected (%d remaining)", len(clients))

        return EventSourceResponse(event_gen(), ping=15)

    def broadcast(data: dict):
        dead = []
        for q in clients:
            try:
                if q.full():
                    try:
                        q.get_nowait()  # drop oldest — overlay only needs latest
                    except asyncio.QueueEmpty:
                        pass
                q.put_nowait(data)
            except Exception:
                dead.append(q)
        for q in dead:
            clients.remove(q)

    def ai_loop():
        import random

        from backend.cv.event_detector import EventDetector
        from backend.personality.engine import PersonalityEngine, ResponseMode
        from backend.personality.behavior_tracker import BehaviorTracker

        cap = create_capture()
        for _ in range(10):
            if cap.grab() is not None:
                break
            time.sleep(0.1)

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            log.error("ANTHROPIC_API_KEY not set! Add it to backend/.env")
            return

        import httpx
        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=httpx.Timeout(30.0, connect=5.0),
            max_retries=2,
        )

        # --- Companion memory (persistent cross-session relationship) ---
        from backend.memory.companion_memory import CompanionMemory
        memory = CompanionMemory(args.game)
        memory.increment_session()
        memory.save()
        log.info("Companion memory: session %d", memory.data["relationship"]["sessions_together"])

        base_system_prompt = get_system_prompt(args.game, args.character, args.locale)

        # Inject companion memory context into system prompt
        memory_context = memory.get_context_for_prompt()
        if memory_context:
            base_system_prompt += f"\n\n[동반자 기억]\n{memory_context}"

        # Layered architecture
        detector = EventDetector(game=args.game)
        personality = PersonalityEngine()

        # Behavior tracker for unprompted observations
        tracker = BehaviorTracker()

        # Apply chattiness setting (0.0=quiet, 0.5=normal, 1.0=chatty)
        chattiness = max(0.0, min(1.0, args.chattiness))
        personality.cooldown_sec = 8.0 - chattiness * 6.0      # quiet=8s, chatty=2s
        personality.react_threshold = 0.7 - chattiness * 0.3   # quiet=0.7, chatty=0.4
        personality.idle_chat_after = 20.0 - chattiness * 12.0  # quiet=20s, chatty=8s
        log.info("Chattiness=%.1f (cooldown=%.1fs, threshold=%.2f, idle=%.0fs)",
                 chattiness, personality.cooldown_sec, personality.react_threshold, personality.idle_chat_after)

        # Optional TTS
        tts = None
        if args.tts:
            try:
                from backend.tts.engine import TTSEngine
                tts = TTSEngine(character=args.character)
                log.info("TTS enabled: %s", tts.voice)
            except Exception as e:
                log.warning("TTS init failed: %s", e)

        total_input_tokens = 0
        total_output_tokens = 0
        cycle = 0
        api_calls = 0

        # Anti-repetition
        history: deque[str] = deque(maxlen=5)

        # Topic registry — track covered topics to prevent loops
        covered_topics: deque[str] = deque(maxlen=8)

        # Rolling event log — last 5 significant events with timestamps
        event_log: deque[str] = deque(maxlen=5)

        # Structured temporal memory — tracks session state across responses
        session_state = _make_session_state()

        REANCHOR_EVERY = 7

        # Prompt caching — cache system prompt by sending it as first user message
        # (Anthropic caches identical prefixes automatically)
        cached_system = [{"type": "text", "text": base_system_prompt, "cache_control": {"type": "ephemeral"}}]

        log.info("Pipeline ready: game=%s char=%s tts=%s", args.game, args.character, bool(tts))
        log.info("Pipeline ready")
        time.sleep(1)

        while not _SHUTDOWN.is_set():
            frame = cap.grab()
            if frame is not None:
                frame = frame.copy()

            if frame is None:
                time.sleep(0.5)
                continue

            cycle += 1

            # --- Layer 1: Local CV event detection (~3ms, free) ---
            signal = detector.analyze(frame)

            # --- Layer 1.5: Optional CLIP scene classification (~50ms) ---
            clip_label = ""
            clip_confidence = 0.0
            try:
                from backend.cv.game_classifier import GameClassifier
                if not hasattr(ai_loop, '_classifier'):
                    ai_loop._classifier = GameClassifier()
                clip_label, clip_confidence = ai_loop._classifier.classify(frame)

                # Use CLIP to improve event detection labels
                if clip_label == "loading_screen" and clip_confidence > 0.70:
                    signal.label = "loading"
                elif clip_confidence > 0.60 and clip_label in (
                    "inventory", "pal_management", "technology_tree",
                    "map_screen", "merchant_shop", "breeding_condenser",
                    "settings_menu", "crafting_menu",
                ):
                    signal.label = clip_label
            except Exception as clip_err:
                if not hasattr(ai_loop, '_clip_warned'):
                    ai_loop._clip_warned = True
                    log.info("CLIP classifier not available: %s", clip_err)

            # --- Layer 2: Personality engine decides response ---
            cv_context = {
                "motion_center": signal.motion_center if hasattr(signal, 'motion_center') else 0,
                "motion_edges": signal.motion_edges if hasattr(signal, 'motion_edges') else 0,
                "menu_likely": signal.menu_likely if hasattr(signal, 'menu_likely') else False,
                "brightness": signal.brightness if hasattr(signal, 'brightness') else 128,
                "clip_label": clip_label,
                "clip_confidence": clip_confidence,
            }
            mode, config = personality.decide(signal.score, signal.label, cv_context)

            # Update behavior tracker every cycle
            tracker.update(session_state, signal.label, personality.state.emotions.tension)

            # Periodic observation check — every 30 cycles (~15s), override SILENT
            if cycle % 30 == 0 and mode == ResponseMode.SILENT:
                obs_prompt = tracker.get_observation_prompt(locale=args.locale)
                if obs_prompt and random.random() < 0.3:  # 30% chance when available
                    mode = ResponseMode.REACT
                    config = {
                        "max_tokens": 100,
                        "temperature": 0.85,
                        "delay_sec": random.uniform(1.0, 3.0),
                        "prompt_hint": obs_prompt,
                    }

            if mode == ResponseMode.SILENT:
                # Stay quiet — check again after short interval
                if _SHUTDOWN.wait(timeout=0.5):
                    break
                continue

            # We're going to speak — optional delay for natural feel
            delay = config.get("delay_sec", 0)
            if delay > 0:
                if _SHUTDOWN.wait(timeout=delay):
                    break

            # --- Check daily reaction limit before API call ---
            if not usage_tracker.check_limit():
                log.info("[c%d] Daily reaction limit reached (%d/%d)",
                         cycle, args.max_reactions, args.max_reactions)
                broadcast({
                    "type": "limit_reached",
                    "text": "일일 반응 한도 도달",
                })
                # Continue CV detection loop but skip API
                if _SHUTDOWN.wait(timeout=args.interval):
                    break
                continue

            broadcast({"type": "thinking"})

            try:
                # --- Pre-written template responses (skip API for known events) ---
                template = _get_template_response(signal.label, mode, args.character, locale=args.locale)
                if template:
                    dialogue = template
                    elapsed_ms = 0
                    input_tokens = 0
                    output_tokens = 0
                    broadcast({"type": "stream_start"})
                    broadcast({"type": "stream_chunk", "text": dialogue})
                    cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                    cost_str = f"{cost:.4f}"
                    broadcast({
                        "type": "stream_end",
                        "text": dialogue,
                        "face": pick_face(dialogue),
                        "mood": detect_mood(dialogue),
                        "debug": {"cycle": cycle, "ms": 0, "cost": cost_str,
                                  "event": signal.label, "score": round(signal.score, 2),
                                  "mode": "template"},
                    })
                    personality.mark_spoken()
                    if args.save_training:
                        _save_training_pair(frame, dialogue, cycle, args.game)
                    history.append(dialogue)
                    event_log.append(f"{signal.label}")
                    log.info("[c%d] template (0ms, %s) %s", cycle, signal.label, dialogue[:40])
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                # --- Layer 3: Claude API call ---
                img_size = 512 if mode == ResponseMode.BURST else 1024
                img_b64 = frame_to_base64(frame, max_size=img_size)
                max_tokens = config.get("max_tokens", 80)
                temperature = config.get("temperature", 0.7)
                prompt_hint = config.get("prompt_hint", "")

                user_content = []
                user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})

                # Build context: CV data + event log + anti-repetition
                prompt_text = ""

                # CV context (structured, helps Claude understand what's happening)
                prompt_text += (
                    f"[화면 분석] 움직임:{signal.motion_pct:.0f}% "
                    f"중앙:{getattr(signal, 'motion_center', 0):.0f}% "
                    f"가장자리:{getattr(signal, 'motion_edges', 0):.0f}% "
                    f"장면전환:{'O' if signal.scene_change else 'X'} "
                    f"메뉴:{'O' if getattr(signal, 'menu_likely', False) else 'X'} "
                    f"밝기:{getattr(signal, 'brightness', 128):.0f}\n"
                )

                # CLIP scene classification context
                if clip_label and clip_confidence > 0:
                    prompt_text += f"[장면 분류] {clip_label} ({clip_confidence:.0%})\n"

                # Event log (what happened recently)
                if event_log:
                    prompt_text += "[최근] " + " → ".join(event_log) + "\n"

                # Structured temporal memory — session state context
                _check_state_contradictions(session_state, cv_context)
                state_ctx = _build_state_context(session_state, locale=args.locale)
                if state_ctx:
                    prompt_text += state_ctx + "\n"

                # Anti-repetition — recent responses + covered topics
                if history:
                    prompt_text += "반복 금지: " + " / ".join(h[:20] for h in history) + "\n"
                if covered_topics:
                    prompt_text += "이미 다룬 주제 (다시 언급 금지): " + ", ".join(covered_topics) + "\n"

                # Instruction
                prompt_text += "\n"
                if prompt_hint:
                    prompt_text += prompt_hint
                else:
                    prompt_text += "화면 보고 캐릭터답게 반응."

                # Mood coloring — natural tonal instructions from emotional state
                mood_coloring = personality.get_mood_coloring(locale=args.locale) if hasattr(personality, 'get_mood_coloring') else personality.get_emotion_context()
                prompt_text += f"\n(톤: {mood_coloring})"

                # Confidence — low confidence allows uncertainty
                confidence = config.get("confidence", 0.5)
                if confidence < 0.4:
                    if args.locale == "en":
                        prompt_text += "\n(Low confidence — okay to express uncertainty or change your mind mid-sentence)"
                    else:
                        prompt_text += "\n(확신 낮음 — 말 중간에 자기 의견 바꿔도 됨)"

                # Disagreement — occasionally push back on player patterns
                disagree_topic = personality.should_disagree(session_state) if hasattr(personality, 'should_disagree') else None
                if disagree_topic and random.random() < 0.25:  # 25% chance when trigger fires
                    if args.locale == "en":
                        prompt_text += f"\n[Disagree] The player keeps {disagree_topic}. Express your disagreement in character."
                    else:
                        prompt_text += f"\n[의견 불일치] 플레이어가 {disagree_topic}. 캐릭터답게 동의하지 않는 의견 표현해."

                # Fuzzy memory callback — cross-session deja vu
                fuzzy = memory.get_fuzzy_callback(
                    f"{session_state.get('location', '')} {session_state.get('activity', '')}",
                    locale=args.locale
                ) if hasattr(memory, 'get_fuzzy_callback') else None
                if fuzzy:
                    prompt_text += f"\n[어렴풋한 기억] {fuzzy}\n이 기억이 자연스럽게 떠올랐으면 넌지시 언급해.\n"

                user_content.append({"type": "text", "text": prompt_text})

                # System prompt with re-anchoring
                system_prompt = base_system_prompt
                if api_calls % REANCHOR_EVERY == 0:
                    if args.locale == "en":
                        system_prompt += (
                            "\n\n[Reminder] Stay in character. English only. "
                            "No analysis/explanation. Dialogue only."
                        )
                    else:
                        system_prompt += (
                            "\n\n[리마인더] 캐릭터 유지. 한국어로만. "
                            "분석/설명/영어 금지. 대사만 출력."
                        )

                t0 = time.perf_counter()
                display_b64 = frame_to_base64(frame, max_size=640, quality=60)

                # --- Streaming response ---
                dialogue = ""
                input_tokens = 0
                output_tokens = 0
                first_token = True

                with client.messages.stream(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                ) as stream:
                    skip_checked = False
                    for event in stream:
                        if hasattr(event, 'type'):
                            if event.type == 'content_block_delta' and hasattr(event, 'delta'):
                                chunk = getattr(event.delta, 'text', '')
                                if chunk:
                                    dialogue += chunk
                                    # Buffer first chars to check for [SKIP]
                                    if not skip_checked and len(dialogue) >= 6:
                                        skip_checked = True
                                        if dialogue.strip().startswith("[SKIP"):
                                            continue  # Don't stream [SKIP] to frontend
                                    if skip_checked and not dialogue.strip().startswith("[SKIP"):
                                        if first_token:
                                            first_token = False
                                            broadcast({"type": "stream_start"})
                                        broadcast({"type": "stream_chunk", "text": chunk})
                                    elif not skip_checked:
                                        pass  # Still buffering
                            elif event.type == 'message_start' and hasattr(event, 'message'):
                                usage = getattr(event.message, 'usage', None)
                                if usage:
                                    input_tokens = getattr(usage, 'input_tokens', 0)
                            elif event.type == 'message_delta':
                                usage = getattr(event, 'usage', None)
                                if usage:
                                    output_tokens = getattr(usage, 'output_tokens', 0)
                    # Flush buffered content if we were still buffering
                    if not skip_checked and dialogue and not dialogue.strip().startswith("[SKIP"):
                        broadcast({"type": "stream_start"})
                        broadcast({"type": "stream_chunk", "text": dialogue})

                dialogue = dialogue.strip()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                api_calls += 1

                # Extract and strip [STATE: ...] from response, update session state
                dialogue = _parse_and_strip_state(dialogue, session_state)

                # [SKIP] escape hatch — Claude chose silence
                if dialogue == "[SKIP]" or dialogue.startswith("[SKIP]"):
                    log.info("[c%d] SKIP (%.0fms, %s) Claude chose silence", cycle, elapsed_ms, signal.label)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                    cost_str = f"{cost:.4f}"
                    usage_tracker.record_api_call()
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                # Similarity gate — suppress if too similar to recent responses
                is_repetitive = any(
                    _trigram_similarity(dialogue, prev) > 0.45
                    for prev in history
                )
                if is_repetitive:
                    log.info("[c%d] SUPPRESSED (too similar to recent)", cycle)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                    cost_str = f"{cost:.4f}"
                    usage_tracker.record_api_call()
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                personality.mark_spoken()

                # Track costs + record successful reaction
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                cost_str = f"{cost:.4f}"
                usage_tracker.record_reaction(input_tokens, output_tokens)
                memory.increment_reactions()

                # Track notable moments in companion memory
                if signal.label in ("major", "scene_change") and dialogue:
                    memory.add_moment(dialogue[:50], signal.label)

                log.info("[c%d] %s (%.0fms, %s, score=%.2f) %s",
                         cycle, mode.value, elapsed_ms, signal.label, signal.score, dialogue[:60])

                # Send final response
                broadcast({
                    "type": "stream_end",
                    "text": dialogue,
                    "face": pick_face(dialogue),
                    "mood": detect_mood(dialogue),
                    "debug": {
                        "cycle": cycle,
                        "ms": round(elapsed_ms),
                        "cost": cost_str,
                        "event": signal.label,
                        "score": round(signal.score, 2),
                        "mode": mode.value,
                    },
                })

                # TTS voice output (after full text is ready)
                if tts and dialogue:
                    emotion = personality.state.emotions.dominant()
                    tts.speak(dialogue, emotion=emotion)

                # Save training data
                if args.save_training:
                    _save_training_pair(frame, dialogue, cycle, args.game)
                history.append(dialogue)

                # Extract topic keywords and add to covered_topics
                topic_keywords = [w for w in dialogue.split() if len(w) >= 3][:3]
                if topic_keywords:
                    covered_topics.append(" ".join(topic_keywords[:2]))

                # Update event log for context
                if signal.label not in ("idle", "minor"):
                    event_log.append(signal.label)

            except Exception as ex:
                log.error("API error: %s", ex)
                # Don't show raw errors to user

            # Variable interval based on mode
            wait = 0.5 if mode == ResponseMode.BURST else args.interval
            if _SHUTDOWN.wait(timeout=wait):
                break

        # After the while loop ends — save companion memory
        memory.update_session(f"Played {args.game}, {api_calls} reactions")
        memory.save()
        log.info("Companion memory saved")

    # Start AI loop in background thread (SSE ping=15 handles keepalive)
    thread = threading.Thread(target=ai_loop, daemon=True)
    thread.start()

    base_url = f"http://localhost:{args.port}"
    log.info("Starting server on %s (game=%s, char=%s)", base_url, args.game, args.character)

    # Auto-open browser (skip if --headless)
    if not args.headless:
        try:
            import webbrowser
            webbrowser.open(base_url)
        except Exception:
            pass

    try:
        log.info("Starting uvicorn...")
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="info")
    except Exception as e:
        log.error("uvicorn failed: %s", e)
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
