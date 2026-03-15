"""Central configuration for the AI Game Overlay backend."""

from dataclasses import dataclass, field
import os


# --- Server ---
WS_HOST = "localhost"
WS_PORT = 9600

# --- Capture ---
CAPTURE_FPS = 10
DIFF_THRESHOLD = 5.0  # mean pixel diff below this = skip processing

# --- CV ---
TEMPLATE_MATCH_THRESHOLD = 0.85
OCR_LANGUAGES = ["ko", "en"]


@dataclass
class ROI:
    """Region of interest on screen."""
    x: int
    y: int
    w: int
    h: int

    @property
    def slice(self) -> tuple[slice, slice]:
        return (slice(self.y, self.y + self.h), slice(self.x, self.x + self.w))


@dataclass
class MinesweeperConfig:
    """Config for Minesweeper detection."""
    grid_roi: ROI | None = None  # auto-detected if None
    cell_size: int = 16  # winmine.html / classic WinMine default cell size
    # BGR colors for numbered cells (classic Minesweeper)
    cell_colors_bgr: dict[tuple[int, int, int], str] = field(default_factory=lambda: {
        (255, 0, 0): "1",      # blue
        (0, 128, 0): "2",      # green
        (0, 0, 255): "3",      # red
        (128, 0, 0): "4",      # dark blue
        (0, 0, 128): "5",      # maroon
        (128, 128, 0): "6",    # teal
        (0, 0, 0): "7",        # black
        (128, 128, 128): "8",  # gray
    })


@dataclass
class MapleStoryConfig:
    """Config for MapleStory detection."""
    hp_bar_roi: ROI = field(default_factory=lambda: ROI(x=250, y=700, w=200, h=15))
    mp_bar_roi: ROI = field(default_factory=lambda: ROI(x=250, y=720, w=200, h=15))
    exp_bar_roi: ROI = field(default_factory=lambda: ROI(x=0, y=755, w=1024, h=10))
    minimap_roi: ROI = field(default_factory=lambda: ROI(x=800, y=0, w=200, h=150))
    chat_roi: ROI = field(default_factory=lambda: ROI(x=0, y=500, w=350, h=200))
    # HP bar color range in HSV
    hp_hsv_lower: tuple[int, int, int] = (0, 150, 150)
    hp_hsv_upper: tuple[int, int, int] = (10, 255, 255)
    mp_hsv_lower: tuple[int, int, int] = (100, 150, 150)
    mp_hsv_upper: tuple[int, int, int] = (130, 255, 255)


@dataclass
class MoondreamConfig:
    """Config for Moondream2 local VLM."""
    model_id: str = "vikhyatk/moondream2"
    device: str = "cuda"
    revision: str | None = None
    query_interval: float = 3.0  # seconds between periodic queries
    default_prompt: str = "Describe what is happening in this game screenshot. Focus on the player's status, any dangers, and important UI elements."
    locale: str = "ko"


@dataclass
class AIConfig:
    """Config for AI model integration."""
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = "claude-haiku-4-5-20251001"
    temperature: float = 0.7
    locale: str = "ko"
    moondream: MoondreamConfig = field(default_factory=MoondreamConfig)


# --- Active game configs ---
GAMES = {
    "minesweeper": MinesweeperConfig(),
    "maplestory": MapleStoryConfig(),
}

AI = AIConfig()
