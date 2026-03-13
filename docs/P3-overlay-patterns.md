# P3 — Overlay UI Patterns & Anti-Cheat Notes

## Overlay Window Setup (Tauri v2)

### Transparent Click-Through Window
- Tauri window config: `transparent: true`, `decorations: false`, `always_on_top: true`
- Click-through: `set_ignore_cursor_events(true)` with forward option
- Toggle interactive mode via global hotkey (F9)
- Fullscreen overlay matching monitor resolution

### Rendering Strategy
- Use HTML Canvas or WebGL for drawing overlay elements
- Render only when data changes (not every animation frame)
- Keep overlay area minimal — small widgets, not full-screen effects
- Semi-transparent backgrounds (rgba) for readability without blocking game view

## Widget Patterns

### HUD Widgets (항상 표시)
- Position: fixed corners, user-draggable
- Style: semi-transparent dark background, white/colored text
- Content: HP/MP bars, buff timers, FPS counter, EXP rate
- Update: real-time from `state_update` messages

### AI Coach Panel (코치 패널)
- Position: side panel, collapsible
- Style: chat-like interface with message bubbles
- Content: strategic suggestions, warnings, tips
- Language: Korean (enforced by i18n + AI system prompt)
- Toggle: hotkey or click (when interactive mode active)

### Suggestion Highlights (제안 하이라이트)
- Colored semi-transparent rectangles over game elements
- Green: safe / recommended
- Red: danger / mines
- Yellow: caution / attention needed
- Position: calculated from `origin` + `cell_size` in state_update

## Anti-Cheat Compatibility

### Safe Practices
- External transparent window (WS_EX_TRANSPARENT + WS_EX_LAYERED)
- Screen capture via DXGI Desktop Duplication (same as OBS, ShareX)
- No process attachment, no memory reading, no DLL injection
- No DirectX/Vulkan hooking

### Known Anti-Cheat Systems
| System | Used By | Our Approach Safe? |
|--------|---------|-------------------|
| nProtect GameGuard | MapleStory | Yes — no injection |
| EasyAntiCheat | Many games | Yes — external window |
| BattlEye | Many games | Yes — external window |
| Riot Vanguard | Valorant | Yes — external window |

### Requirements
- Game MUST run in **Borderless Windowed** or **Windowed** mode
- Exclusive fullscreen will cover our overlay
- Document this clearly for users

### Testing Protocol
1. Launch overlay first, then game
2. Play in town/safe area for 10 minutes
3. Check for anti-cheat warnings or disconnections
4. If clear, proceed to normal gameplay
5. Monitor for any behavioral flags over extended sessions
