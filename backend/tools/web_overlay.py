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
import signal
import sys
import threading
import time
import warnings
from collections import deque
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

# Load .env
_env_path = _REPO_ROOT / "backend" / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

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


def _trigram_similarity(a: str, b: str) -> float:
    """Fast trigram Jaccard similarity — no ML needed."""
    if len(a) < 3 or len(b) < 3:
        return 0.0
    tri_a = set(a[i:i+3] for i in range(len(a) - 2))
    tri_b = set(b[i:i+3] for i in range(len(b) - 2))
    if not tri_a or not tri_b:
        return 0.0
    return len(tri_a & tri_b) / len(tri_a | tri_b)


def _get_template_response(event_label: str, mode, character: str) -> str | None:
    """Pre-written instant responses for common events. Returns None to use API instead."""
    import random
    from backend.personality.engine import ResponseMode

    # Only use templates for BURST mode on clear events
    if mode != ResponseMode.BURST:
        return None

    templates = {
        # Templates are per-event, character-agnostic (personality comes from the delivery)
        # These fire instantly (0ms) instead of waiting 1-2s for API
    }

    # Don't use templates for now — let Claude handle everything
    # This is a placeholder for when we have enough labeled data to
    # know which events are reliably detected
    return None


def _save_training_pair(frame, text: str, cycle: int, game: str) -> None:
    """Save screenshot + AI response as a training pair."""
    import cv2
    from datetime import datetime

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
    args = parser.parse_args()

    import anthropic
    import uvicorn
    from datetime import datetime
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse, JSONResponse
    from sse_starlette.sse import EventSourceResponse

    from backend.capture.screen import create_capture

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
        from backend.cv.event_detector import EventDetector
        from backend.personality.engine import PersonalityEngine, ResponseMode

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
        base_system_prompt = get_system_prompt(args.game, args.character)

        # Layered architecture
        detector = EventDetector(game=args.game)
        personality = PersonalityEngine()

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
        import datetime

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

            # --- Layer 2: Personality engine decides response ---
            cv_context = {
                "motion_center": signal.motion_center if hasattr(signal, 'motion_center') else 0,
                "motion_edges": signal.motion_edges if hasattr(signal, 'motion_edges') else 0,
                "menu_likely": signal.menu_likely if hasattr(signal, 'menu_likely') else False,
                "brightness": signal.brightness if hasattr(signal, 'brightness') else 128,
            }
            mode, config = personality.decide(signal.score, signal.label, cv_context)

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

            broadcast({"type": "thinking"})

            try:
                # --- Pre-written template responses (skip API for known events) ---
                template = _get_template_response(signal.label, mode, args.character)
                if template:
                    dialogue = template
                    elapsed_ms = 0
                    input_tokens = 0
                    output_tokens = 0
                    broadcast({"type": "stream_start"})
                    broadcast({"type": "stream_chunk", "text": dialogue})
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

                # Event log (what happened recently)
                if event_log:
                    prompt_text += "[최근] " + " → ".join(event_log) + "\n"

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

                excitement = personality.get_emotion_context()
                if excitement != "평온":
                    prompt_text += f"\n(기분: {excitement})"

                user_content.append({"type": "text", "text": prompt_text})

                # System prompt with re-anchoring
                system_prompt = base_system_prompt
                if api_calls % REANCHOR_EVERY == 0:
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

                # [SKIP] escape hatch — Claude chose silence
                if dialogue == "[SKIP]" or dialogue.startswith("[SKIP]"):
                    log.info("[c%d] SKIP (%.0fms, %s) Claude chose silence", cycle, elapsed_ms, signal.label)
                    total_input_tokens += input_tokens
                    total_output_tokens += output_tokens
                    cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                    cost_str = f"{cost:.4f}"
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
                    if _SHUTDOWN.wait(timeout=args.interval):
                        break
                    continue

                personality.mark_spoken()

                # Track costs
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                cost_str = f"{cost:.4f}"

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
