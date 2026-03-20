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
    log.info("Shutting down...")
    _SHUTDOWN.set()
    # Force exit after 2s — uvicorn's graceful shutdown hangs on SSE connections
    threading.Timer(2.0, lambda: os._exit(0)).start()


# Register signal handlers — these fire on Ctrl+C
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
    """Tracks daily API reaction counts, cost, and per-provider stats."""

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
            "providers": {},  # provider_name → {"calls": N, "cost": X}
        }

    def _load(self) -> dict:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                if data.get("date") == date.today().isoformat():
                    data.setdefault("providers", {})
                    return data
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

    def record_reaction(self, cost_usd: float, provider: str = "") -> None:
        """Increment reaction count and accumulate cost."""
        with self._lock:
            self._maybe_reset()
            self._data["reactions"] += 1
            self._data["api_calls"] += 1
            self._data["cost_usd"] = round(self._data["cost_usd"] + cost_usd, 6)
            if provider:
                p = self._data["providers"].setdefault(provider, {"calls": 0, "cost": 0.0})
                p["calls"] += 1
                p["cost"] = round(p["cost"] + cost_usd, 6)
            self._save()

    def record_api_call(self, cost_usd: float = 0.0, provider: str = "") -> None:
        """Increment api_calls only (for SKIP/SUPPRESSED responses)."""
        with self._lock:
            self._maybe_reset()
            self._data["api_calls"] += 1
            self._data["cost_usd"] = round(self._data["cost_usd"] + cost_usd, 6)
            if provider:
                p = self._data["providers"].setdefault(provider, {"calls": 0, "cost": 0.0})
                p["calls"] += 1
                p["cost"] = round(p["cost"] + cost_usd, 6)
            self._save()

    def get_usage(self) -> dict:
        with self._lock:
            self._maybe_reset()
            return {
                "date": self._data["date"],
                "reactions": self._data["reactions"],
                "api_calls": self._data["api_calls"],
                "limit": self._max_reactions,
                "cost_usd": self._data["cost_usd"],
                "providers": self._data["providers"],
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


# Character templates loaded from YAML (per-character instant responses)
_CHARACTER_TEMPLATES: dict[str, dict] | None = None

def _get_character_templates() -> dict[str, dict]:
    """Lazy-load per-character templates from YAML."""
    global _CHARACTER_TEMPLATES
    if _CHARACTER_TEMPLATES is None:
        from backend.data.loader import load_character_templates
        _CHARACTER_TEMPLATES = load_character_templates()
    return _CHARACTER_TEMPLATES


# Fallback templates (used if character has no templates in YAML)
_FALLBACK_TEMPLATES = {
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

    # Try character-specific templates first, fall back to defaults
    char_templates = _get_character_templates().get(character, {})
    templates = char_templates.get(event_label, {}).get(locale, [])
    if not templates:
        templates = _FALLBACK_TEMPLATES.get(event_label, {}).get(locale, [])
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
    parser.add_argument("--tier", type=str, default="free", choices=["free", "basic", "pro", "streamer"],
                        help="Subscription tier (free=10/day, basic=50/day, pro=unlimited, streamer=premium)")
    parser.add_argument("--max-reactions", type=int, default=0, dest="max_reactions",
                        help="Daily reaction limit override (0=use tier default)")
    parser.add_argument("--max-cost-usd", type=float, default=0, dest="max_cost_usd",
                        help="Session cost limit override (0=use tier default)")
    parser.add_argument("--gemini-key", type=str, default="", dest="gemini_key",
                        help="Google Gemini API key")
    parser.add_argument("--openai-key", type=str, default="", dest="openai_key",
                        help="OpenAI API key")
    parser.add_argument("--groq-key", type=str, default="", dest="groq_key",
                        help="Groq API key")
    parser.add_argument("--demo", type=str, default="",
                        help="Replay a recorded session file (demo mode)")
    parser.add_argument("--record", action="store_true",
                        help="Record session for later demo replay")
    args = parser.parse_args()

    # --- Tier-based defaults ---
    TIER_DEFAULTS = {
        "free":     {"max_reactions": 60,   "max_cost_usd": 1.00,  "mode": "byok",    "characters": ["nozomi"], "tts": False, "quality": "standard"},
        "basic":    {"max_reactions": 200,  "max_cost_usd": 5.00,  "mode": "byok",    "characters": "all",      "tts": True,  "quality": "standard"},
        "pro":      {"max_reactions": 0,    "max_cost_usd": 10.00, "mode": "managed",  "characters": "all",      "tts": True,  "quality": "smart"},
        "streamer": {"max_reactions": 0,    "max_cost_usd": 20.00, "mode": "managed",  "characters": "all",      "tts": True,  "quality": "premium"},
    }
    tier = TIER_DEFAULTS.get(args.tier, TIER_DEFAULTS["free"])
    if args.max_reactions == 0:
        args.max_reactions = tier["max_reactions"]
    if args.max_cost_usd == 0:
        args.max_cost_usd = tier["max_cost_usd"]
    log.info("Tier=%s: max_reactions=%d, max_cost=$%.2f, quality=%s",
             args.tier, args.max_reactions, args.max_cost_usd, tier["quality"])

    # --- Character restriction based on tier ---
    allowed_chars = tier.get("characters", "all")
    if allowed_chars != "all" and args.character not in allowed_chars:
        log.info("Tier %s: character '%s' not available, using '%s'",
                 args.tier, args.character, allowed_chars[0])
        args.character = allowed_chars[0]

    # --- Managed vs BYOK mode ---
    if tier["mode"] == "managed":
        log.info("Managed mode: API calls routed through companion proxy")
    else:
        log.info("BYOK mode: API calls use user-provided keys directly")

    import anthropic
    import uvicorn
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from sse_starlette.sse import EventSourceResponse

    # Initialize usage tracker
    usage_tracker = UsageTracker(max_reactions=args.max_reactions)
    log.info("Usage tracker: max_reactions=%d (%s)",
             args.max_reactions, "unlimited" if args.max_reactions == 0 else f"{args.tier} tier")

    # Shared state between FastAPI endpoints and ai_loop thread
    shared_state: dict = {"game_db": None, "db_session_id": None}

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

            # Record feedback in game DB
            if shared_state.get("game_db") and shared_state.get("db_session_id"):
                shared_state["game_db"].record_feedback(
                    shared_state["db_session_id"],
                    entry["cycle"],
                    1 if entry["rating"] == "up" else -1,
                    entry.get("text", ""),
                )

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

    @app.get("/stats")
    async def stats():
        db = shared_state.get("game_db")
        sid = shared_state.get("db_session_id")
        if db and sid:
            return JSONResponse(db.get_session_stats(sid))
        return JSONResponse({"error": "no active session"})

    @app.get("/lifetime-stats")
    async def lifetime_stats():
        db = shared_state.get("game_db")
        if db:
            return JSONResponse(db.get_lifetime_stats())
        return JSONResponse({"error": "no database"})

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

        # --- Demo replay mode: no capture, no API ---
        if args.demo:
            from backend.tools.session_recorder import SessionPlayer
            player = SessionPlayer(args.demo)
            log.info("Demo mode: replaying %s (%d events, %.1fs)",
                     args.demo, player.event_count, player.duration)
            while not _SHUTDOWN.is_set():
                for event in player.play():
                    if _SHUTDOWN.is_set():
                        break
                    broadcast(event)
                    if _SHUTDOWN.wait(timeout=event.get("delay", 0.5)):
                        break
                log.info("Demo loop complete, restarting...")
            return

        from backend.cv.event_detector import EventDetector
        from backend.personality.engine import PersonalityEngine, ResponseMode
        from backend.personality.behavior_tracker import BehaviorTracker

        from backend.capture.screen import create_capture
        cap = create_capture()
        for _ in range(10):
            if cap.grab() is not None:
                break
            time.sleep(0.1)

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")

        from backend.ai.provider import create_provider_chain

        # Load additional API keys from environment
        gemini_key = args.gemini_key or os.environ.get("GEMINI_API_KEY", "")
        openai_key = args.openai_key or os.environ.get("OPENAI_API_KEY", "")
        groq_key = args.groq_key or os.environ.get("GROQ_API_KEY", "")

        provider_chain = create_provider_chain(
            anthropic_key=api_key,
            gemini_key=gemini_key,
            openai_key=openai_key,
            groq_key=groq_key,
        )

        if not provider_chain.providers:
            log.error("No AI providers configured! Add at least one API key.")
            return

        log.info("AI providers: %s", [p.name for p in provider_chain.providers])

        # --- Game memory database (always active — training data) ---
        from backend.memory.game_db import GameMemoryDB
        game_db = GameMemoryDB(args.game)
        db_session_id = game_db.start_session(args.character, args.locale, args.tier)
        shared_state["game_db"] = game_db
        shared_state["db_session_id"] = db_session_id
        log.info("Game DB: session %d started", db_session_id)

        # --- Companion memory (tier-gated: basic+ only) ---
        from backend.memory.companion_memory import CompanionMemory
        if args.tier in ("basic", "pro", "streamer"):
            memory = CompanionMemory(args.game)
            memory.increment_session()
            memory.save()
            log.info("Companion memory: session %d", memory.data["relationship"]["sessions_together"])
        else:
            memory = None
            log.info("Companion memory: disabled (free tier)")

        base_system_prompt = get_system_prompt(args.game, args.character, args.locale)

        # Inject companion memory context into system prompt
        memory_context = memory.get_context_for_prompt(locale=args.locale) if memory else ""
        if memory_context:
            header = "[Companion Memory]" if args.locale == "en" else "[동반자 기억]"
            base_system_prompt += f"\n\n{header}\n{memory_context}"

        # Layered architecture
        detector = EventDetector(game=args.game)
        personality = PersonalityEngine()

        # Behavior tracker for unprompted observations
        tracker = BehaviorTracker()

        # Apply chattiness with tier scaling
        chattiness = max(0.0, min(1.0, args.chattiness))
        tier_chattiness_mult = {"free": 0.7, "basic": 1.0, "pro": 1.2, "streamer": 1.5}.get(args.tier, 1.0)
        chattiness = min(1.0, chattiness * tier_chattiness_mult)
        personality.cooldown_sec = 8.0 - chattiness * 6.0      # quiet=8s, chatty=2s
        personality.react_threshold = 0.7 - chattiness * 0.3   # quiet=0.7, chatty=0.4
        personality.idle_chat_after = 20.0 - chattiness * 12.0  # quiet=20s, chatty=8s
        log.info("Chattiness=%.1f (cooldown=%.1fs, threshold=%.2f, idle=%.0fs)",
                 chattiness, personality.cooldown_sec, personality.react_threshold, personality.idle_chat_after)

        # Optional TTS (tier-gated: free tier cannot use TTS)
        tts = None
        tts_allowed = tier.get("tts", False)
        if args.tts and not tts_allowed:
            log.info("TTS not available on %s tier", args.tier)
        elif tts_allowed or args.tts:
            try:
                from backend.tts.engine import TTSEngine
                tts = TTSEngine(character=args.character)
                log.info("TTS enabled: %s", tts.voice)
            except Exception as e:
                log.warning("TTS init failed: %s", e)

        total_cost = 0.0  # cumulative session cost in USD
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

        # Optional session recorder (streamer tier only, or --record override)
        recorder = None
        if args.record:
            if args.tier in ("pro", "streamer"):
                from backend.tools.session_recorder import SessionRecorder
                recorder = SessionRecorder(
                    game=args.game,
                    character=args.character,
                    locale=args.locale,
                )
                recorder.start()
                log.info("Session recording enabled")
            else:
                log.info("Session recording not available on %s tier", args.tier)

        log.info("Pipeline ready: game=%s char=%s tts=%s record=%s",
                 args.game, args.character, bool(tts), bool(recorder))
        log.info("Pipeline ready")
        time.sleep(1)

        session_start_time = time.time()

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

            # Record CV event in game DB
            ts_offset = time.time() - session_start_time
            game_db.record_cv_event(db_session_id, ts_offset, {
                "label": signal.label, "score": signal.score,
                "motion_pct": signal.motion_pct,
                "motion_center": getattr(signal, 'motion_center', 0),
                "motion_edges": getattr(signal, 'motion_edges', 0),
                "brightness": getattr(signal, 'brightness', 0),
                "scene_change": signal.scene_change,
                "menu_likely": getattr(signal, 'menu_likely', False),
            })

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
            if recorder:
                recorder.record_event(
                    label=signal.label, score=signal.score,
                    motion_pct=signal.motion_pct,
                    scene_change=signal.scene_change,
                    menu_likely=getattr(signal, 'menu_likely', False),
                )
                recorder.record_thinking()

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
                    cost_str = f"{total_cost:.4f}"  # template = 0 cost, show session total
                    broadcast({
                        "type": "stream_end",
                        "text": dialogue,
                        "face": pick_face(dialogue),
                        "mood": detect_mood(dialogue),
                        "cycle": cycle,
                        "elapsed_ms": 0,
                        "cost_estimate": cost_str,
                        "debug": {"cycle": cycle, "ms": 0, "cost": cost_str,
                                  "event": signal.label, "score": round(signal.score, 2),
                                  "mode": "template"},
                    })
                    personality.mark_spoken()
                    if recorder:
                        recorder.record_stream_start()
                        recorder.record_stream_chunk(dialogue)
                        recorder.record_response(
                            text=dialogue, mood=detect_mood(dialogue),
                            face=pick_face(dialogue), elapsed_ms=0,
                            cycle=cycle, event_label=signal.label,
                            event_score=signal.score, mode="template",
                            cost_estimate=cost_str,
                        )
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

                # Build context: CV data + event log + anti-repetition
                prompt_text = ""

                # CV context (structured, helps Claude understand what's happening)
                if args.locale == "en":
                    prompt_text += (
                        f"[Screen Analysis] motion:{signal.motion_pct:.0f}% "
                        f"center:{getattr(signal, 'motion_center', 0):.0f}% "
                        f"edges:{getattr(signal, 'motion_edges', 0):.0f}% "
                        f"scene_change:{'Y' if signal.scene_change else 'N'} "
                        f"menu:{'Y' if getattr(signal, 'menu_likely', False) else 'N'} "
                        f"brightness:{getattr(signal, 'brightness', 128):.0f}\n"
                    )
                else:
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
                    label_header = "[Scene Classification]" if args.locale == "en" else "[장면 분류]"
                    prompt_text += f"{label_header} {clip_label} ({clip_confidence:.0%})\n"

                # Event log (what happened recently)
                if event_log:
                    header = "[Recent]" if args.locale == "en" else "[최근]"
                    prompt_text += header + " " + " → ".join(event_log) + "\n"

                # Structured temporal memory — session state context
                _check_state_contradictions(session_state, cv_context)
                state_ctx = _build_state_context(session_state, locale=args.locale)
                if state_ctx:
                    prompt_text += state_ctx + "\n"

                # Anti-repetition — recent responses + covered topics
                if history:
                    prefix = "No repeats: " if args.locale == "en" else "반복 금지: "
                    prompt_text += prefix + " / ".join(h[:20] for h in history) + "\n"
                if covered_topics:
                    prefix = "Already covered (don't repeat): " if args.locale == "en" else "이미 다룬 주제 (다시 언급 금지): "
                    prompt_text += prefix + ", ".join(covered_topics) + "\n"

                # Instruction
                prompt_text += "\n"
                if prompt_hint:
                    prompt_text += prompt_hint
                else:
                    prompt_text += "React in character to what's on screen." if args.locale == "en" else "화면 보고 캐릭터답게 반응."

                # Mood coloring — natural tonal instructions from emotional state
                mood_coloring = personality.get_mood_coloring(locale=args.locale)
                tone_label = "Tone" if args.locale == "en" else "톤"
                prompt_text += f"\n({tone_label}: {mood_coloring})"

                # Game knowledge tips — contextual advice injection
                from backend.data.loader import get_relevant_tips
                activity = session_state.get("activity", "idle")
                max_tips = 1 if args.tier == "free" else 3  # free gets 1 tip, paid gets 3
                tips = get_relevant_tips(args.game, activity, locale=args.locale, max_tips=max_tips)
                if tips:
                    prompt_text += f"\n{tips}"

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
                ) if memory and hasattr(memory, 'get_fuzzy_callback') else None
                if fuzzy:
                    if args.locale == "en":
                        prompt_text += f"\n[Fuzzy Memory] {fuzzy}\nIf this memory feels relevant, mention it casually.\n"
                    else:
                        prompt_text += f"\n[어렴풋한 기억] {fuzzy}\n이 기억이 자연스럽게 떠올랐으면 넌지시 언급해.\n"

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

                # --- Smart quality routing based on tier ---
                tier_quality = tier.get("quality", "standard")
                if tier_quality == "premium":
                    # Streamer tier: prefer Claude for all calls
                    preferred = next((p for p in provider_chain.providers if p.name == "claude"), None)
                    if preferred:
                        active_provider_override = preferred
                    else:
                        active_provider_override = None
                elif tier_quality == "smart":
                    # Pro tier: use Claude for complex scenes (boss, major events)
                    if signal.score >= 0.7 or signal.label in ("scene_change", "major"):
                        preferred = next((p for p in provider_chain.providers if p.name == "claude"), None)
                        if preferred:
                            active_provider_override = preferred
                        else:
                            active_provider_override = None
                    else:
                        active_provider_override = None
                else:
                    active_provider_override = None

                # --- Streaming via provider chain ---
                dialogue = ""
                input_tokens = 0
                output_tokens = 0
                first_token = True
                skip_checked = False

                try:
                    if active_provider_override:
                        try:
                            gen = active_provider_override.stream(
                                image_b64=img_b64,
                                prompt=prompt_text,
                                system_prompt=system_prompt,
                                max_tokens=max_tokens,
                                temperature=temperature,
                            )
                            active_provider = active_provider_override
                        except Exception:
                            # Fall back to chain if preferred provider fails
                            gen, active_provider = provider_chain.stream(
                                image_b64=img_b64,
                                prompt=prompt_text,
                                system_prompt=system_prompt,
                                max_tokens=max_tokens,
                                temperature=temperature,
                            )
                    else:
                        gen, active_provider = provider_chain.stream(
                            image_b64=img_b64,
                            prompt=prompt_text,
                            system_prompt=system_prompt,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )

                    try:
                        while True:
                            chunk = next(gen)
                            if isinstance(chunk, str) and chunk:
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
                    except StopIteration as e:
                        ai_response = e.value  # AIResponse from generator return
                        if ai_response:
                            input_tokens = ai_response.input_tokens
                            output_tokens = ai_response.output_tokens

                    # Flush buffered content if we were still buffering
                    if not skip_checked and dialogue and not dialogue.strip().startswith("[SKIP"):
                        broadcast({"type": "stream_start"})
                        broadcast({"type": "stream_chunk", "text": dialogue})

                except Exception as provider_err:
                    # Try fallback via non-streaming query
                    log.warning("Streaming provider failed: %s, trying fallback query", provider_err)
                    try:
                        result = provider_chain.query(
                            image_b64=img_b64,
                            prompt=prompt_text,
                            system_prompt=system_prompt,
                            max_tokens=max_tokens,
                            temperature=temperature,
                        )
                        if result.error:
                            raise Exception(result.error)
                        dialogue = result.text
                        input_tokens = result.input_tokens
                        output_tokens = result.output_tokens
                        if dialogue and not dialogue.strip().startswith("[SKIP"):
                            broadcast({"type": "stream_start"})
                            broadcast({"type": "stream_chunk", "text": dialogue})
                    except Exception as fallback_err:
                        raise fallback_err

                dialogue = dialogue.strip()
                elapsed_ms = (time.perf_counter() - t0) * 1000
                api_calls += 1

                # Extract and strip [STATE: ...] from response, update session state
                dialogue = _parse_and_strip_state(dialogue, session_state)

                # Record state snapshot in game DB
                if session_state.get("location") or session_state.get("activity"):
                    game_db.record_state_snapshot(
                        db_session_id, time.time() - session_start_time,
                        location=session_state.get("location", ""),
                        activity=session_state.get("activity", ""),
                        quest=session_state.get("active_quest", ""),
                        mood_trend=session_state.get("mood_trend", ""),
                    )

                # Calculate cost using the provider that actually served this request
                used_provider = active_provider or provider_chain.current
                call_cost = used_provider._calc_cost(input_tokens, output_tokens)
                total_cost += call_cost
                cost_str = f"{total_cost:.4f}"
                provider_name = used_provider.name

                # [SKIP] escape hatch — AI chose silence
                if dialogue == "[SKIP]" or dialogue.startswith("[SKIP]"):
                    log.info("[c%d] SKIP (%.0fms, %s, %s) AI chose silence",
                             cycle, elapsed_ms, signal.label, provider_name)
                    usage_tracker.record_api_call(cost_usd=call_cost, provider=provider_name)
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                # Similarity gate — suppress if too similar to recent responses
                is_repetitive = any(
                    _trigram_similarity(dialogue, prev) > 0.45
                    for prev in history
                )
                if is_repetitive:
                    log.info("[c%d] SUPPRESSED (too similar, %s)", cycle, provider_name)
                    usage_tracker.record_api_call(cost_usd=call_cost, provider=provider_name)
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                personality.mark_spoken()

                # Cost ceiling check
                if args.max_cost_usd > 0:
                    if total_cost >= args.max_cost_usd * 0.8 and total_cost < args.max_cost_usd:
                        warning_text = f"비용 경고: ${total_cost:.2f} / ${args.max_cost_usd:.2f}" if args.locale == "ko" else f"Cost warning: ${total_cost:.2f} / ${args.max_cost_usd:.2f}"
                        broadcast({"type": "cost_warning", "text": warning_text, "cost": total_cost, "limit": args.max_cost_usd})
                        log.warning("Cost at 80%%: $%.4f / $%.2f", total_cost, args.max_cost_usd)
                    elif total_cost >= args.max_cost_usd:
                        limit_text = f"비용 한도 도달: ${total_cost:.2f}" if args.locale == "ko" else f"Cost limit reached: ${total_cost:.2f}"
                        broadcast({"type": "cost_limit", "text": limit_text})
                        log.warning("Cost ceiling reached: $%.4f >= $%.2f — stopping API calls", total_cost, args.max_cost_usd)
                        if _SHUTDOWN.wait(timeout=args.interval):
                            break
                        continue

                usage_tracker.record_reaction(cost_usd=call_cost, provider=provider_name)
                if memory:
                    memory.increment_reactions()

                # Track notable moments in companion memory
                if memory and signal.label in ("major", "scene_change") and dialogue:
                    memory.add_moment(dialogue[:50], signal.label)

                log.info("[c%d] %s (%.0fms, %s, score=%.2f) %s",
                         cycle, mode.value, elapsed_ms, signal.label, signal.score, dialogue[:60])

                # Send final response
                broadcast({
                    "type": "stream_end",
                    "text": dialogue,
                    "face": pick_face(dialogue),
                    "mood": detect_mood(dialogue),
                    "cycle": cycle,
                    "elapsed_ms": round(elapsed_ms),
                    "cost_estimate": cost_str,
                    "debug": {
                        "cycle": cycle,
                        "ms": round(elapsed_ms),
                        "cost": cost_str,
                        "event": signal.label,
                        "score": round(signal.score, 2),
                        "mode": mode.value,
                    },
                })

                # Record in game DB
                game_db.record_response(
                    session_id=db_session_id,
                    ts_offset=time.time() - session_start_time,
                    cycle=cycle, text=dialogue, mood=detect_mood(dialogue),
                    face=pick_face(dialogue), mode=mode.value,
                    event_label=signal.label, event_score=signal.score,
                    provider=provider_name, model=getattr(used_provider, 'model', ''),
                    input_tokens=input_tokens, output_tokens=output_tokens,
                    cost_usd=call_cost, elapsed_ms=elapsed_ms,
                )

                # Record session data
                if recorder:
                    recorder.record_stream_start()
                    recorder.record_stream_chunk(dialogue)
                    recorder.record_response(
                        text=dialogue, mood=detect_mood(dialogue),
                        face=pick_face(dialogue),
                        elapsed_ms=round(elapsed_ms),
                        cycle=cycle, event_label=signal.label,
                        event_score=signal.score, mode=mode.value,
                        cost_estimate=cost_str,
                    )

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

            except anthropic.RateLimitError as ex:
                log.warning("[c%d] Rate limited: %s", cycle, ex)
                broadcast({"type": "error", "code": "rate_limit",
                           "text": "API 요청 한도 초과 — 잠시 후 재시도" if args.locale == "ko" else "API rate limited — retrying shortly"})
            except anthropic.AuthenticationError as ex:
                log.error("[c%d] Auth error: %s", cycle, ex)
                broadcast({"type": "error", "code": "auth",
                           "text": "API 키 오류 — 설정에서 확인해주세요" if args.locale == "ko" else "API key error — check settings"})
            except (anthropic.APIConnectionError, anthropic.APITimeoutError) as ex:
                log.warning("[c%d] Connection error: %s", cycle, ex)
                broadcast({"type": "error", "code": "connection",
                           "text": "API 연결 오류 — 네트워크를 확인해주세요" if args.locale == "ko" else "API connection error — check network"})
            except Exception as ex:
                provider_name = getattr(provider_chain, 'current', None) and provider_chain.current.name or 'unknown'
                log.error("[c%d] API error (%s): %s", cycle, provider_name, ex)
                broadcast({"type": "error", "code": "unknown",
                           "text": "오류 발생 — 잠시 후 재시도" if args.locale == "ko" else "Error occurred — retrying shortly"})

            # Variable interval based on mode
            wait = 0.5 if mode == ResponseMode.BURST else args.interval
            if _SHUTDOWN.wait(timeout=wait):
                break

        # After the while loop ends — save companion memory
        if memory:
            memory.update_session(f"Played {args.game}, {api_calls} reactions")
            memory.save()
            log.info("Companion memory saved")

        # Save behavior tracker to game DB
        game_db.save_behavior(db_session_id, {
            "death_count": tracker.death_count,
            "playstyle": tracker.get_playstyle(),
            "activity_time": json.dumps(tracker.activity_time),
        })

        # End session in game DB
        game_db.end_session(db_session_id,
                           summary=f"Played {args.game}, {api_calls} reactions",
                           playstyle=tracker.get_playstyle())
        game_db.close()
        log.info("Game DB: session %d ended", db_session_id)

        # Save session recording
        if recorder:
            session_path = recorder.stop()
            log.info("Session recording saved: %s", session_path)

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
        log.info("Starting uvicorn (Ctrl+C to stop)...")
        config = uvicorn.Config(app, host="127.0.0.1", port=args.port, log_level="info")
        server = uvicorn.Server(config)
        # Disable uvicorn's signal handlers — we use our own _force_exit
        server.install_signal_handlers = lambda: None
        server.run()
    except Exception as e:
        log.error("uvicorn failed: %s", e)
        import traceback
        traceback.print_exc()
    finally:
        os._exit(0)


if __name__ == "__main__":
    main()
