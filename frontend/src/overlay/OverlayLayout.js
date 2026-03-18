import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { StatusBar } from "./widgets/StatusBar";
import { CoachPanel } from "./widgets/CoachPanel";
import { MinesweeperOverlay } from "./widgets/MinesweeperOverlay";
export function OverlayLayout({ connected, gameState, suggestion, perfStatus, }) {
    return (_jsxs("div", { className: "overlay-layout", children: [_jsx(StatusBar, { connected: connected, fps: perfStatus?.fps, captureMs: perfStatus?.capture_ms, processingMs: perfStatus?.processing_ms }), _jsx(CoachPanel, { suggestion: suggestion?.reasoning ?? null, reasoning: suggestion
                    ? `${suggestion.safe_cells.length}개 안전 | ${suggestion.mine_cells.length}개 지뢰`
                    : undefined }), gameState?.grid && (_jsx(MinesweeperOverlay, { grid: gameState.grid, suggestion: suggestion }))] }));
}
