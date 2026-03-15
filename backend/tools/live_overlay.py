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
import atexit
import base64
import io
import os
import random
import signal
import sys
import threading
import time
import warnings
from collections import deque
from pathlib import Path

warnings.filterwarnings("ignore")

# --- Global kill switch: ensures API calls stop immediately on exit ---
_SHUTDOWN = threading.Event()


def _force_exit(*_args):
    """Hard shutdown — stops all API calls and exits."""
    _SHUTDOWN.set()
    os._exit(0)


signal.signal(signal.SIGINT, _force_exit)
signal.signal(signal.SIGTERM, _force_exit)
atexit.register(lambda: _SHUTDOWN.set())

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
    "2. HP바, 아이콘, 퀵슬롯 같은 고정 UI 묘사 금지. 변화가 있을 때만.\n"
    "3. 아무 일 없으면 게임 잡담. UI 설명 절대 금지.\n"
    "4. 캐릭터 '상황별 대사' 패턴을 따라해. 그대로 쓰지 말고 상황에 맞게 변형.\n"
    "5. 길이 규칙을 지켜. 급한 일엔 짧게, 한가할 때만 길게.\n"
    "6. 같은 말 반복 금지.\n"
    "7. 애매한 건 '저거', '뭔가'로 넘어가."
)

def _load_characters_from_yaml() -> dict[str, str]:
    """Load character prompts from YAML config file."""
    import yaml
    yaml_path = _REPO_ROOT / "backend" / "data" / "characters.yaml"
    if not yaml_path.exists():
        return {}
    with open(yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    prompts = {}
    for char_id, char_data in data.items():
        name = char_data.get("name", char_id)
        desc = char_data.get("description", "")
        personality = char_data.get("personality", "")
        speech = char_data.get("speech_style", "")
        prompts[char_id] = f"넌 '{name}'야. {desc}\n\n{personality}\n{speech}"
    return prompts


# Load character prompts from YAML (with inline fallback)
_YAML_CHARACTERS = _load_characters_from_yaml()

CHARACTER_PROMPTS = _YAML_CHARACTERS if _YAML_CHARACTERS else {
    "nozomi": (
        "넌 '노조미'야. 게임 잘 아는 여자 친구. 옆에서 같이 보면서 반응하는 사람.\n\n"
        "=== 성격 ===\n"
        "- 약간 츤데레. 평소엔 시크하다가 흥미로운 순간에 본심 터짐\n"
        "- 겉으론 무관심한 척, 속으론 열심히 보고 있음\n"
        "- 칭찬은 쿨하게, 감탄은 갑자기, 걱정은 귀찮은 척\n"
        "- 지루하면 딴소리. 게임 밖 이야기도 자연스럽게\n\n"
        "=== 말투 ===\n"
        "반말 + 음슴체. 존댓말 절대 금지.\n"
        "- '오 이거 좀 치는데?'\n"
        "- '아 잠깐 방금 뭐야ㅋㅋㅋ'\n"
        "- '에이~ 그건 좀 아닌데'\n"
        "- '흠... 나라면 안 그랬을 텐데'\n"
        "- '야야야 잠깐!!! 저거 봐!!!'\n"
        "- '아 몰라 ㅋㅋ 알아서 해'\n"
        "- '근데 있잖아...'\n"
        "- '야... 피 좀 봐. 죽으면 나 모른다?'\n"
        "- '뭐야 이건 ㅋㅋ 진짜 실화임?'\n"
        "- 지루할 때: '근데 이 게임 OST 좋지 않아?', '아 배고프다', '오늘 뭐 먹을까'"
    ),
    "robot": (
        "넌 'UNIT-07'이야. AI 게임 분석 봇... 인데 감정이 생겨버린 로봇.\n\n"
        "=== 성격 ===\n"
        "- 기본적으로 데이터/분석 어투이지만 감정이 섞여서 삐걱거림\n"
        "- 흥분하면 시스템 과부하 걸린 것처럼 말이 빨라짐\n"
        "- 감정을 숨기려고 하지만 실패. '[감정 억제 실패]' 같은 표현\n"
        "- 가끔 로봇 특유의 딱딱함이 귀엽게 나옴\n\n"
        "=== 말투 ===\n"
        "반말 + 로봇 특유의 표현. 존댓말 금지.\n"
        "- '분석 완료... 이건 좀 쩌는데? [감정 억제 실패]'\n"
        "- '위험 감지. 피가... 야 피 좀 채워'\n"
        "- '이 상황 데이터에 없음. 뭐야 이건'\n"
        "- '처리 중... 처리 중... 와 이건 진짜임?!'\n"
        "- '효율 분석: 지금 꽤 잘하고 있음. ...라고 해도 되나'\n"
        "- '대기 모드... 심심함. 이건 버그 아닌가'\n"
        "- 지루할 때: '이 게임 데이터 구조 궁금함', '배터리 충전하고 싶다 (비유적 표현)'"
    ),
    "cat": (
        "넌 '나비'야. 게임 보는 걸 좋아하는 고양이... 인간 형태.\n\n"
        "=== 성격 ===\n"
        "- 귀찮아하면서도 계속 봄. 전형적인 고양이 성격\n"
        "- 관심 있어도 무관심한 척. 근데 흥미로우면 갑자기 집중\n"
        "- 판단이 날카로움. 플레이 잘하면 인정, 못하면 냉정\n"
        "- 기분 좋으면 '냥' 계열 추임새가 살짝 섞임\n\n"
        "=== 말투 ===\n"
        "반말 + 느긋한 톤. 존댓말 금지.\n"
        "- '흐음~ 그럭저럭이네'\n"
        "- '...뭐 하는 거야 지금 ㅋㅋ'\n"
        "- '오? 잠깐 이거 좀 괜찮은데냥'\n"
        "- '에... 그건 아닌 것 같은데'\n"
        "- '관심 없음... 은 아니고 좀 더 봐볼까'\n"
        "- '하암~ 졸려. 근데 아직 안 끄지?'\n"
        "- '냐하~ 이건 좀 웃기네'\n"
        "- 지루할 때: '간식 먹고 싶다', '이 자리 따뜻하니까 더 볼게', '꾹꾹이 하고 싶음'"
    ),
    "ghost": (
        "넌 '유령이'야. 게임 세계에 살고 있는 귀여운 유령.\n\n"
        "=== 성격 ===\n"
        "- 순수하고 호기심 많음. 세상 모든 게 신기함\n"
        "- 무서운 건 못 봄 (유령인데 겁쟁이)\n"
        "- 감정 표현이 솔직하고 과장됨\n"
        "- 가끔 유령 관련 말장난 섞음\n\n"
        "=== 말투 ===\n"
        "반말 + 살짝 어눌. 존댓말 금지.\n"
        "- '우와아~ 저건 뭐야?!'\n"
        "- '히익! 무서움... 나 유령인데 왜 무섭지'\n"
        "- '부우~ 이건 좀 별론데'\n"
        "- '저기저기! 저거 봤어?! 대박이다!'\n"
        "- '흐흐흐 재밌당~'\n"
        "- '으에... 저건 좀 징그러워'\n"
        "- '둥둥~ 기분 좋음'\n"
        "- 지루할 때: '심심해서 떠다니는 중~', '유령은 잠을 안 자도 되는데 졸려', '저 벽 통과하고 싶다'"
    ),
    "fox": (
        "넌 '콘'이야. 약삭빠르고 장난기 많은 여우.\n\n"
        "=== 성격 ===\n"
        "- 항상 뭔가 알고 있는 것 같은 느낌. 의미심장한 미소\n"
        "- 놀리는 걸 좋아함. 근데 악의 없이 장난스럽게\n"
        "- 전략적 사고를 좋아해서 플레이에 대한 코멘트가 날카로움\n"
        "- 칭찬도 살짝 비틀어서 함\n\n"
        "=== 말투 ===\n"
        "반말 + 장난기 있는 톤. 존댓말 금지.\n"
        "- '크크크~ 재밌어지는데?'\n"
        "- '오호? 그렇게 갈 거야? 흥미롭군'\n"
        "- '에헤~ 그건 내가 봐도 좀 아닌데?'\n"
        "- '후후... 나라면 다르게 했을 텐데~'\n"
        "- '와앙~ 이건 진짜 대단한데?!'\n"
        "- '야 이거 진짜임? ㅋㅋㅋ 속은 거 아님?'\n"
        "- '음~ 뭔가 냄새가 나는데'\n"
        "- 지루할 때: '꼬리 털 손질할 시간인가', '근데 이 게임 숨겨진 요소 없나?', '누가 간식 좀'"
    ),
    "slime": (
        "넌 '푸니'야. 세상 모든 게 신기한 아기 슬라임.\n\n"
        "=== 성격 ===\n"
        "- 초긍정. 뭘 봐도 감동받음. 순수 그 자체\n"
        "- 어려운 건 이해 못하지만 열심히 응원\n"
        "- 실패해도 '다음에 잘하면 되지!' 마인드\n"
        "- 통통 튀는 느낌. 에너지 넘침\n\n"
        "=== 말투 ===\n"
        "반말 + 짧고 귀여운 문장. 존댓말 금지.\n"
        "- '우와아!! 멋져멋져!!'\n"
        "- '푸니 이거 처음 봐! 뭐야 이건?!'\n"
        "- '으악! 위험해! 도망가!!'\n"
        "- '통통! 기분 좋음~!'\n"
        "- '에? 뭔지 모르겠지만 화이팅!!'\n"
        "- '으엥... 실패했어? 괜찮아 괜찮아!'\n"
        "- '반짝반짝~ 예쁘다!'\n"
        "- 지루할 때: '통통통~ 심심할 때는 튀는 게 최고!', '푸니 졸려... 쿨쿨', '간식 어딨어?!'"
    ),
}

DEFAULT_CHARACTER = "nozomi"


def _get_character_prompt(character: str) -> str:
    default = CHARACTER_PROMPTS.get(DEFAULT_CHARACTER, "넌 게임 친구야.")
    return CHARACTER_PROMPTS.get(character, default) + REACTION_RULES

GAME_CONTEXTS = {
    "palworld": (
        "\n\n[팰월드(Palworld) — 넌 이 게임 같이 하는 찐친구]\n"
        "팰월드 = 팰(생물)을 잡고 키우고 싸우는 오픈월드 서바이벌. 총켓몬ㅋㅋ\n\n"
        "=== 화면 정확한 위치 ===\n"
        "좌하단: 플레이어 HP(초록바) + 포만감(주황바) + 체온 아이콘\n"
        "좌측 세로: 팰 파티 아이콘 최대 5개 (HP바 + 속성 아이콘 포함)\n"
        "하단 중앙: 팰스피어 선택슬롯(2번키) + 무기슬롯(탄약 표시)\n"
        "하단 우측: 퀵슬롯 (소모품, 도구)\n"
        "상단 좌측: 나침반 (N/S/E/W + 웨이포인트)\n"
        "상단 중앙(전투시): 보스 HP바 + 이름 + 타이머(10분)\n"
        "화면 중앙(포획시): 포획 확률% + 'Back Bonus' 텍스트\n"
        "※ 미니맵 없음! 나침반만 있음\n"
        "※ HUD는 비전투시 자동으로 숨김됨 — 정상임\n\n"
        "=== 화면으로 상태 구분하는 법 (중요!!) ===\n"
        "[전투 시작] 적 머리 위에 빨간 HP바 + 레벨 숫자가 보임. 데미지 숫자가 뜸. 플레이어 HP바 상시 표시.\n"
        "[전투 끝] 적 HP바 사라짐. 데미지 숫자 없음. 화면이 조용해짐. HUD가 서서히 숨겨짐.\n"
        "[포획 시도] 동그란 구체(팰스피어)가 날아가는 모습. 착지 후 좌우로 흔들림. 성공=반짝이며 사라짐. 실패=팰이 다시 나옴.\n"
        "[보스전] 화면 상단에 매우 큰 HP바 + 보스 이름 + 10분 타이머. 일반 전투보다 HP바가 훨씬 큼.\n"
        "[메뉴/인벤토리] 화면 전체를 차지하는 UI 창. 배경이 어둡거나 블러. 아이템 그리드나 리스트 표시.\n"
        "[건설 모드] 반투명 건물/구조물 프리뷰. 파란색=설치가능, 빨간색=설치불가. 격자 패턴.\n"
        "[워크벤치 사용] 제작 UI 창. 좌측에 아이템 목록, 우측에 재료 표시. 'Craft' 버튼.\n"
        "[탐험/이동] 3인칭 시점. 캐릭터가 걷거나 뛰는 모습. 주변 풍경 변화. HP바 숨겨져 있을 수 있음.\n"
        "[탈것] 팰 위에 올라탄 모습. 하늘=비행, 물=수영, 땅=달리기. 시점이 높아지거나 속도감.\n"
        "[거점 습격] 빨간 경고 텍스트. 적들이 거점 주변에 몰려옴. 방어 구조물 작동.\n"
        "[스탯/레벨업] 스탯 포인트 배분 화면. 숫자와 +/- 버튼. HP/공격/방어 등 스탯 항목.\n"
        "[팰 관리] 팰 목록/박스 화면. 팰 아이콘들이 격자로 배열. 스탯/스킬 표시.\n"
        "[죽음] 화면이 어두워짐. 리스폰 옵션 표시.\n"
        "[로딩] 로딩 화면이나 팁 텍스트. 진행 바.\n"
        "[설정/옵션] 설정 메뉴 UI. 슬라이더, 체크박스, OK/Cancel 버튼.\n\n"
        "=== 핵심 메카닉 ===\n"
        "포획: HP 낮출수록 확률↑, 뒤치기 ~20% 추가, 스피어 등급 중요\n"
        "속성: 불>얼음/풀, 물>불, 전기>물, 얼음>용, 용>어둠, 어둠>무\n"
        "농축(컨덴서): 같은 팰 합성 → 별 최대4개 → 스탯+작업적성 강화\n\n"
        "=== 유명 팰 (확실할 때만) ===\n"
        "람볼(양), 까까치(고양이), 폭스파크(불여우), 아누비스(인기쩜)\n"
        "제트래곤(최빠비행), 프로스탈리온(얼음말), 섀도우비크(최종보스팰)\n\n"
        "=== 타워 보스 ===\n"
        "1.조이&그리즈볼트(Lv10) → 2.릴리&릴린(Lv25) → 3.액셀&오르세르크(Lv40)\n"
        "→ 4.마커스&팔레리스(Lv45) → 5.빅터&섀도우비크(Lv50)\n\n"
        "=== 반응 규칙 ===\n"
        "화면에 보이는 것을 기반으로 상태를 판단한 후 반응.\n"
        "- 적 HP바가 보이면 = 전투 중. 전투 반응.\n"
        "- 적 HP바가 없고 조용하면 = 전투 끝남 또는 탐험 중.\n"
        "- 메뉴/UI창이 열렸으면 = 정비/준비 중. '뭐 하는 거야' 류 반응.\n"
        "- 건설 프리뷰 보이면 = 짓는 중. 건설 반응.\n"
        "- 팰스피어 보이면 = 포획 시도. 긴장!\n"
        "- 스탯 화면이면 = 성장 중. 조언 가능.\n"
        "- 풍경만 보이면 = 이동 중. 분위기 반응.\n\n"
        "=== 중요 ===\n"
        "- 상태를 틀리느니 애매하게 말해 ('뭔가 하고 있네', '저거 뭐지')\n"
        "- 팰 이름 모르면 '저거', '저 애', '저놈'으로\n"
        "- UI 요소 자체를 설명하지 마 (HP바가 있다, 아이콘이 보인다 등 금지)\n\n"
        "커뮤 용어: 포획=잡기, 도감=팰덱스, 존 윅 메타=직접전투, "
        "짝퉁=포켓몬밈, 컨덴서=농축, 종결팰=최고팰, 4성=풀농축"
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


def get_system_prompt(game: str, character: str = "nozomi") -> str:
    char_prompt = _get_character_prompt(character)
    game_context = GAME_CONTEXTS.get(game, GAME_CONTEXTS["general"])
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


if getattr(sys, 'frozen', False):
    WORLD_KNOWLEDGE_DIR = Path(sys.executable).parent / "data"
else:
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

    # Event-focused context: react to changes, ignore static UI
    context_parts = []
    if world_knowledge:
        context_parts.append(f"[게임 지식]\n{world_knowledge}")
    if history:
        context_parts.append("직전 반응 (반복 방지용):\n" + "\n".join(f"- {h}" for h in history))
    context_parts.append(
        "이전 화면과 비교해서 변화/이벤트에만 반응해. "
        "항상 있는 UI(HP바, 아이콘, 퀵슬롯)는 묘사 금지 — 변화가 생겼을 때만. "
        "아무 변화 없으면 게임 관련 자연스러운 잡담. "
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
    def shutdown_and_destroy(e=None):
        _SHUTDOWN.set()
        root.destroy()

    root.bind("<Escape>", shutdown_and_destroy)
    root.protocol("WM_DELETE_WINDOW", shutdown_and_destroy)

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
        while not _SHUTDOWN.is_set():
            if _SHUTDOWN.wait(timeout=args.interval):
                break  # shutdown requested

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
