import { useEffect, useState } from "react";
import ConsentScreen from "./screens/ConsentScreen";
import ConfigScreen from "./screens/ConfigScreen";
import OverlayScreen from "./screens/OverlayScreen";
import ErrorBoundary from "./components/ErrorBoundary";
import Tutorial from "./components/Tutorial";
import type { AppConfig } from "./types";
import "./App.css";

export default function App() {
  const [mode, setMode] = useState<"config" | "overlay">("config");
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [consented, setConsented] = useState(
    () => localStorage.getItem("privacy_consent") === "true"
  );
  const [tutorialDone, setTutorialDone] = useState(
    () => localStorage.getItem("tutorial_completed") === "true"
  );

  useEffect(() => {
    // Route based on hash: #overlay = overlay mode
    if (window.location.hash === "#overlay") {
      const saved = localStorage.getItem("companion_config");
      if (saved) {
        try {
          setConfig(JSON.parse(saved));
          setMode("overlay");
        } catch {
          console.error("Failed to parse saved config");
        }
      }
    }

    // ESC to quit
    const handleKey = async (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        try {
          const { invoke } = await import("@tauri-apps/api/core");
          await invoke("quit_app");
        } catch {
          window.close();
        }
      }
    };
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, []);

  const handleStart = (cfg: AppConfig) => {
    localStorage.setItem("companion_config", JSON.stringify(cfg));
    setConfig(cfg);
    setMode("overlay");
  };

  if (mode === "overlay" && config) {
    return (
      <ErrorBoundary>
        <OverlayScreen config={config} />
      </ErrorBoundary>
    );
  }

  if (!consented) {
    return <ConsentScreen onConsent={() => setConsented(true)} />;
  }

  if (!tutorialDone) {
    return <Tutorial onComplete={() => setTutorialDone(true)} />;
  }

  return <ConfigScreen onStart={handleStart} />;
}
