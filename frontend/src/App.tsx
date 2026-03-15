import { useEffect, useState } from "react";
import ConfigScreen from "./screens/ConfigScreen";
import OverlayScreen from "./screens/OverlayScreen";
import ErrorBoundary from "./components/ErrorBoundary";
import type { AppConfig } from "./types";
import "./App.css";

export default function App() {
  const [mode, setMode] = useState<"config" | "overlay">("config");
  const [config, setConfig] = useState<AppConfig | null>(null);

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

  return <ConfigScreen onStart={handleStart} />;
}
