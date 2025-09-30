"use client";

import { useState, useEffect } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/hooks/use-auth";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { User, Shield, Crown, GraduationCap, BookOpen, AlertTriangle, Users } from "lucide-react";
import { apiClient as api } from "@/lib/api";

interface MockUser {
  nycu_id: string;  // 改為 nycu_id
  email: string;
  name: string;  // 改為 name
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
  };
  role: string;
  description: string;
}

interface MockUserResponse {
  nycu_id: string;  // 改為 nycu_id
  email: string;
  name: string;  // 改為 name
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
  };
  role: string;
}

interface DeveloperProfile {
  nycu_id: string;  // 改為 nycu_id
  email: string;
  name: string;  // 改為 name
  raw_data?: {
    chinese_name?: string;
    english_name?: string;
  };
  role: string;
  developer_id: string;
}

const roleIcons = {
  student: <GraduationCap className="h-4 w-4" />,
  professor: <BookOpen className="h-4 w-4" />,
  college: <User className="h-4 w-4" />,
  admin: <Shield className="h-4 w-4" />,
  super_admin: <Crown className="h-4 w-4" />
};

const roleColors = {
  student: "bg-blue-100 text-blue-800",
  professor: "bg-green-100 text-green-800",
  college: "bg-purple-100 text-purple-800",
  admin: "bg-orange-100 text-orange-800",
  super_admin: "bg-red-100 text-red-800"
};

export function MockSSOLogin() {
  const [mockUsers, setMockUsers] = useState<MockUser[]>([]);
  const [developerProfiles, setDeveloperProfiles] = useState<DeveloperProfile[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loginLoading, setLoginLoading] = useState<string | null>(null);
  const { login } = useAuth();

  useEffect(() => {
    fetchMockUsers();
    fetchDeveloperProfiles();
  }, []);

  const fetchMockUsers = async () => {
    try {
      setIsLoading(true);
      setError(null);
      const response = await api.auth.getMockUsers();
      if (response.success && response.data) {
        setMockUsers(response.data);
      } else {
        setError("Failed to fetch mock users");
      }
    } catch (err) {
      setError("Mock SSO is not available or disabled");
    } finally {
      setIsLoading(false);
    }
  };

  const fetchDeveloperProfiles = async () => {
    try {
      const developersResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/dev-profiles/developers`);
      if (!developersResponse.ok) return;

      const developersData = await developersResponse.json();
      if (!developersData.success) return;

      const allProfiles: DeveloperProfile[] = [];

      for (const developerId of developersData.data) {
        try {
          const profilesResponse = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/v1/auth/dev-profiles/${developerId}`);
          if (profilesResponse.ok) {
            const profilesData = await profilesResponse.json();
            if (profilesData.success) {
              const profiles = profilesData.data.map((profile: any) => ({
                ...profile,
                developer_id: developerId
              }));
              allProfiles.push(...profiles);
            }
          }
        } catch (err) {
          console.warn(`Failed to fetch profiles for developer ${developerId}:`, err);
        }
      }

      setDeveloperProfiles(allProfiles);
    } catch (err) {
      console.warn("Failed to fetch developer profiles:", err);
    }
  };

  const handleMockLogin = async (nycu_id: string) => {
    setLoginLoading(nycu_id);

    try {
      const response = await api.auth.mockSSOLogin(nycu_id);

      if (response.success && response.data) {
        // Store token and user data
        const { access_token, user } = response.data;
        api.setToken(access_token);
        localStorage.setItem("token", access_token);
        localStorage.setItem("user", JSON.stringify(user));

        // Reload page to update auth state
        window.location.reload();
      } else {
        setError("Mock login failed");
      }
    } catch (err) {
      setError("Mock login failed");
    } finally {
      setLoginLoading(null);
    }
  };



  const renderUserCard = (user: MockUser | DeveloperProfile) => (
    <Card key={user.nycu_id} className="border border-gray-200 hover:border-gray-300 transition-colors">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{user.nycu_id}</span>
          </div>
          <Badge variant="outline">{user.role}</Badge>
        </div>

        <div className="space-y-1">
          <p className="text-sm font-medium">
            {user.raw_data?.chinese_name && user.raw_data?.english_name
              ? `${user.raw_data.chinese_name} (${user.raw_data.english_name})`
              : user.name
            }
          </p>
          <p className="text-xs text-gray-500">{user.email}</p>
        </div>
      </CardHeader>

      <CardContent className="pt-0">
        {'description' in user && (
          <p className="text-xs text-gray-600 mb-3">{user.description}</p>
        )}
        <Button
          onClick={() => handleMockLogin(user.nycu_id)}
          disabled={loginLoading === user.nycu_id}
          className="w-full"
          size="sm"
        >
          {loginLoading === user.nycu_id ? "Logging in..." : "Login as this user"}
        </Button>
      </CardContent>
    </Card>
  );

  if (process.env.NODE_ENV === "production") {
    return null; // Don't show in production
  }

  return (
    <Card className="w-full max-w-6xl mx-auto">
      <CardHeader>
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 text-amber-500" />
          <CardTitle className="text-lg">Mock SSO Login (Development Only)</CardTitle>
        </div>
        <CardDescription>
          Quick login as predefined test users for development and testing purposes.
          This feature is automatically disabled in production.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex gap-2">
          <Button
            onClick={() => {
              fetchMockUsers();
              fetchDeveloperProfiles();
            }}
            disabled={isLoading}
            variant="outline"
            size="sm"
          >
            {isLoading ? "Loading..." : "Refresh Users"}
          </Button>
        </div>

        <Separator />

        <Tabs defaultValue="mock-users" className="w-full">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="mock-users" className="flex items-center gap-2">
              <Users className="h-4 w-4" />
              Mock Users ({mockUsers.length})
            </TabsTrigger>
            <TabsTrigger value="dev-profiles" className="flex items-center gap-2">
              <GraduationCap className="h-4 w-4" />
              Developer Profiles ({developerProfiles.length})
            </TabsTrigger>
          </TabsList>

          <TabsContent value="mock-users" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {mockUsers.map(renderUserCard)}
            </div>

            {mockUsers.length === 0 && !isLoading && (
              <div className="text-center py-8 text-gray-500">
                <p>No mock users available. Please ensure the database is initialized with test users.</p>
              </div>
            )}
          </TabsContent>

          <TabsContent value="dev-profiles" className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {developerProfiles.map(renderUserCard)}
            </div>

            {developerProfiles.length === 0 && (
              <div className="text-center py-8 text-gray-500">
                <p>No developer profiles found. Use the Developer Profile Manager to create them.</p>
              </div>
            )}
          </TabsContent>
        </Tabs>

        <Separator />

        <div className="text-xs text-gray-500 space-y-1">
          <p><strong>Development Notes:</strong></p>
          <ul className="list-disc list-inside space-y-1 ml-2">
            <li>All test users have the password: <code className="bg-gray-100 px-1 rounded">dev123456</code></li>
            <li>Developer profiles are created using the Developer Profile Manager</li>
            <li>This interface is only available in development environment</li>
            <li>Tokens generated are real JWT tokens that work with all protected endpoints</li>
            <li>Click any user card above to login instantly without typing credentials</li>
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}
