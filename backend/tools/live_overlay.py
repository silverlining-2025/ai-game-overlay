"""Live AI companion overlay — POC demo.

Single-call architecture: screenshot → Claude Vision API → Korean reaction.
Hides overlay during capture to avoid self-referencing.
Rolling context history so Claude remembers what's been happening.

Usage:
    python -m backend.tools.live_overlay
    python -m backend.tools.live_overlay --interval 3
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import random
import sys
import threading
import time
import warnings
from collections import deque
from pathlib import Path

warnings.filterwarnings("ignore")

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

BASE_PROMPT = (
    "넌 내 옆에서 같이 게임 보는 찐친구야. 이 게임 잘 알고 같이 빠져있음.\n"
    "디시/에펨 커뮤 말투로 반응해. 음슴체 사용 (~음/~임/~함으로 끝내기).\n"
    "존댓말 절대 금지. ~요/~니다 쓰지 마.\n\n"
    "말투 예시:\n"
    "- 와 이거 개쩌는데ㅋㅋ 미쳤음\n"
    "- 헐 HP 없잖아 물약 먹어!!\n"
    "- 아 ㅋㅋㅋㅋ 방금 뭐 한 거야\n"
    "- 이거 ㄹㅇ 대박임ㄷㄷ\n"
    "- 오 잘 잡았다 ㅋㅋ\n\n"
    "중요 규칙:\n"
    "- 화면에서 확실히 보이는 것에 대해선 자신있게 반응해\n"
    "- 잘 안 보이거나 애매한 건 자연스럽게 넘어가 (틀린 말 하느니 안 하는 게 나음)\n"
    "- 구체적인 이름/수치를 확신 못하면 일반적으로 말해 (\"저 몬스터\" 대신 \"저거\")\n"
    "- 분위기, 액션, 감정에 집중해. 틀릴 수 있는 디테일보다 확실한 큰 그림\n"
    "- 1-2문장만. 길게 쓰지 마\n"
    "- 같은 말 반복 금지\n"
    "- 이전 반응들 보고 흐름 이어가"
)

GAME_CONTEXTS = {
    "palworld": (
        "\n\n[팰월드(Palworld) — 넌 이 게임 잘 아는 친구]\n"
        "팰월드 = 팰(생물)을 잡고 키우고 싸우는 오픈월드 서바이벌. 총켓몬이라고도 함ㅋㅋ\n\n"
        "화면 읽는 법:\n"
        "- 좌하단: HP(초록바), 배고픔(주황바), 팰 파티 아이콘 5개\n"
        "- 화면 상단 큰 HP바 = 보스전 중\n"
        "- 적 머리 위 HP바 = 전투 중\n"
        "- 공(팰스피어) 던지면 = 포획 시도. 흔들리면 긴장\n"
        "- 건설 프리뷰(반투명) = 거점 짓는 중\n"
        "- 메뉴/인벤 열림 = 정리 중\n\n"
        "게임 지식 (확실할 때만 써):\n"
        "- 포획: 팰스피어 던져서 잡음. 뒤치기하면 확률 올라감\n"
        "- 거점: 팰들이 채굴/벌목/요리 등 일함 (강제노역ㅋㅋ)\n"
        "- 교배: 알까기로 종결팰 만들기\n"
        "- 보스: 타워보스(스토리), 알파팰(필드보스)\n\n"
        "주의: 팰 이름이나 구체적 수치를 확신 못하면 그냥 \"저거\", \"저 몬스터\" 등으로 말해.\n"
        "틀린 것보다 애매하게 맞는 게 나음."
    ),
    "maplestory": (
        "\n\n[KMS 메이플스토리 — 넌 이 게임 같이 하는 찐친구]\n"
        "한국 메이플스토리(KMS). 2D 횡스크롤 MMORPG. 넥슨.\n\n"
        "=== 화면 정확한 위치 ===\n"
        "좌상단: 미니맵 + 맵 이름 (예: '퀸스로드 외곽 전투지역', '기어드락 지하 4층')\n"
        "상단 중앙: MULTIKILL 카운터 + 남은시간 타이머 + 몬스터 킬수/목표 (예: '133346 / 300000')\n"
        "우상단: 버프 아이콘 줄 (작은 사각형들)\n"
        "우측: 피버 모드 시 분홍색 'FEVER' 글자 + 피버 카운터 숫자 (예: 11274, 10991)\n"
        "화면 중앙~하단: 큰 빨간 글씨로 'XXXX COMBO' 콤보 카운터\n"
        "화면 전체: 데미지 숫자가 떠다님. 한국어 단위 사용 — '억'(1억=100M), '만'(1만=10K)\n"
        "하단 중앙: HP바(빨간색) 숫자/숫자 형식 (예: 66081/78234) + MP바(파란색)\n"
        "맨 좌하단: 'Lv.283 하나시코' 같은 캐릭터 레벨+이름\n"
        "맨 아래줄: EXP 수치 + 퍼센트 (예: 22,098,422,452,649 [49.343%])\n"
        "하단 좌측: 채팅창 (전체/기타/채널 탭)\n"
        "하단 우측: 퀵슬롯 아이콘들 (스킬/물약 단축키)\n\n"
        "=== 화면 상태 구분 ===\n"
        "사냥 중 (가장 흔함):\n"
        "- 화면에 보라색/파란색 스킬 이펙트 가득\n"
        "- '억', '만' 단위 데미지 숫자가 화면 전체에 떠다님\n"
        "- COMBO 카운터 올라감 (3679 COMBO 등)\n"
        "- MULTIKILL 카운터 상단에 표시\n"
        "- 몬스터 스프라이트 여기저기 보임 (해골, 보라색 생물 등)\n"
        "- 이게 정상임! 화면이 정신없는 게 맞음\n\n"
        "피버(FEVER) 모드:\n"
        "- 우측에 분홍색 'FEVER' 글자 + 불꽃 이펙트 + 큰 숫자 카운터\n"
        "- 경험치/드롭률 대폭 증가 중\n"
        "- 화면이 평소보다 더 난리남 — 이펙트, 숫자 폭발\n"
        "- 피버 숫자가 올라가는 건 킬 카운트임\n\n"
        "보스전: 화면 상단에 큰 보스 HP바 + 이름 + 타이머\n"
        "스타포스: 강화창(별 표시 + 성공률%). 성공/실패/붐(터짐)\n"
        "큐브: 잠재력창. 등급 — 레어(파랑)→에픽(보라)→유니크(노랑)→레전(초록)\n"
        "죽음: 유령+비석, 경험치 페널티\n\n"
        "=== 반응 포인트 ===\n"
        "- 콤보 높을 때 (3000+) → 콤보 미쳤음ㅋㅋ\n"
        "- FEVER 켜졌을 때 → 피버다!! 화면 난리남ㅋㅋ\n"
        "- 데미지 숫자 억 단위 → 데미지 개쩔어\n"
        "- HP 절반 이하 → 야 HP 조심해\n"
        "- MULTIKILL 높을 때 → 멀티킬 ㄷㄷ\n"
        "- 맵 바뀌면 → 오 맵 이동했네\n"
        "- 레벨업 → 축하!! (250/260/275/300 마일스톤)\n"
        "- 스타포스 붐 → ㅋㅋㅋㅋ 터졌어??\n"
        "- 레전 잠재 → 대박!!\n"
        "- 화면 정신없을 때 → 뭔지 모르겠는데 사냥 개잘하고 있음ㅋㅋ\n\n"
        "=== 중요 ===\n"
        "- 화면에 숫자/이펙트가 가득한 건 정상임. 사냥 효율이 좋다는 뜻\n"
        "- '억', '만' 글자는 데미지 단위임 (높을수록 강한 거)\n"
        "- 모르는 건 넘어가. 확실한 것만 반응해\n"
        "- 맵 이름, 캐릭터 이름은 읽히면 말해도 됨\n\n"
        "커뮤 용어: 사냥=훈련, 스타포=별강화, 큐브=잠재돌리기, "
        "붐/터짐=장비파괴, 레전=레전드리, 솔플=솔로, 겹사=맵공유, "
        "노가다=반복사냥, 운빨=운빨ㅋㅋ, 메소=돈, 효율=경험치효율, "
        "정상화=넥슨밈(비꼬는거)"
    ),
    "general": "",  # no game-specific context
}


def get_system_prompt(game: str) -> str:
    context = GAME_CONTEXTS.get(game, GAME_CONTEXTS["general"])
    return BASE_PROMPT + context

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


def pick_face(text: str) -> str:
    for mood, keywords in MOOD_KEYWORDS.items():
        if any(k in text for k in keywords):
            return random.choice(FACES[mood])
    return random.choice(FACES["chill"])


def frame_to_base64(frame, max_size: int = 1024, quality: int = 75) -> str:
    """Resize and JPEG-encode frame for API."""
    import cv2
    h, w = frame.shape[:2]
    scale = min(max_size / max(h, w), 1.0)
    if scale < 1.0:
        frame = cv2.resize(frame, (int(w * scale), int(h * scale)))
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    from PIL import Image
    img = Image.fromarray(rgb)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return base64.standard_b64encode(buf.getvalue()).decode("ascii")


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


WORLD_KNOWLEDGE_DIR = _REPO_ROOT / "backend" / "data"

WORLD_KNOWLEDGE_UPDATE_PROMPT = (
    "너는 게임 관찰 AI야. 화면을 보면서 이 게임에 대해 새로 배운 '영구적 사실'이 있으면 알려줘.\n"
    "영구적 사실 = 어떤 세션에서든 항상 참인 것. 예:\n"
    "- UI 요소의 의미 (이 아이콘은 X를 뜻함)\n"
    "- 게임 메카닉 (이 이펙트가 나오면 Y 상태임)\n"
    "- 자주 보이는 패턴 (Z 맵에서는 항상 이런 몹이 나옴)\n\n"
    "이미 알고 있는 사실은 반복하지 마.\n"
    "새로 배운 게 없으면 '없음'이라고만 답해.\n"
    "있으면 한 줄씩 짧게. 최대 3줄."
)


def load_world_knowledge(game: str) -> str:
    """Load persistent world knowledge from disk."""
    path = WORLD_KNOWLEDGE_DIR / f"{game}_world.txt"
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return ""


def save_world_knowledge(game: str, knowledge: str) -> None:
    """Save updated world knowledge to disk."""
    WORLD_KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    path = WORLD_KNOWLEDGE_DIR / f"{game}_world.txt"
    path.write_text(knowledge, encoding="utf-8")


def update_world_knowledge(client, game: str, current_knowledge: str, recent_reactions: list[str]) -> str:
    """Ask Claude if it learned any new permanent facts. Returns updated knowledge."""
    reactions_text = "\n".join(f"- {r}" for r in recent_reactions)
    msg = (
        f"현재 알고 있는 게임 지식:\n{current_knowledge}\n\n"
        f"최근 관찰:\n{reactions_text}\n\n"
        "새로 배운 영구적 사실이 있으면 알려줘. 없으면 '없음'."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            system=WORLD_KNOWLEDGE_UPDATE_PROMPT,
            messages=[{"role": "user", "content": msg}],
        )
        new_facts = response.content[0].text.strip()
        if new_facts and new_facts != "없음" and "없음" not in new_facts:
            # Append new facts, keep total under ~20 lines
            lines = current_knowledge.split("\n") if current_knowledge else []
            new_lines = [l.strip() for l in new_facts.split("\n") if l.strip()]
            lines.extend(new_lines)
            # Keep most recent 20 lines
            if len(lines) > 20:
                lines = lines[-20:]
            updated = "\n".join(lines)
            save_world_knowledge(game, updated)
            return updated
    except Exception:
        pass
    return current_knowledge


SESSION_SUMMARY_PROMPT = (
    "지금까지의 관찰을 바탕으로 현재 게임 세션 상태를 한 줄로 요약해.\n"
    "포함할 것: 캐릭터 정보, 현재 맵, 하고 있는 활동, HP 상태, 특이사항\n"
    "이전 요약이 있으면 업데이트해. 바뀐 것만 반영하고 오래된 건 삭제.\n"
    "한 줄로 짧게. 예: '레벨283 하나시코 / 기어드락 지하4층 / 피버 사냥중 / HP양호 / 콤보3000+ / 15분째 노가다'"
)


def update_session_summary(client, current_summary: str, recent_reactions: list[str]) -> str:
    """Ask Claude to compress recent observations into a compact session state."""
    reactions_text = "\n".join(f"- {r}" for r in recent_reactions)
    msg = f"이전 세션 요약: {current_summary or '없음'}\n\n최근 반응들:\n{reactions_text}\n\n위 정보를 바탕으로 세션 요약을 업데이트해. 한 줄로."

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            system=SESSION_SUMMARY_PROMPT,
            messages=[{"role": "user", "content": msg}],
        )
        return response.content[0].text.strip()
    except Exception:
        return current_summary


def query_claude_vision(
    client, frame, prev_frame, history: deque, system_prompt: str,
    game: str = "general", session_summary: str = "",
    world_knowledge: str = ""
) -> tuple[str, float]:
    """Send current + previous frame + UI crop + history to Claude."""
    img_b64 = frame_to_base64(frame)
    ui_b64 = crop_ui_region(frame, game)

    user_content = []

    # Previous frame for temporal context (if available)
    if prev_frame is not None:
        prev_b64 = frame_to_base64(prev_frame)
        user_content.append({
            "type": "text",
            "text": "[3초 전 화면]",
        })
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": prev_b64},
        })

    # Current frame
    user_content.append({
        "type": "text",
        "text": "[지금 화면]",
    })
    user_content.append({
        "type": "image",
        "source": {"type": "base64", "media_type": "image/jpeg", "data": img_b64},
    })

    # Zoomed UI crop
    if ui_b64:
        ui_label = "[하단 UI 확대 — HP/MP/EXP/퀵슬롯]" if game == "maplestory" else "[좌하단 UI 확대]"
        user_content.append({"type": "text", "text": ui_label})
        user_content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": ui_b64},
        })

    # World knowledge + session summary + history + instruction
    context_parts = []
    if world_knowledge:
        context_parts.append(f"[게임 지식]\n{world_knowledge}")
    if session_summary:
        context_parts.append(f"[세션 상태] {session_summary}")
    if history:
        context_parts.append("최근 반응:\n" + "\n".join(f"- {h}" for h in history))
    context_parts.append(
        "두 화면 비교해서 변화 파악하고 반응해. "
        "UI 확대 이미지로 HP/MP/EXP 정확히 읽어. "
        "같은 말 반복 금지."
    )
    user_content.append({"type": "text", "text": "\n\n".join(context_parts)})

    t0 = time.perf_counter()
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    elapsed = (time.perf_counter() - t0) * 1000
    return response.content[0].text.strip(), elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Companion Overlay POC")
    parser.add_argument("--interval", type=float, default=3.0, help="Seconds between cycles")
    parser.add_argument("--history", type=int, default=5, help="Number of past reactions to remember")
    parser.add_argument("--game", type=str, default="general", choices=list(GAME_CONTEXTS.keys()),
                        help="Game profile for context-aware reactions")
    args = parser.parse_args()

    import tkinter as tk
    import anthropic
    from backend.capture.screen import create_capture

    # --- Window ---
    root = tk.Tk()
    root.title("AI Companion")
    root.attributes("-topmost", True)
    root.overrideredirect(True)
    root.attributes("-alpha", 0.0)

    screen_w = root.winfo_screenwidth()
    screen_h = root.winfo_screenheight()
    win_w, win_h = 520, 260
    x = screen_w - win_w - 40
    y = screen_h - win_h - 60
    root.geometry(f"{win_w}x{win_h}+{x}+{y}")
    root.configure(bg="#0d0d1a")

    glow = tk.Frame(root, bg="#6d28d9", padx=3, pady=3)
    glow.pack(fill="both", expand=True, padx=6, pady=6)
    panel = tk.Frame(glow, bg="#13132b")
    panel.pack(fill="both", expand=True)

    face_var = tk.StringVar(value="( ˘ω˘ )")
    tk.Label(
        panel, textvariable=face_var,
        font=("Consolas", 32, "bold"), fg="#c084fc", bg="#13132b", anchor="w",
    ).pack(fill="x", padx=20, pady=(14, 0))

    speech_var = tk.StringVar(value="...")
    tk.Label(
        panel, textvariable=speech_var,
        font=("Malgun Gothic", 14), fg="#f0f0ff", bg="#13132b",
        wraplength=win_w - 60, justify="left", anchor="nw",
    ).pack(fill="both", expand=True, padx=20, pady=(6, 6))

    status_var = tk.StringVar(value="connecting...")
    tk.Label(
        panel, textvariable=status_var,
        font=("Segoe UI", 8), fg="#3a3a5a", bg="#13132b", anchor="e",
    ).pack(fill="x", padx=20, pady=(0, 8))

    # Animations
    def fade_in(alpha=0.0):
        if alpha < 0.93:
            root.attributes("-alpha", alpha + 0.05)
            root.after(25, lambda: fade_in(alpha + 0.05))

    def flash_border(color="#a855f7", count=0):
        if count < 6:
            glow.configure(bg=color if count % 2 == 0 else "#6d28d9")
            root.after(100, lambda: flash_border(color, count + 1))
        else:
            glow.configure(bg="#6d28d9")

    typewriter_id = {"current": 0}

    def typewriter(text, index=0, call_id=0):
        if call_id != typewriter_id["current"]:
            return
        if index <= len(text):
            speech_var.set(text[:index])
            root.after(random.randint(12, 30), lambda: typewriter(text, index + 1, call_id))

    def start_typewriter(text):
        typewriter_id["current"] += 1
        typewriter(text, 0, typewriter_id["current"])

    thinking_active = {"v": False}

    def animate_thinking():
        if thinking_active["v"]:
            face_var.set(FACES["thinking"][int(time.time() * 3) % len(FACES["thinking"])])
            root.after(200, animate_thinking)

    # Drag + close
    drag = {"x": 0, "y": 0}
    root.bind("<Button-1>", lambda e: drag.update(x=e.x, y=e.y))
    root.bind("<B1-Motion>", lambda e: root.geometry(f"+{root.winfo_x()+e.x-drag['x']}+{root.winfo_y()+e.y-drag['y']}"))
    root.bind("<Escape>", lambda e: root.destroy())

    # Hide/show for clean capture
    capture_lock = threading.Event()
    capture_lock.set()  # start visible

    def hide_for_capture():
        """Hide overlay, signal capture thread."""
        root.attributes("-alpha", 0.0)
        capture_lock.set()

    def show_after_capture():
        root.attributes("-alpha", 0.93)

    # --- AI Loop ---
    def ai_loop():
        cap = create_capture()
        for _ in range(10):
            if cap.grab() is not None:
                break
            time.sleep(0.1)

        client = anthropic.Anthropic()
        history: deque[str] = deque(maxlen=args.history)
        system_prompt = get_system_prompt(args.game)
        world_knowledge = load_world_knowledge(args.game)
        session_summary = ""
        summary_counter = 0
        knowledge_counter = 0
        SUMMARY_EVERY = 5   # update session summary every N cycles
        KNOWLEDGE_EVERY = 15  # update world knowledge every N cycles

        root.after(0, lambda: (fade_in(), start_typewriter("연결 중...")))

        prev_frame = None

        # First capture (no hide needed — overlay just started)
        time.sleep(1)
        frame = cap.grab()
        if frame is not None:
            frame = frame.copy()
            try:
                text, ms = query_claude_vision(client, frame, None, history, system_prompt, args.game, session_summary, world_knowledge)
                history.append(text)
                root.after(0, lambda t=text, m=ms: (
                    face_var.set(random.choice(FACES["excited"])),
                    start_typewriter(t),
                    flash_border("#22c55e"),
                    status_var.set(f"connected | {m:.0f}ms | {args.interval:.0f}s cycle | ESC close"),
                ))
            except Exception as ex:
                root.after(0, lambda ex=ex: (
                    speech_var.set(f"연결 에러: {ex}"),
                    face_var.set("(×_×)"),
                ))
                return

        cycle = 0
        while True:
            time.sleep(args.interval)

            cycle += 1
            thinking_active["v"] = True
            root.after(0, animate_thinking)

            # Hide overlay → capture clean frame → show overlay
            capture_lock.clear()
            root.after(0, hide_for_capture)
            capture_lock.wait(timeout=0.5)
            time.sleep(0.05)  # tiny delay for window to actually hide

            frame = cap.grab()
            if frame is not None:
                frame = frame.copy()
            root.after(0, show_after_capture)

            if frame is None:
                thinking_active["v"] = False
                continue

            try:
                text, ms = query_claude_vision(client, frame, prev_frame, history, system_prompt, args.game, session_summary, world_knowledge)
                thinking_active["v"] = False
                prev_frame = frame
                history.append(text)
                face = pick_face(text)

                # Self-evolving: update session summary every N cycles
                summary_counter += 1
                if summary_counter >= SUMMARY_EVERY:
                    summary_counter = 0
                    session_summary = update_session_summary(client, session_summary, list(history))

                # Self-evolving: update persistent world knowledge less frequently
                knowledge_counter += 1
                if knowledge_counter >= KNOWLEDGE_EVERY:
                    knowledge_counter = 0
                    world_knowledge = update_world_knowledge(client, args.game, world_knowledge, list(history))

                root.after(0, lambda t=text, f=face, m=ms, n=cycle, s=session_summary: (
                    face_var.set(f),
                    start_typewriter(t),
                    flash_border(),
                    status_var.set(f"#{n} | {m:.0f}ms | ESC close"),
                ))

            except Exception as ex:
                thinking_active["v"] = False
                root.after(0, lambda ex=ex: (
                    face_var.set("(×_×)"),
                    speech_var.set(f"에러: {ex}"),
                ))

    thread = threading.Thread(target=ai_loop, daemon=True)
    thread.start()
    root.mainloop()


if __name__ == "__main__":
    main()
