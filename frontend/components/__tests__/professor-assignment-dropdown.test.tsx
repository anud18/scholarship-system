/**
 * Pins the professor-list fetch policy of ProfessorAssignmentDropdown (#1499).
 *
 * The admin applications table renders one compact dropdown per row. When each
 * row fetched the full list on mount (twice: mount effect + debounce effect),
 * ~360 rows fired ~720 GET /admin/professors in a burst, tripped the nginx
 * per-IP rate limit, and the eye-icon detail request came back 429.
 */

import React from "react";
import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import { ProfessorAssignmentDropdown } from "../professor-assignment-dropdown";
import { apiClient } from "@/lib/api";

const PROFESSORS = [
  { nycu_id: "prof001", name: "王教授", dept_code: "CS", dept_name: "資工系" },
  { nycu_id: "prof002", name: "李教授", dept_code: "EE", dept_name: "電機系" },
];

function spyGetProfessors() {
  return jest
    .spyOn(apiClient.admin, "getProfessors")
    .mockResolvedValue({ success: true, message: "", data: PROFESSORS });
}

describe("ProfessorAssignmentDropdown fetch policy", () => {
  beforeAll(() => {
    // cmdk scrolls the selected item into view; jsdom has no layout
    Element.prototype.scrollIntoView = jest.fn();
  });

  beforeEach(() => {
    jest.restoreAllMocks();
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
    // Outlast the old 300ms debounced fetch
    await act(() => new Promise(resolve => setTimeout(resolve, 400)));

    expect(getProfessors).not.toHaveBeenCalled();
  });

  it("does not fetch on mount for an unassigned full-mode dropdown", async () => {
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} />);
    await act(() => new Promise(resolve => setTimeout(resolve, 400)));

    expect(getProfessors).not.toHaveBeenCalled();
  });

  it("fetches once when opened and lists the professors", async () => {
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    fireEvent.click(screen.getByRole("combobox"));

    expect(await screen.findByText("王教授")).toBeInTheDocument();
    expect(getProfessors).toHaveBeenCalledTimes(1);
    expect(getProfessors).toHaveBeenCalledWith("");
  });

  it("labels a compact row with an assigned professor as 修改 before any fetch", () => {
    spyGetProfessors();

    render(
      <ProfessorAssignmentDropdown
        applicationId={1}
        currentProfessorId="prof001"
        compact
      />
    );

    expect(screen.getByRole("combobox")).toHaveTextContent("修改");
  });

  it("prefetches once in full mode to show the current professor's name", async () => {
    const getProfessors = spyGetProfessors();

    render(
      <ProfessorAssignmentDropdown applicationId={1} currentProfessorId="prof002" />
    );

    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveTextContent("李教授")
    );
    expect(getProfessors).toHaveBeenCalledTimes(1);

    // Opening reuses the prefetched list instead of fetching again
    fireEvent.click(screen.getByRole("combobox"));
    expect(await screen.findByText("王教授")).toBeInTheDocument();
    await act(() => new Promise(resolve => setTimeout(resolve, 400)));
    expect(getProfessors).toHaveBeenCalledTimes(1);
  });

  it("debounces search while open", async () => {
    const getProfessors = spyGetProfessors();

    render(<ProfessorAssignmentDropdown applicationId={1} compact />);
    fireEvent.click(screen.getByRole("combobox"));
    await screen.findByText("王教授");

    const input = screen.getByPlaceholderText("搜尋姓名或 NYCU ID...");
    fireEvent.change(input, { target: { value: "王" } });
    fireEvent.change(input, { target: { value: "王教" } });

    await waitFor(() => expect(getProfessors).toHaveBeenCalledWith("王教"));
    expect(getProfessors).toHaveBeenCalledTimes(2);
  });
});
