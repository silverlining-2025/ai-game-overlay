"""Central configuration for the AI Game Overlay backend."""

from dataclasses import dataclass, field
import os


# --- Server ---
SSE_HOST = "127.0.0.1"
SSE_PORT = 8080

# --- Capture ---
CAPTURE_FPS = 10
DIFF_THRESHOLD = 5.0  # mean pixel diff below this = skip processing


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
class AIConfig:
    """Config for AI model integration."""
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = "claude-haiku-4-5-20251001"
    temperature: float = 0.7
    locale: str = "ko"


# --- Active config ---
AI = AIConfig()
