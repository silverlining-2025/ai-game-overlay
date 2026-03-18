import { jsx as _jsx } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import ConsentScreen from "./screens/ConsentScreen";
import ConfigScreen from "./screens/ConfigScreen";
import OverlayScreen from "./screens/OverlayScreen";
import ErrorBoundary from "./components/ErrorBoundary";
import "./App.css";
export default function App() {
    const [mode, setMode] = useState("config");
    const [config, setConfig] = useState(null);
    const [consented, setConsented] = useState(() => localStorage.getItem("privacy_consent") === "true");
    useEffect(() => {
        // Route based on hash: #overlay = overlay mode
        if (window.location.hash === "#overlay") {
            const saved = localStorage.getItem("companion_config");
            if (saved) {
                try {
                    setConfig(JSON.parse(saved));
                    setMode("overlay");
                }
                catch {
                    console.error("Failed to parse saved config");
                }
            }
        }
        // ESC to quit
        const handleKey = async (e) => {
            if (e.key === "Escape") {
                try {
                    const { invoke } = await import("@tauri-apps/api/core");
                    await invoke("quit_app");
                }
                catch {
                    window.close();
                }
            }
        };
        window.addEventListener("keydown", handleKey);
        return () => window.removeEventListener("keydown", handleKey);
    }, []);
    const handleStart = (cfg) => {
        localStorage.setItem("companion_config", JSON.stringify(cfg));
        setConfig(cfg);
        setMode("overlay");
    };
    if (mode === "overlay" && config) {
        return (_jsx(ErrorBoundary, { children: _jsx(OverlayScreen, { config: config }) }));
    }
    if (!consented) {
        return _jsx(ConsentScreen, { onConsent: () => setConsented(true) });
    }
    return _jsx(ConfigScreen, { onStart: handleStart });
}
