import { useState } from "react";
import type { AppConfig } from "../types";
import { useTranslation } from "../i18n/useTranslation";
import type { Locale } from "../i18n/index";
import "./ConfigScreen.css";

const CHARACTER_IDS = ["nozomi", "robot", "cat", "ghost", "fox", "slime"] as const;
const CHARACTER_EMOJIS: Record<string, string> = {
  nozomi: "\u{1F466}",
  robot: "\u{1F916}",
  cat: "\u{1F431}",
  ghost: "\u{1F47B}",
  fox: "\u{1F98A}",
  slime: "\u{1F7E2}",
};

const GAMES: Array<{ id: AppConfig["game"]; label?: string; labelKey?: "config.game_other" }> = [
  { id: "maplestory", label: "MapleStory (KMS)" },
  { id: "palworld", label: "Palworld" },
  { id: "general", labelKey: "config.game_other" },
];

const POSITION_IDS = ["top-right", "top-left", "bottom-right", "bottom-left"] as const;
const POSITION_KEYS: Record<string, string> = {
  "top-right": "config.position_top_right",
  "top-left": "config.position_top_left",
  "bottom-right": "config.position_bottom_right",
  "bottom-left": "config.position_bottom_left",
};

interface Props {
  onStart: (config: AppConfig) => void;
}

function loadSaved<T>(key: string, fallback: T): T {
  try {
    const saved = localStorage.getItem("companion_config");
    if (saved) {
      const config = JSON.parse(saved);
      if (key in config) return config[key];
    }
  } catch { /* ignore */ }
  return fallback;
}

function detectDefaultLocale(): Locale {
  const saved = localStorage.getItem("overlay-locale") as Locale | null;
  if (saved === "ko" || saved === "en") return saved;
  const browserLang = navigator.language ?? "";
  return browserLang.startsWith("ko") ? "ko" : "en";
}

export default function ConfigScreen({ onStart }: Props) {
  const { t, setLocale } = useTranslation();

  const [locale, setLocaleState] = useState<Locale>(() => detectDefaultLocale());
  const [character, setCharacter] = useState<AppConfig["character"]>(() => loadSaved("character", "nozomi"));
  const [game, setGame] = useState<AppConfig["game"]>(() => loadSaved("game", "palworld"));
  const [position, setPosition] = useState<AppConfig["position"]>(() => loadSaved("position", "top-right"));
  const [chattiness, setChattiness] = useState(() => loadSaved("chattiness", 0.5));

  const handleLocaleChange = (newLocale: Locale) => {
    setLocaleState(newLocale);
    setLocale(newLocale);
  };

  const chattinessLabel =
    chattiness < 0.3
      ? t("config.chattiness_quiet")
      : chattiness < 0.7
        ? t("config.chattiness_normal")
        : t("config.chattiness_talkative");

  const handleStart = async () => {
    const config: AppConfig = { game, character, interval: 3, position, chattiness, locale };

    // Save config BEFORE creating overlay window (overlay reads this on load)
    localStorage.setItem("companion_config", JSON.stringify(config));

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      await invoke("start_companion", {
        game: config.game,
        character: config.character,
        interval: 3.0,
        chattiness: config.chattiness,
        locale: config.locale,
      });
    } catch {
      // Not in Tauri
    }

    onStart(config);
  };

  return (
    <div className="config-root">
      <div className="config-card">
        <h1 className="config-title">{t("config.title")}</h1>
        <p className="config-subtitle">
          {t("config.subtitle")}
        </p>

        <div className="config-section">
          <label className="config-label">{t("config.language_label")}</label>
          <select
            className="config-select"
            title={t("config.language_label")}
            value={locale}
            onChange={(e) => handleLocaleChange(e.target.value as Locale)}
          >
            <option value="ko">한국어</option>
            <option value="en">English</option>
          </select>
        </div>

        <div className="config-section">
          <label className="config-label">{t("config.character_label")}</label>
          <div className="character-grid">
            {CHARACTER_IDS.map((id) => (
              <button
                type="button"
                key={id}
                className={`char-btn ${character === id ? "selected" : ""}`}
                onClick={() => setCharacter(id)}
              >
                <span className="char-emoji">{CHARACTER_EMOJIS[id]}</span>
                <span className="char-label">{t(`config.char_${id}` as any)}</span>
              </button>
            ))}
          </div>
        </div>

        <div className="config-section">
          <label className="config-label">{t("config.game_label")}</label>
          <select
            className="config-select"
            title={t("config.game_select_title")}
            value={game}
            onChange={(e) => setGame(e.target.value as AppConfig["game"])}
          >
            {GAMES.map((g) => (
              <option key={g.id} value={g.id}>
                {g.labelKey ? t(g.labelKey) : g.label}
              </option>
            ))}
          </select>
        </div>

        <div className="config-section">
          <label className="config-label">{t("config.position_label")}</label>
          <select
            className="config-select"
            title={t("config.position_select_title")}
            value={position}
            onChange={(e) => setPosition(e.target.value as AppConfig["position"])}
          >
            {POSITION_IDS.map((id) => (
              <option key={id} value={id}>{t(POSITION_KEYS[id] as any)}</option>
            ))}
          </select>
        </div>

        <div className="config-section">
          <label className="config-label">
            {t("config.chattiness_label")}: {chattinessLabel}
          </label>
          <input
            type="range"
            className="config-slider"
            title={t("config.chattiness_slider_title")}
            min={0} max={1} step={0.1}
            value={chattiness}
            onChange={(e) => setChattiness(parseFloat(e.target.value))}
          />
        </div>

        <p className="config-hint">
          {t("config.hint")}
        </p>

        <button type="button" className="btn-start" onClick={handleStart}>
          {t("config.start")}
        </button>

        <p className="config-cost">
          {t("config.cost")}
        </p>
        <button type="button" className="btn-quit" onClick={async () => {
          try {
            const { invoke } = await import("@tauri-apps/api/core");
            await invoke("quit_app");
          } catch {
            window.close();
          }
        }}>{t("config.quit")}</button>
      </div>
    </div>
  );
}
