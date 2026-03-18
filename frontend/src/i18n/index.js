/**
 * Custom i18n system — zero dependencies, type-safe keys.
 * Korean primary, English fallback.
 */
import ko from "./ko";
import en from "./en";
const translations = { ko, en };
let currentLocale = "ko";
const listeners = new Set();
export function t(key, params) {
    let text = translations[currentLocale]?.[key] ??
        translations["ko"][key] ??
        key;
    if (params) {
        for (const [k, v] of Object.entries(params)) {
            text = text.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), String(v));
        }
    }
    return text;
}
export function setLocale(locale) {
    currentLocale = locale;
    localStorage.setItem("overlay-locale", locale);
    listeners.forEach((fn) => fn());
}
export function getLocale() {
    return currentLocale;
}
export function initLocale() {
    const saved = localStorage.getItem("overlay-locale");
    if (saved && saved in translations) {
        currentLocale = saved;
    }
    else {
        // Auto-detect from browser language
        const browserLang = navigator.language ?? "";
        currentLocale = browserLang.startsWith("ko") ? "ko" : "en";
    }
}
export function subscribe(fn) {
    listeners.add(fn);
    return () => listeners.delete(fn);
}
