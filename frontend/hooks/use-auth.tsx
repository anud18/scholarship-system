"use client";

import { apiClient, User } from "@/lib/api";
import { logger } from "@/lib/utils/logger";
import { useRouter } from "next/navigation";
import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  logout: () => void;
  login: (token: string, userData: User) => void;
  updateUser: (userData: Partial<User>) => Promise<void>;
  error: string | null;
  token: string | null;
}

const AuthContext = createContext<AuthContextType | null>(null);

// Single source of truth for shaping a user object, wherever it came from
// (JWT stub, /auth/me, stored JSON): backend sends numeric id and may leave
// name null; the app contract is string id and non-empty name.
function normalizeUser(raw: User): User {
  return {
    ...raw,
    id: String(raw.id),
    name: raw.full_name || raw.name || raw.nycu_id,
    role: raw.role?.toLowerCase() as User["role"],
  };
}

function persistUser(normalizedUser: User): void {
  const json = JSON.stringify(normalizedUser);
  localStorage.setItem("user", json);
  localStorage.setItem("dev_user", json);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // SSO logins only carry JWT claims (nycu_id/role) — server-only fields like
  // college_code stay undefined until this /auth/me refresh lands, and the
  // college UI (e.g. 系所匯出總表 dropdown) filters on college_code.
  const refreshUserFromServer = useCallback(async () => {
    try {
      const response = await apiClient.auth.getCurrentUser();
      // The user may have logged out while /me was in flight — applying the
      // response would resurrect the session.
      if (!localStorage.getItem("auth_token")) return;
      if (response?.success && response.data) {
        const normalizedUser = normalizeUser(response.data as User);
        // Skip the state write when nothing changed — setUser here re-renders
        // the whole provider tree on every page load otherwise.
        if (JSON.stringify(normalizedUser) === localStorage.getItem("user")) {
          return;
        }
        persistUser(normalizedUser);
        setUser(normalizedUser);
        logger.debug("User profile refreshed from server", {
          role: normalizedUser.role,
          hasCollegeCode: !!normalizedUser.college_code,
        });
      }
    } catch (err) {
      // Keep the locally stored user — a transient /me failure must not log the user out.
      logger.warn("Failed to refresh user profile from server", { err });
    }
  }, []);

  // Check for existing authentication on mount
  useEffect(() => {
    const checkExistingAuth = () => {
      logger.debug("Checking existing authentication");
      const token = localStorage.getItem("auth_token");
      const userJson =
        localStorage.getItem("user") || localStorage.getItem("dev_user");

      logger.debug("Auth storage probed", {
        hasToken: !!token,
        hasUserJson: !!userJson,
      });

      if (token && userJson) {
        try {
          const userData = JSON.parse(userJson);
          apiClient.setToken(token);
          const normalizedUser = normalizeUser(userData);
          setUser(normalizedUser);
          logger.debug("Authentication restored from localStorage", {
            role: normalizedUser.role,
          });
          // Stored user may be a stale JWT-derived stub — re-sync from the server.
          void refreshUserFromServer();
        } catch (err) {
          logger.error("Failed to parse stored user data", { err });
          localStorage.removeItem("auth_token");
          localStorage.removeItem("user");
          localStorage.removeItem("dev_user");
        }
      } else {
        logger.debug("No existing authentication found");
      }
      setIsLoading(false);
    };

    checkExistingAuth();
  }, [refreshUserFromServer]);

  const login = useCallback((token: string, userData: User) => {
    logger.debug("useAuth.login() called", {
      hasToken: !!token,
      role: userData.role,
    });

    try {
      apiClient.setToken(token);
      localStorage.setItem("auth_token", token);
      const finalUser = normalizeUser(userData);
      persistUser(finalUser);
      setUser(finalUser);
      setError(null);
      logger.debug("useAuth.login() completed", {
        role: finalUser.role,
      });
      // SSO callbacks pass a JWT-derived stub; replace it with the full server profile.
      void refreshUserFromServer();
    } catch (err) {
      logger.error("Error in login", { err });
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }, [refreshUserFromServer]);

  const logout = useCallback(() => {
    logger.debug("Logging out");
    apiClient.clearToken();
    localStorage.removeItem("auth_token");
    localStorage.removeItem("user");
    localStorage.removeItem("dev_user");
    setUser(null);
    setError(null);

    // Redirect to dev-login in development mode
    if (typeof window !== "undefined") {
      const isLocalhost =
        window.location.hostname === "localhost" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.hostname.startsWith("192.168.") ||
        window.location.hostname.includes("dev");

      if (isLocalhost) {
        router.push("/dev-login");
      } else {
        // In production, redirect to home page or SSO login.
        // Flag that this is a real logout so the login page can warn that the
        // NYCU Portal SSO session is NOT cleared (it's a host-only cookie on
        // portal.test we can't touch cross-origin, and the Portal exposes no
        // app-initiable logout) — otherwise the next click re-logs in instantly.
        try {
          sessionStorage.setItem("nycu_portal_logout_notice", "1");
        } catch {
          // sessionStorage may be unavailable (private mode); the notice is best-effort.
        }
        router.push("/");
      }
    }
  }, [router]);

  const updateUser = useCallback(async (userData: Partial<User>) => {
    try {
      setError(null);
      const response = await apiClient.users.updateProfile(userData);

      if (response.success && response.data) {
        const updatedUser = normalizeUser(response.data);
        persistUser(updatedUser);
        setUser(updatedUser);
      } else {
        throw new Error(response.message || "Update failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
      throw err;
    }
  }, []);

  const value: AuthContextType = {
    user,
    isLoading,
    isAuthenticated: !!user,
    logout,
    login,
    updateUser,
    error,
    token:
      typeof window !== "undefined" ? localStorage.getItem("auth_token") : null,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within AuthProvider");
  }
  return context;
}
