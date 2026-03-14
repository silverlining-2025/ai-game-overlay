"""Web-based AI companion overlay — serves the overlay as a browser page.

Screen capture + Claude Vision runs locally. Results stream to browser via SSE.
Open the browser on any device on the same network to see the overlay.

Usage:
    python -m backend.tools.web_overlay --game palworld
    python -m backend.tools.web_overlay --game palworld --port 8080
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import os
import random
import sys
import threading
import time
import warnings
from collections import deque
from pathlib import Path

warnings.filterwarnings("ignore")

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
    display: flex;
    justify-content: center;
    align-items: center;
    min-height: 100vh;
    overflow: hidden;
  }
  .container {
    width: 680px;
    border: 3px solid #6d28d9;
    border-radius: 16px;
    background: #13132b;
    padding: 24px;
    box-shadow: 0 0 40px rgba(109, 40, 217, 0.3);
    transition: border-color 0.3s, box-shadow 0.3s;
  }
  .container.flash {
    border-color: #a855f7;
    box-shadow: 0 0 60px rgba(168, 85, 247, 0.5);
  }
  .face {
    font-family: 'Consolas', monospace;
    font-size: 42px;
    font-weight: bold;
    color: #c084fc;
    margin-bottom: 8px;
    transition: transform 0.2s;
  }
  .face.bounce {
    animation: bounce 0.4s ease;
  }
  @keyframes bounce {
    0%, 100% { transform: scale(1); }
    50% { transform: scale(1.15); }
  }
  .speech {
    font-size: 18px;
    line-height: 1.6;
    min-height: 60px;
    color: #e8e8f0;
    margin-bottom: 12px;
  }
  .speech .cursor {
    display: inline-block;
    width: 2px;
    height: 1.1em;
    background: #c084fc;
    margin-left: 2px;
    animation: blink 0.6s infinite;
    vertical-align: text-bottom;
  }
  @keyframes blink {
    0%, 100% { opacity: 1; }
    50% { opacity: 0; }
  }
  .screen {
    width: 100%;
    border-radius: 8px;
    margin-bottom: 12px;
    border: 1px solid #2a2a4a;
    display: none;
  }
  .screen.visible { display: block; }
  .status {
    font-size: 11px;
    color: #4a4a6a;
    text-align: right;
  }
  .thinking .face {
    animation: pulse 0.8s infinite alternate;
  }
  @keyframes pulse {
    from { opacity: 0.5; }
    to { opacity: 1; }
  }
</style>
</head>
<body>
<div class="container" id="container">
  <img class="screen" id="screen" alt="screen capture">
  <div class="face" id="face">( ˘ω˘ )</div>
  <div class="speech" id="speech">연결 중...<span class="cursor"></span></div>
  <div class="status" id="status">connecting...</div>
</div>
<script>
const face = document.getElementById('face');
const speech = document.getElementById('speech');
const status = document.getElementById('status');
const container = document.getElementById('container');
const screen = document.getElementById('screen');

let typewriterTimer = null;

function typewrite(text, callback) {
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
      speech.innerHTML = text;
      if (callback) callback();
    }
  }, 25);
}

function flashBorder() {
  container.classList.add('flash');
  setTimeout(() => container.classList.remove('flash'), 600);
}

function bounceFace() {
  face.classList.remove('bounce');
  void face.offsetWidth;  // force reflow
  face.classList.add('bounce');
}

// SSE connection
const evtSource = new EventSource('/stream');

evtSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'thinking') {
    container.classList.add('thinking');
    status.textContent = 'thinking...';
  } else if (data.type === 'response') {
    container.classList.remove('thinking');
    face.textContent = data.face;
    bounceFace();
    typewrite(data.text);
    flashBorder();
    if (data.screenshot) {
      screen.src = 'data:image/jpeg;base64,' + data.screenshot;
      screen.classList.add('visible');
    }
    status.textContent = `#${data.cycle} | ${data.elapsed_ms}ms | ${data.interval}s cycle`;
  } else if (data.type === 'error') {
    container.classList.remove('thinking');
    face.textContent = '(×_×)';
    speech.textContent = data.text;
  } else if (data.type === 'status') {
    status.textContent = data.text;
  }
};

evtSource.onerror = () => {
  status.textContent = 'disconnected — retrying...';
};
</script>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Web AI Companion Overlay")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--history", type=int, default=5)
    parser.add_argument("--game", type=str, default="general")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()

    import anthropic
    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
    from sse_starlette.sse import EventSourceResponse

    from backend.capture.screen import create_capture

    app = FastAPI()
    clients: list[asyncio.Queue] = []

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTML_PAGE

    @app.get("/stream")
    async def stream():
        q: asyncio.Queue = asyncio.Queue()
        clients.append(q)
        try:
            async def event_gen():
                while True:
                    data = await q.get()
                    yield {"data": json.dumps(data, ensure_ascii=False)}
            return EventSourceResponse(event_gen())
        except Exception:
            clients.remove(q)

    def broadcast(data: dict):
        for q in clients:
            try:
                q.put_nowait(data)
            except Exception:
                pass

    def ai_loop():
        cap = create_capture()
        for _ in range(10):
            if cap.grab() is not None:
                break
            time.sleep(0.1)

        client = anthropic.Anthropic()
        system_prompt = get_system_prompt(args.game)
        history: deque[str] = deque(maxlen=args.history)
        prev_frame = None

        broadcast({"type": "status", "text": f"ready | {args.game} | {args.interval}s cycle"})
        time.sleep(1)

        cycle = 0
        while True:
            frame = cap.grab()
            if frame is not None:
                frame = frame.copy()

            if frame is None:
                time.sleep(1)
                continue

            cycle += 1
            broadcast({"type": "thinking"})

            try:
                # Build API request
                img_b64 = frame_to_base64(frame)
                ui_b64 = crop_ui_region(frame, args.game)

                user_content = []
                if prev_frame is not None:
                    user_content.append({"type": "text", "text": "[이전 화면]"})
                    user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": frame_to_base64(prev_frame)}})

                user_content.append({"type": "text", "text": "[지금 화면]"})
                user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64}})

                if ui_b64:
                    user_content.append({"type": "text", "text": "[좌하단 UI 확대]"})
                    user_content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": ui_b64}})

                if history:
                    history_text = "\n".join(f"- {h}" for h in history)
                    user_content.append({"type": "text", "text": f"최근 네 반응:\n{history_text}\n\n화면 보고 반응해. 같은 말 반복 금지."})
                else:
                    user_content.append({"type": "text", "text": "화면 보고 반응해."})

                t0 = time.perf_counter()
                response = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=100,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                text = response.content[0].text.strip()

                prev_frame = frame
                history.append(text)

                # Send smaller screenshot for browser display
                display_b64 = frame_to_base64(frame, max_size=640, quality=60)

                broadcast({
                    "type": "response",
                    "text": text,
                    "face": pick_face(text),
                    "cycle": cycle,
                    "elapsed_ms": round(elapsed_ms),
                    "interval": args.interval,
                    "screenshot": display_b64,
                })

            except Exception as ex:
                broadcast({"type": "error", "text": f"에러: {ex}"})

            time.sleep(args.interval)

    # Start AI loop in background thread
    thread = threading.Thread(target=ai_loop, daemon=True)
    thread.start()

    print(f"\n  AI Companion overlay running at:")
    print(f"  http://localhost:{args.port}")
    print(f"  Game: {args.game} | Interval: {args.interval}s")
    print(f"  Open this URL in your browser!\n")

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
