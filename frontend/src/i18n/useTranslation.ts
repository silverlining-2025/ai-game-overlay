import { useSyncExternalStore, useCallback } from "react";
import {
  t,
  subscribe,
  getLocale,
  setLocale,
  type TranslationKey,
  type Locale as _Locale,
} from "./index";

export function useTranslation() {
  const locale = useSyncExternalStore(subscribe, getLocale, getLocale);

  const translate = useCallback(
    (key: TranslationKey, params?: Record<string, string | number>) =>
      t(key, params),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [locale],
  );

  return { t: translate, locale, setLocale } as const;
}
