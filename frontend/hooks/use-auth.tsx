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

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
          // Convert role to lowercase for frontend consistency
          const normalizedUser = {
            ...userData,
            name: userData.full_name || userData.name,
            role: userData.role?.toLowerCase(),
          };
          setUser(normalizedUser);
          logger.debug("Authentication restored from localStorage", {
            role: normalizedUser.role,
          });
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
  }, []);

  const login = useCallback((token: string, userData: User) => {
    logger.debug("useAuth.login() called", {
      hasToken: !!token,
      role: userData.role,
    });

    try {
      apiClient.setToken(token);
      localStorage.setItem("auth_token", token);
      localStorage.setItem("user", JSON.stringify(userData));

      // Also store as dev_user for backwards compatibility
      const devUser = {
        ...userData,
        name: userData.full_name || userData.name,
        role: userData.role?.toLowerCase(),
      };
      localStorage.setItem("dev_user", JSON.stringify(devUser));
      const finalUser = {
        ...userData,
        name: userData.full_name || userData.name,
        role: userData.role?.toLowerCase() as
          | "student"
          | "professor"
          | "college"
          | "admin"
          | "super_admin",
      };
      setUser(finalUser);
      setError(null);
      logger.debug("useAuth.login() completed", {
        role: finalUser.role,
      });
    } catch (err) {
      logger.error("Error in login", { err });
      setError(err instanceof Error ? err.message : "Login failed");
    }
  }, []);

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
        // In production, redirect to home page or SSO login
        router.push("/");
      }
    }
  }, [router]);

  const updateUser = useCallback(async (userData: Partial<User>) => {
    try {
      setError(null);
      const response = await apiClient.users.updateProfile(userData);

      if (response.success && response.data) {
        // Map full_name to name for component compatibility
        const updatedUser = {
          ...response.data,
          name: response.data.full_name ?? response.data.name,
        };
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
