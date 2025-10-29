"use client";

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/hooks/use-auth";
import { SessionExpiredModal } from "@/components/session-expired-modal";
import { Locale } from "@/lib/validators";

interface SessionExpiredContextType {
  isSessionExpired: boolean;
  sessionExpiredType: "token_expired" | "unauthorized" | "forbidden";
}

const SessionExpiredContext = createContext<SessionExpiredContextType | null>(null);

export function SessionExpiredProvider({ children }: { children: ReactNode }) {
  const [isSessionExpired, setIsSessionExpired] = useState(false);
  const [sessionExpiredType, setSessionExpiredType] = useState<
    "token_expired" | "unauthorized" | "forbidden"
  >("token_expired");
  const [locale, setLocale] = useState<Locale>("zh");
  const { logout } = useAuth();
  const router = useRouter();

  // Listen for session expiration events
  useEffect(() => {
    const handleSessionExpired = (event: CustomEvent) => {
      const { type, status, endpoint } = event.detail;

      console.warn(`Session expired event received:`, {
        type,
        status,
        endpoint,
        timestamp: new Date().toISOString(),
      });

      // Set the type of session expiration
      setSessionExpiredType(type);

      // Show the modal (only if not already showing)
      if (!isSessionExpired) {
        setIsSessionExpired(true);
      }
    };

    // Type assertion for CustomEvent
    window.addEventListener("session-expired", handleSessionExpired as EventListener);

    return () => {
      window.removeEventListener("session-expired", handleSessionExpired as EventListener);
    };
  }, [isSessionExpired]);

  // Detect user locale (could be enhanced to use user preferences)
  useEffect(() => {
    const browserLang = navigator.language.toLowerCase();
    setLocale(browserLang.startsWith("zh") ? "zh" : "en");
  }, []);

  const handleRelogin = useCallback(() => {
    console.log("Session expired - redirecting to login");

    // Clear session expired state
    setIsSessionExpired(false);

    // Logout (clears tokens and user state)
    logout();

    // Logout already handles redirection based on environment
    // In development: redirects to /dev-login
    // In production: redirects to / (home page or SSO)
  }, [logout]);

  const contextValue: SessionExpiredContextType = {
    isSessionExpired,
    sessionExpiredType,
  };

  return (
    <SessionExpiredContext.Provider value={contextValue}>
      {children}
      <SessionExpiredModal
        isOpen={isSessionExpired}
        onRelogin={handleRelogin}
        locale={locale}
        type={sessionExpiredType}
      />
    </SessionExpiredContext.Provider>
  );
}

export function useSessionExpired() {
  const context = useContext(SessionExpiredContext);
  if (!context) {
    throw new Error("useSessionExpired must be used within SessionExpiredProvider");
  }
  return context;
}
