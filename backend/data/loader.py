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


def load_game_knowledge(game: str, locale: str = "ko") -> dict[str, list[str]]:
    """Load game knowledge tips from YAML. Returns dict of category → tips list."""
    data = _load_yaml(_DATA_DIR / "games" / f"{game}.yaml")
    if not data:
        return {}
    key = "knowledge_en" if locale == "en" else "knowledge_ko"
    knowledge = data.get(key, {})
    if not knowledge:
        # Fall back to other locale
        fallback_key = "knowledge_ko" if locale == "en" else "knowledge_en"
        knowledge = data.get(fallback_key, {})
    return knowledge if isinstance(knowledge, dict) else {}


def get_relevant_tips(game: str, activity: str, locale: str = "ko", max_tips: int = 3) -> str:
    """Get contextually relevant tips for injection into the AI prompt.

    Args:
        game: Game identifier (e.g. "palworld")
        activity: Current activity from session state (combat, capture, build, etc.)
        locale: Language
        max_tips: Maximum tips to include

    Returns:
        Formatted tips string for prompt injection, or empty string.
    """
    import random
    knowledge = load_game_knowledge(game, locale)
    if not knowledge:
        return ""

    # Map activities to knowledge categories
    activity_map = {
        "combat": ["combat", "capture"],
        "capture": ["capture"],
        "build": ["base"],
        "craft": ["base", "progression"],
        "gather": ["base", "progression"],
        "explore": ["progression", "capture"],
        "menu": ["progression"],
        "idle": ["progression"],
        "travel": ["progression"],
    }

    categories = activity_map.get(activity, ["progression"])
    tips = []
    for cat in categories:
        cat_tips = knowledge.get(cat, [])
        tips.extend(cat_tips)

    if not tips:
        # Fall back to any available tips
        for cat_tips in knowledge.values():
            tips.extend(cat_tips)

    if not tips:
        return ""

    # Select random subset
    selected = random.sample(tips, min(max_tips, len(tips)))

    if locale == "en":
        header = "[Game Tips — use naturally if relevant]"
    else:
        header = "[게임 팁 — 관련 있으면 자연스럽게 활용]"

    return header + "\n" + "\n".join(f"- {tip}" for tip in selected)
