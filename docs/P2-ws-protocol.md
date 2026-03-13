# P2 — WebSocket Protocol Specification

Communication between Python backend (port 9600) and Tauri frontend.

## Connection
- URL: `ws://localhost:9600`
- Reconnect: frontend auto-reconnects with 2s backoff
- All messages: JSON with `type` (string) and `ts` (Unix ms timestamp)

## Backend → Frontend (Downstream)

### `state_update` — Game state changed
```json
{
  "type": "state_update",
  "ts": 1710300000000,
  "game": "minesweeper",
  "data": {
    "grid": {
      "rows": 9, "cols": 9,
      "origin": [120, 200],
      "cell_size": [32, 32],
      "cells": [["?","1"," "], ...]
    },
    "status": "playing"
  }
}
```

### `suggestion` — AI recommendation
```json
{
  "type": "suggestion",
  "ts": 1710300000100,
  "game": "minesweeper",
  "data": {
    "safe_cells": [[2,3],[4,5]],
    "mine_cells": [[1,0]],
    "confidence": 0.95,
    "reasoning": "셀 (2,3)은 안전합니다 — 인접 지뢰가 모두 표시됨"
  }
}
```

### `status` — Performance metrics
```json
{
  "type": "status",
  "ts": 1710300000000,
  "data": {
    "fps": 15.2,
    "processing_ms": 12,
    "capture_ms": 4,
    "vram_mb": 1500
  }
}
```

## Frontend → Backend (Upstream)

### `config` — Settings change
```json
{
  "type": "config",
  "ts": 1710300000000,
  "data": {
    "capture_fps": 10,
    "game": "minesweeper",
    "show_reasoning": true,
    "locale": "ko"
  }
}
```

### `set_region` — ROI selection
```json
{
  "type": "set_region",
  "ts": 1710300000000,
  "data": { "x": 120, "y": 200, "w": 288, "h": 288 }
}
```

## Message Flow

```
Startup:
  Frontend connects → sends config → Backend starts capture loop

Runtime:
  Backend: capture → diff → process → state_update (if changed)
  Backend: solve/analyze → suggestion (when new insights)
  Backend: every 5s → status (performance metrics)

User action:
  Frontend: set_region → Backend adjusts ROI
  Frontend: config (game change) → Backend swaps processor
```
