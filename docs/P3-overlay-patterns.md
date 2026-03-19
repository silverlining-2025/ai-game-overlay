# P3 — Overlay UI Patterns & Anti-Cheat Notes

## Overlay Window Setup (Tauri v2)

### Window Configuration
- Config window: `500×780`, centered, decorations on, non-transparent
- Overlay window: `620×320`, transparent, no decorations, always on top
- Created dynamically in `lib.rs` via `start_companion` command
- Overlay excluded from screen capture: `SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE)`

### Click-Through Behavior
- Default: `setIgnoreCursorEvents(true)` — clicks pass through to game
- Hold Alt: temporarily interactive (drag, click buttons)
- Overlay controls (⚙ and ✕) always clickable via `.ctrl-btn` class

### Window Lifecycle
- Start: Config window → user clicks Start → overlay created → config closed
- Stop: Overlay ⚙ button → `stop_companion` → Python killed → config recreated → overlay closed
- Quit: ✕ button → `quit_app` → Python killed → app exits
- **Critical**: Always create new window BEFORE closing old one (prevents zero-window exit)

## Character Avatar System

### Nozomi (Primary)
- WebP sprite assets in `frontend/public/characters/nozomi/`
- 22 expressions × 4 outfits (casual, dress, outdoor, school)
- Mood → expression mapping via `NOZOMI_EXPRESSIONS` lookup
- Crossfade transition (300ms opacity) between expressions
- Eye blink animation (150ms every 3-6s)
- Mood-specific CSS animations (breathing, bouncing, swaying)

### Other Characters (Lottie Fallback)
- Lottie JSON animations in `frontend/public/lottie/`
- `robot.json`, `cat.json`, `ghost.json`, `fox.json`, `slime.json`
- Mood adjusts playback speed

### Micro-Expressions (VTuber-style)
- Random mood shifts every 15-30s during idle
- Moods: curious, amused, chill, blush
- 2.5s duration, then returns to base mood
- Only triggers when not thinking or speaking

## Speech Bubble

### Streaming Text Display
- `stream_start` → clear bubble, show thinking
- `stream_chunk` → append text directly to DOM (no React re-render per char)
- `stream_end` → set final text, show feedback buttons
- Auto-hide after `min(15s, max(4s, text.length × 80ms))`

### Feedback Buttons
- ▲ (up) / ▼ (down) appear after each response for 6s
- Sends to `POST /feedback` with cycle number and response text
- Used for training data collection

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Alt (hold) | Make overlay interactive (drag, click) |
| Ctrl+Shift+D | Toggle debug bar (cycle, latency, cost, event) |
| Ctrl+Shift+S | Toggle session stats panel |
| Alt+F | Toggle text feedback form |
| Esc | Close overlay (in standalone mode) |

## System Tray

- Icon in system tray with menu:
  - "오버레이 보기/숨기기" — toggle overlay visibility
  - "설정" — show config window
  - "종료" — quit everything

## Anti-Cheat Compatibility

### Safe Practices
- External transparent window (not attached to game process)
- Screen capture via DXGI Desktop Duplication (same as OBS, ShareX, Discord)
- Overlay excluded from own capture via `WDA_EXCLUDEFROMCAPTURE`
- No process attachment, no memory reading, no DLL injection
- No DirectX/Vulkan hooking

### Known Anti-Cheat Systems
| System | Used By | Our Approach Safe? |
|--------|---------|-------------------|
| nProtect GameGuard | MapleStory | Yes — no injection |
| EasyAntiCheat | Palworld, many | Yes — external window |
| BattlEye | Many games | Yes — external window |
| Riot Vanguard | Valorant | Yes — external window |

### Requirements
- Game MUST run in **Borderless Windowed** or **Windowed** mode
- Exclusive fullscreen will cover our overlay
- Document this clearly for users
