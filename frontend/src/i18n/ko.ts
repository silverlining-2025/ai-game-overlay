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
} as const;

export default ko;
export type TranslationKey = keyof typeof ko;
