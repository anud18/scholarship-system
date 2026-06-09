import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { SSOLoginPage } from "../sso-login-page";

describe("SSOLoginPage", () => {
  beforeEach(() => {
    sessionStorage.clear();
    // jsdom default location host is "localhost" → portal.test URL branch
  });

  it("always renders the Portal login button", () => {
    render(<SSOLoginPage />);
    expect(screen.getByText("使用 NYCU Portal 登入")).toBeInTheDocument();
  });

  it("does NOT show the logout notice on a normal visit", () => {
    render(<SSOLoginPage />);
    expect(screen.queryByText(/NYCU Portal 仍保持登入/)).not.toBeInTheDocument();
    expect(screen.queryByText("前往登出 NYCU Portal")).not.toBeInTheDocument();
  });

  it("shows the Portal-still-logged-in notice after a real logout (flag set)", () => {
    sessionStorage.setItem("nycu_portal_logout_notice", "1");
    render(<SSOLoginPage />);
    expect(screen.getByText(/NYCU Portal 仍保持登入/)).toBeInTheDocument();
    // and the flag is consumed so it doesn't show again on the next mount
    expect(sessionStorage.getItem("nycu_portal_logout_notice")).toBeNull();
  });

  it("the Portal-logout button opens the NYCU Portal", () => {
    sessionStorage.setItem("nycu_portal_logout_notice", "1");
    const openSpy = jest.spyOn(window, "open").mockImplementation(() => null);
    render(<SSOLoginPage />);
    fireEvent.click(screen.getByText("前往登出 NYCU Portal"));
    expect(openSpy).toHaveBeenCalledTimes(1);
    expect(String(openSpy.mock.calls[0][0])).toContain("portal");
    openSpy.mockRestore();
  });
});
