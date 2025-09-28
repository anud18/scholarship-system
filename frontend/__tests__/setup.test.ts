/**
 * Basic setup test to verify Jest configuration is working
 */

import { apiClient } from "@/lib/api";

describe("Jest Setup", () => {
  it("should resolve @/ path aliases correctly", () => {
    expect(apiClient).toBeDefined();
    expect(typeof apiClient).toBe("object");
  });

  it("should have testing environment configured", () => {
    expect(process.env.NODE_ENV).toBe("test");
  });

  it("should mock API client methods", () => {
    expect(apiClient.auth.login).toBeDefined();
    expect(apiClient.setToken).toBeDefined();
    expect(typeof apiClient.auth.login).toBe("function");
    expect(typeof apiClient.setToken).toBe("function");
  });

  it("should have DOM testing utilities available", () => {
    expect(document).toBeDefined();
    expect(window).toBeDefined();
  });
});
