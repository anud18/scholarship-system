import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NotificationButton } from "../notification-button";

// Create mutable mock function
const mockGetUnreadCount = jest
  .fn()
  .mockResolvedValue({ success: true, data: 0 });

// Mock the API client
jest.mock("@/lib/api", () => ({
  apiClient: {
    notifications: {
      getUnreadCount: (...args: any[]) => mockGetUnreadCount(...args),
    },
  },
}));

// Mock the NotificationPanel component
jest.mock("../notification-panel", () => ({
  NotificationPanel: ({
    locale,
    onNotificationClick,
    onMarkAsRead,
    onMarkAllAsRead,
  }: any) => (
    <div data-testid="notification-panel">
      <button onClick={onNotificationClick}>Test Notification Click</button>
      <button onClick={onMarkAsRead}>Mark As Read</button>
      <button onClick={onMarkAllAsRead}>Mark All As Read</button>
      <span>Locale: {locale}</span>
    </div>
  ),
}));

import { apiClient as mockApiClient } from "@/lib/api";

// Override with mutable mock
mockApiClient.notifications.getUnreadCount = mockGetUnreadCount;

// Mock console.error to avoid test noise
const originalConsoleError = console.error;
beforeAll(() => {
  console.error = jest.fn();
});

afterAll(() => {
  console.error = originalConsoleError;
});

describe("NotificationButton Component", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("should render notification button", () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass("relative");
  });

  it("should show unread count indicator when there are unread notifications", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 5,
    });

    render(<NotificationButton locale="zh" />);

    // Wait for the API call to complete
    await waitFor(() => {
      const indicator = document.querySelector(".animate-pulse");
      expect(indicator).toBeInTheDocument();
    });
  });

  it("should show badge when unread count is greater than 3", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 5,
    });

    render(<NotificationButton locale="zh" />);

    await waitFor(() => {
      const badge = screen.getByText("5");
      expect(badge).toBeInTheDocument();
    });
  });

  it("should show 99+ when unread count exceeds 99", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 150,
    });

    render(<NotificationButton locale="zh" />);

    await waitFor(() => {
      const badge = screen.getByText("99+");
      expect(badge).toBeInTheDocument();
    });
  });

  it("should not show badge when unread count is 3 or less", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 3,
    });

    render(<NotificationButton locale="zh" />);

    await waitFor(() => {
      const indicator = document.querySelector(".animate-pulse");
      expect(indicator).toBeInTheDocument();
    });

    // Badge should not be present
    expect(screen.queryByText("3")).not.toBeInTheDocument();
  });

  it("should open notification panel when clicked", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      const panel = screen.getByTestId("notification-panel");
      expect(panel).toBeInTheDocument();
    });
  });

  it("should pass correct locale to notification panel", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    render(<NotificationButton locale="en" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByText("Locale: en")).toBeInTheDocument();
    });
  });

  it("should handle mark as read action", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 5,
    });

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      const markAsReadButton = screen.getByText("Mark As Read");
      fireEvent.click(markAsReadButton);
    });

    // Should call getUnreadCount again
    expect(mockApiClient.notifications.getUnreadCount).toHaveBeenCalledTimes(2);
  });

  it("should handle mark all as read action", async () => {
    mockApiClient.notifications.getUnreadCount
      .mockResolvedValueOnce({ success: true, data: 5 })
      .mockResolvedValueOnce({ success: true, data: 0 });

    render(<NotificationButton locale="zh" />);

    // Wait for initial load
    await waitFor(() => {
      expect(screen.getByText("5")).toBeInTheDocument();
    });

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      const markAllAsReadButton = screen.getByText("Mark All As Read");
      fireEvent.click(markAllAsReadButton);
    });

    // Should call getUnreadCount again and update the count
    await waitFor(() => {
      expect(mockApiClient.notifications.getUnreadCount).toHaveBeenCalledTimes(
        2
      );
    });
  });

  it("should handle API error gracefully", async () => {
    mockApiClient.notifications.getUnreadCount.mockRejectedValue(
      new Error("API Error")
    );

    render(<NotificationButton locale="zh" />);

    // Should not crash and should not show any badges
    await waitFor(() => {
      const indicator = document.querySelector(".animate-pulse");
      expect(indicator).not.toBeInTheDocument();
    });
  });

  it("should handle API response without success flag", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: false,
      data: null,
    });

    render(<NotificationButton locale="zh" />);

    await waitFor(() => {
      const indicator = document.querySelector(".animate-pulse");
      expect(indicator).not.toBeInTheDocument();
    });
  });

  it("should set up interval for periodic updates", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    render(<NotificationButton locale="zh" />);

    // Initial call should happen
    expect(mockApiClient.notifications.getUnreadCount).toHaveBeenCalledTimes(1);

    // Fast forward 30 seconds
    jest.advanceTimersByTime(30000);

    await waitFor(() => {
      expect(mockApiClient.notifications.getUnreadCount).toHaveBeenCalledTimes(
        2
      );
    });

    // Fast forward another 30 seconds
    jest.advanceTimersByTime(30000);

    await waitFor(() => {
      expect(mockApiClient.notifications.getUnreadCount).toHaveBeenCalledTimes(
        3
      );
    });
  });

  it("should cleanup interval on unmount", () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    const { unmount } = render(<NotificationButton locale="zh" />);

    // Spy on clearInterval
    const clearIntervalSpy = jest.spyOn(global, "clearInterval");

    unmount();

    expect(clearIntervalSpy).toHaveBeenCalled();

    clearIntervalSpy.mockRestore();
  });

  it("should apply custom className", () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    render(<NotificationButton locale="zh" className="custom-class" />);

    const button = screen.getByRole("button");
    expect(button).toHaveClass("custom-class");
  });

  it("should handle notification click callback", async () => {
    mockApiClient.notifications.getUnreadCount.mockResolvedValue({
      success: true,
      data: 0,
    });

    const consoleSpy = jest.spyOn(console, "log").mockImplementation();

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      const notificationClickButton = screen.getByText(
        "Test Notification Click"
      );
      fireEvent.click(notificationClickButton);
    });

    expect(consoleSpy).toHaveBeenCalledWith("Notification clicked");

    consoleSpy.mockRestore();
  });

  describe("unread count display logic", () => {
    it("should not show anything when count is 0", async () => {
      mockApiClient.notifications.getUnreadCount.mockResolvedValue({
        success: true,
        data: 0,
      });

      render(<NotificationButton locale="zh" />);

      await waitFor(() => {
        const indicator = document.querySelector(".animate-pulse");
        expect(indicator).not.toBeInTheDocument();
      });
    });

    it("should show only indicator dot for count 1-3", async () => {
      for (let count = 1; count <= 3; count++) {
        mockApiClient.notifications.getUnreadCount.mockResolvedValue({
          success: true,
          data: count,
        });

        const { unmount } = render(<NotificationButton locale="zh" />);

        await waitFor(() => {
          const indicator = document.querySelector(".animate-pulse");
          expect(indicator).toBeInTheDocument();
          expect(screen.queryByText(count.toString())).not.toBeInTheDocument();
        });

        unmount();
      }
    });

    it("should show both indicator and badge for count > 3", async () => {
      mockApiClient.notifications.getUnreadCount.mockResolvedValue({
        success: true,
        data: 5,
      });

      render(<NotificationButton locale="zh" />);

      await waitFor(() => {
        const indicator = document.querySelector(".animate-pulse");
        expect(indicator).toBeInTheDocument();
        expect(screen.getByText("5")).toBeInTheDocument();
      });
    });
  });
});
