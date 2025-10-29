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

  const [locale, setLocale] = useState<Locale>(() => {
    if (!shouldUsePreference) return "zh";

    if (typeof window !== "undefined") {
      const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
      return (stored as Locale) || defaultLocale;
    }
    return defaultLocale;
  });

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
