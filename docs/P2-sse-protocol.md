# P2 — SSE Protocol Specification

Communication between Python backend (FastAPI on port 8080) and Tauri frontend (React).

## Connection

- URL: `http://localhost:8080/stream` (Server-Sent Events)
- Reconnect: frontend auto-reconnects with 2s backoff
- All messages: JSON in `data` field of SSE events
- Direction: **server → client only** (unidirectional push)
- Heartbeat: empty `{"type": "heartbeat"}` every 30s (keepalive)

## Downstream Messages (Backend → Frontend)

### `thinking` — AI is processing
```json
{"type": "thinking"}
```
Triggers thinking animation on the avatar.

### `stream_start` — Streaming response begins
```json
{"type": "stream_start"}
```
Clears the speech bubble, prepares for incoming text chunks.

### `stream_chunk` — Partial text from Claude API
```json
{"type": "stream_chunk", "text": "헐!"}
```
Appended to the speech bubble as it arrives (real-time streaming feel).

### `stream_end` — Complete response with metadata
```json
{
  "type": "stream_end",
  "text": "헐! 저거 좀 세 보이는데?",
  "face": "(≧▽≦)",
  "mood": "excited",
  "cycle": 42,
  "elapsed_ms": 1200,
  "cost_estimate": "0.0012",
  "debug": {
    "cycle": 42,
    "ms": 1200,
    "cost": "0.0012",
    "event": "major",
    "score": 0.85,
    "mode": "burst"
  }
}
```

### `limit_reached` — Daily reaction limit hit
```json
{"type": "limit_reached", "text": "일일 반응 한도 도달"}
```

### `heartbeat` — Keepalive
```json
{"type": "heartbeat"}
```

## REST Endpoints

### `POST /feedback` — Reaction feedback (up/down)
```json
{"cycle": 42, "text": "헐!", "rating": "up", "game": "palworld", "character": "nozomi"}
```

### `POST /text-feedback` — Free-text feedback (Alt+F)
```json
{"text": "캐릭터가 너무 시끄러워요", "game": "palworld", "character": "nozomi"}
```

### `GET /usage` — Daily usage stats
```json
{"date": "2026-03-20", "reactions": 15, "api_calls": 22, "limit": 20, "cost_usd": 0.045}
```

### `POST /shutdown` — Graceful shutdown
```json
{"status": "shutting down"}
```

## Message Flow

```
Startup:
  Tauri spawns Python backend → FastAPI starts on :8080
  Frontend connects to /stream → receives heartbeats
  Backend starts ai_loop in background thread

Runtime (ai_loop cycle):
  1. dxcam captures frame
  2. EventDetector.analyze(frame) → EventSignal (score, label, motion)
  3. CLIP classify(frame) → label override (optional)
  4. PersonalityEngine.decide(score, label) → mode (SILENT/BURST/REACT/CHAT)
  5. If SILENT → skip, wait 0.5s, next cycle
  6. If BURST and template hit (30%) → instant response (0ms)
  7. Otherwise → Claude Haiku Vision API (streaming)
  8. stream_start → stream_chunk(s) → stream_end
  9. Similarity gate: suppress if >45% similar to recent
  10. [SKIP] escape: Claude chose silence

Shutdown:
  Tauri calls stop_companion → kills Python process
  Or: POST /shutdown → _SHUTDOWN event set → threads exit
```
