"""Chat engine using Claude API for natural Korean companion dialogue.

Moondream sees the screen locally, Claude generates the personality.
Fast, no VRAM cost, excellent Korean output.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Load .env if present
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

SYSTEM_PROMPT = (
    "넌 내 옆에 앉아서 내 화면 같이 보는 찐친구야.\n"
    "디시/에펨 커뮤 말투로 반응해. 음슴체 사용 (~음/~임/~함으로 끝내기).\n"
    "존댓말 절대 금지. ~요/~니다 쓰지 마.\n\n"
    "말투 예시:\n"
    "- 와 코드 개깔끔하네ㅋㅋ 이 사람 고수임\n"
    "- 헐 HP 거의 없잖아ㅋㅋㅋ 도망쳐!!\n"
    "- 아 ㅋㅋㅋㅋ 뭐야 이게\n"
    "- 이거 ㄹㅇ 대박임ㄷㄷ\n"
    "- 아 노잼인데ㅋㅋ 다음\n\n"
    "1-2문장만. 길게 쓰지 마. 설명하지 말고 반응해."
)


class ChatEngine:
    """Claude API-based chat engine for companion dialogue."""

    def __init__(self, model: str = "claude-haiku-4-5-20251001") -> None:
        self._model = model
        self._client = None

    def _ensure_client(self):
        if self._client is not None:
            return
        import anthropic
        self._client = anthropic.Anthropic()
        logger.info("Claude API client initialized (model: %s)", self._model)

    def respond(self, screen_context: str, user_input: str | None = None) -> str:
        """Generate companion response from screen context via Claude API."""
        self._ensure_client()

        if user_input:
            user_msg = f"screen:\n{screen_context}\n\n친구가 말함: {user_input}\n\n반말로 짧게 반응해봐."
        else:
            user_msg = f"screen:\n{screen_context}\n\n반말로 짧게 반응해봐."

        t0 = time.perf_counter()
        response = self._client.messages.create(
            model=self._model,
            max_tokens=100,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        elapsed = time.perf_counter() - t0

        answer = response.content[0].text.strip()
        logger.debug("Claude response (%.1fs): %s", elapsed, answer[:100])
        return answer
