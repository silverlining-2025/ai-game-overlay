import type { TranslationKey } from "./ko";

const en: Record<TranslationKey, string> = {
  "status.connected": "Connected",
  "status.disconnected": "Disconnected",
  "status.reconnecting": "Reconnecting...",

  "overlay.coach_title": "AI Coach",
  "overlay.stats_title": "Match Stats",
  "overlay.timer": "Elapsed Time",

  "coach.thinking": "Analyzing...",
  "coach.no_suggestion": "No suggestions yet",
  "coach.error": "Cannot connect to coach service",

  "controls.toggle_overlay": "Toggle Overlay (Alt+O)",
  "controls.toggle_clickthrough": "Toggle Click-Through (Alt+T)",
  "controls.request_advice": "Request Advice (Alt+C)",

  "settings.language": "Language",
  "settings.opacity": "Opacity",
  "settings.position": "Position",

  "minesweeper.safe_cell": "Safe",
  "minesweeper.mine_cell": "Mine",
  "minesweeper.confidence": "Confidence: {{value}}%",
  "minesweeper.game_status": "Game Status: {{status}}",
  "minesweeper.mines_remaining": "Mines Remaining: {{count}}",
  "minesweeper.analyzing_grid": "Analyzing grid...",
  "minesweeper.no_grid": "Grid not detected",

  "perf.fps": "{{value}} FPS",
  "perf.capture_ms": "Capture: {{value}}ms",
  "perf.processing_ms": "Process: {{value}}ms",
};

export default en;
