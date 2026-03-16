import { useState } from "react";
import type { AppConfig } from "../types";
import "./ConfigScreen.css";

const CHARACTERS = [
  { id: "nozomi" as const, emoji: "\u{1F466}", label: "노조미" },
  { id: "robot" as const, emoji: "\u{1F916}", label: "로봇" },
  { id: "cat" as const, emoji: "\u{1F431}", label: "고양이" },
  { id: "ghost" as const, emoji: "\u{1F47B}", label: "유령" },
  { id: "fox" as const, emoji: "\u{1F98A}", label: "여우" },
  { id: "slime" as const, emoji: "\u{1F7E2}", label: "슬라임" },
];

const GAMES = [
  { id: "maplestory" as const, label: "MapleStory (KMS)" },
  { id: "palworld" as const, label: "Palworld" },
  { id: "general" as const, label: "기타 / 일반" },
];

const POSITIONS = [
  { id: "top-right" as const, label: "우상단" },
  { id: "top-left" as const, label: "좌상단" },
  { id: "bottom-right" as const, label: "우하단" },
  { id: "bottom-left" as const, label: "좌하단" },
];

interface Props {
  onStart: (config: AppConfig) => void;
}

export default function ConfigScreen({ onStart }: Props) {
  const [character, setCharacter] = useState<AppConfig["character"]>("nozomi");
  const [game, setGame] = useState<AppConfig["game"]>("palworld");
  const [position, setPosition] = useState<AppConfig["position"]>("top-right");
  const [chattiness, setChattiness] = useState(0.5);

  const handleStart = async () => {
    const config: AppConfig = { game, character, interval: 3, position, chattiness };

    // Save config BEFORE creating overlay window (overlay reads this on load)
    localStorage.setItem("companion_config", JSON.stringify(config));

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("start_companion", {
        game: config.game,
        character: config.character,
        interval: 3.0,
        chattiness: config.chattiness,
      });
    } catch {
      // Not in Tauri
    }

    onStart(config);
  };

  return (
    <div className="config-root">
      <div className="config-card">
        <h1 className="config-title">AI Gaming Companion</h1>
        <p className="config-subtitle">
          게임 화면을 보면서 실시간으로 반응하는 AI 친구
        </p>

        <div className="config-section">
          <label className="config-label">캐릭터 선택</label>
          <div className="character-grid">
            {CHARACTERS.map((c) => (
              <button
                type="button"
                key={c.id}
                className={`char-btn ${character === c.id ? "selected" : ""}`}
                onClick={() => setCharacter(c.id)}
              >
                <span className="char-emoji">{c.emoji}</span>
                <span className="char-label">{c.label}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="config-section">
          <label className="config-label">게임</label>
          <select
            className="config-select"
            title="게임 선택"
            value={game}
            onChange={(e) => setGame(e.target.value as AppConfig["game"])}
          >
            {GAMES.map((g) => (
              <option key={g.id} value={g.id}>{g.label}</option>
            ))}
          </select>
        </div>

        <div className="config-section">
          <label className="config-label">위치</label>
          <select
            className="config-select"
            title="오버레이 위치"
            value={position}
            onChange={(e) => setPosition(e.target.value as AppConfig["position"])}
          >
            {POSITIONS.map((p) => (
              <option key={p.id} value={p.id}>{p.label}</option>
            ))}
          </select>
        </div>

        <div className="config-section">
          <label className="config-label">
            수다 레벨: {chattiness < 0.3 ? "조용" : chattiness < 0.7 ? "보통" : "수다쟁이"}
          </label>
          <input
            type="range"
            className="config-slider"
            title="수다 레벨"
            min={0} max={1} step={0.1}
            value={chattiness}
            onChange={(e) => setChattiness(parseFloat(e.target.value))}
          />
        </div>

        <p className="config-hint">
          이벤트 기반 반응 — 화면 변화가 감지될 때만 반응합니다.
          Hold Alt to interact with overlay.
        </p>

        <button type="button" className="btn-start" onClick={handleStart}>
          시작하기
        </button>

        <p className="config-cost">
          예상 비용: ~$0.05~0.10/시간 (이벤트 기반, Claude Haiku)
        </p>
        <button type="button" className="btn-quit" onClick={async () => {
          try {
            const { invoke } = await import("@tauri-apps/api/core");
            await invoke("quit_app");
          } catch {
            window.close();
          }
        }}>종료</button>
      </div>
    </div>
  );
}
