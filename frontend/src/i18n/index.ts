/**
 * Custom i18n system — zero dependencies, type-safe keys.
 * Korean primary, English fallback.
 */

import ko, { type TranslationKey } from "./ko";
import en from "./en";

type Locale = "ko" | "en";

const translations: Record<Locale, Record<TranslationKey, string>> = { ko, en };

let currentLocale: Locale = "ko";
const listeners = new Set<() => void>();

export type { TranslationKey, Locale };

export function t(
  key: TranslationKey,
  params?: Record<string, string | number>,
): string {
  let text =
    translations[currentLocale]?.[key] ??
    translations["ko"][key] ??
    key;

  if (params) {
    for (const [k, v] of Object.entries(params)) {
      text = text.replace(new RegExp(`\\{\\{${k}\\}\\}`, "g"), String(v));
    }
  }
  return text;
}

export function setLocale(locale: Locale): void {
  currentLocale = locale;
  localStorage.setItem("overlay-locale", locale);
  listeners.forEach((fn) => fn());
}

export function getLocale(): Locale {
  return currentLocale;
}

export function initLocale(): void {
  const saved = localStorage.getItem("overlay-locale") as Locale | null;
  if (saved && saved in translations) {
    currentLocale = saved;
  } else {
    // Auto-detect from browser language
    const browserLang = navigator.language ?? "";
    currentLocale = browserLang.startsWith("ko") ? "ko" : "en";
  }
}

export function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}
