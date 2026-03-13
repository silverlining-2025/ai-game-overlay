import { StatusBar } from "./widgets/StatusBar";
import { CoachPanel } from "./widgets/CoachPanel";
import { MinesweeperOverlay } from "./widgets/MinesweeperOverlay";

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

interface OverlayLayoutProps {
  connected: boolean;
  gameState: GameState | null;
  suggestion: Suggestion | null;
  perfStatus: PerfStatus | null;
}

export function OverlayLayout({
  connected,
  gameState,
  suggestion,
  perfStatus,
}: OverlayLayoutProps) {
  return (
    <div className="overlay-layout">
      <StatusBar
        connected={connected}
        fps={perfStatus?.fps}
        captureMs={perfStatus?.capture_ms}
        processingMs={perfStatus?.processing_ms}
      />

      <CoachPanel
        suggestion={suggestion?.reasoning ?? null}
        reasoning={
          suggestion
            ? `${suggestion.safe_cells.length}개 안전 | ${suggestion.mine_cells.length}개 지뢰`
            : undefined
        }
      />

      {gameState?.grid && (
        <MinesweeperOverlay
          grid={gameState.grid}
          suggestion={suggestion}
        />
      )}
    </div>
  );
}
