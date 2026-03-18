import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState } from "react";
import { useTranslation } from "../i18n/useTranslation";
import "./ConfigScreen.css";
const CHARACTER_IDS = ["nozomi", "robot", "cat", "ghost", "fox", "slime"];
const CHARACTER_EMOJIS = {
    nozomi: "\u{1F466}",
    robot: "\u{1F916}",
    cat: "\u{1F431}",
    ghost: "\u{1F47B}",
    fox: "\u{1F98A}",
    slime: "\u{1F7E2}",
};
const GAMES = [
    { id: "maplestory", label: "MapleStory (KMS)" },
    { id: "palworld", label: "Palworld" },
    { id: "general", labelKey: "config.game_other" },
];
const POSITION_IDS = ["top-right", "top-left", "bottom-right", "bottom-left"];
const POSITION_KEYS = {
    "top-right": "config.position_top_right",
    "top-left": "config.position_top_left",
    "bottom-right": "config.position_bottom_right",
    "bottom-left": "config.position_bottom_left",
};
function loadSaved(key, fallback) {
    try {
        const saved = localStorage.getItem("companion_config");
        if (saved) {
            const config = JSON.parse(saved);
            if (key in config)
                return config[key];
        }
    }
    catch { /* ignore */ }
    return fallback;
}
function detectDefaultLocale() {
    const saved = localStorage.getItem("overlay-locale");
    if (saved === "ko" || saved === "en")
        return saved;
    const browserLang = navigator.language ?? "";
    return browserLang.startsWith("ko") ? "ko" : "en";
}
export default function ConfigScreen({ onStart }) {
    const { t, setLocale } = useTranslation();
    const [locale, setLocaleState] = useState(() => detectDefaultLocale());
    const [character, setCharacter] = useState(() => loadSaved("character", "nozomi"));
    const [game, setGame] = useState(() => loadSaved("game", "palworld"));
    const [position, setPosition] = useState(() => loadSaved("position", "top-right"));
    const [chattiness, setChattiness] = useState(() => loadSaved("chattiness", 0.5));
    const handleLocaleChange = (newLocale) => {
        setLocaleState(newLocale);
        setLocale(newLocale);
    };
    const chattinessLabel = chattiness < 0.3
        ? t("config.chattiness_quiet")
        : chattiness < 0.7
            ? t("config.chattiness_normal")
            : t("config.chattiness_talkative");
    const handleStart = async () => {
        const config = { game, character, interval: 3, position, chattiness, locale };
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
        }
        catch {
            // Not in Tauri
        }
        onStart(config);
    };
    return (_jsx("div", { className: "config-root", children: _jsxs("div", { className: "config-card", children: [_jsx("h1", { className: "config-title", children: t("config.title") }), _jsx("p", { className: "config-subtitle", children: t("config.subtitle") }), _jsxs("div", { className: "config-section", children: [_jsx("label", { className: "config-label", children: t("config.language_label") }), _jsxs("select", { className: "config-select", title: t("config.language_label"), value: locale, onChange: (e) => handleLocaleChange(e.target.value), children: [_jsx("option", { value: "ko", children: "\uD55C\uAD6D\uC5B4" }), _jsx("option", { value: "en", children: "English" })] })] }), _jsxs("div", { className: "config-section", children: [_jsx("label", { className: "config-label", children: t("config.character_label") }), _jsx("div", { className: "character-grid", children: CHARACTER_IDS.map((id) => (_jsxs("button", { type: "button", className: `char-btn ${character === id ? "selected" : ""}`, onClick: () => setCharacter(id), children: [_jsx("span", { className: "char-emoji", children: CHARACTER_EMOJIS[id] }), _jsx("span", { className: "char-label", children: t(`config.char_${id}`) })] }, id))) })] }), _jsxs("div", { className: "config-section", children: [_jsx("label", { className: "config-label", children: t("config.game_label") }), _jsx("select", { className: "config-select", title: t("config.game_select_title"), value: game, onChange: (e) => setGame(e.target.value), children: GAMES.map((g) => (_jsx("option", { value: g.id, children: g.labelKey ? t(g.labelKey) : g.label }, g.id))) })] }), _jsxs("div", { className: "config-section", children: [_jsx("label", { className: "config-label", children: t("config.position_label") }), _jsx("select", { className: "config-select", title: t("config.position_select_title"), value: position, onChange: (e) => setPosition(e.target.value), children: POSITION_IDS.map((id) => (_jsx("option", { value: id, children: t(POSITION_KEYS[id]) }, id))) })] }), _jsxs("div", { className: "config-section", children: [_jsxs("label", { className: "config-label", children: [t("config.chattiness_label"), ": ", chattinessLabel] }), _jsx("input", { type: "range", className: "config-slider", title: t("config.chattiness_slider_title"), min: 0, max: 1, step: 0.1, value: chattiness, onChange: (e) => setChattiness(parseFloat(e.target.value)) })] }), _jsx("p", { className: "config-hint", children: t("config.hint") }), _jsx("button", { type: "button", className: "btn-start", onClick: handleStart, children: t("config.start") }), _jsx("p", { className: "config-cost", children: t("config.cost") }), _jsx("button", { type: "button", className: "btn-quit", onClick: async () => {
                        try {
                            const { invoke } = await import("@tauri-apps/api/core");
                            await invoke("quit_app");
                        }
                        catch {
                            window.close();
                        }
                    }, children: t("config.quit") })] }) }));
}
