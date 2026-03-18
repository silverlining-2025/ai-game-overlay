import { jsx as _jsx, jsxs as _jsxs, Fragment as _Fragment } from "react/jsx-runtime";
import { useState } from "react";
import { useTranslation } from "@/i18n/useTranslation";
export function CoachPanel({ suggestion, reasoning }) {
    const { t } = useTranslation();
    const [collapsed, setCollapsed] = useState(false);
    return (_jsxs("div", { className: "coach-panel", children: [_jsxs("div", { className: "coach-header", children: [_jsx("span", { children: t("overlay.coach_title") }), _jsx("button", { className: "coach-toggle", onClick: () => setCollapsed((c) => !c), children: collapsed ? "▼" : "▲" })] }), !collapsed && (_jsx("div", { className: "coach-body", children: suggestion ? (_jsxs(_Fragment, { children: [_jsx("div", { className: "coach-bubble", children: suggestion }), reasoning && (_jsx("div", { className: "coach-bubble", style: { opacity: 0.7 }, children: reasoning }))] })) : (_jsx("p", { className: "loading-text", children: t("coach.no_suggestion") })) }))] }));
}
