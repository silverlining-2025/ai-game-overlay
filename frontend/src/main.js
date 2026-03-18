import { jsx as _jsx } from "react/jsx-runtime";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { initLocale } from "./i18n";
import App from "./App";
initLocale();
createRoot(document.getElementById("root")).render(_jsx(StrictMode, { children: _jsx(App, {}) }));
