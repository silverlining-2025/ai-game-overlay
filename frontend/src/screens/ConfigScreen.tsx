import { useState } from "react";
import type { AppConfig } from "../types";
import "./ConfigScreen.css";

const CHARACTERS = [
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
  const [character, setCharacter] = useState<AppConfig["character"]>("robot");
  const [game, setGame] = useState<AppConfig["game"]>("maplestory");
  const [interval, setInterval_] = useState(3);
  const [position, setPosition] = useState<AppConfig["position"]>("top-right");

  const handleStart = async () => {
    const config: AppConfig = { game, character, interval, position };

    // Try to open Tauri overlay window
    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("open_overlay");
    } catch {
      // Not in Tauri — just switch mode in-page
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
            value={game}
            onChange={(e) => setGame(e.target.value as AppConfig["game"])}
          >
            {GAMES.map((g) => (
              <option key={g.id} value={g.id}>{g.label}</option>
            ))}
          </select>
        </div>

        <div className="config-row">
          <div className="config-section config-half">
            <label className="config-label">반응 간격</label>
            <select
              className="config-select"
              value={interval}
              onChange={(e) => setInterval_(Number(e.target.value))}
            >
              <option value={2}>2초 (빠름)</option>
              <option value={3}>3초 (보통)</option>
              <option value={5}>5초 (느림)</option>
            </select>
          </div>
          <div className="config-section config-half">
            <label className="config-label">위치</label>
            <select
              className="config-select"
              value={position}
              onChange={(e) => setPosition(e.target.value as AppConfig["position"])}
            >
              {POSITIONS.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
              ))}
            </select>
          </div>
        </div>

        <button className="btn-start" onClick={handleStart}>
          시작하기
        </button>

        <p className="config-cost">
          예상 비용: ~$0.07~0.20/시간 (Claude Haiku)
        </p>
      </div>
    </div>
  );
}
