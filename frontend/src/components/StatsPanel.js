import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useEffect, useState } from "react";
import "./StatsPanel.css";
function formatDuration(ms) {
    const totalSec = Math.floor(ms / 1000);
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = totalSec % 60;
    if (h > 0)
        return `${h}시간 ${m}분`;
    if (m > 0)
        return `${m}분 ${s}초`;
    return `${s}초`;
}
export default function StatsPanel({ visible, stats }) {
    const [elapsed, setElapsed] = useState(0);
    useEffect(() => {
        if (!visible)
            return;
        const tick = () => setElapsed(Date.now() - stats.sessionStart);
        tick();
        const id = window.setInterval(tick, 1000);
        return () => clearInterval(id);
    }, [visible, stats.sessionStart]);
    if (!visible)
        return null;
    const totalReactions = stats.reactionCount.burst + stats.reactionCount.react + stats.reactionCount.chat;
    const eventEntries = Object.entries(stats.events).filter(([, v]) => v > 0);
    return (_jsxs("div", { className: "stats-panel", children: [_jsx("div", { className: "stats-header", children: "\uC138\uC158 \uD1B5\uACC4" }), _jsxs("div", { className: "stats-row", children: [_jsx("span", { className: "stats-label", children: "\uC2DC\uAC04" }), _jsx("span", { className: "stats-value", children: formatDuration(elapsed) })] }), _jsxs("div", { className: "stats-row", children: [_jsx("span", { className: "stats-label", children: "\uBC18\uC751 \uD69F\uC218" }), _jsx("span", { className: "stats-value", children: totalReactions })] }), totalReactions > 0 && (_jsxs("div", { className: "stats-sub", children: [stats.reactionCount.burst > 0 && _jsxs("span", { children: ["\uC989\uC2DC: ", stats.reactionCount.burst] }), stats.reactionCount.react > 0 && _jsxs("span", { children: ["\uBC18\uC751: ", stats.reactionCount.react] }), stats.reactionCount.chat > 0 && _jsxs("span", { children: ["\uB300\uD654: ", stats.reactionCount.chat] })] })), _jsxs("div", { className: "stats-row", children: [_jsx("span", { className: "stats-label", children: "API \uD638\uCD9C" }), _jsx("span", { className: "stats-value", children: stats.apiCalls })] }), _jsxs("div", { className: "stats-row", children: [_jsx("span", { className: "stats-label", children: "\uC608\uC0C1 \uBE44\uC6A9" }), _jsxs("span", { className: "stats-value stats-cost", children: ["$", stats.totalCost.toFixed(4)] })] }), _jsxs("div", { className: "stats-row", children: [_jsx("span", { className: "stats-label", children: "\uD53C\uB4DC\uBC31" }), _jsxs("span", { className: "stats-value", children: [_jsx("span", { className: "stats-up", title: "\uC88B\uC544\uC694", children: stats.feedbackUp }), " / ", _jsx("span", { className: "stats-down", title: "\uBCC4\uB85C\uC608\uC694", children: stats.feedbackDown })] })] }), eventEntries.length > 0 && (_jsxs(_Fragment, { children: [_jsx("div", { className: "stats-divider" }), _jsx("div", { className: "stats-section-label", children: "\uAC10\uC9C0\uB41C \uC774\uBCA4\uD2B8" }), eventEntries.map(([event, count]) => (_jsxs("div", { className: "stats-row stats-event-row", children: [_jsx("span", { className: "stats-label", children: event }), _jsx("span", { className: "stats-value", children: count })] }, event)))] }))] }));
}
