"""Data loading utilities for YAML-based configuration.

Shared by live_overlay.py and tts/engine.py to avoid circular imports.
"""

from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, 'frozen', False):
    _REPO_ROOT = Path(sys.executable).parent
else:
    _REPO_ROOT = Path(__file__).resolve().parents[2]

_DATA_DIR = _REPO_ROOT / "backend" / "data"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file, returning empty dict on failure."""
    import yaml
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_characters_yaml() -> dict:
    """Load the raw characters.yaml data."""
    return _load_yaml(_DATA_DIR / "characters.yaml")


def load_characters_prompts(locale: str = "ko") -> dict[str, str]:
    """Load character prompts from YAML, formatted for the given locale."""
    data = load_characters_yaml()
    prompts = {}
    for char_id, char_data in data.items():
        if not isinstance(char_data, dict):
            continue
        name = char_data.get("name", char_id)
        desc = char_data.get("description", "")
        if locale == "en":
            personality = char_data.get("personality_en") or char_data.get("personality", "")
            speech = char_data.get("speech_style_en") or char_data.get("speech_style", "")
            prompts[char_id] = f"You are '{name}'. {desc}\n\n{personality}\n{speech}"
        else:
            personality = char_data.get("personality", "")
            speech = char_data.get("speech_style", "")
            prompts[char_id] = f"넌 '{name}'야. {desc}\n\n{personality}\n{speech}"
    return prompts


def load_character_templates() -> dict[str, dict]:
    """Load per-character template responses from YAML."""
    data = load_characters_yaml()
    templates = {}
    for char_id, char_data in data.items():
        if not isinstance(char_data, dict):
            continue
        char_templates = char_data.get("templates", {})
        if char_templates:
            templates[char_id] = char_templates
    return templates


def load_character_tts_config() -> dict[str, dict]:
    """Load per-character TTS config from YAML."""
    data = load_characters_yaml()
    tts_configs = {}
    for char_id, char_data in data.items():
        if not isinstance(char_data, dict):
            continue
        tts = char_data.get("tts", {})
        if tts:
            tts_configs[char_id] = tts
    return tts_configs


def load_game_context(game: str, locale: str = "ko") -> str:
    """Load game context from YAML file. Returns empty string if not found."""
    data = _load_yaml(_DATA_DIR / "games" / f"{game}.yaml")
    if not data:
        return ""
    if locale == "en":
        return data.get("context_en", data.get("context_ko", ""))
    return data.get("context_ko", "")
