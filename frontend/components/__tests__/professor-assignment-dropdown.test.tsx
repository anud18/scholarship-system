/**
 * Pins the professor-list fetch policy of ProfessorAssignmentDropdown (#1499).
 *
 * The admin applications table renders one compact dropdown per row. When each
 * row fetched the full list on mount (twice: mount effect + debounce effect),
 * ~360 rows fired ~720 GET /admin/professors in a burst, tripped the nginx
 * per-IP rate limit, and the eye-icon detail request came back 429.
 */

import React from "react";
import { render, screen, fireEvent, act } from "@testing-library/react";
import { ProfessorAssignmentDropdown } from "../professor-assignment-dropdown";
import { apiClient } from "@/lib/api";

const PROFESSORS = [
  { nycu_id: "prof001", name: "王教授", dept_code: "CS", dept_name: "資工系" },
  { nycu_id: "prof002", name: "李教授", dept_code: "EE", dept_name: "電機系" },
];
const DEBOUNCE_MS = 300;

// Mimics the backend: filters by name or NYCU ID
function spyGetProfessors() {
  return jest
    .spyOn(apiClient.admin, "getProfessors")
    .mockImplementation(async (search = "") => ({
      success: true,
      message: "",
      data: PROFESSORS.filter(
        p => p.name.includes(search) || p.nycu_id.includes(search)
      ),
    }));
}

async function advance(ms: number) {
  await act(async () => {
    jest.advanceTimersByTime(ms);
  });
}

function openDropdown() {
  fireEvent.click(screen.getByRole("combobox"));
}

describe("ProfessorAssignmentDropdown fetch policy", () => {
  beforeAll(() => {
    // cmdk scrolls the selected item into view; jsdom has no layout
    Element.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    jest.restoreAllMocks();
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("does not fetch on mount for compact per-row dropdowns", async () => {
    const getProfessors = spyGetProfessors();

    render(
      <>
        {[1, 2, 3, 4, 5].map(id => (
          <ProfessorAssignmentDropdown
            key={id}
            applicationId={id}
            currentProfessorId={id % 2 ? "prof001" : undefined}
            compact
          />
        ))}
      </>
    );
    await advance(DEBOUNCE_MS * 3);

    expect(getProfessors).not.toHaveBeenCalled();
  });

  it("labels an assigned compact row 修改 without fetching", async () => {
    const getProfessors = spyGetProfessors();

    render(
      <ProfessorAssignmentDropdown
        applicationId={1}
        currentProfessorId="prof001"
        compact
      />
    );
    await advance(DEBOUNCE_MS * 3);

    expect(screen.getByRole("combobox")).toHaveTextContent("修改");
    expect(getProfessors).not.toHaveBeenCalled();
  });

  it("shows the caller-provided professor name in full mode without fetching", async () => {
    const getProfessors = spyGetProfessors();

    render(
      <ProfessorAssignmentDropdown
        applicationId={1}
        currentProfessorId="prof002"
        currentProfessorName="李教授"
      />
    );
    await advance(DEBOUNCE_MS * 3);

    expect(screen.getByRole("combobox")).toHaveTextContent("李教授");
    expect(screen.getByRole("combobox")).toHaveTextContent("prof002");
    expect(getProfessors).not.toHaveBeenCalled();
  });

  it("shows 載入中 (not 找不到) on open, then fetches the list once", async () => {
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    openDropdown();

    expect(screen.getByText("載入中...")).toBeInTheDocument();
    expect(screen.queryByText("找不到符合的教授")).toBeNull();

    await advance(0);
    expect(screen.getByText("王教授")).toBeInTheDocument();
    expect(screen.getByText("李教授")).toBeInTheDocument();

    await advance(DEBOUNCE_MS * 3);
    expect(getProfessors).toHaveBeenCalledTimes(1);
    expect(getProfessors).toHaveBeenCalledWith("");
  });

  it("checks the current professor in the opened list", async () => {
    spyGetProfessors();

    render(
      <ProfessorAssignmentDropdown
        applicationId={1}
        currentProfessorId="prof002"
        currentProfessorName="李教授"
      />
    );
    openDropdown();
    await advance(0);

    const option = screen.getAllByRole("option").find(o =>
      o.textContent?.includes("prof002")
    );
    expect(option?.querySelector("svg.opacity-100")).not.toBeNull();
  });

  it("shows name-search results returned by the backend", async () => {
    // cmdk filters on the item value (nycu_id) by default and hid name hits
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    openDropdown();
    await advance(0);

    fireEvent.change(screen.getByPlaceholderText("搜尋姓名或 NYCU ID..."), {
      target: { value: "王" },
    });
    await advance(DEBOUNCE_MS);

    expect(getProfessors).toHaveBeenLastCalledWith("王");
    expect(screen.getByText("王教授")).toBeInTheDocument();
    expect(screen.queryByText("李教授")).toBeNull();
  });

  it("debounces search while open", async () => {
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    openDropdown();
    await advance(0);

    const input = screen.getByPlaceholderText("搜尋姓名或 NYCU ID...");
    fireEvent.change(input, { target: { value: "王" } });
    await advance(DEBOUNCE_MS - 100);
    fireEvent.change(input, { target: { value: "王教" } });
    await advance(DEBOUNCE_MS);

    expect(getProfessors).toHaveBeenCalledTimes(2);
    expect(getProfessors).toHaveBeenLastCalledWith("王教");
  });

  it("shows an error with 重試 on a failed fetch and does not auto-retry", async () => {
    const getProfessors = jest
      .spyOn(apiClient.admin, "getProfessors")
      .mockResolvedValueOnce({
        success: false,
        message: "Too Many Requests",
        data: undefined,
      });

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    openDropdown();
    await advance(0);

    expect(screen.getByText("載入教授清單失敗，請稍後再試")).toBeInTheDocument();
    expect(screen.queryByText("找不到符合的教授")).toBeNull();
    await advance(DEBOUNCE_MS * 3);
    expect(getProfessors).toHaveBeenCalledTimes(1);

    getProfessors.mockResolvedValueOnce({
      success: true,
      message: "",
      data: PROFESSORS,
    });
    fireEvent.click(screen.getByRole("button", { name: "重試" }));
    await advance(0);

    expect(getProfessors).toHaveBeenCalledTimes(2);
    expect(screen.getByText("王教授")).toBeInTheDocument();
  });
});
