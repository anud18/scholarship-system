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
      console.log("Checking existing authentication...");
      // Check if user is already authenticated (from localStorage)
      const token = localStorage.getItem("auth_token");
      const userJson =
        localStorage.getItem("user") || localStorage.getItem("dev_user");

      console.log("Found token:", !!token, "Found user data:", !!userJson);

      if (token && userJson) {
        try {
          const userData = JSON.parse(userJson);
          console.log("Parsed user data:", userData);
          apiClient.setToken(token);
          // Convert role to lowercase for frontend consistency
          const normalizedUser = {
            ...userData,
            name: userData.full_name || userData.name,
            role: userData.role?.toLowerCase(),
          };
          setUser(normalizedUser);
          console.log("Authentication restored from localStorage");
        } catch (err) {
          logger.error("Failed to parse stored user data", {});
          localStorage.removeItem("auth_token");
          localStorage.removeItem("user");
          localStorage.removeItem("dev_user");
        }
      } else {
        console.log("No existing authentication found");
      }
      setIsLoading(false);
    };

    checkExistingAuth();
  }, []);

  const login = useCallback((token: string, userData: User) => {
    console.log("🔐 useAuth.login() called with:", {
      token: !!token,
      tokenPreview: token ? `${token.substring(0, 20)}...` : "none",
      userData,
    });

    try {
      console.log("🌐 Setting API client token...");
      apiClient.setToken(token);
      console.log("✅ API client token set");

      console.log("💾 Storing token in localStorage...");
      localStorage.setItem("auth_token", token);
      console.log("💾 Storing user data in localStorage...");
      localStorage.setItem("user", JSON.stringify(userData));

      // Also store as dev_user for backwards compatibility
      const devUser = {
        ...userData,
        name: userData.full_name || userData.name,
        role: userData.role?.toLowerCase(),
      };
      console.log("💾 Storing dev_user for backwards compatibility...");
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
      console.log("👤 Setting user state:", finalUser);
      setUser(finalUser);
      setError(null);
      console.log("✅ useAuth.login() completed successfully");
      console.log("🔍 Final authentication state:", {
        userSet: !!finalUser,
        userRole: finalUser.role,
        errorCleared: true,
      });
    } catch (error) {
      logger.error("Error in login", {});
      setError(error instanceof Error ? error.message : "Login failed");
    }
  }, []);

  const logout = useCallback(() => {
    console.log("Logging out...");
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
