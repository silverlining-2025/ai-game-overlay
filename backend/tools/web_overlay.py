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
    parser.add_argument("--save-training", action="store_true", dest="save_training",
                        help="Save screenshots + AI responses as training data")
    parser.add_argument("--tts", action="store_true", help="Enable voice output (Edge TTS)")
    args = parser.parse_args()

    import anthropic
    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import HTMLResponse
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
            broadcast({"type": "error", "text": "API 키가 설정되지 않았습니다. backend/.env 파일을 확인하세요."})
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

        # Anti-repetition only
        history: deque[str] = deque(maxlen=2)

        REANCHOR_EVERY = 7

        log.info("Pipeline ready: game=%s char=%s tts=%s", args.game, args.character, bool(tts))
        broadcast({"type": "status", "text": f"ready | {args.game} | {args.character} | event-driven"})
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
            mode, config = personality.decide(signal.score, signal.label)

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
                # --- Layer 3: Claude API call (event-driven, variable tokens) ---
                img_b64 = frame_to_base64(frame)
                max_tokens = config.get("max_tokens", 80)
                temperature = config.get("temperature", 0.7)
                prompt_hint = config.get("prompt_hint", "")

                user_content = []
                user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})

                prompt_text = ""
                if history:
                    prompt_text += "직전 (반복 금지): " + " / ".join(history) + "\n\n"
                if prompt_hint:
                    prompt_text += prompt_hint
                else:
                    prompt_text += "화면 보고 캐릭터답게 반응."

                # Add excitement context
                excitement = personality.get_emotion_context()
                if excitement != "평온":
                    prompt_text += f"\n(지금 기분: {excitement})"

                user_content.append({"type": "text", "text": prompt_text})

                # Re-anchoring
                system_prompt = base_system_prompt
                if api_calls % REANCHOR_EVERY == 0:
                    system_prompt += (
                        f"\n\n[리마인더] 넌 '{args.character}'야. "
                        "캐릭터 유지. 분석/설명 금지. 대사만."
                    )

                t0 = time.perf_counter()
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=max_tokens,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                dialogue = response.content[0].text.strip()
                api_calls += 1
                personality.mark_spoken()  # Update cooldown AFTER successful response

                # Track costs
                total_input_tokens += response.usage.input_tokens
                total_output_tokens += response.usage.output_tokens
                cost = (total_input_tokens * 1.0 + total_output_tokens * 5.0) / 1_000_000
                cost_str = f"{cost:.4f}"

                log.info("[c%d] %s (%.0fms, %s, score=%.2f) %s",
                         cycle, mode.value, elapsed_ms, signal.label, signal.score, dialogue[:60])

                # TTS voice output
                if tts and dialogue:
                    emotion = personality.state.emotions.dominant()
                    tts.speak(dialogue, emotion=emotion)

                # Save training data
                if args.save_training:
                    _save_training_pair(frame, dialogue, cycle, args.game)
                history.append(dialogue)

                # Send to frontend
                display_b64 = frame_to_base64(frame, max_size=640, quality=60)

                broadcast({
                    "type": "response",
                    "text": dialogue,
                    "face": pick_face(dialogue),
                    "mood": detect_mood(dialogue),
                    "cycle": cycle,
                    "elapsed_ms": round(elapsed_ms),
                    "interval": args.interval,
                    "screenshot": display_b64,
                    "cost_estimate": cost_str,
                    "event": signal.label,
                    "event_score": round(signal.score, 2),
                    "mode": mode.value,
                    "excitement": personality.get_emotion_context(),
                })

            except Exception as ex:
                broadcast({"type": "error", "text": f"에러: {ex}"})

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
