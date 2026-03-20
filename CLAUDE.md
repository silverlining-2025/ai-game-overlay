# AI Game Overlay (게임 오버레이)

AI companion overlay for PC games. Captures screen via `dxcam`, detects events with OpenCV + CLIP, generates personality-driven reactions via Claude Haiku Vision API, displays through a transparent Tauri overlay. **Anti-cheat safe** — no memory reading, no injection, screen capture only.

**Current target**: Palworld (primary), MapleStory (secondary)

## Tech Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Capture | Python + `dxcam` | Windows DXGI, ~240 FPS, sub-5ms |
| CV/Detection | OpenCV (event detection) + CLIP (scene classification) | Morphological, spatial zones, zero-shot |
| AI | Claude Haiku Vision API | Streaming SSE, ~1-2s latency |
| Communication | HTTP SSE (localhost:8080) | FastAPI + sse-starlette, unidirectional |
| Overlay UI | Tauri v2 + React + TypeScript | Transparent, click-through, ~20MB RAM |
| i18n | Custom TS `t()` (ko primary, en fallback) | ~80 lines, zero deps, type-safe keys |
| TTS | Edge TTS (optional) | Per-character voice + emotion prosody |

## Architecture

```
[Screen] → CAPTURE (dxcam) → CV EVENT DETECT → PERSONALITY ENGINE → CLAUDE API → OVERLAY
                                    │                    │                │           │
                               L1: ~3ms           L2: routing      L3: streaming   L4: Tauri
                               L1.5: ~50ms         + emotions       + [SKIP]        + sprites
                               (CLIP optional)     + cooldowns      + similarity     + micro-expr
```

5-layer event-driven pipeline:
- **L1 (~3ms)**: Local CV event detection — motion, spatial zones, brightness, variance
- **L1.5 (~50ms)**: CLIP scene classification — 26 game state labels (optional)
- **L2**: Personality engine — OCC emotions, dynamic cooldowns, response routing
- **L3**: Claude Haiku Vision API — streaming, [SKIP] escape, similarity gate
- **L4**: Tauri overlay — character sprites, crossfade, micro-expressions, TTS

## Project Structure

```
ai-game-overlay/
├── backend/                  # Python — capture + CV + AI + HTTP server
│   ├── config.py             # Constants, thresholds
│   ├── capture/              # dxcam screen grab (+ mss fallback)
│   ├── cv/                   # Event detection + CLIP game classifier
│   ├── personality/          # OCC emotions, timing, behavior tracking
│   ├── memory/               # Cross-session companion memory
│   ├── tts/                  # Edge TTS with per-character voices
│   ├── tools/                # Entry points + training pipeline tools
│   │   ├── web_overlay.py    # Main entry: FastAPI SSE + ai_loop
│   │   └── live_overlay.py   # Character prompts, game contexts, helpers
│   ├── data/                 # YAML configs (characters, games)
│   │   ├── characters.yaml   # 6 characters with KO+EN personalities
│   │   └── games/            # Per-game context (palworld.yaml, etc.)
│   └── tests/                # Pytest
├── frontend/                 # Tauri v2 + React + TypeScript
│   ├── src/                  # Screens (Config, Overlay, Consent), components
│   │   └── i18n/             # Custom i18n: ko.ts, en.ts, index.ts
│   └── src-tauri/            # Rust backend (window mgmt, system tray)
├── docs/                     # Layered documentation (see below)
└── scripts/                  # Launch scripts (.bat for Windows)
```

## Commands

```bash
# Backend
python -X utf8 -m backend.tools.web_overlay --game palworld --character nozomi

# Frontend (Tauri)
cd frontend && npm run tauri dev

# Tests
cd backend && pytest tests/

# Both (Windows)
scripts\start_all.bat
```

## Adding New Content (Data-Driven Pipeline)

**New character** — edit `backend/data/characters.yaml` only:
- Add personality, speech_style (KO), personality_en, speech_style_en
- Add templates (per-event instant responses), tts (voice + rate)
- Add preferences, disagreement_style
- Add sprite assets to `frontend/public/characters/<name>/` or Lottie to `frontend/public/lottie/`

**New game** — add `backend/data/games/<game>.yaml`:
- context_ko, context_en (game-specific visual cues, action categories)
- No code changes needed

## Documentation Strategy

| Priority | Auto-loaded? | Files | Update Frequency |
|----------|-------------|-------|-----------------|
| P0 | Always | `CLAUDE.md` (this), `MEMORY.md` | Every major change |
| P1 | On-demand | `docs/P1-cv-guide.md` — CV + CLIP detection | Per new game added |
| P2 | On-demand | `docs/P2-sse-protocol.md` — SSE message spec | On protocol change |
| P3 | On-demand | `docs/P3-overlay-patterns.md` — UI patterns, anti-cheat | Rarely |

## Anti-Cheat Safety Rules

1. NEVER read game process memory (`ReadProcessMemory`)
2. NEVER inject DLLs or hook DirectX/Vulkan
3. ONLY capture screen via OS-level APIs (DXGI Desktop Duplication)
4. Overlay is a separate window — never attached to game process
5. Overlay excluded from capture via `WDA_EXCLUDEFROMCAPTURE`
6. Games MUST run in Borderless Windowed or Windowed mode

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Windows 10 (21H2+) | Windows 11 |
| GPU | GTX 1060 6GB | RTX 3060 12GB |
| CPU | Any quad-core (i5/Ryzen 5) | 6+ cores |
| RAM | 8 GB | 16 GB |
| Network | Required (API calls) | Required |
| Display | Borderless Windowed mode | Same |

**GPU usage breakdown:**
- Screen capture (dxcam): ~0 VRAM (uses DXGI, not GPU compute)
- OpenCV event detection: CPU only (~3ms/frame)
- CLIP classifier (optional): ~1 GB VRAM
- Game: 2-8 GB VRAM (varies)
- With local VLM fallback (optional): +2-4 GB VRAM

## Key Constraints

- VRAM budget: Game (~2-4GB) + CLIP (~1GB) = ~5GB (Claude API is remote)
- Platform: Native Windows only (screen capture requires direct display access)
- Development: Can edit code in WSL2/VS Code, but run/test on Windows side
- Dependencies: ALWAYS install latest stable versions. Pin after install via `pip freeze`.

## Engineering Workflow (MANDATORY)

Claude is **Researcher + Planner + Orchestrator + Reviewer**. Agents are **Workers**.

### Phase 1: RESEARCH → Phase 2: PLAN (present, wait for approval) → Phase 3: EXECUTE (parallel agents) → Phase 4: REVIEW (test, verify, commit)

**Pre-authorized actions** (no confirmation needed):
- Edit/create files in this repo
- Run `pytest`, `npm test`, `cargo check`
- Read files, search codebase, fetch docs
- Spawn subagents for research or isolated file edits

**Always confirm before**:
- `git push`, PR creation, branch deletion
- Installing new packages (show what and why first)
- Any action outside this repo
