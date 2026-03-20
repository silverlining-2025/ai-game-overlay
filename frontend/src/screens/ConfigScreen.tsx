import { useState, useEffect } from "react";
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

  // API key state
  const [apiKey, setApiKey] = useState("");
  const [showApiKey, setShowApiKey] = useState(false);
  const [apiKeyStatus, setApiKeyStatus] = useState<"idle" | "testing" | "valid" | "invalid">("idle");
  const [apiKeyError, setApiKeyError] = useState("");
  const [geminiKey, setGeminiKey] = useState(() => localStorage.getItem("gemini_api_key") || "");
  const [openaiKey, setOpenaiKey] = useState(() => localStorage.getItem("openai_api_key") || "");

  // License key state
  const [licenseKey, setLicenseKey] = useState("");
  const [licenseActivated, setLicenseActivated] = useState(false);

  // Load API key and license key from localStorage on mount
  useEffect(() => {
    const savedApiKey = localStorage.getItem("anthropic_api_key");
    if (savedApiKey) setApiKey(savedApiKey);
    const savedLicense = localStorage.getItem("license_key");
    if (savedLicense) {
      setLicenseKey(savedLicense);
      setLicenseActivated(true);
    }
  }, []);

  // Save API key to localStorage whenever it changes
  useEffect(() => {
    if (apiKey) {
      localStorage.setItem("anthropic_api_key", apiKey);
    } else {
      localStorage.removeItem("anthropic_api_key");
    }
  }, [apiKey]);

  useEffect(() => { localStorage.setItem("gemini_api_key", geminiKey); }, [geminiKey]);
  useEffect(() => { localStorage.setItem("openai_api_key", openaiKey); }, [openaiKey]);

  const handleTestApiKey = async () => {
    if (!apiKey.trim()) return;
    setApiKeyStatus("testing");
    setApiKeyError("");
    try {
      const resp = await fetch("https://api.anthropic.com/v1/messages", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-api-key": apiKey,
          "anthropic-version": "2023-06-01",
          "anthropic-dangerous-direct-browser-access": "true",
        },
        body: JSON.stringify({
          model: "claude-haiku-4-5-20251001",
          max_tokens: 1,
          messages: [{ role: "user", content: "test" }],
        }),
      });
      if (resp.ok) {
        setApiKeyStatus("valid");
      } else {
        const body = await resp.json().catch(() => ({}));
        setApiKeyStatus("invalid");
        setApiKeyError(body?.error?.message || `HTTP ${resp.status}`);
      }
    } catch (err: any) {
      setApiKeyStatus("invalid");
      setApiKeyError(err?.message || "Network error");
    }
  };

  const handleActivateLicense = () => {
    if (!licenseKey.trim()) return;
    localStorage.setItem("license_key", licenseKey);
    setLicenseActivated(true);
  };

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

  const hasAnyKey = !!(geminiKey.trim() || apiKey.trim() || openaiKey.trim());
  const currentTier = licenseActivated ? "pro" : "free";

  const handleStart = async () => {
    if (!hasAnyKey) return; // Block start without any API key

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
        apiKey: apiKey || undefined,
        geminiKey: geminiKey || undefined,
        openaiKey: openaiKey || undefined,
        tier: currentTier,
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

        {/* Gemini API Key — PRIMARY (free tier) */}
        <div className="config-section">
          <label className="config-label">{t("config.gemini_key_label")}</label>
          <div className="api-key-row">
            <input
              type="password"
              className="config-input"
              placeholder={t("config.gemini_key_placeholder")}
              value={geminiKey}
              onChange={(e) => setGeminiKey(e.target.value)}
            />
          </div>
          <a
            href="https://aistudio.google.com/apikey"
            target="_blank"
            rel="noopener noreferrer"
            className="api-key-link"
          >
            {t("config.gemini_get_key")}
          </a>
        </div>

        {/* Anthropic API Key — optional */}
        <div className="config-section">
          <label className="config-label">{t("config.api_key_label")}</label>
          <div className="api-key-row">
            <input
              type={showApiKey ? "text" : "password"}
              className="config-input"
              placeholder={t("config.api_key_placeholder")}
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                setApiKeyStatus("idle");
                setApiKeyError("");
              }}
            />
            <button
              type="button"
              className="btn-toggle-vis"
              onClick={() => setShowApiKey(!showApiKey)}
            >
              {showApiKey ? "Hide" : "Show"}
            </button>
            <button
              type="button"
              className="btn-test-key"
              onClick={handleTestApiKey}
              disabled={!apiKey.trim() || apiKeyStatus === "testing"}
            >
              {apiKeyStatus === "testing" ? "..." : t("config.test_key")}
            </button>
          </div>
          {apiKeyStatus === "valid" && (
            <div className="key-status key-valid">
              <span className="status-icon">&#x2714;</span> {t("config.key_valid")}
            </div>
          )}
          {apiKeyStatus === "invalid" && (
            <div className="key-status key-invalid">
              <span className="status-icon">&#x2718;</span> {t("config.key_invalid")}{apiKeyError ? `: ${apiKeyError}` : ""}
            </div>
          )}
        </div>

        {/* OpenAI API Key — optional */}
        <div className="config-section">
          <label className="config-label">{t("config.openai_key_label")}</label>
          <div className="api-key-row">
            <input
              type="password"
              className="config-input"
              placeholder={t("config.openai_key_placeholder")}
              value={openaiKey}
              onChange={(e) => setOpenaiKey(e.target.value)}
            />
          </div>
        </div>

        <div className="config-section">
          <p className="config-hint api-priority-text">{t("config.api_priority")}</p>
          <p className="config-hint api-key-help-text">{t("config.api_key_help")}</p>
        </div>

        {/* License Key */}
        <div className="config-section">
          <label className="config-label">{t("config.license_label")}</label>
          <div className="api-key-row">
            <input
              type="text"
              className="config-input"
              placeholder={t("config.license_placeholder")}
              value={licenseKey}
              onChange={(e) => {
                setLicenseKey(e.target.value);
                if (licenseActivated) setLicenseActivated(false);
              }}
            />
            <button
              type="button"
              className="btn-test-key"
              onClick={handleActivateLicense}
              disabled={!licenseKey.trim()}
            >
              {t("config.activate")}
            </button>
          </div>
          <div className={`license-tier ${licenseActivated ? "tier-premium" : "tier-free"}`}>
            {licenseActivated ? t("config.premium_tier") : t("config.free_tier")}
          </div>
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

        <button type="button" className="btn-start" onClick={handleStart} disabled={!hasAnyKey}>
          {hasAnyKey ? t("config.start") : t("config.need_key")}
        </button>

        <p className="config-cost">
          {geminiKey.trim() ? t("config.cost_free") : t("config.cost")}
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
