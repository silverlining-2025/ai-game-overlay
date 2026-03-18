import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useTranslation } from "@/i18n/useTranslation";
export function MinesweeperOverlay({ grid, suggestion, }) {
    const { t } = useTranslation();
    if (!grid || !suggestion) {
        return null;
    }
    const [originX, originY] = grid.origin;
    const [cellW, cellH] = grid.cell_size;
    return (_jsxs("div", { className: "minesweeper-overlay", children: [suggestion.safe_cells.map(([r, c]) => (_jsx("div", { className: "cell-highlight safe new", style: {
                    left: originX + c * cellW,
                    top: originY + r * cellH,
                    width: cellW,
                    height: cellH,
                }, children: t("minesweeper.safe_cell") }, `safe-${r}-${c}`))), suggestion.mine_cells.map(([r, c]) => (_jsx("div", { className: "cell-highlight mine new", style: {
                    left: originX + c * cellW,
                    top: originY + r * cellH,
                    width: cellW,
                    height: cellH,
                }, children: t("minesweeper.mine_cell") }, `mine-${r}-${c}`))), suggestion.confidence > 0 && (_jsx("div", { className: "widget", style: {
                    position: "absolute",
                    left: originX,
                    top: originY + grid.rows * cellH + 8,
                }, children: t("minesweeper.confidence", {
                    value: (suggestion.confidence * 100).toFixed(0),
                }) }))] }));
}
