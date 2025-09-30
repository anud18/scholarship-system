"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  User,
  Shield,
  Crown,
  GraduationCap,
  BookOpen,
  Users,
  AlertTriangle,
} from "lucide-react";
import { apiClient as api } from "@/lib/api";
import { useAuth } from "@/hooks/use-auth";

interface MockUser {
  id: string;
  nycu_id: string; // 改為 nycu_id
  name: string; // 改為 name
  email: string;
  role: "student" | "professor" | "college" | "admin" | "super_admin";
  description: string;
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
  };
}

const roleIcons = {
  student: <GraduationCap className="h-4 w-4" />,
  professor: <BookOpen className="h-4 w-4" />,
  college: <Users className="h-4 w-4" />,
  admin: <Shield className="h-4 w-4" />,
  super_admin: <Crown className="h-4 w-4" />,
};

const roleColors = {
  student: "bg-blue-100 text-blue-800",
  professor: "bg-green-100 text-green-800",
  college: "bg-purple-100 text-purple-800",
  admin: "bg-orange-100 text-orange-800",
  super_admin: "bg-red-100 text-red-800",
};

const roleLabels = {
  student: "Student",
  professor: "Professor",
  college: "College Reviewer",
  admin: "Administrator",
  super_admin: "Super Administrator",
};

export function DevLoginPage() {
  console.log("DevLoginPage component rendering...");
  const { login } = useAuth();
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mockUsers, setMockUsers] = useState<MockUser[]>([]);
  const [isLoadingUsers, setIsLoadingUsers] = useState(true);
  const router = useRouter();

  console.log("DevLoginPage state:", {
    selectedUser,
    isLoggingIn,
    error,
    usersCount: mockUsers.length,
  });

  // Load mock users from API
  const loadMockUsers = async () => {
    try {
      console.log("Loading mock users from API...");
      setIsLoadingUsers(true);
      setError(null);

      const response = await api.auth.getMockUsers();
      console.log("Mock users response:", response);

      if (response.success && response.data) {
        setMockUsers(response.data);
      } else {
        setError(
          "Failed to load users: " + (response.message || "Unknown error")
        );
      }
    } catch (err) {
      console.error("Failed to load mock users:", err);
      let errorMessage = "Failed to load users. ";
      if (err instanceof Error) {
        if (
          err.message.includes("Failed to fetch") ||
          err.message.includes("NetworkError")
        ) {
          errorMessage += "Backend server is not running or not accessible.";
        } else {
          errorMessage += `Error: ${err.message}`;
        }
      } else {
        errorMessage += "Unknown error occurred.";
      }
      setError(errorMessage);
    } finally {
      setIsLoadingUsers(false);
    }
  };

  // Check if we should allow dev login and load users
  useEffect(() => {
    console.log(
      "DevLoginPage useEffect running, NODE_ENV:",
      process.env.NODE_ENV
    );
    console.log("Current hostname:", window.location.hostname);
    console.log("API client:", api);

    // Allow dev login if:
    // 1. We're on localhost or 127.0.0.1 (local development)
    // 2. Or if we're explicitly accessing /dev-login (manual override)
    const isLocalhost =
      window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname.startsWith("192.168.") ||
      window.location.hostname.includes("dev");

    const isDevLoginPath = window.location.pathname === "/dev-login";

    console.log("Is localhost:", isLocalhost);
    console.log("Is dev-login path:", isDevLoginPath);

    // Only redirect if we're in a real production environment
    if (
      typeof window !== "undefined" &&
      process.env.NODE_ENV === "production" &&
      !isLocalhost &&
      !isDevLoginPath
    ) {
      console.log("Real production mode detected, redirecting to home page");
      router.push("/");
    } else {
      console.log("Allowing dev login access");
      // Load mock users when component mounts
      loadMockUsers();
    }
  }, [router]);

  const handleUserLogin = async (user: MockUser) => {
    console.log("Calling mock SSO login API with nycu_id:", user.nycu_id);

    try {
      const response = await api.auth.mockSSOLogin(user.nycu_id);
      console.log("Mock SSO login response:", response);

      if (response.success && response.data) {
        // Store token and user data using the authentication context
        const { access_token, user: userData } = response.data;
        console.log("Login successful, setting authentication via context");

        // Use the auth context login function to properly set state
        login(access_token, userData);

        console.log("Redirecting to main page");
        // Redirect to main page (role-based dashboard)
        router.push("/");
      } else {
        console.error("Mock login failed with response:", response);
        setError("Mock login failed: " + (response.message || "Unknown error"));
      }
    } catch (error) {
      console.error("Dev login failed with error:", error);

      // More detailed error message
      let errorMessage = "Mock login failed. ";
      if (error instanceof Error) {
        if (
          error.message.includes("Failed to fetch") ||
          error.message.includes("NetworkError")
        ) {
          errorMessage +=
            "Backend server is not running or not accessible. Please start the backend server.";
        } else if (error.message.includes("404")) {
          errorMessage +=
            "Mock SSO endpoint not found. Please ensure the backend supports mock authentication.";
        } else {
          errorMessage += `Error: ${error.message}`;
        }
      } else {
        errorMessage += "Unknown error occurred.";
      }

      setError(errorMessage);
    } finally {
      setIsLoggingIn(false);
      setSelectedUser(null);
    }
  };

  // Don't render in real production (but allow in Docker development)
  const isLocalhost =
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" ||
      window.location.hostname === "127.0.0.1" ||
      window.location.hostname.startsWith("192.168.") ||
      window.location.hostname.includes("dev"));

  const isDevLoginPath =
    typeof window !== "undefined" && window.location.pathname === "/dev-login";

  if (
    typeof window !== "undefined" &&
    process.env.NODE_ENV === "production" &&
    !isLocalhost &&
    !isDevLoginPath
  ) {
    console.log("Blocking dev login in real production");
    return null;
  }

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center p-4">
      <div className="w-full max-w-4xl">
        <Card className="mb-6">
          <CardHeader className="text-center">
            <div className="flex items-center justify-center gap-2 mb-2">
              <AlertTriangle className="h-6 w-6 text-orange-500" />
              <CardTitle className="text-2xl">Development Login</CardTitle>
            </div>
            <CardDescription>
              Select a user to simulate login in development mode. This page is
              only available in development.
            </CardDescription>
          </CardHeader>
        </Card>

        <Alert className="mb-6 border-orange-200 bg-orange-50">
          <AlertTriangle className="h-4 w-4 text-orange-600" />
          <AlertDescription className="text-orange-800">
            <strong>Development Only:</strong> This interface allows you to
            quickly switch between different user roles for testing. Uses real
            authentication tokens that work with all API endpoints.
          </AlertDescription>
        </Alert>

        {error && (
          <Alert className="mb-6 border-red-200 bg-red-50">
            <AlertTriangle className="h-4 w-4 text-red-600" />
            <AlertDescription className="text-red-800">
              {error}
            </AlertDescription>
          </Alert>
        )}

        <div className="mb-6 flex gap-2">
          <Button
            onClick={() => {
              console.log("Refresh users button clicked!");
              loadMockUsers();
            }}
            disabled={isLoadingUsers}
            variant="secondary"
            size="sm"
          >
            {isLoadingUsers ? "Loading..." : "Refresh Users"}
          </Button>
        </div>

        {isLoadingUsers ? (
          <div className="flex justify-center items-center py-12">
            <div className="text-center">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600 mb-2"></div>
              <p className="text-gray-600">Loading users...</p>
            </div>
          </div>
        ) : mockUsers.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-gray-600 mb-4">
              No users found. Please ensure the database is initialized with
              test users.
            </p>
            <Button
              onClick={() => {
                console.log("Refresh users button clicked!");
                loadMockUsers();
              }}
              disabled={isLoadingUsers}
              variant="secondary"
            >
              {isLoadingUsers ? "Loading..." : "Refresh Users"}
            </Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {mockUsers.map(user => (
              <Card
                key={user.id}
                className="border border-gray-200 hover:border-gray-300 transition-all hover:shadow-md cursor-pointer"
                onClick={() => {
                  console.log("Card clicked!", user);
                  handleUserLogin(user);
                }}
              >
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      {roleIcons[user.role]}
                      <span className="font-medium text-sm">
                        {user.nycu_id}
                      </span>
                    </div>
                    <Badge className={roleColors[user.role]}>
                      {roleLabels[user.role]}
                    </Badge>
                  </div>

                  <div className="space-y-1">
                    <p className="text-sm font-medium">
                      {user.raw_data?.chinese_name &&
                      user.raw_data?.english_name
                        ? `${user.raw_data.chinese_name} (${user.raw_data.english_name})`
                        : user.name}
                    </p>
                    <p className="text-xs text-gray-500">{user.email}</p>
                  </div>
                </CardHeader>

                <CardContent className="pt-0">
                  <p className="text-xs text-gray-600 mb-3">
                    {user.description}
                  </p>
                  <Button
                    onClick={e => {
                      console.log("Button clicked!", user);
                      e.stopPropagation(); // Prevent card click
                      handleUserLogin(user);
                    }}
                    disabled={isLoggingIn}
                    className="w-full"
                    size="sm"
                    variant={selectedUser === user.id ? "default" : "outline"}
                  >
                    {selectedUser === user.id && isLoggingIn
                      ? "Logging in..."
                      : `Login as ${roleLabels[user.role]}`}
                  </Button>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <Card className="mt-6">
          <CardContent className="pt-6">
            <div className="text-center text-sm text-gray-600">
              <p className="mb-2">
                <strong>Instructions:</strong>
              </p>
              <ul className="text-left max-w-2xl mx-auto space-y-1">
                <li>• User list is loaded dynamically from the database</li>
                <li>• Click any user card to simulate login as that user</li>
                <li>
                  • Uses real authentication tokens that work with all API
                  endpoints
                </li>
                <li>• You'll be automatically redirected to the main page</li>
                <li>• This interface is only available in development mode</li>
                <li>• Use different roles to test various permission levels</li>
                <li>
                  • Click "Refresh Users" to reload the user list from database
                </li>
                <li>
                  • Test users are automatically created during database
                  initialization
                </li>
              </ul>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
