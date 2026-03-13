# P1 — Computer Vision Guide

Reference for CV techniques used per game. Update when adding a new game or changing detection methods.

## General Techniques

### Frame Differencing (Gate)
- `cv2.absdiff(prev, curr)` → mean pixel diff < threshold (5.0) → skip
- Eliminates 80-95% of redundant processing
- Applied before any game-specific processing

### Template Matching
- `cv2.matchTemplate(img, template, cv2.TM_CCOEFF_NORMED)`
- Threshold: 0.85+ for reliable matches
- Store templates as small PNGs in `backend/templates/{game}/`
- Works best for static UI elements (icons, buttons, indicators)

### Color Thresholding (HSV)
- Convert ROI to HSV: `cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)`
- Mask color range: `cv2.inRange(hsv, lower, upper)`
- Count non-zero pixels for bar fill percentage
- Ideal for HP/MP/EXP bars with known colors

### EasyOCR (Korean + English)
- `reader = easyocr.Reader(['ko', 'en'], gpu=True)`
- Lazy-load on first use (~1.5GB VRAM)
- Pre-crop ROI to text-only region for speed
- Game fonts may need preprocessing (threshold, denoise)

---

## Game: Minesweeper (지뢰찾기)

### ROI Definition
- Grid region: manually configured or auto-detected via contour detection
- Cell size: typically 16x16 or 32x32 depending on version

### Cell Classification
Primary method: **dominant color matching** (Minesweeper numbers have unique colors)

```python
CELL_COLORS_BGR = {
    (255, 0, 0): "1",      # blue
    (0, 128, 0): "2",      # green
    (0, 0, 255): "3",      # red
    (128, 0, 0): "4",      # dark blue
    (0, 0, 128): "5",      # maroon
    (128, 128, 0): "6",    # teal
}
```

Fallback: template matching against captured cell reference images.

### State Detection
- Unrevealed: 3D raised border pattern (edge detection)
- Revealed empty: uniform flat color
- Flag: specific icon template
- Mine: specific icon template (game over state)

---

## Game: MapleStory (메이플스토리)

### ROI Definitions
| Element | Location | Detection Method |
|---------|----------|-----------------|
| HP bar | Bottom-center, fixed | Red color threshold + pixel count |
| MP bar | Below HP, fixed | Blue color threshold + pixel count |
| EXP bar | Bottom of screen, fixed | Yellow color threshold |
| Minimap | Top-right corner | Template match frame, analyze contents |
| Buff icons | Top-right, below minimap | Template matching per icon |
| Chat | Bottom-left | EasyOCR (Korean) |
| Damage numbers | Floating above mobs | EasyOCR or color-based blob detection |

### Tiered Processing
- **Every frame**: HP/MP percentage (fast color threshold, <5ms)
- **Every 500ms**: Buff icons via template matching (~20ms)
- **Every 3s**: Chat OCR, damage number OCR (~100ms)

### Templates Needed
Capture manually during gameplay and store in `backend/templates/maplestory/`:
- `hp_bar_frame.png` — HP bar border for locating
- `buff_*.png` — each buff icon (Holy Symbol, etc.)
- `mob_hp_bar.png` — generic mob HP bar template
