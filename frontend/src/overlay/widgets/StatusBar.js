import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useTranslation } from "@/i18n/useTranslation";
export function StatusBar({ connected, fps, captureMs, processingMs, }) {
    const { t } = useTranslation();
    const statusClass = connected ? "connected" : "disconnected";
    const statusText = connected
        ? t("status.connected")
        : t("status.disconnected");
    return (_jsxs("div", { className: "status-bar", children: [_jsx("span", { className: `status-dot ${statusClass}` }), _jsx("span", { children: statusText }), fps != null && _jsx("span", { children: t("perf.fps", { value: fps.toFixed(1) }) }), captureMs != null && (_jsx("span", { children: t("perf.capture_ms", { value: captureMs.toFixed(0) }) })), processingMs != null && (_jsx("span", { children: t("perf.processing_ms", { value: processingMs.toFixed(0) }) }))] }));
}
