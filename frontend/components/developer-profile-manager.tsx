"use client";

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export function DeveloperProfileManager() {
  if (process.env.NODE_ENV === "production") {
    return null;
  }

  return (
    <Card className="w-full max-w-6xl mx-auto">
      <CardHeader>
        <CardTitle>Developer Profile Manager</CardTitle>
        <CardDescription>
          Component temporarily simplified for testing
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p>Developer profile management functionality temporarily disabled for system testing.</p>
      </CardContent>
    </Card>
  );
}
