# AI Gaming Companion / AI 게임 친구

A real-time AI companion that watches your screen and reacts like a friend sitting next to you. Uses Claude Vision API for game understanding and responds with unique character personalities in Korean.

게임 화면을 보면서 실시간으로 반응하는 AI 친구. Claude Vision API로 화면을 이해하고, 캐릭터 성격에 맞춰 한국어로 반응합니다.

---

## Screenshots / Demo

> _Screenshots coming soon._

---

## Features

- **Real-time screen watching** -- captures your screen via DXGI (dxcam), no memory reading, no injection
- **Claude Vision AI** -- sends screenshots to Claude Haiku for natural, context-aware reactions
- **6 unique characters** -- each with distinct Korean speech patterns (tsundere girlfriend, emotional robot, lazy cat, baby ghost, cunning fox, baby slime)
- **Event-driven reactions** -- local CV detects motion, scene changes, menus; personality engine decides when and how to speak
- **Streaming responses** -- text appears as Claude generates it, with typewriter effect
- **Transparent overlay** -- Tauri v2 window sits on top of your game, click-through by default
- **Voice output (optional)** -- Edge TTS reads reactions aloud in character voice
- **Feedback system** -- rate reactions with thumbs up/down, write text feedback (saved as training data)
- **Session stats** -- track API calls, cost, event breakdown
- **Anti-cheat safe** -- screen capture only, no process memory access, no DLL injection

---

## Quick Start

### Prerequisites

- **Python 3.11+** (Windows native, not WSL)
- **Node.js 18+** and npm
- **Rust** (for Tauri v2) -- install via [rustup.rs](https://rustup.rs/)
- **Anthropic API key** -- get one at [console.anthropic.com](https://console.anthropic.com/)

### Setup

```bash
# Clone the repository
git clone https://github.com/your-username/ai-game-overlay.git
cd ai-game-overlay

# Install Python dependencies
cd backend
pip install -r requirements.txt

# Create .env file with your API key
echo ANTHROPIC_API_KEY=sk-ant-your-key-here > .env
cd ..

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Run

```bash
cd frontend
npm run tauri dev
```

This launches both the Tauri overlay (frontend) and the Python backend. A config screen appears where you pick your character, game, and chattiness level -- then click "Start".

---

## Configuration

| Setting | Options | Description |
|---------|---------|-------------|
| **Game** | MapleStory, Palworld, General | Adjusts CV detection and AI prompts for the game |
| **Character** | Nozomi, Robot, Cat, Ghost, Fox, Slime | Each has unique personality and speech patterns |
| **Chattiness** | 0.0 (quiet) -- 1.0 (chatty) | Controls reaction frequency and cooldown timing |
| **Position** | Top-right, Top-left, Bottom-right, Bottom-left | Where the companion appears on screen |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| **Alt** (hold) | Enable mouse interaction with overlay (release to go click-through) |
| **Ctrl+Shift+D** | Toggle debug info bar (cycle, latency, cost, event) |
| **Ctrl+Shift+S** | Toggle session stats panel |
| **Alt+F** | Open text feedback form |
| **Esc** | Quit application |

---

## Architecture

```
Screen Capture (dxcam, ~240 FPS)
        |
  [L1] Local CV Event Detection (~3ms, free)
        |  motion %, scene change, menu detection, brightness
        |
  [L2] Personality Engine (timing + emotion routing)
        |  decides: SILENT / BURST / REACT / CHAT
        |  adds natural delay, cooldowns, anti-repetition
        |
  [L3] Claude Haiku Vision API (on-demand, ~1-2s)
        |  screenshot + CV context + session state + character prompt
        |  streaming response via SSE
        |
  [L4] Natural Timing Layer
        |  typewriter effect, bubble auto-hide, variable intervals
        |
  [L5] Edge TTS Voice Output (optional)
        |  character-matched voice, emotion-aware
        v
  Tauri v2 Transparent Overlay
```

**Communication**: FastAPI backend (port 8080) serves SSE stream to the Tauri frontend. No WebSocket -- pure Server-Sent Events for simplicity.

---

## Characters

| ID | Name | Personality |
|----|------|-------------|
| `nozomi` | 노조미 | Tsundere girlfriend -- cares deeply but pretends not to. Backhanded compliments, worried excuses. |
| `robot` | UNIT-07 | AI analysis bot developing feelings -- tries to suppress emotions and fails. System error comedy. |
| `cat` | 나비 | Lazy cat -- acts disinterested but keeps watching. Short, sarcastic comments with occasional "냥". |
| `ghost` | 유령이 | Baby ghost -- everything is amazing and new. A ghost who is afraid of scary things. |
| `fox` | 콘 | Cunning fox -- loves teasing, gives hints wrapped in riddles. Always knows something you don't. |
| `slime` | 푸니 | Baby slime -- pure positivity. Doesn't understand complex things but cheers with all its heart. |

---

## Supported Games

| Game | Status | Notes |
|------|--------|-------|
| **Palworld** | Active | Primary test target |
| **MapleStory (KMS)** | Active | Korean MMORPG support |
| **General** | Active | Works with any game (generic prompts) |
| **Minesweeper** | Legacy | Original CV pipeline demo (template matching + solver) |

---

## Cost Estimate

The companion uses **Claude Haiku** (claude-haiku-4-5-20251001), the most cost-effective vision model:

- **Typical session**: ~$0.05--0.10 per hour
- **Quiet play**: Less frequent reactions = lower cost
- **Chatty mode**: More reactions = ~$0.15/hour max
- Input: ~$1.00 / million tokens, Output: ~$5.00 / million tokens

The config screen shows an estimate, and the debug bar (Ctrl+Shift+D) displays running cost.

---

## Privacy

- **Screen capture**: Screenshots are sent to Anthropic's Claude API for analysis. They are not stored by Anthropic beyond the API call (per their data policy).
- **No game memory access**: Only OS-level screen capture (DXGI Desktop Duplication). No process injection or memory reading.
- **Local training data**: If `--save-training` is enabled, screenshots and AI responses are saved locally in `training_data/` for future model fine-tuning. This data never leaves your machine unless you choose to share it.
- **Feedback data**: Thumbs up/down ratings and text feedback are saved locally in `training_data/<game>/feedback.jsonl`.
- **API key**: Stored in `backend/.env` (git-ignored). Never transmitted anywhere except Anthropic's API.
- **First-run consent**: The app shows a privacy consent screen before any data is captured.

---

## Project Structure

```
ai-game-overlay/
├── backend/
│   ├── tools/
│   │   ├── web_overlay.py    # Main entry point (5-layer pipeline)
│   │   └── live_overlay.py   # Character prompts, system prompts, utilities
│   ├── cv/
│   │   └── event_detector.py # L1: Local CV event detection
│   ├── personality/
│   │   └── engine.py         # L2: Personality engine (timing, emotions)
│   ├── capture/
│   │   └── screen.py         # dxcam/mss screen capture
│   ├── tts/
│   │   └── engine.py         # L5: Edge TTS voice output
│   ├── data/
│   │   └── characters.yaml   # Character definitions (personality, speech)
│   ├── static/
│   │   └── overlay.html      # Standalone HTML overlay (fallback)
│   └── .env                  # API keys (git-ignored)
├── frontend/
│   ├── src/
│   │   ├── screens/          # ConfigScreen, ConsentScreen, OverlayScreen
│   │   ├── components/       # CharacterAvatar, FeedbackForm, StatsPanel
│   │   └── App.tsx           # Main app (config -> consent -> overlay flow)
│   └── src-tauri/            # Rust backend (window management, process spawning)
├── training_data/            # Local training pairs (git-ignored)
└── README.md
```

---

## Contributing

Contributions welcome! Some areas that need work:

- **New characters**: Add entries to `backend/data/characters.yaml`
- **New game support**: Add game-specific prompts in `live_overlay.py`
- **CV improvements**: Enhance event detection in `backend/cv/event_detector.py`
- **UI polish**: Improve overlay animations and character avatars
- **Testing**: End-to-end tests for the full pipeline

### Development

```bash
# Run backend tests
cd backend && pytest tests/

# Run frontend in dev mode
cd frontend && npm run tauri dev

# Run backend standalone (for testing without Tauri)
cd backend && python -m backend.tools.web_overlay --game palworld --headless
```

---

## License

_License to be determined._
