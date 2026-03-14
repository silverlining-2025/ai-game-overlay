import type { AppConfig, CompanionReaction } from "../types";
import "./CharacterAvatar.css";

interface Props {
  character: AppConfig["character"];
  mood: CompanionReaction["mood"];
}

// Pure CSS/SVG animated characters — no external assets needed
// Each character has mood-based expression changes + idle animation

export default function CharacterAvatar({ character, mood }: Props) {
  return (
    <div className={`avatar avatar-${character} mood-${mood}`}>
      {character === "robot" && <RobotChar mood={mood} />}
      {character === "cat" && <CatChar mood={mood} />}
      {character === "ghost" && <GhostChar mood={mood} />}
      {character === "fox" && <FoxChar mood={mood} />}
      {character === "slime" && <SlimeChar mood={mood} />}
    </div>
  );
}

function eyes(mood: string): [string, string] {
  switch (mood) {
    case "excited": return ["◕", "◕"];
    case "curious": return ["◔", "◕"];
    case "worried": return ["◉", "◉"];
    case "amused": return ["≧", "≦"];
    case "thinking": return ["◑", "◐"];
    default: return ["●", "●"];
  }
}

function mouth(mood: string): string {
  switch (mood) {
    case "excited": return "▽";
    case "curious": return "○";
    case "worried": return "﹏";
    case "amused": return "ω";
    case "thinking": return "─";
    default: return "◡";
  }
}

function RobotChar({ mood }: { mood: string }) {
  const [l, r] = eyes(mood);
  const m = mouth(mood);
  return (
    <svg viewBox="0 0 64 64" className="char-svg">
      {/* Antenna */}
      <line x1="32" y1="4" x2="32" y2="14" stroke="#c084fc" strokeWidth="2" className="antenna" />
      <circle cx="32" cy="4" r="3" fill="#a855f7" className="antenna-dot" />
      {/* Head */}
      <rect x="12" y="14" width="40" height="36" rx="8" fill="#2d1f5e" stroke="#6d28d9" strokeWidth="2" />
      {/* Screen face */}
      <rect x="16" y="18" width="32" height="24" rx="4" fill="#13132b" />
      {/* Eyes */}
      <text x="24" y="34" fontSize="10" fill="#c084fc" textAnchor="middle" className="eye-l">{l}</text>
      <text x="40" y="34" fontSize="10" fill="#c084fc" textAnchor="middle" className="eye-r">{r}</text>
      {/* Mouth */}
      <text x="32" y="40" fontSize="8" fill="#818cf8" textAnchor="middle">{m}</text>
      {/* Body hint */}
      <rect x="22" y="50" width="20" height="10" rx="3" fill="#2d1f5e" stroke="#6d28d9" strokeWidth="1.5" />
    </svg>
  );
}

function CatChar({ mood }: { mood: string }) {
  const [l, r] = eyes(mood);
  const m = mouth(mood);
  return (
    <svg viewBox="0 0 64 64" className="char-svg">
      {/* Ears */}
      <polygon points="14,22 10,4 24,18" fill="#2d1f5e" stroke="#a855f7" strokeWidth="1.5" />
      <polygon points="50,22 54,4 40,18" fill="#2d1f5e" stroke="#a855f7" strokeWidth="1.5" />
      <polygon points="15,20 13,8 22,17" fill="#c084fc" opacity="0.3" />
      <polygon points="49,20 51,8 42,17" fill="#c084fc" opacity="0.3" />
      {/* Head */}
      <ellipse cx="32" cy="34" rx="22" ry="20" fill="#2d1f5e" stroke="#6d28d9" strokeWidth="2" />
      {/* Eyes */}
      <text x="23" y="34" fontSize="11" fill="#c084fc" textAnchor="middle" className="eye-l">{l}</text>
      <text x="41" y="34" fontSize="11" fill="#c084fc" textAnchor="middle" className="eye-r">{r}</text>
      {/* Nose */}
      <polygon points="32,37 30,39 34,39" fill="#a855f7" />
      {/* Mouth */}
      <text x="32" y="46" fontSize="8" fill="#818cf8" textAnchor="middle">{m}</text>
      {/* Whiskers */}
      <line x1="8" y1="36" x2="18" y2="38" stroke="#6d28d9" strokeWidth="1" opacity="0.5" />
      <line x1="8" y1="40" x2="18" y2="40" stroke="#6d28d9" strokeWidth="1" opacity="0.5" />
      <line x1="56" y1="36" x2="46" y2="38" stroke="#6d28d9" strokeWidth="1" opacity="0.5" />
      <line x1="56" y1="40" x2="46" y2="40" stroke="#6d28d9" strokeWidth="1" opacity="0.5" />
    </svg>
  );
}

function GhostChar({ mood }: { mood: string }) {
  const [l, r] = eyes(mood);
  const m = mouth(mood);
  return (
    <svg viewBox="0 0 64 64" className="char-svg ghost-float">
      {/* Body */}
      <path
        d="M16,30 C16,16 24,8 32,8 C40,8 48,16 48,30 L48,52 L42,46 L36,52 L32,48 L28,52 L22,46 L16,52 Z"
        fill="#2d1f5e"
        stroke="#a855f7"
        strokeWidth="2"
      />
      {/* Glow */}
      <path
        d="M20,30 C20,19 25,12 32,12 C39,12 44,19 44,30 L44,48 L40,44 L36,48 L32,45 L28,48 L24,44 L20,48 Z"
        fill="#3d2f6e"
        opacity="0.5"
      />
      {/* Eyes */}
      <text x="25" y="30" fontSize="11" fill="#c084fc" textAnchor="middle" className="eye-l">{l}</text>
      <text x="39" y="30" fontSize="11" fill="#c084fc" textAnchor="middle" className="eye-r">{r}</text>
      {/* Mouth */}
      <text x="32" y="40" fontSize="9" fill="#818cf8" textAnchor="middle">{m}</text>
    </svg>
  );
}

function FoxChar({ mood }: { mood: string }) {
  const [l, r] = eyes(mood);
  const m = mouth(mood);
  return (
    <svg viewBox="0 0 64 64" className="char-svg">
      {/* Ears (taller, pointier) */}
      <polygon points="16,24 8,2 26,18" fill="#5e2d1f" stroke="#d97706" strokeWidth="1.5" />
      <polygon points="48,24 56,2 38,18" fill="#5e2d1f" stroke="#d97706" strokeWidth="1.5" />
      <polygon points="17,22 12,6 24,17" fill="#f59e0b" opacity="0.3" />
      <polygon points="47,22 52,6 40,17" fill="#f59e0b" opacity="0.3" />
      {/* Head */}
      <ellipse cx="32" cy="36" rx="21" ry="18" fill="#5e2d1f" stroke="#d97706" strokeWidth="2" />
      {/* White muzzle */}
      <ellipse cx="32" cy="42" rx="12" ry="10" fill="#3d2518" />
      {/* Eyes */}
      <text x="23" y="34" fontSize="10" fill="#f59e0b" textAnchor="middle" className="eye-l">{l}</text>
      <text x="41" y="34" fontSize="10" fill="#f59e0b" textAnchor="middle" className="eye-r">{r}</text>
      {/* Nose */}
      <circle cx="32" cy="39" r="2.5" fill="#1a1a1a" />
      {/* Mouth */}
      <text x="32" y="48" fontSize="7" fill="#d97706" textAnchor="middle">{m}</text>
    </svg>
  );
}

function SlimeChar({ mood }: { mood: string }) {
  const [l, r] = eyes(mood);
  const m = mouth(mood);
  return (
    <svg viewBox="0 0 64 64" className="char-svg slime-wobble">
      {/* Body blob */}
      <ellipse cx="32" cy="40" rx="24" ry="18" fill="#1f5e2d" stroke="#22c55e" strokeWidth="2" />
      {/* Highlight */}
      <ellipse cx="26" cy="34" rx="6" ry="4" fill="#34d399" opacity="0.3" />
      {/* Eyes */}
      <text x="24" y="38" fontSize="11" fill="#22c55e" textAnchor="middle" className="eye-l">{l}</text>
      <text x="40" y="38" fontSize="11" fill="#22c55e" textAnchor="middle" className="eye-r">{r}</text>
      {/* Mouth */}
      <text x="32" y="48" fontSize="9" fill="#16a34a" textAnchor="middle">{m}</text>
    </svg>
  );
}
