import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { NotificationButton } from "../notification-button";

const mockNotificationPanel = jest.fn(
  ({ locale, onNotificationClick }: { locale: string; onNotificationClick?: () => void }) => (
    <div data-testid="notification-panel">
      <button onClick={onNotificationClick}>Trigger Notification Click</button>
      <span data-testid="notification-locale">{locale}</span>
    </div>
  )
);

jest.mock("../notification-panel", () => ({
  NotificationPanel: (props: unknown) => mockNotificationPanel(props as any),
}));

const mockUseNotifications = jest.fn();

jest.mock("@/contexts/notification-context", () => ({
  useNotifications: () => mockUseNotifications(),
}));

function setupNotifications(overrides: {
  unreadCount?: number;
  notifyPanelOpen?: () => void;
} = {}) {
  const value = {
    unreadCount: 0,
    notifyPanelOpen: jest.fn(),
    refreshUnreadCount: jest.fn(),
    markAsRead: jest.fn(),
    markAllAsRead: jest.fn(),
  };

  Object.assign(value, overrides);
  mockUseNotifications.mockReturnValue(value);

  return value;
}

describe("NotificationButton", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("renders notification button", () => {
    setupNotifications();

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    expect(button).toBeInTheDocument();
    expect(button).toHaveClass("relative");
  });

  it("shows unread indicator when unread count is greater than 0", () => {
    setupNotifications({ unreadCount: 2 });

    const { container } = render(<NotificationButton locale="zh" />);

    const indicator = container.querySelector(".animate-pulse");
    expect(indicator).not.toBeNull();
  });

  it("shows badge when unread count is greater than 3", () => {
    setupNotifications({ unreadCount: 5 });

    render(<NotificationButton locale="zh" />);

    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("shows 99+ when unread count exceeds 99", () => {
    setupNotifications({ unreadCount: 120 });

    render(<NotificationButton locale="zh" />);

    expect(screen.getByText("99+")).toBeInTheDocument();
  });

  it("does not show indicator when unread count is 0", () => {
    setupNotifications({ unreadCount: 0 });

    const { container } = render(<NotificationButton locale="zh" />);

    const indicator = container.querySelector(".animate-pulse");
    expect(indicator).toBeNull();
  });

  it("opens notification panel when button is clicked", async () => {
    setupNotifications();

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(screen.getByTestId("notification-panel")).toBeInTheDocument();
    });
  });

  it("notifies context when panel is opened", async () => {
    const { notifyPanelOpen } = setupNotifications();

    render(<NotificationButton locale="zh" />);

    const button = screen.getByRole("button");
    fireEvent.click(button);

    await waitFor(() => {
      expect(notifyPanelOpen).toHaveBeenCalledTimes(1);
    });
  });

  it("passes locale to notification panel", async () => {
    setupNotifications();

    render(<NotificationButton locale="en" />);

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => {
      expect(screen.getByTestId("notification-locale")).toHaveTextContent("en");
    });
  });

  it("applies custom className", () => {
    setupNotifications();

    render(<NotificationButton locale="zh" className="custom-class" />);

    expect(screen.getByRole("button")).toHaveClass("custom-class");
  });

  it("handles notification click callback", async () => {
    setupNotifications();
    const consoleSpy = jest.spyOn(console, "log").mockImplementation(() => undefined);

    render(<NotificationButton locale="zh" />);

    fireEvent.click(screen.getByRole("button"));

    await waitFor(() => expect(mockNotificationPanel).toHaveBeenCalled());

    fireEvent.click(screen.getByText("Trigger Notification Click"));

    expect(consoleSpy).toHaveBeenCalledWith("Notification clicked");

    consoleSpy.mockRestore();
  });
});
