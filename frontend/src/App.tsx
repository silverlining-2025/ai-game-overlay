import { useEffect, useState } from "react";
import { coachSocket } from "./lib/websocket";
import { setupHotkeys, cleanupHotkeys } from "./lib/hotkeys";
import { OverlayLayout } from "./overlay/OverlayLayout";
import "./App.css";

// Types matching the WS protocol
interface GameState {
  grid?: {
    origin: [number, number];
    cell_size: [number, number];
    rows: number;
    cols: number;
    cells: string[][];
  };
  status?: string;
}

interface Suggestion {
  safe_cells: [number, number][];
  mine_cells: [number, number][];
  confidence: number;
  reasoning: string;
}

interface PerfStatus {
  fps: number;
  capture_ms: number;
  processing_ms: number;
}

export default function App() {
  const [connected, setConnected] = useState(false);
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [suggestion, setSuggestion] = useState<Suggestion | null>(null);
  const [perfStatus, setPerfStatus] = useState<PerfStatus | null>(null);

  useEffect(() => {
    // WebSocket handlers
    const unsubs = [
      coachSocket.on("connected", () => setConnected(true)),
      coachSocket.on("disconnected", () => setConnected(false)),
      coachSocket.on("state_update", (data) => {
        setGameState(data as GameState);
      }),
      coachSocket.on("suggestion", (data) => {
        setSuggestion(data as Suggestion);
      }),
      coachSocket.on("status", (data) => {
        setPerfStatus(data as PerfStatus);
      }),
    ];

    coachSocket.connect();

    // Hotkeys (will fail gracefully outside Tauri)
    setupHotkeys().catch(() => {
      // Not in Tauri environment — hotkeys unavailable
    });

    return () => {
      unsubs.forEach((unsub) => unsub());
      coachSocket.disconnect();
      cleanupHotkeys().catch(() => {});
    };
  }, []);

  return (
    <OverlayLayout
      connected={connected}
      gameState={gameState}
      suggestion={suggestion}
      perfStatus={perfStatus}
    />
  );
}
