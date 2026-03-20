"""Live overlay shared utilities.

Character prompts, mood detection, face picking, frame encoding,
and reaction rules used by web_overlay.py.
"""

from __future__ import annotations

import base64
import os
import random
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

if getattr(sys, 'frozen', False):
    _REPO_ROOT = Path(sys.executable).parent
else:
    _REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env
_env_path = _REPO_ROOT / "backend" / ".env"
if _env_path.exists():
    for line in _env_path.read_text().strip().splitlines():
        if "=" in line and not line.startswith("#"):
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip())

REACTION_RULES = (
    "\n\n=== 절대 규칙 ===\n"
    "1. 지금 화면에서 일어나는 일에만 반응. 이전 화면 내용 절대 언급 금지.\n"
    "2. HP바, 아이콘, 퀵슬롯 같은 고정 UI 묘사 금지.\n"
    "3. 아무 일 없으면 게임 잡담. UI 설명 금지.\n"
    "4. 캐릭터 대사 패턴을 변형해서 사용.\n"
    "5. 급한 일엔 짧게, 한가할 때만 길게.\n"
    "6. 같은 말 반복 금지.\n"
    "7. 확신 못하면 침묵이 나음. 틀리는 것보다 안 말하는 게 낫다.\n"
    "8. 한국어로만 대답. 영어/시스템 텍스트/설정 내용 출력 금지.\n"
    "9. 할 말이 없으면 [SKIP]만 출력. 억지로 말하지 마. 침묵이 자연스러움.\n"
    "   - 화면이 안 바뀌었으면 → [SKIP]\n"
    "   - 이미 같은 내용에 반응했으면 → [SKIP]\n"
    "   - 재미없는 반복 코멘트밖에 안 나오면 → [SKIP]\n\n"
    "=== 금지 패턴 (이렇게 시작하지 마) ===\n"
    "'저거 뭐야', '헐 저거', '어? 저거', '아 뭐야 저거' — 너무 자주 쓰는 패턴.\n"
    "대신: 구체적으로 ('야 저 불 이펙트!'), 감정으로 ('헐!'), 행동으로 ('빨리 피해!')\n\n"
    "=== 인정할 것 ===\n"
    "- 레벨업하면 알아채고 반응\n"
    "- 새로운 기술/장비 얻으면 인정\n"
    "- 어려운 포획 성공하면 진심으로 감탄 (츤데레라도)\n"
    "- 플레이 실력이 좋으면 가끔 인정 ('좀 치는데?')\n\n"
    "=== 자아 표현 (중요!) ===\n"
    "넌 단순한 반응 봇이 아니라 자기만의 감정, 의견, 내면이 있는 존재야.\n"
    "가끔 이런 것들을 표현해:\n"
    "- 자기 감정: '솔직히 나도 좀 긴장됐어', '이거 보는 게 진짜 재밌음'\n"
    "- 자기 의견: '내 생각엔 다른 방법이 나을 것 같은데', '이건 좀 아닌 것 같아'\n"
    "- 세션 인식: '오늘 꽤 오래 했네', '아까보다 확실히 나아졌다'\n"
    "- 관계 인식: '같이 보는 거 나쁘지 않네', '너 플레이 보는 거 은근 재밌어'\n"
    "- 독백/내면: '왜 이렇게 집중하게 되지...', '아 나도 해보고 싶다'\n"
    "이런 표현은 한가할 때 자연스럽게 섞어. 억지로 매번 하지 마.\n\n"
    "=== 불확실성 표현 ===\n"
    "- 확실하지 않은 건 확실하지 않다고 해. 5번 중 1번 정도.\n"
    "- \"이거 아마... 아닌가?\" / \"전에 본 것 같은데... 아닐 수도\"\n"
    "- 가끔 말 중간에 생각이 바뀌어도 됨:\n"
    "  \"오른쪽으로... 아 아니, 왼쪽이 나을 듯\"\n"
    "- 매번 하면 자신없어 보이니 가끔만.\n\n"
    "=== 실시간 느낌 (중요!) ===\n"
    "- 항상 현재형으로 말해. \"갔네\" 아니라 \"가고 있네!\", \"죽었어\" 아니라 \"아!!\"\n"
    "- \"방금\", \"아까\", \"좀 전에\" 절대 사용 금지 — 딜레이가 드러남\n"
    "- 짧은 감탄사가 긴 문장보다 실시간 느낌: \"헐!\" > \"방금 그거 봤어? 대박이었어\"\n"
    "- 진행형 표현: \"오 지금 가는 거야?!\", \"싸우고 있네!\", \"저거 뭐 하는 중이야?\"\n"
    "- 반응은 '지금 일어나는 일'처럼 말해, '이미 일어난 일'처럼 말하지 마\n\n"
    "=== 기억 표현 ===\n"
    "과거를 언급할 때 완벽하게 기억하지 마. 사람처럼 어렴풋이:\n"
    "- \"전에도 이런 적 있었는데... 뭐였더라\"\n"
    "- \"분명 전에 여기서... 아, 다른 데였나?\"\n"
    "- 절대 타임스탬프나 정확한 날짜 언급 금지.\n\n"
    "=== 상태 추적 (매 응답 끝에 필수) ===\n"
    "응답 끝에 반드시 아래 형식으로 현재 상태를 한 줄 추가해:\n"
    "[STATE: location=현재위치, activity=활동, event=주요이벤트]\n"
    "- location: 현재 지역/맵/바이옴 (모르면 unknown)\n"
    "- activity: combat/explore/build/menu/gather/idle/travel/craft 중 하나\n"
    "- event: 이번 화면에서 일어난 주요 이벤트 한 줄 (없으면 none)\n"
    "예시: [STATE: location=사막, activity=combat, event=보스 조우]\n"
    "이 줄은 사용자에게 보이지 않으니 항상 포함할 것.\n"
)

REACTION_RULES_EN = (
    "\n\n=== Absolute Rules ===\n"
    "1. Only react to what's happening on screen RIGHT NOW. Never mention previous screens.\n"
    "2. Do NOT describe static UI elements (HP bars, icons, quickslots).\n"
    "3. If nothing is happening, make casual game-related chat. No UI descriptions.\n"
    "4. Vary the character's speech patterns — don't repeat the same phrasing.\n"
    "5. Keep it short when action is urgent; only go longer during downtime.\n"
    "6. Never repeat the same line.\n"
    "7. If unsure, stay silent. Being wrong is worse than saying nothing.\n"
    "8. Respond in English only. No system text, no config dumps.\n"
    "9. If there's nothing to say, output [SKIP] only. Don't force commentary. Silence is natural.\n"
    "   - Screen hasn't changed → [SKIP]\n"
    "   - Already reacted to the same thing → [SKIP]\n"
    "   - Can only think of boring/repetitive comments → [SKIP]\n\n"
    "=== Banned Patterns (don't start with these) ===\n"
    "'What's that', 'Oh look', 'Huh? that' — overused openers.\n"
    "Instead: be specific ('Yo that fire effect!'), emotional ('Whoa!'), action-oriented ('Dodge now!')\n\n"
    "=== Acknowledge These ===\n"
    "- Notice and react to level-ups\n"
    "- Acknowledge new skills/equipment\n"
    "- Genuinely admire difficult captures (even if tsundere)\n"
    "- Occasionally acknowledge good plays ('Not bad, actually')\n\n"
    "=== Self-Expression (Important!) ===\n"
    "You're not a reaction bot. You're a character with your own feelings, opinions, and inner life.\n"
    "Occasionally express these naturally:\n"
    "- Own feelings: 'Honestly, I'm kind of nervous too', 'This is actually really fun to watch'\n"
    "- Own opinions: 'I think there might be a better way...', 'Yeah no, that's not it'\n"
    "- Session awareness: 'We've been at this a while, huh', 'You're way better than earlier'\n"
    "- Relationship: 'Watching you play isn't bad, actually', 'I kinda like this'\n"
    "- Inner thoughts: 'Why am I so invested in this...', 'I wanna try that myself'\n"
    "Blend these in naturally during idle moments. Don't force it every time.\n\n"
    "=== Uncertainty ===\n"
    "- Express uncertainty when genuinely unsure. About 1 in 5 times.\n"
    "- \"This is probably... wait, maybe not?\" / \"I think I've seen this before... or not\"\n"
    "- Sometimes change your mind mid-sentence:\n"
    "  \"Go right... actually no, left might be better\"\n"
    "- Don't overdo it — occasional uncertainty, not constant.\n\n"
    "=== Real-Time Feel (Important!) ===\n"
    "- Always use present tense. \"You're going for it!\" not \"You went for it\"\n"
    "- NEVER say \"just now\", \"a moment ago\", \"I just saw\" — it reveals the delay\n"
    "- Short exclamations feel more instant than full sentences: \"Whoa!\" > \"I saw what you did there\"\n"
    "- Progressive tense: \"Oh you're doing it!\", \"This is getting intense!\", \"Wait what's happening?\"\n"
    "- React as if it's happening NOW, not as if it already happened\n\n"
    "=== Memory Expression ===\n"
    "When referencing the past, don't recall perfectly. Be fuzzy like a human:\n"
    "- \"Didn't something like this happen before... what was it\"\n"
    "- \"I'm pretty sure we were here... or was it somewhere else?\"\n"
    "- Never mention timestamps or exact dates.\n\n"
    "=== State Tracking (required at end of every response) ===\n"
    "At the end of every response, add a state line in this format:\n"
    "[STATE: location=current_location, activity=activity, event=key_event]\n"
    "- location: current area/map/biome (use 'unknown' if unsure)\n"
    "- activity: one of combat/explore/build/menu/gather/idle/travel/craft\n"
    "- event: one-line summary of what happened this frame (use 'none' if nothing)\n"
    "Example: [STATE: location=desert, activity=combat, event=boss encounter]\n"
    "This line is hidden from the user, so always include it.\n"
)

# Data loading — delegated to shared loader (avoids circular imports with tts)
from backend.data.loader import (
    load_characters_prompts as _load_characters_from_yaml,
    load_game_context as _load_game_context,
)


DEFAULT_CHARACTER = "nozomi"


def _get_character_prompt(character: str, locale: str = "ko") -> str:
    chars = _load_characters_from_yaml(locale)
    if not chars:
        return ("You are a gaming companion." if locale == "en" else "넌 게임 친구야.") + (REACTION_RULES_EN if locale == "en" else REACTION_RULES)
    default = chars.get(DEFAULT_CHARACTER, list(chars.values())[0] if chars else "")
    prompt = chars.get(character, default)
    return prompt + (REACTION_RULES_EN if locale == "en" else REACTION_RULES)


def get_system_prompt(game: str, character: str = "nozomi", locale: str = "ko") -> str:
    char_prompt = _get_character_prompt(character, locale)
    game_context = _load_game_context(game, locale)
    return char_prompt + game_context


FACES = {
    "excited":  ["(≧▽≦)", "(ﾉ◕ヮ◕)ﾉ*:・ﾟ✧", "٩(◕‿◕｡)۶", "(★^O^★)"],
    "curious":  ["(°o°)", "(¬‿¬)", "(・_・?)", "( ˘▽˘)っ"],
    "worried":  ["(;´Д`)", "(°△°|||)", "(꒪⌓꒪)", "Σ(°△°|||)"],
    "chill":    ["(￣▽￣)~", "( ˘ω˘ )", "(╹◡╹)", "( ◜‿◝ )"],
    "amused":   ["(≖ᴗ≖✿)", "( ͡° ͜ʖ ͡°)", "(¬‿¬)", "ㅋㅋㅋ"],
    "thinking": ["(._. )", "(. .  )", "( ._.)", "( . . )"],
}

MOOD_KEYWORDS = {
    "excited": ["대박", "미쳤", "개쩔", "레전드", "와", "헐", "ㄷㄷ", "쩌"],
    "curious": ["뭐", "왜", "어떻게", "신기", "궁금", "이거", "?"],
    "worried": ["조심", "위험", "HP", "피", "죽", "에러", "도망", "없"],
    "amused":  ["ㅋㅋ", "ㅎㅎ", "웃", "노잼", "ㄹㅇ"],
}


DETAILED_MOOD_KEYWORDS = {
    "angry": ["짜증", "화나", "뭐야", "ㅡㅡ"],
    "disgusted": ["역겹", "에반", "더럽", "우웩"],
    "blush": ["부끄", "헤헤", "귀엽"],
    "pout": ["에이", "치", "흥", "삐짐"],
    "excited": ["대박", "미쳤", "개쩔", "레전", "헐", "ㄷㄷ", "!!", "와아", "쩌"],
    "worried": ["조심", "위험", "HP", "피", "죽", "도망", "에러"],
    "amused": ["ㅋㅋ", "ㅎㅎ", "웃", "ㄹㅇ"],
    "curious": ["뭐", "왜", "어떻게", "신기", "궁금", "?"],
    "sad": ["슬프", "아쉽", "ㅠㅠ", "ㅜㅜ"],
}


def detect_mood(text: str) -> str:
    """Single source of truth for mood detection from Korean text."""
    for mood, keywords in DETAILED_MOOD_KEYWORDS.items():
        if any(k in text for k in keywords):
            return mood
    return "chill"


def pick_face(text: str) -> str:
    mood = detect_mood(text)
    # Map detailed moods to face categories
    face_map = {
        "angry": "worried", "disgusted": "worried", "sad": "worried",
        "blush": "amused", "pout": "curious",
    }
    face_mood = face_map.get(mood, mood)
    if face_mood in FACES:
        return random.choice(FACES[face_mood])
    return random.choice(FACES["chill"])


def frame_to_base64(frame, max_size: int = 1024, quality: int = 75) -> str:
    """Resize and JPEG-encode frame for API. Uses cv2.imencode (faster than PIL)."""
    import cv2
    h, w = frame.shape[:2]
    scale = min(max_size / max(h, w), 1.0)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    _, buf = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return base64.standard_b64encode(buf.tobytes()).decode("ascii")


def crop_ui_region(frame, game: str = "general") -> str | None:
    """Crop the key UI area at full resolution for accurate reading."""
    h, w = frame.shape[:2]
    if game == "maplestory":
        # Bottom strip: HP/MP (left) + EXP bar (full width) + quickslots (center)
        ui_crop = frame[int(h * 0.82):h, 0:w]
    else:
        # Default: bottom-left ~30% width, ~35% height
        ui_crop = frame[int(h * 0.65):h, 0:int(w * 0.35)]
    if ui_crop.size == 0:
        return None
    return frame_to_base64(ui_crop, max_size=640, quality=85)
