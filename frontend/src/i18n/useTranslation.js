import { useSyncExternalStore, useCallback } from "react";
import { t, subscribe, getLocale, setLocale, } from "./index";
export function useTranslation() {
    const locale = useSyncExternalStore(subscribe, getLocale, getLocale);
    const translate = useCallback((key, params) => t(key, params), 
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [locale]);
    return { t: translate, locale, setLocale };
}
