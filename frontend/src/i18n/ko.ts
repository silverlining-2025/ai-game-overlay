const ko = {
  // 상태
  "status.connected": "연결됨",
  "status.disconnected": "연결 끊김",
  "status.reconnecting": "재연결 중...",

  // 오버레이
  "overlay.coach_title": "AI 코치",
  "overlay.stats_title": "경기 통계",
  "overlay.timer": "경과 시간",

  // 코치
  "coach.thinking": "분석 중...",
  "coach.no_suggestion": "아직 제안이 없습니다",
  "coach.error": "코치 서비스에 연결할 수 없습니다",

  // 조작
  "controls.toggle_overlay": "오버레이 표시/숨기기 (Alt+O)",
  "controls.toggle_clickthrough": "클릭 통과 전환 (Alt+T)",
  "controls.request_advice": "코치 조언 요청 (Alt+C)",

  // 설정
  "settings.language": "언어",
  "settings.opacity": "투명도",
  "settings.position": "위치",

  // 지뢰찾기
  "minesweeper.safe_cell": "안전",
  "minesweeper.mine_cell": "지뢰",
  "minesweeper.confidence": "신뢰도: {{value}}%",
  "minesweeper.game_status": "게임 상태: {{status}}",
  "minesweeper.mines_remaining": "남은 지뢰: {{count}}개",
  "minesweeper.analyzing_grid": "그리드 분석 중...",
  "minesweeper.no_grid": "그리드를 찾을 수 없습니다",

  // 성능
  "perf.fps": "{{value}} FPS",
  "perf.capture_ms": "캡처: {{value}}ms",
  "perf.processing_ms": "처리: {{value}}ms",

  // 설정 화면
  "config.title": "AI Gaming Companion",
  "config.subtitle": "게임 화면을 보면서 실시간으로 반응하는 AI 친구",
  "config.language_label": "언어 / Language",
  "config.character_label": "캐릭터 선택",
  "config.game_label": "게임",
  "config.game_select_title": "게임 선택",
  "config.game_other": "기타 / 일반",
  "config.position_label": "위치",
  "config.position_select_title": "오버레이 위치",
  "config.position_top_right": "우상단",
  "config.position_top_left": "좌상단",
  "config.position_bottom_right": "우하단",
  "config.position_bottom_left": "좌하단",
  "config.chattiness_label": "수다 레벨",
  "config.chattiness_quiet": "조용",
  "config.chattiness_normal": "보통",
  "config.chattiness_talkative": "수다쟁이",
  "config.chattiness_slider_title": "수다 레벨",
  "config.hint": "AI가 적절한 타이밍에 자동으로 반응합니다. 오버레이 조작: Alt 키를 누른 채로 드래그/클릭.",
  "config.start": "시작하기",
  "config.cost": "예상 비용: ~$0.05~0.10/시간 (이벤트 기반, Claude Haiku)",
  "config.quit": "종료",
  "config.api_key_label": "Anthropic API 키",
  "config.api_key_placeholder": "sk-ant-... 형식의 API 키 입력",
  "config.test_key": "키 테스트",
  "config.key_valid": "유효함",
  "config.key_invalid": "유효하지 않은 키",
  "config.license_label": "라이선스 키",
  "config.license_placeholder": "라이선스 키 입력",
  "config.activate": "활성화",
  "config.free_tier": "무료 — 하루 20회 반응",
  "config.premium_tier": "프리미엄 — 무제한",
  "config.char_nozomi": "노조미",
  "config.char_robot": "로봇",
  "config.char_cat": "고양이",
  "config.char_ghost": "유령",
  "config.char_fox": "여우",
  "config.char_slime": "슬라임",

  // 동의 화면
  "consent.title": "개인정보 처리 안내",
  "consent.subtitle": "AI Gaming Companion을 사용하기 전에 아래 내용을 확인해주세요.",
  "consent.section_title": "수집 및 처리 항목",
  "consent.item_capture_label": "화면 캡처",
  "consent.item_capture_desc": "게임 화면을 캡처하여 AI에게 전송합니다",
  "consent.item_transfer_label": "데이터 전송",
  "consent.item_transfer_desc": "캡처된 이미지는 Anthropic API(미국)로 전송되어 분석됩니다",
  "consent.item_storage_label": "데이터 저장",
  "consent.item_storage_desc": "이미지는 서버에 저장되지 않습니다 (분석 후 즉시 삭제)",
  "consent.item_training_label": "학습 데이터",
  "consent.item_training_desc": "--save-training 옵션 사용 시 로컬에 저장될 수 있습니다",
  "consent.safety": "안티치트 안전: 게임 메모리를 읽거나 수정하지 않습니다. OS 수준의 화면 캡처만 사용합니다.",
  "consent.checkbox_label": "위 내용을 확인했으며, 데이터 처리에 동의합니다",
  "consent.button": "동의하고 시작",

  // 오버레이 동반자
  "companion.thinking": "생각 중...",
  "companion.greeting_ko": "음~ 게임 시작하는 거야?",
  "companion.greeting_en": "Hmm~ starting a game?",
  "companion.error_api": "API 연결 오류",
  "companion.error_retry": "잠시 후 재시도합니다",
  "companion.cost_warning": "비용 경고",
  "companion.back_to_settings": "설정으로 돌아가기",
  "companion.quit": "종료",
} as const;

export default ko;
export type TranslationKey = keyof typeof ko;
