/**
 * Unit tests for the uppercase input helper
 */

import { uppercaseInputValue } from "./uppercase-input";

function inputWith(value: string, caret: number): HTMLInputElement {
  const input = document.createElement("input");
  document.body.appendChild(input);
  input.value = value;
  input.setSelectionRange(caret, caret);
  return input;
}

describe("uppercaseInputValue", () => {
  afterEach(() => {
    document.body.innerHTML = "";
  });

  it("returns the uppercased value and writes it back to the input", () => {
    const input = inputWith("p00a1", 5);
    expect(uppercaseInputValue(input)).toBe("P00A1");
    expect(input.value).toBe("P00A1");
  });

  it("keeps the caret where the user typed a mid-string edit", () => {
    const input = inputWith("P0a01", 3);
    uppercaseInputValue(input);
    expect(input.value).toBe("P0A01");
    expect(input.selectionStart).toBe(3);
    expect(input.selectionEnd).toBe(3);
  });

  it("leaves an already-uppercase value untouched", () => {
    const input = inputWith("P001", 2);
    expect(uppercaseInputValue(input)).toBe("P001");
    expect(input.selectionStart).toBe(2);
  });
});
