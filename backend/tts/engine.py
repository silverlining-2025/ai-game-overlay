"""Edge TTS integration — converts AI dialogue to spoken Korean audio.

Uses Microsoft Edge's neural TTS voices (free, no API key).
Adjusts speech rate and volume based on emotional state.

Voices:
- ko-KR-SunHiNeural (female, default)
- ko-KR-InJoonNeural (male)
- ko-KR-HyunsuNeural, ko-KR-BongJinNeural, etc.
"""

from __future__ import annotations

import asyncio
import io
import logging
import tempfile
import threading
from pathlib import Path

log = logging.getLogger(__name__)

# Voice + base prosody per character
CHARACTER_VOICES: dict[str, dict] = {
    "nozomi": {
        "voice": "ko-KR-SunHiNeural",    # Young, bright — matches tsundere energy
        "base_rate": "+5%",                # Slightly fast — energetic personality
    },
    "robot": {
        "voice": "ko-KR-InJoonNeural",    # Male, steady — robotic feel
        "base_rate": "-5%",                # Slightly slow — deliberate/analytical
    },
    "cat": {
        "voice": "ko-KR-YuJinNeural",     # Soft female — lazy cat vibe
        "base_rate": "-10%",               # Slow — languid, unbothered
    },
    "ghost": {
        "voice": "ko-KR-YuJinNeural",     # Soft female — ethereal/airy
        "base_rate": "-5%",                # Slightly slow — floaty
    },
    "fox": {
        "voice": "ko-KR-SeoHyeonNeural",  # Clear female — sharp/cunning
        "base_rate": "+10%",               # Fast — quick-witted
    },
    "slime": {
        "voice": "ko-KR-SunHiNeural",     # Bright female — bubbly energy
        "base_rate": "+15%",               # Fast — bouncy, hyper
    },
}

# Emotion → additional rate/volume adjustments (stacks on base_rate)
EMOTION_RATE: dict[str, int] = {
    "excitement": 30,
    "tension": 10,
    "amusement": 20,
    "concern": -15,
    "calm": 0,
}

EMOTION_VOLUME: dict[str, str] = {
    "excitement": "+20%",
    "tension": "+5%",
    "amusement": "+10%",
    "concern": "-5%",
    "calm": "+0%",
}


class TTSEngine:
    """Async TTS engine using edge-tts."""

    def __init__(self, character: str = "nozomi"):
        char_config = CHARACTER_VOICES.get(character, CHARACTER_VOICES["nozomi"])
        self.voice = char_config["voice"]
        self.base_rate = char_config.get("base_rate", "+0%")
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._start_async_loop()

    def _start_async_loop(self):
        """Start a dedicated asyncio event loop in a background thread."""
        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)

    def speak(self, text: str, emotion: str = "calm", on_done: callable = None):
        """Generate and play TTS audio in the background.

        Args:
            text: Korean text to speak
            emotion: dominant emotion for prosody adjustment
            on_done: optional callback when playback finishes
        """
        if not self._loop:
            log.warning("TTS loop not ready")
            return

        asyncio.run_coroutine_threadsafe(
            self._speak_async(text, emotion, on_done),
            self._loop,
        )

    async def _speak_async(self, text: str, emotion: str, on_done: callable = None):
        """Generate audio with edge-tts and play it."""
        try:
            import edge_tts

            # Combine base character rate + emotion adjustment
            base = int(self.base_rate.replace("%", "").replace("+", ""))
            emotion_adj = EMOTION_RATE.get(emotion, 0)
            combined = base + emotion_adj
            rate = f"{'+' if combined >= 0 else ''}{combined}%"
            volume = EMOTION_VOLUME.get(emotion, "+0%")

            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=rate,
                volume=volume,
            )

            # Save to temp file and play
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                tmp_path = tmp.name

            await communicate.save(tmp_path)

            # Play audio (non-blocking)
            self._play_audio(tmp_path)

            if on_done:
                on_done()

        except Exception as e:
            log.error(f"TTS error: {e}")

    def _play_audio(self, path: str):
        """Play an MP3 file on Windows."""
        import subprocess
        try:
            # Use Windows Media Player COM via PowerShell (supports MP3)
            ps_cmd = (
                f'Add-Type -AssemblyName presentationCore; '
                f'$p = New-Object System.Windows.Media.MediaPlayer; '
                f'$p.Open([Uri]"{Path(path).resolve()}"); '
                f'$p.Play(); '
                f'Start-Sleep -Milliseconds 100; '
                f'while($p.Position -lt $p.NaturalDuration.TimeSpan) {{ Start-Sleep -Milliseconds 100 }}; '
                f'$p.Close()'
            )
            subprocess.run(
                ["powershell", "-c", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception as e:
            log.error(f"Audio playback error: {e}")
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    async def generate_audio_bytes(self, text: str, emotion: str = "calm") -> bytes:
        """Generate TTS audio and return as bytes (for streaming via SSE)."""
        try:
            import edge_tts

            base = int(self.base_rate.replace("%", "").replace("+", ""))
            emotion_adj = EMOTION_RATE.get(emotion, 0)
            combined = base + emotion_adj
            rate = f"{'+' if combined >= 0 else ''}{combined}%"
            volume = EMOTION_VOLUME.get(emotion, "+0%")

            communicate = edge_tts.Communicate(
                text=text,
                voice=self.voice,
                rate=rate,
                volume=volume,
            )

            buf = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])

            return buf.getvalue()

        except Exception as e:
            log.error(f"TTS generation error: {e}")
            return b""

    def shutdown(self):
        """Clean up the async loop."""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
