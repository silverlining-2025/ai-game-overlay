# AI Game Overlay (게임 오버레이)

CV-based AI overlay for PC games. Captures screen via `dxcam`, processes with OpenCV/EasyOCR, displays insights through a transparent Tauri overlay. **Anti-cheat safe** — no memory reading, no injection, screen capture only.

**Demo targets**: Minesweeper (pipeline validation) → MapleStory → Mabinogi Mobile

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Capture | Python + `dxcam` | Windows DXGI, ~240 FPS, sub-5ms |
| CV/Detection | OpenCV, EasyOCR (Korean) | Template matching, color thresholding, OCR |
| Local AI | Moondream2 (Phase 3) | 1.8B params, ~4GB VRAM, on-demand |
| Communication | WebSocket (localhost:9600) | JSON protocol, bidirectional |
| Overlay UI | Tauri v2 + TypeScript | Transparent, click-through, ~20MB RAM |
| i18n | Custom TS `t()` (ko primary, en fallback) | ~80 lines, zero deps, type-safe keys |

## Architecture

```
[Screen] → CAPTURE (dxcam) → PROCESS (OpenCV/AI) → DISPLAY (Tauri overlay)
                                    │
                        Tiered: <20ms / ~500ms / ~3s
                                    │
                            WebSocket (port 9600)
```

Three processing tiers:
- **Tier 1 (<20ms)**: OpenCV template matching, color thresholding (every frame)
- **Tier 2 (~500ms)**: EasyOCR, buff detection (periodic)
- **Tier 3 (~3s)**: Moondream2 local VLM reasoning (on-demand, Phase 3)

## Project Structure

```
ai-game-overlay/
├── backend/              # Python — capture + CV + AI + WebSocket server
│   ├── main.py           # Entry point: threads + WS server
│   ├── config.py         # Constants, ROI coords, thresholds
│   ├── capture/          # dxcam screen grab + frame diff
│   ├── processors/       # Per-game CV pipelines (minesweeper.py, maplestory.py)
│   ├── solver/           # Game-specific logic (minesweeper solver)
│   ├── ai/               # OCR wrapper, Moondream2 (Phase 3)
│   ├── state/            # Rolling game state accumulator
│   ├── server/           # WebSocket server
│   └── tests/            # Pytest + screenshot fixtures
├── frontend/             # Tauri v2 + TypeScript
│   ├── src/              # Web UI (overlay renderer, widgets, WS client)
│   │   └── i18n/         # Custom i18n: ko.ts, en.ts, index.ts (zero deps)
│   └── src-tauri/        # Rust backend (window config, hotkeys, capabilities)
├── docs/                 # Layered documentation (see below)
└── scripts/              # Launch scripts (.bat for Windows)
```

## Commands

```bash
# Backend (Python, Windows native)
cd backend && python main.py --game minesweeper

# Frontend (Tauri, Windows native)
cd frontend && npm run tauri dev

# Tests
cd backend && pytest tests/

# Both (Windows)
scripts\start_all.bat
```

## Korean UI / English Code

- All user-facing text in Korean (한국어) via custom `t()` function (`src/i18n/`)
- Translations: `src/i18n/ko.ts` (primary), `src/i18n/en.ts` (fallback) — typed keys, zero deps
- AI coach responses: NOT through i18n — backend uses locale-specific system prompts
- All code, comments, variable names in English

## WebSocket Protocol

All messages: `{ "type": string, "ts": number, "game"?: string, "data": object }`

| Direction | Types | Purpose |
|-----------|-------|---------|
| Backend → Frontend | `state_update`, `suggestion`, `status` | Game state, AI suggestions, perf stats |
| Frontend → Backend | `config`, `set_region` | Settings, ROI selection |

> Full protocol spec: [docs/P2-ws-protocol.md](docs/P2-ws-protocol.md)

## Documentation Strategy

Priority-layered system — only highest-priority docs loaded per session:

| Priority | Auto-loaded? | Files | Update Frequency |
|----------|-------------|-------|-----------------|
| P0 | Always | `CLAUDE.md` (this), `MEMORY.md` | Every major change |
| P1 | On-demand | `docs/P1-cv-guide.md` — CV techniques, ROI definitions | Per new game added |
| P2 | On-demand | `docs/P2-ws-protocol.md` — message format spec | On protocol change |
| P3 | On-demand | `docs/P3-overlay-patterns.md` — UI patterns, anti-cheat | Rarely |

**Update rule**: After any session that changes architecture, adds a game, or modifies the protocol, update the relevant doc. CLAUDE.md stays under 150 lines.

## Anti-Cheat Safety Rules

1. NEVER read game process memory (`ReadProcessMemory`)
2. NEVER inject DLLs or hook DirectX/Vulkan
3. ONLY capture screen via OS-level APIs (DXGI Desktop Duplication)
4. Overlay is a separate window — never attached to game process
5. Games MUST run in Borderless Windowed or Windowed mode

## Key Constraints

- VRAM budget: Game (~2-4GB) + EasyOCR (~1.5GB) + Moondream2 (~4GB) = ~9.5GB max
- Platform: Native Windows only (screen capture requires direct display access)
- Development: Can edit code in WSL2/VS Code, but run/test on Windows side
- Dependencies: ALWAYS install latest stable versions. Never trust hardcoded versions from AI — run `pip install --upgrade` and `npm update` before coding. Pin after install via `pip freeze`.

## Session Checklist

Before each coding session:
1. `cd backend && pip install --upgrade -r requirements.txt`
2. `cd frontend && npm update`
3. Read this file + check MEMORY.md for context
4. Reference P1-P3 docs only when working on that specific area
