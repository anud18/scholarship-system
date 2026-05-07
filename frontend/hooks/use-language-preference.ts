"use client";

import { useState, useEffect } from "react";
import type { Locale } from "@/lib/i18n";

const LANGUAGE_STORAGE_KEY = "scholarship-system-language";

export function useLanguagePreference(
  userRole: string,
  defaultLocale: Locale = "zh"
) {
  // 只有學生角色才使用語言偏好儲存
  const shouldUsePreference = userRole === "student";

  // Always start with `defaultLocale` so the SSR-rendered HTML matches the
  // initial CSR render. Reading localStorage in the lazy initializer produced
  // a server/client mismatch on every page load (server returned
  // `defaultLocale`, client returned the stored preference) and was the
  // source of the hydration warnings flagged in the Phase 1 audit. The
  // stored preference is applied via the useEffect below, after first paint.
  const [locale, setLocale] = useState<Locale>(defaultLocale);

  // Hydrate the stored preference on mount.
  useEffect(() => {
    if (!shouldUsePreference) return;
    if (typeof window === "undefined") return;
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY) as Locale | null;
    if (stored && stored !== locale) {
      setLocale(stored);
    }
    // Run on mount + when role-eligibility changes; the cross-tab `storage`
    // listener below handles subsequent external updates.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldUsePreference]);

  const changeLocale = (newLocale: Locale) => {
    if (!shouldUsePreference) return;

    setLocale(newLocale);
    if (typeof window !== "undefined") {
      localStorage.setItem(LANGUAGE_STORAGE_KEY, newLocale);
    }
  };

  // 監聽其他標籤頁的語言變更
  useEffect(() => {
    if (!shouldUsePreference) return;

    const handleStorageChange = (e: StorageEvent) => {
      if (e.key === LANGUAGE_STORAGE_KEY && e.newValue) {
        setLocale(e.newValue as Locale);
      }
    };

    window.addEventListener("storage", handleStorageChange);
    return () => window.removeEventListener("storage", handleStorageChange);
  }, [shouldUsePreference]);

  return {
    locale: shouldUsePreference ? locale : "zh",
    changeLocale,
    isLanguageSwitchEnabled: shouldUsePreference,
  };
}
