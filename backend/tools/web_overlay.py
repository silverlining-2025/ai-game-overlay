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
    FACES,
    MOOD_KEYWORDS,
    pick_face,
    frame_to_base64,
    crop_ui_region,
)

# ---------- HTML page ----------
HTML_PAGE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Companion</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0a0a1a;
    font-family: 'Malgun Gothic', 'Segoe UI', sans-serif;
    color: #f0f0ff;
    overflow: hidden;
  }
  /* Two modes: ?mode=overlay (compact, no screenshot) vs default (full, with screenshot) */
  .container {
    border: 2px solid #6d28d9;
    border-radius: 12px;
    background: #13132bee;
    padding: 14px 18px;
    margin: 8px;
    box-shadow: 0 0 30px rgba(109, 40, 217, 0.2);
    transition: border-color 0.3s, box-shadow 0.3s;
  }
  .container.flash {
    border-color: #a855f7;
    box-shadow: 0 0 50px rgba(168, 85, 247, 0.5);
  }
  .top-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 6px;
  }
  .face {
    font-family: 'Consolas', monospace;
    font-size: 28px;
    font-weight: bold;
    color: #c084fc;
    transition: transform 0.2s;
  }
  .face.bounce { animation: bounce 0.4s ease; }
  @keyframes bounce {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.2); }
  }
  .status {
    font-size: 10px;
    color: #4a4a6a;
    text-align: right;
  }
  .status .cost { color: #22c55e; font-weight: bold; }
  .speech {
    font-size: 15px;
    line-height: 1.6;
    min-height: 36px;
    color: #e8e8f0;
  }
  .cursor {
    display: inline-block;
    width: 2px;
    height: 1em;
    background: #c084fc;
    margin-left: 2px;
    animation: blink 0.6s infinite;
    vertical-align: text-bottom;
  }
  @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
  .thinking .face { animation: pulse 0.8s infinite alternate; }
  @keyframes pulse { from { opacity: 0.4; } to { opacity: 1; } }
  .screen {
    width: 100%;
    border-radius: 6px;
    margin-top: 10px;
    border: 1px solid #2a2a4a;
  }
  .history {
    margin-top: 8px;
    padding-top: 8px;
    border-top: 1px solid #1a1a2e;
    max-height: 120px;
    overflow-y: auto;
  }
  .hist-item {
    font-size: 11px;
    color: #5a5a8a;
    padding: 2px 0;
    border-bottom: 1px solid #0f0f1e;
  }
  .hist-face { margin-right: 6px; font-size: 13px; }
  /* Hide elements based on mode */
  body.overlay-mode .screen,
  body.overlay-mode .history { display: none; }
  body.overlay-mode .container { background: #13132bdd; }
  body.overlay-mode { background: transparent; }
</style>
</head>
<body>
<div class="container" id="container">
  <div class="top-row">
    <div class="face" id="face">( ˘ω˘ )</div>
    <div class="status" id="status">connecting...</div>
  </div>
  <div class="speech" id="speech">연결 중...<span class="cursor"></span></div>
  <img class="screen" id="screen" alt="capture" style="display:none">
  <div class="history" id="history"></div>
</div>
<script>
const face = document.getElementById('face');
const speech = document.getElementById('speech');
const status = document.getElementById('status');
const container = document.getElementById('container');
const screenImg = document.getElementById('screen');
const historyEl = document.getElementById('history');

// Check URL param for overlay mode (compact, no screenshot)
const params = new URLSearchParams(window.location.search);
const isOverlay = params.get('mode') === 'overlay';
if (isOverlay) document.body.classList.add('overlay-mode');

let typewriterTimer = null;

function typewrite(text) {
  if (typewriterTimer) clearInterval(typewriterTimer);
  let i = 0;
  speech.innerHTML = '<span class="cursor"></span>';
  typewriterTimer = setInterval(() => {
    if (i < text.length) {
      speech.innerHTML = text.substring(0, i + 1) + '<span class="cursor"></span>';
      i++;
    } else {
      clearInterval(typewriterTimer);
      typewriterTimer = null;
      speech.textContent = text;
    }
  }, 22);
}

function flashBorder() {
  container.classList.add('flash');
  setTimeout(() => container.classList.remove('flash'), 600);
}

function bounceFace() {
  face.classList.remove('bounce');
  void face.offsetWidth;
  face.classList.add('bounce');
}

function addHistory(f, text) {
  const item = document.createElement('div');
  item.className = 'hist-item';
  item.innerHTML = '<span class="hist-face">' + f + '</span>' + text;
  historyEl.prepend(item);
  while (historyEl.children.length > 5) historyEl.removeChild(historyEl.lastChild);
}

const evtSource = new EventSource('/stream');

evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'thinking') {
    container.classList.add('thinking');
  } else if (data.type === 'response') {
    container.classList.remove('thinking');
    face.textContent = data.face;
    bounceFace();
    typewrite(data.text);
    flashBorder();
    addHistory(data.face, data.text);
    if (data.screenshot && !isOverlay) {
      screenImg.src = 'data:image/jpeg;base64,' + data.screenshot;
      screenImg.style.display = 'block';
    }
    const cost = data.cost_estimate || '?';
    status.innerHTML = '#' + data.cycle + ' | ' + data.elapsed_ms + 'ms | <span class="cost">$' + cost + '</span>';
  } else if (data.type === 'error') {
    container.classList.remove('thinking');
    face.textContent = '(×_×)';
    speech.textContent = data.text;
  } else if (data.type === 'status') {
    status.textContent = data.text;
  }
};

evtSource.onerror = () => { status.textContent = 'disconnected...'; };
</script>
</body>
</html>"""


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:1420", "https://tauri.localhost", "tauri://localhost"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    clients: list[asyncio.Queue] = []

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTML_PAGE

    @app.post("/shutdown")
    async def shutdown():
        _SHUTDOWN.set()
        return {"status": "shutting down"}

    @app.get("/stream")
    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        clients.append(q)

        async def event_gen():
            try:
                while True:
                    data = await q.get()
                    yield {"data": json.dumps(data, ensure_ascii=False)}
            except asyncio.CancelledError:
                pass
            finally:
                # Clean up on disconnect
                if q in clients:
                    clients.remove(q)
                log.info("SSE client disconnected (%d remaining)", len(clients))

        return EventSourceResponse(event_gen())

    def broadcast(data: dict):
        dead = []
        for q in clients:
            try:
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

        client = anthropic.Anthropic(api_key=api_key)
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
                excitement = personality.get_excitement_label()
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
                    "cycle": cycle,
                    "elapsed_ms": round(elapsed_ms),
                    "interval": args.interval,
                    "screenshot": display_b64,
                    "cost_estimate": cost_str,
                    "event": signal.label,
                    "event_score": round(signal.score, 2),
                    "mode": mode.value,
                    "excitement": personality.get_excitement_label(),
                })

            except Exception as ex:
                broadcast({"type": "error", "text": f"에러: {ex}"})

            # Variable interval based on mode
            wait = 0.5 if mode == ResponseMode.BURST else args.interval
            if _SHUTDOWN.wait(timeout=wait):
                break

    # SSE heartbeat to prevent connection timeouts
    def heartbeat_loop():
        while not _SHUTDOWN.is_set():
            broadcast({"type": "heartbeat"})
            if _SHUTDOWN.wait(timeout=15):
                break

    # Start AI loop + heartbeat in background threads
    thread = threading.Thread(target=ai_loop, daemon=True)
    thread.start()
    hb_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    hb_thread.start()

    base_url = f"http://localhost:{args.port}"
    overlay_url = f"{base_url}?mode=overlay"

    print(f"\n  AI Companion running:")
    print(f"  Full view (2nd monitor): {base_url}")
    print(f"  Compact overlay:         {overlay_url}")
    print(f"  Game: {args.game} | Interval: {args.interval}s")
    print(f"  Ctrl+C to stop\n")

    # Auto-open browser (skip if --headless, i.e. Tauri is the frontend)
    import webbrowser
    if args.headless:
        pass
    elif args.popup:
        # Try to open as a small popup window via Chrome app mode
        import subprocess
        chrome_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]
        opened = False
        for cp in chrome_paths:
            if Path(cp).exists():
                subprocess.Popen([
                    cp, f"--app={overlay_url}",
                    "--window-size=420,200",
                    "--window-position=20,20",
                ])
                opened = True
                break
        if not opened:
            webbrowser.open(overlay_url)
    else:
        webbrowser.open(base_url)

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
