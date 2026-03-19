# P1 — Computer Vision & Detection Guide

Reference for the CV event detection pipeline. Update when changing detection methods or adding a new game.

## Event Detection Pipeline (`backend/cv/event_detector.py`)

### Overview
Runs every frame at ~30 FPS. Produces an `EventSignal` with a score (0.0–1.0) that determines whether to call the Claude API and with what urgency.

All analysis is done on **downscaled grayscale** (320×180) for speed. Target: <5ms per frame.

### Techniques Used

#### 1. Frame Differencing (Motion Detection)
- `cv2.absdiff(blur_prev, blur_curr)` with threshold > 18
- Gaussian blur (5×5) pre-filter removes particle/damage number noise
- Morphological opening (3×3 ellipse kernel) filters small noise
- Adaptive baseline from rolling median of last 20 frames

#### 2. Spatial Motion Zones (4×4 Grid)
- Frame divided into 4×4 grid zones
- Center 2×2 zones = gameplay area (motion_center)
- Outer 12 zones = UI/edge areas (motion_edges)
- Center-only motion = gameplay animation (lower score)
- Edge motion with UI change = state change (higher score)

#### 3. Brightness & Variance Tracking
- Mean brightness: sudden drops indicate danger/death screens
- Variance (std dev): sharp drops indicate menu/loading screens
- Menu detection: current variance < 40% of recent median

#### 4. Optical Flow (Every 3rd Frame)
- Farneback dense optical flow
- Mean magnitude indicates action intensity
- Skipped during sustained idle (adaptive frame skipping)

#### 5. Color Histogram Comparison
- HSV histogram (24×24 bins)
- Correlation < 0.6 = scene transition
- Skipped during idle periods

### Event Scoring

| Score | Label | Trigger |
|-------|-------|---------|
| 0.85+ | `scene_change` | Histogram shift or menu detected |
| 0.75 | `major` | Motion ratio > 6× baseline (not center-only) |
| 0.55 | `event` | Motion ratio > 3× or high flow + motion |
| 0.60 | `ui_event` | Edge motion + UI region change |
| 0.20 | `minor` | Motion > 2% or flow > 1.0 |
| 0.0 | `idle` | Nothing happening |

### EventSignal Fields
```python
@dataclass
class EventSignal:
    score: float          # 0.0–1.0 importance
    motion_pct: float     # % of pixels changed
    flow_magnitude: float # optical flow intensity
    scene_change: bool    # histogram/SSIM scene transition
    ui_change: bool       # UI region changed
    label: str            # idle/minor/event/major/scene_change
    motion_center: float  # center 2×2 zone motion %
    motion_edges: float   # outer zone motion %
    brightness: float     # mean brightness
    variance: float       # std deviation
    menu_likely: bool     # variance dropped significantly
```

---

## CLIP Scene Classification (`backend/cv/game_classifier.py`)

### Overview
Optional layer that classifies the current game state using CLIP (openai/clip-vit-base-patch32). Runs ~50ms on GPU, ~30ms cached.

### Modes
1. **Fine-tuned (CoOp)**: loads trained prompt embeddings from `backend/models/game_classifier/`
2. **Zero-shot**: uses hand-crafted text prompts — works out of the box

### 26-Label Taxonomy (Palworld)

| Group | Labels |
|-------|--------|
| Combat (3) | `combat`, `capturing`, `boss_fight` |
| Exploration (5) | `exploring`, `mounted_ground`, `mounted_flying`, `gathering`, `dungeon` |
| Base (3) | `building`, `base_view`, `crafting_menu` |
| Menu/UI (7) | `inventory`, `pal_management`, `technology_tree`, `map_screen`, `merchant_shop`, `breeding_condenser`, `settings_menu` |
| Game Flow (7) | `loading_screen`, `death_respawn`, `cutscene_notification`, `dialogue_interaction`, `character_creation`, `world_select`, `title_screen` |
| Meta (1) | `external_app` |

### Integration with Event Detector
CLIP labels override event detector labels when confidence is high:
- `loading_screen` at >70% → forces `loading` label
- Menu-type labels at >60% → forces that label
- Helps the personality engine route to appropriate responses

---

## Adding a New Game

1. Add game-specific UI regions to `EventDetector._get_ui_regions()`
2. Create `backend/data/games/<game>.yaml` with visual cue descriptions
3. Optionally add game-specific CLIP labels if the 26-label taxonomy doesn't fit
4. Update `event_detector.py` if game has unique UI patterns worth detecting

---

## Anti-Cheat Safety

All detection uses screen capture only (DXGI Desktop Duplication via dxcam). No memory reading, no process attachment, no injection. The overlay window is excluded from capture via `WDA_EXCLUDEFROMCAPTURE`.
