import { useTranslation } from "@/i18n/useTranslation";

interface SuggestionData {
  safe_cells: [number, number][];
  mine_cells: [number, number][];
  confidence: number;
  reasoning: string;
}

interface GridData {
  origin: [number, number];
  cell_size: [number, number];
  rows: number;
  cols: number;
}

interface MinesweeperOverlayProps {
  grid: GridData | null;
  suggestion: SuggestionData | null;
}

export function MinesweeperOverlay({
  grid,
  suggestion,
}: MinesweeperOverlayProps) {
  const { t } = useTranslation();

  if (!grid || !suggestion) {
    return null;
  }

  const [originX, originY] = grid.origin;
  const [cellW, cellH] = grid.cell_size;

  return (
    <div className="minesweeper-overlay">
      {/* Safe cell highlights */}
      {suggestion.safe_cells.map(([r, c]) => (
        <div
          key={`safe-${r}-${c}`}
          className="cell-highlight safe new"
          style={{
            left: originX + c * cellW,
            top: originY + r * cellH,
            width: cellW,
            height: cellH,
          }}
        >
          {t("minesweeper.safe_cell")}
        </div>
      ))}

      {/* Mine cell highlights */}
      {suggestion.mine_cells.map(([r, c]) => (
        <div
          key={`mine-${r}-${c}`}
          className="cell-highlight mine new"
          style={{
            left: originX + c * cellW,
            top: originY + r * cellH,
            width: cellW,
            height: cellH,
          }}
        >
          {t("minesweeper.mine_cell")}
        </div>
      ))}

      {/* Confidence badge */}
      {suggestion.confidence > 0 && (
        <div
          className="widget"
          style={{
            position: "absolute",
            left: originX,
            top: originY + grid.rows * cellH + 8,
          }}
        >
          {t("minesweeper.confidence", {
            value: (suggestion.confidence * 100).toFixed(0),
          })}
        </div>
      )}
    </div>
  );
}
